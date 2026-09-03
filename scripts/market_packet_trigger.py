#!/usr/bin/env python3
"""Decide whether a completed market-price update should build the close packet."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
MARKET_PRICES = ROOT / "data" / "market-prices.json"
PREVIOUS_PACKET = ROOT / "data" / "market-briefing-packet.json"
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
    """Return the latest common NY close date, regardless of scheduler delay."""
    # ``now`` remains accepted for callers/tests, but wall-clock time must not
    # reject an already completed close. GitHub scheduled runs can arrive hours
    # late; freshness is enforced by comparing with the canonical packet below.
    del now
    eastern = ZoneInfo("America/New_York")

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
    if len(dates) != 1:
        return None
    return next(iter(dates))


def packet_is_complete_for_date(payload: object, trading_date: str) -> bool:
    if not isinstance(payload, dict) or payload.get("tradingDate") != trading_date:
        return False
    validation = payload.get("validation")
    return (
        isinstance(validation, dict)
        and validation.get("complete") is True
        and not validation.get("criticalErrors")
    )


def main() -> int:
    date = closed_snapshot_date(load_json(MARKET_PRICES))
    if not date:
        print("Market close snapshot is not ready; packet build not requested.")
        return 1
    previous_path = Path(os.getenv("PREVIOUS_PACKET_PATH", str(PREVIOUS_PACKET)))
    if packet_is_complete_for_date(load_json(previous_path), date):
        print(f"Canonical packet is already complete for {date}; rebuild not requested.")
        return 1
    print(f"Market close snapshot is ready for {date}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
