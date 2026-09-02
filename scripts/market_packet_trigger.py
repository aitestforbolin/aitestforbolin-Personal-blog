#!/usr/bin/env python3
"""Decide whether a completed market-price update should build the close packet."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
MARKET_PRICES = ROOT / "data" / "market-prices.json"
REQUIRED_CLOSE_SYMBOLS = {"SPY.US", "QQQ.US", "DIA.US"}


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def last_timestamp(row: dict) -> int | None:
    values = [
        point.get("timestamp")
        for point in row.get("points", [])
        if isinstance(point, dict) and isinstance(point.get("timestamp"), (int, float))
    ]
    return int(max(values)) if values else None


def closed_snapshot_date(payload: object, now: dt.datetime | None = None) -> str | None:
    """Return the common NY close date only during the post-close packet window."""
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=dt.timezone.utc)
    eastern = ZoneInfo("America/New_York")
    local_now = current.astimezone(eastern)
    if local_now.weekday() >= 5 or not dt.time(16, 0) <= local_now.time() < dt.time(20, 0):
        return None

    rows = payload.get("symbols", []) if isinstance(payload, dict) else []
    by_symbol = {
        str(row.get("symbol")): row
        for row in rows
        if isinstance(row, dict) and row.get("symbol")
    }
    if not REQUIRED_CLOSE_SYMBOLS <= set(by_symbol):
        return None

    dates: set[str] = set()
    for symbol in REQUIRED_CLOSE_SYMBOLS:
        timestamp = last_timestamp(by_symbol[symbol])
        if timestamp is None:
            return None
        moment = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(eastern)
        if moment.time() < dt.time(16, 0):
            return None
        dates.add(moment.date().isoformat())
    if len(dates) != 1 or next(iter(dates)) != local_now.date().isoformat():
        return None
    return next(iter(dates))


def main() -> int:
    date = closed_snapshot_date(load_json(MARKET_PRICES))
    if not date:
        print("Market close snapshot is not ready; packet build not requested.")
        return 1
    print(f"Market close snapshot is ready for {date}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
