#!/usr/bin/env python3
"""Validate and print the requested briefing date for an auditable X backfill."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REQUEST = ROOT / "data" / "x-publish-request.json"


class RequestError(RuntimeError):
    """The repository backfill request is missing or malformed."""


def requested_as_of(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RequestError(f"X publish request is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RequestError(f"X publish request is invalid JSON: {path}") from exc

    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise RequestError("X publish request must use schemaVersion 1")
    if payload.get("action") != "publish_missing_x":
        raise RequestError("X publish request action must be publish_missing_x")

    as_of = str(payload.get("asOf") or "").strip()
    try:
        dt.date.fromisoformat(as_of)
    except ValueError as exc:
        raise RequestError("X publish request asOf must be an ISO date") from exc
    return as_of


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    args = parser.parse_args()
    print(requested_as_of(args.request))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
