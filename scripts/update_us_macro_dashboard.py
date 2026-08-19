#!/usr/bin/env python3
"""Persist newly released U.S. macro calendar values into the core dashboard.

The calendar remains a short release window. This script is deliberately
event-driven: it exits without writing unless one of the tracked releases has
a newer released date than the dashboard's stored sourceEvents value.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALENDAR = ROOT / "data" / "us-macro-calendar.json"
DEFAULT_DASHBOARD = ROOT / "data" / "us-macro-dashboard.json"

TRACKED_TITLES = {
    "美国CPI / 核心CPI",
    "美国PPI",
    "美国非农 / 失业率 / 平均时薪",
    "美国PCE / 核心PCE",
    "美国GDP",
    "美国零售销售",
    "美国ISM制造业PMI",
    "美国ISM服务业PMI",
}

SAFE_METRIC_MAP = {
    "美国CPI / 核心CPI": {
        "CPI环比": ("cpi", "MoM"),
        "CPI同比": ("cpi", "YoY"),
        "核心CPI环比": ("core-cpi", "MoM"),
        "核心CPI同比": ("core-cpi", "YoY"),
    },
    "美国非农 / 失业率 / 平均时薪": {
        "非农": ("nfp", "当月新增"),
        "失业率": ("unemployment", "失业率"),
        "时薪": ("earnings", "MoM"),
    },
    "美国零售销售": {
        "零售": ("retail-sales", "MoM"),
    },
    "美国PCE / 核心PCE": {
        "综合值": ("core-pce", "MoM"),
    },
    "美国GDP": {
        "综合值": ("real-gdp", "QoQ年化"),
    },
    "美国ISM制造业PMI": {
        "综合值": ("ism-manufacturing", "PMI"),
    },
    "美国ISM服务业PMI": {
        "综合值": ("ism-services", "PMI"),
    },
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def card_lookup(dashboard: dict) -> dict[str, dict]:
    return {
        card["id"]: card
        for group in dashboard.get("groups", [])
        for card in group.get("cards", [])
    }


def normalized_metrics(event: dict) -> list[dict]:
    metrics = event.get("metric_values")
    if isinstance(metrics, list):
        return [item for item in metrics if isinstance(item, dict)]
    return []


def event_fingerprint(event: dict) -> str:
    material = {
        "date": event.get("date"),
        "period": event.get("period"),
        "metrics": normalized_metrics(event),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_event(dashboard: dict, event: dict) -> int:
    title = event.get("title_cn", "")
    mapping = SAFE_METRIC_MAP.get(title, {})
    cards = card_lookup(dashboard)
    updates = 0
    touched_cards: set[str] = set()

    for metric in normalized_metrics(event):
        target = mapping.get(metric.get("label", ""))
        if not target:
            continue
        card_id, row_label = target
        card = cards.get(card_id)
        if not card:
            continue
        row = next((item for item in card.get("rows", []) if item.get("label") == row_label), None)
        if not row:
            continue
        for source_key, target_key in (
            ("actual", "actual"),
            ("forecast", "consensus"),
            ("previous", "previous"),
        ):
            value = metric.get(source_key)
            if value not in (None, "") and row.get(target_key) != value:
                row[target_key] = value
                updates += 1
        card["period"] = event.get("period") or card.get("period")
        card["releaseDate"] = event.get("date") or card.get("releaseDate")
        touched_cards.add(card_id)

    if updates:
        dashboard.setdefault("sourceEvents", {})[title] = event["date"]
        for card_id in touched_cards:
            cards[card_id]["trend"] = "新一期数据已写入，趋势结论等待完整官方口径复核。"
    return updates


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    calendar = load_json(args.calendar)
    dashboard = load_json(args.dashboard)
    source_events = dashboard.setdefault("sourceEvents", {})
    fingerprints = dashboard.setdefault("sourceEventFingerprints", {})

    candidates = [
        event
        for event in calendar
        if event.get("title_cn") in TRACKED_TITLES
        and event.get("release_status") == "released"
        and event.get("date")
        and (
            event.get("date") > source_events.get(event.get("title_cn"), "")
            or event_fingerprint(event) != fingerprints.get(event.get("title_cn"), "")
        )
    ]

    if not candidates:
        print("no new core U.S. macro release; dashboard unchanged")
        return 0

    updates = 0
    unsupported = []
    for event in sorted(candidates, key=lambda item: item["date"]):
        changed = apply_event(dashboard, event)
        updates += changed
        if changed:
            fingerprints[event.get("title_cn")] = event_fingerprint(event)
        if not changed:
            unsupported.append(event.get("title_cn"))

    if not updates:
        print("new release detected but no safe metric mapping; dashboard unchanged")
        return 0

    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()
    dashboard["generatedAt"] = now
    dashboard["asOf"] = max(
        card.get("releaseDate", "")
        for group in dashboard.get("groups", [])
        for card in group.get("cards", [])
    )
    quality = dashboard.setdefault("dataQuality", {})
    quality["fetchedAt"] = now
    if unsupported:
        warning = "以下新数据等待完整官方口径复核：" + "、".join(sorted(set(unsupported)))
        warnings = quality.setdefault("warnings", [])
        if warning not in warnings:
            warnings.append(warning)

    if args.dry_run:
        print(f"dry run: would update {updates} fields")
        return 0

    args.dashboard.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"updated {updates} dashboard fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
