#!/usr/bin/env python3
"""Merge the preserved U.S. calendar and normalized China calendar for the page."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_US = SITE_ROOT / "data" / "us-macro-calendar.json"
DEFAULT_CHINA = SITE_ROOT / "data" / "china-macro-calendar.json"
DEFAULT_OUTPUT = SITE_ROOT / "data" / "macro-calendar.json"
IMPORTANCE_STARS = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "background": 1,
}


def stable_us_id(event: dict) -> str:
    identity = "|".join(
        str(event.get(field, ""))
        for field in ("date_shanghai", "date", "time_shanghai", "title")
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"us-{digest}"


def us_scheduled_at(event: dict) -> str | None:
    day = event.get("date_shanghai") or event.get("date")
    if not day:
        return None
    clock = event.get("time_shanghai")
    if not clock:
        return None
    return f"{day}T{clock}:00+08:00"


def normalize_us_event(event: dict) -> dict:
    actual = event.get("actual")
    forecast = event.get("forecast")
    previous = event.get("previous")
    metrics = []
    if any(value not in (None, "") for value in (actual, forecast, previous)):
        metrics.append(
            {
                "id": "headline",
                "label": "综合值",
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
                "unit": None,
                "sourceUrl": event.get("result_url") or event.get("url"),
            }
        )
    scheduled_at = us_scheduled_at(event)
    stars = event.get("stars") or IMPORTANCE_STARS.get(event.get("importance"), 3)
    normalized = {
        "id": event.get("id") or stable_us_id(event),
        "country": "US",
        "period": event.get("period"),
        "scheduledAt": scheduled_at,
        "dateStatus": "confirmed" if scheduled_at else "date_tbd",
        "title": event.get("title_cn") or event.get("title") or "美国宏观数据",
        "category": event.get("category") or "macro",
        "importance": event.get("importance") or "medium",
        "stars": int(stars),
        "source": event.get("source"),
        "sourceUrl": event.get("url"),
        "metrics": metrics,
        "releasedAt": event.get("released_at"),
        "retrievedAt": event.get("updated_at"),
        "revisionStatus": event.get("revision_status") or "not_revised",
        "releaseStatus": event.get("release_status") or "scheduled",
        "legacy": copy.deepcopy(event),
    }
    if event.get("fallback_url"):
        normalized["fallbackSourceUrl"] = event["fallback_url"]
        normalized["fallbackSourceLabel"] = event.get("fallback_label") or "备用链接"
    return normalized


def event_sort_key(event: dict) -> tuple[str, str, str]:
    if event.get("scheduledAt"):
        stamp = event["scheduledAt"]
    else:
        window = event.get("expectedWindow") or {}
        stamp = f"{window.get('start', '9999-12-31')}T23:59:59+08:00"
    return stamp, event.get("country", ""), event.get("id", "")


def validate_unified(payload: dict) -> None:
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Unified macro calendar is empty")
    required = {
        "id",
        "country",
        "period",
        "scheduledAt",
        "dateStatus",
        "title",
        "category",
        "importance",
        "source",
        "sourceUrl",
        "metrics",
        "releasedAt",
        "retrievedAt",
        "revisionStatus",
    }
    ids: set[str] = set()
    countries: set[str] = set()
    for event in events:
        missing = required - set(event)
        if missing:
            raise ValueError(f"{event.get('id')} missing fields: {sorted(missing)}")
        if event["id"] in ids:
            raise ValueError(f"Duplicate unified event id: {event['id']}")
        ids.add(event["id"])
        countries.add(event["country"])
    if not {"CN", "US"}.issubset(countries):
        raise ValueError("Unified calendar must include both CN and US")
    if events != sorted(events, key=event_sort_key):
        raise ValueError("Unified events are not sorted by Asia/Shanghai display time")


def build_payload(us_events: list[dict], china_payload: dict, generated_at: str) -> dict:
    events = [normalize_us_event(event) for event in us_events]
    events.extend(copy.deepcopy(china_payload["events"]))
    payload = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "timezone": "Asia/Shanghai",
        "status": china_payload.get("status", "unknown"),
        "failedSources": china_payload.get("failedSources", []),
        "sourcePolicy": "China official-only; U.S. legacy calendar preserved",
        "events": sorted(events, key=event_sort_key),
    }
    validate_unified(payload)
    return payload


def comparable(payload: dict) -> dict:
    result = copy.deepcopy(payload)
    result.pop("generatedAt", None)
    return result


def write_if_changed(path: Path, payload: dict) -> bool:
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if comparable(previous) == comparable(payload):
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--us", type=Path, default=DEFAULT_US)
    parser.add_argument("--china", type=Path, default=DEFAULT_CHINA)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validate_only:
        validate_unified(json.loads(args.output.read_text(encoding="utf-8")))
        print(f"Validated {args.output}")
        return 0
    us_events = json.loads(args.us.read_text(encoding="utf-8"))
    china_payload = json.loads(args.china.read_text(encoding="utf-8"))
    if not isinstance(us_events, list):
        raise ValueError("The preserved U.S. calendar must remain an array")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = build_payload(us_events, china_payload, now)
    wrote = write_if_changed(args.output, payload)
    print("Updated unified macro calendar" if wrote else "Unified macro calendar is unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
