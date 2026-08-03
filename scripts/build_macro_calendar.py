#!/usr/bin/env python3
"""Combine the China and U.S. calendars into the site-facing JSON."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_US_INPUT = SITE_ROOT / "data" / "us-macro-calendar.json"
DEFAULT_CHINA_INPUT = SITE_ROOT / "data" / "china-macro-calendar.json"
DEFAULT_OUTPUT = SITE_ROOT / "data" / "macro-calendar.json"


def read_events(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list) or not all(
        isinstance(item, dict) for item in payload
    ):
        raise ValueError(f"{path} must contain a JSON array of objects")
    return payload


def slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized or "event"


def normalize_event(event: dict[str, Any], country: str) -> dict[str, Any]:
    normalized = dict(event)
    normalized["country"] = country
    date_status = str(
        event.get("dateStatus") or event.get("date_status") or "confirmed"
    )
    normalized["dateStatus"] = date_status
    normalized["date_status"] = date_status

    source_url = str(event.get("sourceUrl") or event.get("url") or "")
    normalized["sourceUrl"] = source_url
    normalized["url"] = source_url

    event_date = str(event.get("date_shanghai") or event.get("date") or "")
    if not event_date:
        raise ValueError("calendar event is missing date")
    normalized["date"] = event_date
    normalized.setdefault("date_end", event_date)

    time_shanghai = str(event.get("time_shanghai") or "")
    normalized["time_shanghai"] = time_shanghai
    scheduled_at = event.get("scheduledAt")
    if scheduled_at is None and time_shanghai and date_status == "confirmed":
        scheduled_at = f"{event_date}T{time_shanghai}:00+08:00"
    normalized["scheduledAt"] = scheduled_at

    event_id = event.get("id")
    if not event_id:
        title = str(event.get("title") or event.get("title_cn") or "event")
        event_id = (
            f"{country}-{event_date}-{time_shanghai or 'tbd'}-{slug(title)}"
        )
    normalized["id"] = str(event_id)

    if "title_cn" not in normalized:
        normalized["title_cn"] = str(event.get("title") or "")

    metrics = event.get("metrics")
    if not isinstance(metrics, list):
        metrics = []
    if not metrics:
        metric: dict[str, str] = {
            "name": str(event.get("title_cn") or event.get("title") or "")
        }
        for field in ("actual", "forecast", "previous"):
            value = event.get(field)
            if value not in (None, ""):
                metric[field] = str(value)
        if len(metric) > 1:
            metrics = [metric]
    normalized["metrics"] = metrics
    normalized.setdefault("releasedAt", None)
    return normalized


def build_calendar(
    us_events: list[dict[str, Any]],
    china_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    combined = [
        *(normalize_event(event, "US") for event in us_events),
        *(normalize_event(event, "CN") for event in china_events),
    ]
    ids = [event["id"] for event in combined]
    if len(ids) != len(set(ids)):
        raise ValueError("combined calendar contains duplicate event ids")
    return sorted(
        combined,
        key=lambda item: (
            str(item["date"]),
            str(item.get("time_shanghai") or "99:99"),
            str(item["country"]),
            str(item.get("title_cn") or item.get("title") or ""),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--us-input", type=Path, default=DEFAULT_US_INPUT)
    parser.add_argument("--china-input", type=Path, default=DEFAULT_CHINA_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    events = build_calendar(
        read_events(args.us_input),
        read_events(args.china_input),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(events)} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
