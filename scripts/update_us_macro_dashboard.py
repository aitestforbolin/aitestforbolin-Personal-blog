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


def parse_number(value) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).replace("%", "").replace("+", "").replace(",", "").strip()
    multiplier = 1.0
    if text.lower().endswith("k"):
        multiplier = 1.0
        text = text[:-1]
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def row_value(cards: dict[str, dict], card_id: str, label: str, field: str = "actual") -> float | None:
    card = cards.get(card_id, {})
    row = next((item for item in card.get("rows", []) if item.get("label") == label), None)
    return parse_number(row.get(field)) if row else None


def refresh_summary(dashboard: dict) -> None:
    cards = card_lookup(dashboard)
    summary = {item.get("id"): item for item in dashboard.get("summary", [])}

    core_cpi = row_value(cards, "core-cpi", "YoY")
    core_cpi_previous = row_value(cards, "core-cpi", "YoY", "previous")
    core_pce = row_value(cards, "core-pce", "YoY")
    core_pce_previous = row_value(cards, "core-pce", "YoY", "previous")
    ppi = row_value(cards, "ppi", "Headline YoY")
    inflation = summary.get("inflation")
    if inflation and None not in (core_cpi, core_cpi_previous, core_pce, core_pce_previous):
        cooling = core_cpi <= core_cpi_previous and core_pce <= core_pce_previous
        elevated = max(core_cpi, core_pce) > 2.0
        inflation["state"] = ("仍偏高，" if elevated else "") + ("边际降温" if cooling else "压力回升")
        inflation["tone"] = "cooling" if cooling else "weakening"
        inflation["detail"] = f"核心CPI同比{core_cpi:.1f}%，核心PCE同比{core_pce:.1f}%，PPI同比{ppi:.1f}%。"

    nfp = row_value(cards, "nfp", "当月新增")
    unemployment = row_value(cards, "unemployment", "失业率")
    earnings = row_value(cards, "earnings", "YoY")
    employment = summary.get("employment")
    if employment and nfp is not None:
        employment["state"] = "明显降温" if nfp < 50 else ("温和降温" if nfp < 150 else "保持韧性")
        employment["tone"] = "weakening" if nfp < 150 else "expanding"
        employment["detail"] = f"当月非农{nfp:+.0f}k，失业率{unemployment:.1f}%，工资同比{earnings:.1f}%。"

    retail = row_value(cards, "retail-sales", "MoM")
    real_pce = row_value(cards, "real-pce", "MoM")
    consumption = summary.get("consumption")
    if consumption and None not in (retail, real_pce):
        if retail < 0 and real_pce < 0:
            state, tone = "明显转弱", "weakening"
        elif retail < 0:
            state, tone = "分化转弱", "weakening"
        else:
            state, tone = "仍有韧性", "expanding"
        consumption["state"] = state
        consumption["tone"] = tone
        consumption["detail"] = f"零售销售环比{retail:+.1f}%，Real PCE环比{real_pce:+.1f}%。"

    manufacturing = row_value(cards, "ism-manufacturing", "PMI")
    services = row_value(cards, "ism-services", "PMI")
    production = row_value(cards, "industrial-production", "MoM")
    activity = summary.get("activity")
    if activity and None not in (manufacturing, services, production):
        if manufacturing >= 50 and services >= 50 and production >= 0:
            state, tone = "保持扩张", "expanding"
        elif manufacturing < 50 and services < 50 and production < 0:
            state, tone = "转向收缩", "weakening"
        else:
            state, tone = "扩张放缓", "cooling"
        activity["state"] = state
        activity["tone"] = tone
        activity["detail"] = f"制造业ISM {manufacturing:.1f}，服务业ISM {services:.1f}，工业产出环比{production:+.1f}%。"


def apply_event(dashboard: dict, event: dict) -> int:
    title = event.get("title_cn", "")
    mapping = SAFE_METRIC_MAP.get(title, {})
    cards = card_lookup(dashboard)
    updates = 0
    touched_cards: set[str] = set()
    forecast_cards: set[str] = set()

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
            if source_key == "forecast" and value not in (None, ""):
                forecast_cards.add(card_id)
        card["period"] = event.get("period") or card.get("period")
        card["releaseDate"] = event.get("date") or card.get("releaseDate")
        touched_cards.add(card_id)

    if updates:
        dashboard.setdefault("sourceEvents", {})[title] = event["date"]
        consensus_name = event.get("consensus_source") or event.get("result_source")
        consensus_url = event.get("consensus_url") or event.get("result_url")
        for card_id in forecast_cards:
            if consensus_name and consensus_url:
                cards[card_id]["consensusSources"] = [
                    {"name": consensus_name, "url": consensus_url}
                ]
            else:
                cards[card_id].pop("consensusSources", None)
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
    refresh_summary(dashboard)
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
