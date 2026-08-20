#!/usr/bin/env python3
"""Render and publish the daily market briefing as one X longform Post.

The renderer intentionally mirrors the final, user-approved web "X 发布" output.
Publishing is single-attempt: an ambiguous network failure is never retried because
retrying a create request can produce a duplicate Post.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "data" / "daily-market-status.json"
DEFAULT_STATE = ROOT / "data" / "x-publish-log.json"
X_CREATE_POST_URL = "https://api.x.com/2/tweets"
SHANGHAI = ZoneInfo("Asia/Shanghai")
UTC = dt.timezone.utc
MAX_LONGFORM_CHARACTERS = 25_000
CALENDAR_WINDOW = dt.timedelta(hours=48)
INDEX_CONFIG = (("SPX", "标普500"), ("IXIC", "纳斯达克"), ("DJI", "道琼斯"))
WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")


class PublishError(RuntimeError):
    """A safe, user-actionable publishing failure."""


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PublishError(f"Required file is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PublishError(f"Invalid JSON in {path}: {exc}") from exc


def parse_datetime(value: str) -> dt.datetime:
    source = str(value or "").strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(source)
    except ValueError as exc:
        raise PublishError(f"Invalid ISO datetime: {value!r}") from exc
    if parsed.tzinfo is None:
        raise PublishError(f"Datetime must include a timezone: {value!r}")
    return parsed


def finite_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def format_number(value: Any, decimals: int) -> str:
    number = finite_number(value)
    if number is None:
        return "—"
    return f"{number:,.{decimals}f}"


def format_percent(value: Any) -> str:
    number = finite_number(value)
    if number is None:
        return "—"
    sign = "+" if number > 0 else "−" if number < 0 else ""
    return f"{sign}{abs(number):.2f}%"


def direction_icon(previous: Any, current: Any) -> str:
    before = finite_number(previous)
    now = finite_number(current)
    if before is None or now is None or before == now:
        return "—"
    return "📈" if now > before else "📉"


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def concise_driver_reason(value: Any) -> str:
    source = clean_text(value)
    source = re.sub(r"^公司给出的", "", source)
    source = re.sub(r"^公司", "", source)
    if not source:
        return ""

    first_sentence = next((part for part in re.split(r"[。！？!?]", source) if part), source)
    clauses = [part.strip() for part in re.split(r"[，；]", first_sentence) if part.strip()]
    clauses = [
        part
        for part in clauses
        if not re.search(r"股价创|单日最大涨幅|直接推动|成为标普.*涨幅|成为.*涨幅个股", part)
    ]
    if not clauses:
        return re.sub(r"[，；。\s]+$", "", first_sentence) + "。"

    picked: list[str] = []
    length = 0
    for clause in clauses:
        next_length = length + len(clause) + (1 if picked else 0)
        if len(picked) >= 2 and next_length > 88:
            break
        if len(picked) >= 3:
            break
        if picked and next_length > 96:
            break
        picked.append(clause)
        length = next_length

    if len(picked) == 1 and len(clauses) > 1 and length < 42:
        picked.append(clauses[1])
    return re.sub(r"[，；。\s]+$", "", "，".join(picked)) + "。"


def published_date_label(snapshot: dict[str, Any]) -> str:
    published_at = parse_datetime(snapshot.get("publishedAt", ""))
    local = published_at.astimezone(SHANGHAI)
    return f"{local.year}年{local.month}月{local.day}日"


def market_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = snapshot.get("fallback", {}).get("markets", [])
    return {str(row.get("id")): row for row in rows if isinstance(row, dict) and row.get("id")}


def macro_anchor_map(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = snapshot.get("macroAnchors", [])
    return {str(row.get("id")): row for row in rows if isinstance(row, dict) and row.get("id")}


def macro_line(label: str, previous: Any, current: Any, decimals: int, suffix: str = "") -> str:
    icon = direction_icon(previous, current)
    left = format_number(previous, decimals) + (suffix if finite_number(previous) is not None else "")
    right = format_number(current, decimals) + (suffix if finite_number(current) is not None else "")
    return f"{icon}{label}： {left} → {right}"


def event_time(value: str) -> dt.datetime:
    return parse_datetime(value).astimezone(SHANGHAI)


def validate_snapshot(snapshot: dict[str, Any], required_as_of: str | None = None) -> str:
    as_of = str(snapshot.get("asOf") or "")
    try:
        dt.date.fromisoformat(as_of)
    except ValueError as exc:
        raise PublishError("Snapshot asOf must be an ISO date") from exc
    parse_datetime(snapshot.get("publishedAt", ""))
    if required_as_of and required_as_of != as_of:
        raise PublishError(f"Requested asOf {required_as_of} does not match snapshot {as_of}")

    markets = market_map(snapshot)
    missing_markets = sorted({item[0] for item in INDEX_CONFIG} - set(markets))
    if missing_markets:
        raise PublishError("Snapshot is missing required markets: " + ", ".join(missing_markets))
    if len(snapshot.get("fallback", {}).get("breadth", [])) < 2:
        raise PublishError("Snapshot breadth is incomplete")
    if not snapshot.get("view"):
        raise PublishError("Snapshot view section is empty")
    return as_of


def build_x_post(snapshot: dict[str, Any], now: dt.datetime | None = None) -> str:
    """Build the final approved longform text without changing its content rules."""
    validate_snapshot(snapshot)
    current = (now or dt.datetime.now(UTC)).astimezone(SHANGHAI)
    markets = market_map(snapshot)
    anchors = macro_anchor_map(snapshot)
    lines = [f"每日市场早报｜{published_date_label(snapshot)}", "", "01｜美股", "", "▍三大核心指数"]

    for market_id, label in INDEX_CONFIG:
        lines.append(f"• {label}：{format_percent(markets[market_id].get('changePercent'))}")

    lines.extend(("", "▍市场宽度"))
    breadth_by_id = {
        str(row.get("id")): row
        for row in snapshot.get("fallback", {}).get("breadth", [])
        if isinstance(row, dict)
    }
    for breadth_id, label in (("SP500", "标普500"), ("NASDAQ", "Nasdaq交易所")):
        row = breadth_by_id.get(breadth_id)
        if not row:
            continue
        percent = row.get("advancePercent", row.get("advancingPercent"))
        lines.append(
            f"· {label}：{format_number(percent, 1)}%上涨（涨{format_number(row.get('advancers'), 0)}"
            f"｜跌{format_number(row.get('decliners'), 0)}｜平{format_number(row.get('unchanged'), 0)}）"
        )

    lines.extend(("", "▍核心个股驱动", ""))
    drivers = [row for row in snapshot.get("drivers", []) if isinstance(row, dict)]
    def driver_sort_value(row: dict[str, Any]) -> float:
        value = finite_number(row.get("changePercent"))
        return value if value is not None else float("-inf")

    drivers.sort(key=driver_sort_value, reverse=True)
    for index, row in enumerate(drivers[:8]):
        lines.append(f"· {row.get('name')}（{row.get('ticker')}）：{format_percent(row.get('changePercent'))}")
        lines.append(concise_driver_reason(row.get("reason")))
        if index < min(len(drivers), 8) - 1:
            lines.append("")

    lines.extend(("", "02｜宏观资产数据（美股交易时段变化）", ""))
    dxy = anchors.get("DXY", {})
    us02y = markets.get("US02Y", {})
    us10y = markets.get("US10Y", {})
    us30y = markets.get("US30Y", {})
    fed = snapshot.get("fedProbability", {})
    brent = anchors.get("BRN1!", {})
    gold = anchors.get("GOLD", {})
    btc = anchors.get("BTCUSDT", {})
    lines.extend(
        (
            macro_line("美元", dxy.get("previous"), dxy.get("anchor"), 3),
            macro_line("美债2Y", us02y.get("previousClose"), us02y.get("price"), 3, "%"),
            macro_line("美债10Y", us10y.get("previousClose"), us10y.get("price"), 3, "%"),
            macro_line("美债30Y", us30y.get("previousClose"), us30y.get("price"), 3, "%"),
            macro_line("加息概率", fed.get("previous"), fed.get("current"), 1, str(fed.get("unit") or "")),
            macro_line("Brent", brent.get("previous"), brent.get("anchor"), 2),
            macro_line("XAU/USD", gold.get("previous"), gold.get("anchor"), 2),
            macro_line("BTC", btc.get("previous"), btc.get("anchor"), 0),
        )
    )

    lines.extend(("", "03｜日历、事件"))
    future: list[tuple[dt.datetime, dict[str, Any]]] = []
    deadline = current + CALENDAR_WINDOW
    for row in snapshot.get("events", []):
        if not isinstance(row, dict) or not row.get("startAt"):
            continue
        starts = event_time(str(row["startAt"]))
        if current < starts <= deadline:
            future.append((starts, row))
    future.sort(key=lambda item: item[0])

    if not future:
        lines.append("未来48小时暂无重点事件。")
    else:
        grouped: dict[dt.date, list[tuple[dt.datetime, dict[str, Any]]]] = {}
        for starts, row in future:
            grouped.setdefault(starts.date(), []).append((starts, row))
        for day, items in grouped.items():
            lines.append("")
            prefix = "（今晚）" if day == current.date() else ""
            lines.append(f"{prefix}{day.month}月{day.day}日｜{WEEKDAYS[day.weekday()]}")
            for starts, row in items:
                lines.append(f"· {starts:%H:%M}｜{clean_text(row.get('name'))}")

    lines.extend(("", "04｜看法和观点"))
    for paragraph in snapshot.get("view", []):
        text = clean_text(paragraph)
        if not text or "跨资产" in text:
            continue
        lines.extend(("", text))

    result = "\n".join(lines).strip()
    if not result.startswith("每日市场早报｜"):
        raise PublishError("Rendered X text has an invalid title")
    if len(result) > MAX_LONGFORM_CHARACTERS:
        raise PublishError(
            f"Rendered X text has {len(result)} characters; limit is {MAX_LONGFORM_CHARACTERS}"
        )
    return result


def percent_encode(value: Any) -> str:
    return quote(str(value), safe="~-._")


def oauth1_header(url: str, api_key: str, api_secret: str, token: str, token_secret: str) -> str:
    params = {
        "oauth_consumer_key": api_key,
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": token,
        "oauth_version": "1.0",
    }
    normalized = "&".join(
        f"{percent_encode(key)}={percent_encode(value)}" for key, value in sorted(params.items())
    )
    base_string = "&".join(("POST", percent_encode(url), percent_encode(normalized)))
    signing_key = f"{percent_encode(api_secret)}&{percent_encode(token_secret)}"
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    params["oauth_signature"] = signature
    values = ", ".join(
        f'{percent_encode(key)}="{percent_encode(value)}"' for key, value in sorted(params.items())
    )
    return "OAuth " + values


def create_x_post(text: str, credentials: dict[str, str], url: str = X_CREATE_POST_URL) -> str:
    body = json.dumps({"text": text}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    authorization = oauth1_header(
        url,
        credentials["X_API_KEY"],
        credentials["X_API_SECRET"],
        credentials["X_ACCESS_TOKEN"],
        credentials["X_ACCESS_TOKEN_SECRET"],
    )
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": authorization,
            "Content-Type": "application/json",
            "User-Agent": "bolin-brief-x-publisher/1.0",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise PublishError(f"X API rejected the Post (HTTP {exc.code}): {detail}") from exc
    except URLError as exc:
        raise PublishError(
            "X API response was not confirmed; the create request will not be retried automatically"
        ) from exc
    except json.JSONDecodeError as exc:
        raise PublishError("X API returned an unreadable response; no retry will be attempted") from exc

    post_id = str(payload.get("data", {}).get("id") or "")
    if not re.fullmatch(r"\d{1,25}", post_id):
        raise PublishError("X API did not return a valid Post ID; no retry will be attempted")
    return post_id


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schemaVersion": 1, "publishedByAsOf": {}}
    state = load_json(path)
    if not isinstance(state, dict) or state.get("schemaVersion") != 1:
        raise PublishError("X publish log has an unsupported schema")
    records = state.get("publishedByAsOf")
    if not isinstance(records, dict):
        raise PublishError("X publish log is missing publishedByAsOf")
    return state


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def github_output(**values: Any) -> None:
    target = os.getenv("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def credentials_from_environment() -> dict[str, str]:
    names = ("X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET")
    values = {name: os.getenv(name, "") for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise PublishError("Missing GitHub Actions secrets: " + ", ".join(missing))
    return values


def publish(
    snapshot_path: Path,
    state_path: Path,
    required_as_of: str | None,
    dry_run: bool,
    mode: str,
    now: dt.datetime | None = None,
) -> dict[str, str]:
    snapshot = load_json(snapshot_path)
    if not isinstance(snapshot, dict):
        raise PublishError("Daily market snapshot must be a JSON object")
    as_of = validate_snapshot(snapshot, required_as_of)
    state = load_state(state_path)
    existing = state["publishedByAsOf"].get(as_of)
    if existing:
        post_id = str(existing.get("postId") or "")
        github_output(status="skipped_duplicate", as_of=as_of, post_id=post_id)
        print(f"Already published asOf {as_of}; Post ID {post_id}. Skipping.")
        return {"status": "skipped_duplicate", "asOf": as_of, "postId": post_id}

    text = build_x_post(snapshot, now=now)
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if dry_run:
        github_output(status="dry_run", as_of=as_of, content_sha256=content_hash)
        print(text)
        print(f"\n[DRY RUN] asOf={as_of} characters={len(text)} sha256={content_hash}")
        return {"status": "dry_run", "asOf": as_of, "contentSha256": content_hash}

    post_id = create_x_post(text, credentials_from_environment())
    published_at = dt.datetime.now(UTC).isoformat(timespec="seconds")
    record = {
        "postId": post_id,
        "url": f"https://x.com/i/web/status/{post_id}",
        "publishedAt": published_at,
        "contentSha256": content_hash,
        "sourceCommit": os.getenv("GITHUB_SHA", ""),
        "mode": mode,
    }
    state["publishedByAsOf"][as_of] = record
    save_state(state_path, state)
    github_output(status="published", as_of=as_of, post_id=post_id, post_url=record["url"])
    print(f"Published asOf {as_of}; Post ID {post_id}.")
    return {"status": "published", "asOf": as_of, "postId": post_id}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--mode", choices=("manual", "automatic"), default="manual")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--now", help="Override current time for deterministic validation")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        now = parse_datetime(args.now) if args.now else None
        publish(
            snapshot_path=args.snapshot,
            state_path=args.state,
            required_as_of=args.as_of or None,
            dry_run=args.dry_run,
            mode=args.mode,
            now=now,
        )
        return 0
    except PublishError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        github_output(status="failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
