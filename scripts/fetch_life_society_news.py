#!/usr/bin/env python3
"""Collect RSS titles into a rolling store and publish a fixed 07:30 BJT snapshot."""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "life-society-news-sources.json"
DEFAULT_STORE = ROOT / "data" / "life-society-news-store.json"
DEFAULT_SNAPSHOT = ROOT / "data" / "life-society-news.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")
STORE_HOURS = 48
SNAPSHOT_HOUR = 7
SNAPSHOT_MINUTE = 30


def node_text(node: ET.Element | None, *names: str) -> str:
    if node is None:
        return ""
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return re.sub(r"<[^>]+>", "", html.unescape(child.text)).strip()
    return ""


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; BolinBriefCountryNews/1.0)", "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urlopen(request, timeout=12) as response:
        return response.read()


def parse_entries(payload: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(payload)
    found: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        found.append({"originalTitle": node_text(item, "title"), "url": node_text(item, "link"), "publishedAt": node_text(item, "pubDate", "{http://purl.org/dc/elements/1.1/}date")})
    atom = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{atom}entry"):
        link = item.find(f"{atom}link")
        found.append({"originalTitle": node_text(item, f"{atom}title"), "url": link.get("href", "") if link is not None else "", "publishedAt": node_text(item, f"{atom}updated", f"{atom}published")})
    return [row for row in found if row["originalTitle"] and row["url"]]


def parse_datetime(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds")


def load_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def effective_time(row: dict) -> dt.datetime | None:
    return parse_datetime(row.get("publishedAt")) or parse_datetime(row.get("firstSeenAt"))


def merge_store(existing: object, candidates: list[dict], now: dt.datetime) -> list[dict]:
    previous = existing.get("items", []) if isinstance(existing, dict) else []
    by_url = {row["url"]: dict(row) for row in previous if isinstance(row, dict) and isinstance(row.get("url"), str)}
    now_value = iso(now)
    for candidate in candidates:
        old = by_url.get(candidate["url"], {})
        published = parse_datetime(candidate.get("publishedAt"))
        by_url[candidate["url"]] = {**old, **candidate, "publishedAt": iso(published) if published else old.get("publishedAt"), "firstSeenAt": old.get("firstSeenAt") or now_value, "lastSeenAt": now_value}
    cutoff = now - dt.timedelta(hours=STORE_HOURS)
    retained = [row for row in by_url.values() if (effective_time(row) or now) >= cutoff]
    retained.sort(key=lambda row: effective_time(row) or now, reverse=True)
    return retained


def snapshot_window(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    local = now.astimezone(SHANGHAI)
    end = local.replace(
        hour=SNAPSHOT_HOUR,
        minute=SNAPSHOT_MINUTE,
        second=0,
        microsecond=0,
    )
    if local < end:
        end -= dt.timedelta(days=1)
    return (end - dt.timedelta(hours=24)).astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)


def snapshot_is_due(existing: object, now: dt.datetime) -> bool:
    if not isinstance(existing, dict):
        return True
    published_end = parse_datetime(existing.get("asOf") or existing.get("windowEnd"))
    _, expected_end = snapshot_window(now)
    return published_end is None or published_end < expected_end


def build_snapshot(store: dict, now: dt.datetime) -> dict:
    start, end = snapshot_window(now)
    items = [row for row in store.get("items", []) if effective_time(row) is not None and start <= effective_time(row) < end]
    items.sort(key=lambda row: effective_time(row), reverse=True)
    return {"schemaVersion": 2, "generatedAt": iso(now), "asOf": end.astimezone(SHANGHAI).isoformat(timespec="seconds"), "windowStart": start.astimezone(SHANGHAI).isoformat(timespec="seconds"), "windowEnd": end.astimezone(SHANGHAI).isoformat(timespec="seconds"), "sourceAudit": store.get("sourceAudit", []), "items": items}


def collect_sources(now: dt.datetime) -> tuple[list[dict], list[dict]]:
    registry = json.loads(SOURCES.read_text(encoding="utf-8"))
    sources = [source for source in registry["sources"] if source.get("enabled")]
    def collect(source: dict) -> tuple[dict, list[dict]]:
        try:
            rows = parse_entries(fetch(source["rssUrl"]))
            audit = {"country": source["country"], "outlet": source["outlet"], "rssUrl": source["rssUrl"], "status": "ok" if rows else "empty", "count": len(rows), "checkedAt": iso(now)}
            return audit, [{**row, "country": source["country"], "countryCode": source["countryCode"], "outlet": source["outlet"], "sectionUrl": source["sectionUrl"]} for row in rows]
        except Exception as exc:
            return {"country": source["country"], "outlet": source["outlet"], "rssUrl": source["rssUrl"], "status": "error", "error": type(exc).__name__, "checkedAt": iso(now)}, []
    audits, candidates = [], []
    with ThreadPoolExecutor(max_workers=len(sources)) as pool:
        futures = [pool.submit(collect, source) for source in sources]
        for future in as_completed(futures):
            audit, rows = future.result()
            audits.append(audit)
            candidates.extend(rows)
    audits.sort(key=lambda row: row["country"])
    return audits, candidates


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--store-file", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--snapshot-file", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--snapshot-if-due", action="store_true")
    parser.add_argument("--now", help="UTC/offset ISO timestamp for deterministic tests")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = parse_datetime(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    if now is None:
        raise SystemExit("--now must be a valid ISO timestamp")
    previous = load_json(args.store_file, {})
    publish_snapshot = args.snapshot or (
        args.snapshot_if_due
        and snapshot_is_due(load_json(args.snapshot_file, {}), now)
    )
    audits, candidates = collect_sources(now)
    store = {"schemaVersion": 2, "generatedAt": iso(now), "retentionHours": STORE_HOURS, "sourceAudit": audits, "items": merge_store(previous, candidates, now)}
    args.store_file.parent.mkdir(parents=True, exist_ok=True)
    args.store_file.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if publish_snapshot:
        args.snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        args.snapshot_file.write_text(json.dumps(build_snapshot(store, now), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"audit": audits, "stored": len(store["items"]), "snapshot": publish_snapshot}, ensure_ascii=False))
    return 0 if candidates or store["items"] else 1


if __name__ == "__main__":
    sys.exit(main())
