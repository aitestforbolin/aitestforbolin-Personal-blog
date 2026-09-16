#!/usr/bin/env python3
"""Publish the U.S.-only macro calendar envelope consumed by the website."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_US = ROOT / "data" / "us-macro-calendar.json"
DEFAULT_OUTPUT = ROOT / "data" / "macro-calendar.json"


def stable_id(event):
    raw = "|".join(str(event.get(key, "")) for key in ("date", "time_shanghai", "title"))
    return "us-" + hashlib.sha256(raw.encode()).hexdigest()[:12]


def normalize_event(event):
    metrics = []
    for index, metric in enumerate(event.get("metric_values", []), 1):
        if isinstance(metric, dict):
            metrics.append({"id": f"metric-{index}", "label": metric.get("label") or "综合值", "actual": metric.get("actual"), "forecast": metric.get("forecast"), "previous": metric.get("previous"), "unit": None, "sourceUrl": event.get("result_url") or event.get("url")})
    return {"id": event.get("id") or stable_id(event), "eventType": "data", "country": "US", "period": event.get("period"), "scheduledAt": f"{event['date']}T{event['time_shanghai']}:00+08:00", "dateStatus": "confirmed", "title": event.get("title_cn") or event.get("title") or "美国宏观数据", "category": event.get("category") or "macro", "importance": event.get("importance") or "medium", "stars": int(event.get("stars") or 3), "source": event.get("source") or "Forex Factory", "sourceUrl": event.get("url"), "metrics": metrics, "releasedAt": event.get("released_at"), "retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "revisionStatus": "not_revised", "releaseStatus": event.get("release_status") or "scheduled", "legacy": copy.deepcopy(event)}


def build_payload(events):
    normalized = sorted((normalize_event(event) for event in events if isinstance(event, dict)), key=lambda item: (item["scheduledAt"], item["id"]))
    if not normalized: raise ValueError("U.S. calendar is empty")
    status = "stale" if all(event.get("calendar_status") == "stale_snapshot" for event in events) else "healthy"
    return {"schemaVersion": 2, "generatedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"), "timezone": "Asia/Shanghai", "status": status, "failedSources": ["Forex Factory"] if status == "stale" else [], "health": {"US": {"status": status, "primarySource": "Forex Factory", "fomcValidation": "Federal Reserve"}}, "sourcePolicy": "U.S. calendar: curated CPI, PPI, PCE, NFP, retail sales and FOMC events rated Medium or High by Forex Factory; Federal Reserve validates FOMC dates.", "events": normalized}


def comparable(value):
    result = copy.deepcopy(value); result.pop("generatedAt", None)
    for event in result.get("events", []): event.pop("retrievedAt", None)
    return result


def validate(payload):
    events = payload.get("events")
    if not isinstance(events, list) or not events: raise ValueError("U.S. macro calendar must contain events")
    if any(event.get("country") != "US" for event in events): raise ValueError("calendar must contain only U.S. events")
    if events != sorted(events, key=lambda item: (item.get("scheduledAt", ""), item.get("id", ""))): raise ValueError("calendar events are not sorted")


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--us", type=Path, default=DEFAULT_US); parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT); parser.add_argument("--validate-only", action="store_true"); args = parser.parse_args()
    if args.validate_only:
        validate(json.loads(args.output.read_text(encoding="utf-8"))); print(f"Validated {args.output}"); return
    events = json.loads(args.us.read_text(encoding="utf-8"))
    if not isinstance(events, list): raise ValueError("U.S. calendar must be an array")
    payload = build_payload(events); validate(payload)
    old = json.loads(args.output.read_text(encoding="utf-8")) if args.output.exists() else None
    if old and comparable(old) == comparable(payload): print("Unified U.S. calendar is unchanged"); return
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Updated unified U.S. calendar")


if __name__ == "__main__": main()
