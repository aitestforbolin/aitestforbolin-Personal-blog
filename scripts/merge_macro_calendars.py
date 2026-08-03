#!/usr/bin/env python3
"""Merge the preserved U.S. calendar and normalized China calendar for the page."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_US = SITE_ROOT / "data" / "us-macro-calendar.json"
DEFAULT_CHINA = SITE_ROOT / "data" / "china-macro-calendar.json"
DEFAULT_POLICY_EVENTS = SITE_ROOT / "data" / "china-policy-events.json"
DEFAULT_OUTPUT = SITE_ROOT / "data" / "macro-calendar.json"
IMPORTANCE_STARS = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
    "background": 1,
}
POLICY_OFFICIAL_HOST_SUFFIXES = (
    "gov.cn",
    "news.cn",
    "pbc.gov.cn",
    "ndrc.gov.cn",
)


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
        "eventType": "data",
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
    elif event.get("eventDate"):
        stamp = f"{event['eventDate']}T12:00:00+08:00"
    else:
        window = event.get("expectedWindow") or {}
        stamp = f"{window.get('start', '9999-12-31')}T23:59:59+08:00"
    return stamp, event.get("country", ""), event.get("id", "")


def is_official_policy_url(url: str | None) -> bool:
    if not url:
        return False
    host = (urlparse(url).hostname or "").lower()
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in POLICY_OFFICIAL_HOST_SUFFIXES)


def validate_policy_payload(payload: dict) -> None:
    if payload.get("sourcePolicy") != "official_only":
        raise ValueError("China policy events must use the official-only source policy")
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("China policy events must be a list")
    ids: set[str] = set()
    for event in events:
        required = {
            "id",
            "eventType",
            "country",
            "scheduledAt",
            "eventDate",
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
            "releaseStatus",
            "summary",
            "scheduleNote",
        }
        missing = required - set(event)
        if missing:
            raise ValueError(f"{event.get('id')} missing policy fields: {sorted(missing)}")
        if event["id"] in ids:
            raise ValueError(f"Duplicate China policy event id: {event['id']}")
        ids.add(event["id"])
        if event["eventType"] != "policy_event" or event["country"] != "CN":
            raise ValueError(f"{event['id']} is not a China policy event")
        if event["metrics"] != []:
            raise ValueError(f"{event['id']} policy metrics must be an empty list")
        if not is_official_policy_url(event["sourceUrl"]):
            raise ValueError(f"{event['id']} uses a non-official policy source URL")
        if event.get("outcomeUrl") and not is_official_policy_url(event["outcomeUrl"]):
            raise ValueError(f"{event['id']} uses a non-official outcome URL")
        if event["dateStatus"] == "confirmed_date" and not event.get("eventDate"):
            raise ValueError(f"{event['id']} confirmed_date requires eventDate")
        if event["dateStatus"] == "expected_window" and not event.get("expectedWindow"):
            raise ValueError(f"{event['id']} expected_window requires expectedWindow")


def validate_unified(payload: dict) -> None:
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("Unified macro calendar is empty")
    required = {
        "id",
        "eventType",
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
        if not isinstance(event["metrics"], list):
            raise ValueError(f"{event['id']} metrics must be a list")
        if event["eventType"] == "policy_event":
            if event["country"] != "CN" or event["metrics"]:
                raise ValueError(f"{event['id']} has an invalid policy event shape")
        elif event["eventType"] != "data":
            raise ValueError(f"{event['id']} has an unknown eventType")
    if not {"CN", "US"}.issubset(countries):
        raise ValueError("Unified calendar must include both CN and US")
    if events != sorted(events, key=event_sort_key):
        raise ValueError("Unified events are not sorted by Asia/Shanghai display time")


def build_payload(
    us_events: list[dict],
    china_payload: dict,
    generated_at: str,
    policy_payload: dict | None = None,
) -> dict:
    events = [normalize_us_event(event) for event in us_events]
    for china_event in copy.deepcopy(china_payload["events"]):
        china_event.setdefault("eventType", "data")
        events.append(china_event)
    if policy_payload is not None:
        validate_policy_payload(policy_payload)
        events.extend(copy.deepcopy(policy_payload["events"]))
    payload = {
        "schemaVersion": 1,
        "generatedAt": generated_at,
        "timezone": "Asia/Shanghai",
        "status": china_payload.get("status", "unknown"),
        "failedSources": china_payload.get("failedSources", []),
        "sourcePolicy": "China official-only; U.S. legacy calendar preserved",
        "policyEventsUpdatedAt": (
            policy_payload.get("updatedAt") if policy_payload is not None else None
        ),
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
    parser.add_argument("--policy-events", type=Path, default=DEFAULT_POLICY_EVENTS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validate_only:
        validate_policy_payload(json.loads(args.policy_events.read_text(encoding="utf-8")))
        validate_unified(json.loads(args.output.read_text(encoding="utf-8")))
        print(f"Validated {args.output}")
        return 0
    us_events = json.loads(args.us.read_text(encoding="utf-8"))
    china_payload = json.loads(args.china.read_text(encoding="utf-8"))
    policy_payload = json.loads(args.policy_events.read_text(encoding="utf-8"))
    if not isinstance(us_events, list):
        raise ValueError("The preserved U.S. calendar must remain an array")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    payload = build_payload(us_events, china_payload, now, policy_payload)
    wrote = write_if_changed(args.output, payload)
    print("Updated unified macro calendar" if wrote else "Unified macro calendar is unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
