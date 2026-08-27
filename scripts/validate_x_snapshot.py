#!/usr/bin/env python3
"""Block X publication when the daily market briefing contains missing display data.

The X renderer turns missing numeric values into an em dash.  That is acceptable for
manual inspection, but an automatic post must never publish placeholders such as
"—%", "涨—" or "XAU/USD: ... -> —".  This validator checks the exact fields the
current X template renders and fails before the create-post request is made.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "data" / "daily-market-status.json"
REQUIRED_INDEXES = ("SPX", "IXIC", "DJI")
REQUIRED_BREADTH = ("SP500", "NASDAQ")
REQUIRED_TREASURIES = ("US02Y", "US10Y", "US30Y")
REQUIRED_MACRO_ANCHORS = ("DXY", "BRN1!", "GOLD", "BTCUSDT")


class SnapshotQualityError(RuntimeError):
    """The daily snapshot is not complete enough for automatic X publication."""


def finite_number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def keyed_rows(rows: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }


def require_numbers(errors: list[str], label: str, row: dict[str, Any], fields: tuple[str, ...]) -> None:
    missing = [field for field in fields if finite_number(row.get(field)) is None]
    if missing:
        errors.append(f"{label}: missing numeric {', '.join(missing)}")


def validate_snapshot(snapshot: dict[str, Any]) -> None:
    errors: list[str] = []
    markets = keyed_rows(snapshot.get("fallback", {}).get("markets"))
    breadth = keyed_rows(snapshot.get("fallback", {}).get("breadth"))
    anchors = keyed_rows(snapshot.get("macroAnchors"))

    for market_id in REQUIRED_INDEXES:
        row = markets.get(market_id)
        if not row:
            errors.append(f"{market_id}: missing market row")
            continue
        require_numbers(errors, market_id, row, ("changePercent",))

    for breadth_id in REQUIRED_BREADTH:
        row = breadth.get(breadth_id)
        if not row:
            errors.append(f"{breadth_id}: missing breadth row")
            continue
        require_numbers(
            errors,
            breadth_id,
            row,
            ("advancers", "decliners", "unchanged", "advancePercent"),
        )
        if str(row.get("status") or "").lower() == "unavailable":
            errors.append(f"{breadth_id}: source status is unavailable")

    for market_id in REQUIRED_TREASURIES:
        row = markets.get(market_id)
        if not row:
            errors.append(f"{market_id}: missing Treasury row")
            continue
        require_numbers(errors, market_id, row, ("previousClose", "price"))

    for anchor_id in REQUIRED_MACRO_ANCHORS:
        row = anchors.get(anchor_id)
        if not row:
            errors.append(f"{anchor_id}: missing macro anchor row")
            continue
        require_numbers(errors, anchor_id, row, ("previous", "anchor"))

    fed = snapshot.get("fedProbability")
    if not isinstance(fed, dict):
        errors.append("fedProbability: missing object")
    else:
        require_numbers(errors, "fedProbability", fed, ("previous", "current"))

    if not snapshot.get("view"):
        errors.append("view: empty")

    if errors:
        raise SnapshotQualityError("X publication blocked: " + "; ".join(errors))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        if not isinstance(snapshot, dict):
            raise SnapshotQualityError("snapshot root must be an object")
        validate_snapshot(snapshot)
    except (OSError, json.JSONDecodeError, SnapshotQualityError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print("X snapshot quality gate passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
