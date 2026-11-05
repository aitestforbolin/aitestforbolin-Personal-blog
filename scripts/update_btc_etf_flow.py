#!/usr/bin/env python3
"""Build the static Bitcoin ETF flow JSON for the personal site."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


SITE_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = SITE_ROOT / "data" / "btc-etf-flow.json"
FARSIDE_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
FARSIDE_BRIDGE_URL = "https://farside-etf-bridge.laibocszd.chatgpt.site/api/btc-etf-flow"
FETCH_TIMEOUT = 90
FETCH_RETRIES = 3
SUMMARY_DAYS = 5


class IncompleteFlowError(RuntimeError):
    """A total needed for the five-day summary has not been published yet."""


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "personal-site-btc-etf-flow/1.0 (+https://github.com/)",
        },
    )
    last_error: Exception | None = None
    for _ in range(FETCH_RETRIES):
        try:
            with urlopen(request, timeout=FETCH_TIMEOUT) as response:
                body = response.read()
                encoding = response.headers.get_content_charset() or "utf-8"
            return body.decode(encoding, errors="replace")
        except (TimeoutError, URLError) as error:
            last_error = error
    raise RuntimeError(f"Could not fetch {url}") from last_error


def html_text_lines(html: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(html)
    return parser.parts


def parse_money(value: str) -> float | None:
    text = value.strip()
    if text in {"", "-"}:
        return None

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]

    text = text.replace(",", "")
    try:
        parsed = float(text)
    except ValueError:
        return None

    if not math.isfinite(parsed):
        return None
    return -parsed if negative else parsed


def parse_date(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%d %b %Y").date().isoformat()
    except ValueError:
        return None


def parse_farside_rows(lines: list[str]) -> list[dict[str, object]]:
    try:
        start = lines.index("Date")
        header_end = lines.index("Total", start + 1)
    except ValueError as exc:
        raise RuntimeError("Could not find Farside ETF flow table header") from exc

    rows: list[dict[str, object]] = []
    index = header_end + 1
    cells_per_row = header_end - start  # Fund columns plus the published total.
    while index < len(lines):
        date_value = parse_date(lines[index])
        if not date_value:
            break

        values = lines[index + 1 : index + 1 + cells_per_row]
        if len(values) < cells_per_row:
            break

        rows.append({"date": date_value, "total": parse_money(values[-1])})
        index += 1 + cells_per_row

    if not rows:
        raise RuntimeError("Farside ETF flow table was empty")

    return sorted(rows, key=lambda row: str(row["date"]), reverse=True)


def summarize_rows(source_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], int]:
    """Use published daily totals; missing individual fund values do not remove a day."""
    rows: list[dict[str, object]] = []
    dates: set[str] = set()
    for source in source_rows:
        if not isinstance(source, dict) or not isinstance(source.get("date"), str):
            raise RuntimeError("Farside returned a malformed date row")
        day = source["date"]
        try:
            valid_date = datetime.strptime(day, "%Y-%m-%d").date().isoformat()
        except ValueError as exc:
            raise RuntimeError(f"Farside returned an invalid date: {day}") from exc
        if valid_date != day or day in dates:
            raise RuntimeError(f"Farside returned an invalid or duplicate date: {day}")
        dates.add(day)
        value = source.get("total")
        if isinstance(value, str):
            value = parse_money(value)
        elif isinstance(value, bool) or not isinstance(value, (int, float)):
            value = None
        elif not math.isfinite(value):
            value = None
        rows.append({"date": day, "total": value})

    rows.sort(key=lambda row: row["date"], reverse=True)
    if len(rows) < SUMMARY_DAYS or any(row["total"] is None for row in rows[:SUMMARY_DAYS]):
        raise IncompleteFlowError("Farside has not published five consecutive daily totals")

    direction = (rows[0]["total"] > 0) - (rows[0]["total"] < 0)
    streak_days = 0
    if direction:
        for row in rows:
            total = row["total"]
            if total is None or total * direction <= 0:
                break
            streak_days += 1
    return rows[:SUMMARY_DAYS], streak_days


def build_payload() -> dict[str, object]:
    try:
        bridge_payload = json.loads(fetch_text(FARSIDE_BRIDGE_URL))
        bridge_rows = bridge_payload.get("rows", [])
        if not isinstance(bridge_rows, list) or not bridge_rows:
            raise RuntimeError("Farside bridge returned no rows")
        rows = bridge_rows
    except Exception as bridge_error:
        try:
            html = fetch_text(FARSIDE_URL)
            rows = parse_farside_rows(html_text_lines(html))
        except Exception as direct_error:
            raise RuntimeError(
                "Both the Farside bridge and direct source failed"
            ) from ExceptionGroup("Farside fetch failures", [bridge_error, direct_error])
    output_rows, streak_days = summarize_rows(rows)
    latest = output_rows[0]
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Farside Investors",
        "source_url": FARSIDE_URL,
        "unit": "US$m",
        "latest": {
            "date": latest["date"],
            "total": latest["total"],
            "streak_days": streak_days,
        },
        "rows": output_rows,
    }


def main() -> None:
    try:
        payload = build_payload()
    except IncompleteFlowError as error:
        print(f"{error}. Keeping the previous dataset; a later run will retry.")
        return

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
