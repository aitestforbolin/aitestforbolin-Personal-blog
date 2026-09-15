#!/usr/bin/env python3
"""Check that today's market briefing has a valid terminal run status."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
from zoneinfo import ZoneInfo

import finalize_run_status as status_contract


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "data" / "run-status.json"
DEFAULT_SNAPSHOT = ROOT / "data" / "daily-market-status.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def github_output(**values: object) -> None:
    target = os.getenv("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={'' if value is None else value}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--now")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        now = status_contract.parse_datetime(args.now)
        run_date = now.astimezone(SHANGHAI).date().isoformat()
        current = status_contract.load_json(args.status, {})
        if isinstance(current, dict) and current.get("runDate") == run_date:
            status_contract.validate_status(current)
            if current["status"] == "failed":
                github_output(action="notify_existing_failure", status="failed")
                print("Today's run is finalized as failed; requesting an alert.")
                return 0
            github_output(action="none", status=current["status"])
            print(f"Today's run is already finalized as {current['status']}.")
            return 0

        snapshot = status_contract.load_json(args.snapshot, {})
        as_of = snapshot.get("asOf") if isinstance(snapshot, dict) else None
        payload = status_contract.build_status(
            status="failed",
            stage="briefing",
            run_date=run_date,
            as_of=status_contract.iso_date(as_of, "snapshot asOf", optional=True),
            briefing_commit=None,
            x_post_id=None,
            x_post_url=None,
            reason_code="status_missing_after_deadline",
            now=now,
        )
        status_contract.atomic_write(args.status, payload)
        github_output(action="created_failure", status="failed", as_of=payload.get("asOf"))
        print("Today's run status was missing after the deadline; recorded failure.")
        return 0
    except (status_contract.RunStatusError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
