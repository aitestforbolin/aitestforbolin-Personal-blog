#!/usr/bin/env python3
"""Atomically persist complete U.S. macro release bundles into the dashboard."""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALENDAR = ROOT / "data" / "us-macro-calendar.json"
DEFAULT_DASHBOARD = ROOT / "data" / "us-macro-dashboard.json"
DEFAULT_HISTORY = ROOT / "data" / "us-macro-history.json"

OFFICIAL_SOURCES = {
    "美国CPI / 核心CPI": ("BLS", "https://www.bls.gov/news.release/cpi.nr0.htm"),
    "美国PPI": ("BLS", "https://www.bls.gov/news.release/ppi.nr0.htm"),
    "美国非农 / 失业率 / 平均时薪": ("BLS", "https://www.bls.gov/news.release/empsit.nr0.htm"),
    "美国PCE / 核心PCE": ("BEA", "https://www.bea.gov/news/current-releases"),
    "美国GDP": ("BEA", "https://www.bea.gov/news/current-releases"),
    "美国零售销售": ("Census", "https://www.census.gov/retail/index.html"),
    "美国ISM制造业PMI": ("ISM", "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"),
    "美国ISM服务业PMI": ("ISM", "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"),
    "美国工业产出": ("Federal Reserve", "https://www.federalreserve.gov/releases/g17/current/"),
}

# Every target in a release must have an actual value before any target writes.
RELEASE_BUNDLES = {
    "美国CPI / 核心CPI": {"targets": {
        "CPI环比": ("cpi", "MoM"), "CPI同比": ("cpi", "YoY"),
        "核心CPI环比": ("core-cpi", "MoM"), "核心CPI同比": ("core-cpi", "YoY"),
    }},
    "美国PCE / 核心PCE": {"targets": {
        "PCE环比": ("pce", "MoM"), "PCE同比": ("pce", "YoY"),
        "核心PCE环比": ("core-pce", "MoM"), "核心PCE同比": ("core-pce", "YoY"),
        "实际PCE环比": ("real-pce", "MoM"),
    }, "optional_consensus": {"实际PCE环比"}},
    "美国PPI": {"targets": {
        "PPI环比": ("ppi", "Headline MoM"), "PPI同比": ("ppi", "Headline YoY"),
        "PPI剔除食品能源贸易服务环比": ("ppi", "Ex F/E/Trade MoM"),
        "PPI剔除食品能源贸易服务同比": ("ppi", "Ex F/E/Trade YoY"),
    }, "optional_consensus": {
        "PPI剔除食品能源贸易服务环比", "PPI剔除食品能源贸易服务同比",
    }},
    "美国非农 / 失业率 / 平均时薪": {"targets": {
        "非农": ("nfp", "当月新增"), "失业率": ("unemployment", "失业率"),
        "时薪环比": ("earnings", "MoM"), "时薪同比": ("earnings", "YoY"),
    }},
    "美国零售销售": {"targets": {
        "零售环比": ("retail-sales", "MoM"), "零售同比": ("retail-sales", "YoY"),
        "零售控制组环比": ("retail-control", "MoM"),
    }, "optional_consensus": {"零售同比"}},
    "美国ISM制造业PMI": {"targets": {"ISM制造业PMI": ("ism-manufacturing", "PMI")}},
    "美国ISM服务业PMI": {"targets": {"ISM服务业PMI": ("ism-services", "PMI")}},
    "美国工业产出": {"targets": {
        "工业产出环比": ("industrial-production", "MoM"),
        "工业产出同比": ("industrial-production", "YoY"),
    }, "optional_consensus": {"工业产出同比"}},
    "美国GDP": {"targets": {"GDP年化环比": ("real-gdp", "QoQ年化")}},
}

LABEL_ALIASES = {
    "美国非农 / 失业率 / 平均时薪": {"时薪": "时薪环比"},
    "美国零售销售": {"零售": "零售环比"},
    "美国PCE / 核心PCE": {"综合值": "核心PCE环比"},
    "美国GDP": {"综合值": "GDP年化环比"},
    "美国ISM制造业PMI": {"综合值": "ISM制造业PMI"},
    "美国ISM服务业PMI": {"综合值": "ISM服务业PMI"},
    "美国PPI": {"PPI": "PPI环比"},
}
ALLOWED_CONSENSUS_SOURCES = ("Reuters", "Investing.com")


def load_json(path: Path, default=None):
    if not path.exists() and default is not None:
        return deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def card_lookup(dashboard: dict) -> dict[str, dict]:
    return {card["id"]: card for group in dashboard.get("groups", []) for card in group.get("cards", [])}


def normalized_metrics(event: dict) -> list[dict]:
    metrics = event.get("metric_values")
    return [item for item in metrics if isinstance(item, dict)] if isinstance(metrics, list) else []


def canonical_metrics(event: dict) -> dict[str, dict]:
    aliases = LABEL_ALIASES.get(event.get("title_cn", ""), {})
    result = {}
    for metric in normalized_metrics(event):
        label = aliases.get(metric.get("label", ""), metric.get("label", ""))
        if label:
            result[label] = metric
    return result


def event_fingerprint(event: dict) -> str:
    material = {
        "date": event.get("date"), "period": event.get("period"),
        "metrics": canonical_metrics(event),
        "actual_source": event.get("actual_source"),
        "consensus_source": event.get("consensus_source"),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def parse_number(value) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).replace("%", "").replace("+", "").replace(",", "").strip()
    if text.lower().endswith("k"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def find_row(cards: dict[str, dict], card_id: str, label: str) -> dict | None:
    return next((row for row in cards.get(card_id, {}).get("rows", []) if row.get("label") == label), None)


def row_value(cards: dict[str, dict], card_id: str, label: str, field: str = "actual") -> float | None:
    row = find_row(cards, card_id, label)
    return parse_number(row.get(field)) if row else None


def source_name_allowed(name: str | None) -> bool:
    return bool(name) and any(str(name).startswith(prefix) for prefix in ALLOWED_CONSENSUS_SOURCES)


def metric_source(metric: dict, event: dict, kind: str) -> tuple[str | None, str | None]:
    return metric.get(f"{kind}_source") or event.get(f"{kind}_source"), metric.get(f"{kind}_url") or event.get(f"{kind}_url")


def validate_bundle(dashboard: dict, event: dict) -> tuple[bool, list[str]]:
    title = event.get("title_cn", "")
    bundle = RELEASE_BUNDLES.get(title)
    if not bundle:
        return False, ["unsupported release"]
    metrics, cards, problems = canonical_metrics(event), card_lookup(dashboard), []
    for label, (card_id, row_label) in bundle["targets"].items():
        metric = metrics.get(label)
        if not metric or metric.get("actual") in (None, ""):
            problems.append(f"{label}:actual")
            continue
        if not find_row(cards, card_id, row_label):
            problems.append(f"{label}:target")
        if label not in bundle.get("optional_consensus", set()):
            if metric.get("forecast") in (None, ""):
                problems.append(f"{label}:forecast")
            else:
                source, url = metric_source(metric, event, "consensus")
                if not source_name_allowed(source) or not str(url or "").startswith("https://"):
                    problems.append(f"{label}:consensus-source")
    return not problems, problems


def update_history(history: dict, event: dict, staged_rows: list[dict], fetched_at: str) -> None:
    observations = history.setdefault("observations", [])
    for item in staged_rows:
        observation = {
            "eventTitle": event["title_cn"], "cardId": item["card_id"], "rowLabel": item["row_label"],
            "period": event.get("period"), "releaseDate": event.get("date"),
            "actual": item["actual"], "consensus": item["consensus"], "previous": item["previous"],
            "actualSource": item["actual_source"], "actualUrl": item["actual_url"],
            "consensusSource": item["consensus_source"], "consensusUrl": item["consensus_url"],
            "fetchedAt": fetched_at,
        }
        key = observation["cardId"], observation["rowLabel"], observation["releaseDate"]
        observations[:] = [old for old in observations if (old.get("cardId"), old.get("rowLabel"), old.get("releaseDate")) != key]
        observations.append(observation)
    observations.sort(key=lambda item: (item.get("releaseDate") or "", item.get("cardId") or "", item.get("rowLabel") or ""))


def seed_history_from_dashboard(history: dict, dashboard: dict) -> None:
    """Use the currently displayed release as the first historical checkpoint."""
    observations = history.setdefault("observations", [])
    existing = {
        (item.get("cardId"), item.get("rowLabel"), item.get("releaseDate"))
        for item in observations
    }
    for group in dashboard.get("groups", []):
        for card in group.get("cards", []):
            release_date = card.get("releaseDate")
            if not release_date:
                continue
            consensus_source = (card.get("consensusSources") or [{}])[0]
            for row in card.get("rows", []):
                key = card.get("id"), row.get("label"), release_date
                if row.get("actual") in (None, "") or key in existing:
                    continue
                observations.append({
                    "eventTitle": None, "cardId": card.get("id"), "rowLabel": row.get("label"),
                    "period": card.get("period"), "releaseDate": release_date,
                    "actual": row.get("actual"), "consensus": row.get("consensus"), "previous": row.get("previous"),
                    "actualSource": card.get("source", {}).get("name"), "actualUrl": card.get("source", {}).get("url"),
                    "consensusSource": consensus_source.get("name"), "consensusUrl": consensus_source.get("url"),
                    "fetchedAt": dashboard.get("generatedAt"),
                })
                existing.add(key)
    observations.sort(key=lambda item: (item.get("releaseDate") or "", item.get("cardId") or "", item.get("rowLabel") or ""))


def trend_from_history(history: dict, card_id: str) -> str | None:
    by_release = {}
    for item in history.get("observations", []):
        if item.get("cardId") == card_id:
            value = parse_number(item.get("actual"))
            if value is not None:
                by_release[item.get("releaseDate", "")] = value
    values = sorted(by_release.items())[-6:]
    if len(values) < 3:
        return None
    first, last = values[0][1], values[-1][1]
    direction = "总体上行" if last > first else ("总体下行" if last < first else "总体持平")
    return f"最近{len(values)}期由{first:g}变为{last:g}，{direction}。"


def apply_complete_event(dashboard: dict, history: dict, event: dict, fetched_at: str) -> int:
    valid, problems = validate_bundle(dashboard, event)
    if not valid:
        print(f"skip incomplete {event.get('title_cn')}: {', '.join(problems)}")
        return 0
    title, cards = event["title_cn"], card_lookup(dashboard)
    bundle, metrics = RELEASE_BUNDLES[title], canonical_metrics(event)
    official_name, official_url = OFFICIAL_SOURCES[title]
    staged, touched, sources, consensus = [], set(), {}, {}
    for label, (card_id, row_label) in bundle["targets"].items():
        metric, row = metrics[label], find_row(cards, card_id, row_label)
        previous = metric.get("previous") if metric.get("previous") not in (None, "") else row.get("actual")
        actual_source, actual_url = metric_source(metric, event, "actual")
        actual_source, actual_url = actual_source or official_name, actual_url or official_url
        consensus_source, consensus_url = metric_source(metric, event, "consensus")
        staged.append({
            "card_id": card_id, "row_label": row_label, "actual": metric.get("actual"),
            "consensus": metric.get("forecast"), "previous": previous,
            "actual_source": actual_source, "actual_url": actual_url,
            "consensus_source": consensus_source, "consensus_url": consensus_url,
        })
        sources[card_id] = (actual_source, actual_url)
        if metric.get("forecast") not in (None, "") and source_name_allowed(consensus_source) and consensus_url:
            consensus.setdefault(card_id, {})[(consensus_source, consensus_url)] = None
        touched.add(card_id)

    # The write starts only after the whole release has passed validation.
    for item in staged:
        row = find_row(cards, item["card_id"], item["row_label"])
        row.update({"actual": item["actual"], "consensus": item["consensus"], "previous": item["previous"]})
    for card_id in touched:
        card = cards[card_id]
        card["period"], card["releaseDate"] = event.get("period") or card.get("period"), event["date"]
        card["source"] = {"name": sources[card_id][0], "url": sources[card_id][1]}
        card_sources = consensus.get(card_id, {})
        if card_sources:
            card["consensusSources"] = [{"name": name, "url": url} for name, url in card_sources]
        else:
            card.pop("consensusSources", None)

    update_history(history, event, staged, fetched_at)
    for card_id in touched:
        cards[card_id]["trend"] = trend_from_history(history, card_id) or "新一期完整数据已写入；积累满3期后显示中期趋势。"
    dashboard.setdefault("sourceEvents", {})[title] = event["date"]
    dashboard.setdefault("sourceEventFingerprints", {})[title] = event_fingerprint(event)
    return len(staged)


def refresh_summary(dashboard: dict) -> None:
    cards = card_lookup(dashboard)
    summary = {item.get("id"): item for item in dashboard.get("summary", [])}
    core_cpi, old_cpi = row_value(cards, "core-cpi", "YoY"), row_value(cards, "core-cpi", "YoY", "previous")
    core_pce, old_pce = row_value(cards, "core-pce", "YoY"), row_value(cards, "core-pce", "YoY", "previous")
    ppi, inflation = row_value(cards, "ppi", "Headline YoY"), summary.get("inflation")
    if inflation and None not in (core_cpi, old_cpi, core_pce, old_pce, ppi):
        cooling = core_cpi <= old_cpi and core_pce <= old_pce
        inflation.update({
            "state": ("仍偏高，" if max(core_cpi, core_pce) > 2 else "") + ("边际降温" if cooling else "压力回升"),
            "tone": "cooling" if cooling else "weakening",
            "detail": f"核心CPI同比{core_cpi:.1f}%，核心PCE同比{core_pce:.1f}%，PPI同比{ppi:.1f}%。",
        })
    nfp, unemployment, earnings = row_value(cards, "nfp", "当月新增"), row_value(cards, "unemployment", "失业率"), row_value(cards, "earnings", "YoY")
    employment = summary.get("employment")
    if employment and None not in (nfp, unemployment, earnings):
        employment.update({
            "state": "明显降温" if nfp < 50 else ("温和降温" if nfp < 150 else "保持韧性"),
            "tone": "weakening" if nfp < 150 else "expanding",
            "detail": f"当月非农{nfp:+.0f}k，失业率{unemployment:.1f}%，工资同比{earnings:.1f}%。",
        })
    retail, real_pce, consumption = row_value(cards, "retail-sales", "MoM"), row_value(cards, "real-pce", "MoM"), summary.get("consumption")
    if consumption and None not in (retail, real_pce):
        state, tone = (("明显转弱", "weakening") if retail < 0 and real_pce < 0 else (("分化转弱", "weakening") if retail < 0 else ("仍有韧性", "expanding")))
        consumption.update({"state": state, "tone": tone, "detail": f"零售销售环比{retail:+.1f}%，Real PCE环比{real_pce:+.1f}%。"})
    manufacturing, services = row_value(cards, "ism-manufacturing", "PMI"), row_value(cards, "ism-services", "PMI")
    production, activity = row_value(cards, "industrial-production", "MoM"), summary.get("activity")
    if activity and None not in (manufacturing, services, production):
        if manufacturing >= 50 and services >= 50 and production >= 0:
            state, tone = "保持扩张", "expanding"
        elif manufacturing < 50 and services < 50 and production < 0:
            state, tone = "转向收缩", "weakening"
        else:
            state, tone = "扩张放缓", "cooling"
        activity.update({"state": state, "tone": tone, "detail": f"制造业ISM {manufacturing:.1f}，服务业ISM {services:.1f}，工业产出环比{production:+.1f}%。"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    calendar, dashboard = load_json(args.calendar), load_json(args.dashboard)
    history = load_json(args.history, {"schemaVersion": "1.0", "observations": []})
    seed_history_from_dashboard(history, dashboard)
    source_events = dashboard.setdefault("sourceEvents", {})
    fingerprints = dashboard.setdefault("sourceEventFingerprints", {})
    candidates = [event for event in calendar if event.get("title_cn") in RELEASE_BUNDLES
                  and event.get("release_status") == "released" and event.get("date")
                  and (event.get("date") > source_events.get(event.get("title_cn"), "")
                       or (fingerprints.get(event.get("title_cn"))
                           and event_fingerprint(event) != fingerprints.get(event.get("title_cn"))))]
    if not candidates:
        print("no new core U.S. macro release; dashboard unchanged")
        return 0
    now = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()
    updates = sum(apply_complete_event(dashboard, history, event, now) for event in sorted(candidates, key=lambda item: item["date"]))
    if not updates:
        print("new release detected but no complete publishable bundle; dashboard unchanged")
        return 0
    refresh_summary(dashboard)
    dashboard["generatedAt"] = now
    dashboard["asOf"] = max(card.get("releaseDate", "") for group in dashboard.get("groups", []) for card in group.get("cards", []))
    dashboard.setdefault("dataQuality", {})["fetchedAt"] = now
    if args.dry_run:
        print(f"dry run: would atomically update {updates} rows")
        return 0
    atomic_write_json(args.dashboard, dashboard)
    atomic_write_json(args.history, history)
    print(f"updated {updates} dashboard rows from complete release bundles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
