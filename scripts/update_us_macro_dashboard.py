#!/usr/bin/env python3
"""Build the U.S. macro dashboard from released Forex Factory calendar data."""

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
FOREX_FACTORY = "Forex Factory"
FOREX_FACTORY_URL = "https://www.forexfactory.com/calendar"

# Limited to fields already emitted by the Forex Factory calendar adapter. A
# missing Actual never blocks another metric from the same release.
EVENT_TARGETS = {
    "美国CPI / 核心CPI": {
        "CPI环比": ("cpi", "MoM"), "CPI同比": ("cpi", "YoY"),
        "核心CPI环比": ("core-cpi", "MoM"), "核心CPI同比": ("core-cpi", "YoY"),
    },
    "美国PPI": {
        "PPI环比": ("ppi", "MoM"), "PPI同比": ("ppi", "YoY"),
        "核心PPI环比": ("core-ppi", "MoM"), "核心PPI同比": ("core-ppi", "YoY"),
    },
    "美国PCE / 核心PCE": {
        "核心PCE环比": ("core-pce", "MoM"), "核心PCE同比": ("core-pce", "YoY"),
        "实际PCE环比": ("personal-spending", "MoM"),
    },
    "美国非农 / 失业率 / 平均时薪": {
        "非农": ("nfp", "Non-Farm Employment Change"), "失业率": ("unemployment", "Unemployment Rate"),
        "时薪环比": ("earnings", "MoM"), "时薪同比": ("earnings", "YoY"),
    },
    "美国零售销售": {
        "零售环比": ("retail-sales", "Retail Sales m/m"),
        "核心零售环比": ("core-retail-sales", "Core Retail Sales m/m"),
    },
    "美国GDP": {"GDP年化环比": ("real-gdp", "GDP q/q")},
    "美国ISM制造业PMI": {"ISM制造业PMI": ("ism-manufacturing", "ISM Manufacturing PMI")},
    "美国ISM服务业PMI": {"ISM服务业PMI": ("ism-services", "ISM Services PMI")},
    "美国工业产出": {"工业产出环比": ("industrial-production", "Industrial Production m/m")},
}

LAYOUT = [
    ("inflation", "01", "通胀", "以 Forex Factory 公布的消费价格、生产价格与核心PCE判断通胀方向。", [
        ("cpi", "CPI", ["MoM", "YoY"]), ("core-cpi", "Core CPI", ["MoM", "YoY"]),
        ("ppi", "PPI", ["MoM", "YoY"]), ("core-ppi", "Core PPI", ["MoM", "YoY"]),
        ("core-pce", "Core PCE", ["MoM", "YoY"]),
    ]),
    ("employment", "02", "就业", "用非农、失业率与平均时薪观察劳动力市场。", [
        ("nfp", "Non-Farm Employment Change", ["Non-Farm Employment Change"]),
        ("unemployment", "Unemployment Rate", ["Unemployment Rate"]),
        ("earnings", "Average Hourly Earnings", ["MoM", "YoY"]),
    ]),
    ("consumption", "03", "消费", "只保留 Forex Factory 稳定提供的零售与个人消费字段。", [
        ("retail-sales", "Retail Sales", ["Retail Sales m/m"]),
        ("core-retail-sales", "Core Retail Sales", ["Core Retail Sales m/m"]),
        ("personal-spending", "Personal Spending", ["MoM"]),
    ]),
    ("activity", "04", "经济活动", "用GDP、ISM与工业产出确认经济活动的方向。", [
        ("real-gdp", "GDP", ["GDP q/q"]),
        ("ism-manufacturing", "ISM Manufacturing PMI", ["ISM Manufacturing PMI"]),
        ("ism-services", "ISM Services PMI", ["ISM Services PMI"]),
        ("industrial-production", "Industrial Production", ["Industrial Production m/m"]),
    ]),
]


def load_json(path: Path, default=None):
    if not path.exists() and default is not None:
        return deepcopy(default)
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_number(value) -> float | None:
    if value in (None, ""):
        return None
    value = str(value).replace("%", "").replace("+", "").replace(",", "").strip()
    if value.lower().endswith("k"):
        value = value[:-1]
    try:
        return float(value)
    except ValueError:
        return None


def card_lookup(dashboard: dict) -> dict[str, dict]:
    return {card["id"]: card for group in dashboard.get("groups", []) for card in group.get("cards", [])}


def make_dashboard() -> dict:
    groups = []
    for group_id, number, title, description, cards in LAYOUT:
        groups.append({
            "id": group_id, "number": number, "title": title, "description": description,
            "cards": [{
                "id": card_id, "title": card_title, "period": None, "releaseDate": None,
                "updatedAt": None, "source": FOREX_FACTORY, "sourceUrl": FOREX_FACTORY_URL,
                "rows": [{"label": label, "actual": None, "forecast": None, "previous": None} for label in rows],
                "trend": "等待 Forex Factory 的已发布数据。",
            } for card_id, card_title, rows in cards],
        })
    return {
        "schemaVersion": "2.0", "generatedAt": None, "asOf": None, "title": "美国宏观核心数据",
        "summary": [
            {"id": "inflation", "label": "通胀", "state": "等待最新发布", "tone": "cooling", "detail": "仅使用 Forex Factory 已发布值。"},
            {"id": "employment", "label": "就业", "state": "等待最新发布", "tone": "cooling", "detail": "仅使用 Forex Factory 已发布值。"},
            {"id": "consumption", "label": "消费", "state": "等待最新发布", "tone": "cooling", "detail": "仅使用 Forex Factory 已发布值。"},
            {"id": "activity", "label": "经济活动", "state": "等待最新发布", "tone": "cooling", "detail": "仅使用 Forex Factory 已发布值。"},
        ],
        "groups": groups, "sourceEvents": {}, "sourceEventFingerprints": {},
        "dataQuality": {
            "status": "forex_factory_only",
            "warnings": ["只写入 release_status=released 且 actual 非空的 Forex Factory 数据。", "没有当前已发布值的字段会等待下一次对应数据发布。"],
            "fetchedAt": None, "source": FOREX_FACTORY,
        },
    }


def normalize_dashboard(existing: dict) -> tuple[dict, bool]:
    """Migrate the old official-source layout once; later runs preserve FF values."""
    if existing.get("schemaVersion") == "2.0":
        return existing, False
    return make_dashboard(), True


def find_row(card: dict | None, label: str) -> dict | None:
    return next((row for row in (card or {}).get("rows", []) if row.get("label") == label), None)


def metric_fingerprint(event: dict) -> str:
    material = {"date": event.get("date"), "period": event.get("period"), "metrics": event.get("metric_values", []), "released_at": event.get("released_at")}
    return hashlib.sha256(json.dumps(material, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def upsert_history(history: dict, event: dict, card_id: str, row_label: str, metric: dict, fetched_at: str) -> None:
    observations = history.setdefault("observations", [])
    observation = {
        "eventTitle": event.get("title_cn"), "cardId": card_id, "rowLabel": row_label,
        "period": event.get("period"), "releaseDate": event.get("date"),
        "actual": metric.get("actual"), "forecast": metric.get("forecast"), "previous": metric.get("previous"),
        "source": FOREX_FACTORY, "sourceUrl": metric.get("actual_url") or event.get("result_url") or event.get("url") or FOREX_FACTORY_URL,
        "updatedAt": fetched_at,
    }
    key = card_id, row_label, event.get("date")
    observations[:] = [item for item in observations if (item.get("cardId"), item.get("rowLabel"), item.get("releaseDate")) != key]
    observations.append(observation)
    observations.sort(key=lambda item: (item.get("releaseDate") or "", item.get("cardId") or "", item.get("rowLabel") or ""))


def trend_from_history(history: dict, card_id: str, row_label: str) -> str:
    values = {}
    for item in history.get("observations", []):
        if item.get("source") == FOREX_FACTORY and item.get("cardId") == card_id and item.get("rowLabel") == row_label:
            value = parse_number(item.get("actual"))
            if value is not None:
                values[item.get("releaseDate") or ""] = value
    series = sorted(values.items())[-6:]
    if len(series) < 3:
        return "已写入最新一期；积累满3期后显示中期趋势。"
    first, last = series[0][1], series[-1][1]
    direction = "总体上行" if last > first else ("总体下行" if last < first else "总体持平")
    return f"最近{len(series)}期由{first:g}变为{last:g}，{direction}。"


def apply_released_event(dashboard: dict, history: dict, event: dict, fetched_at: str) -> int:
    targets = EVENT_TARGETS.get(event.get("title_cn"), {})
    if event.get("release_status") != "released" or not targets:
        return 0
    cards, updates = card_lookup(dashboard), 0
    for metric in event.get("metric_values", []):
        if not isinstance(metric, dict) or metric.get("actual") in (None, ""):
            continue
        target = targets.get(metric.get("label"))
        if not target:
            continue
        card_id, row_label = target
        card, row = cards.get(card_id), find_row(cards.get(card_id), row_label)
        if not row or (card.get("releaseDate") and event.get("date", "") < card["releaseDate"]):
            continue
        changed = any(row.get(field) != metric.get(field) for field in ("actual", "forecast", "previous")) or card.get("releaseDate") != event.get("date")
        row.update({"actual": metric.get("actual"), "forecast": metric.get("forecast"), "previous": metric.get("previous")})
        card.update({"period": event.get("period"), "releaseDate": event.get("date"), "updatedAt": fetched_at, "source": FOREX_FACTORY, "sourceUrl": metric.get("actual_url") or event.get("result_url") or event.get("url") or FOREX_FACTORY_URL})
        upsert_history(history, event, card_id, row_label, metric, fetched_at)
        if changed:
            updates += 1
    if updates:
        dashboard.setdefault("sourceEvents", {})[event["title_cn"]] = event.get("date")
        dashboard.setdefault("sourceEventFingerprints", {})[event["title_cn"]] = metric_fingerprint(event)
    return updates


def row_value(cards: dict[str, dict], card_id: str, label: str, field: str = "actual") -> float | None:
    row = find_row(cards.get(card_id), label)
    return parse_number(row.get(field)) if row else None


def refresh_summary(dashboard: dict) -> None:
    cards, summary = card_lookup(dashboard), {item["id"]: item for item in dashboard["summary"]}
    available = [("核心CPI同比", row_value(cards, "core-cpi", "YoY")), ("核心PCE同比", row_value(cards, "core-pce", "YoY")), ("PPI同比", row_value(cards, "ppi", "YoY"))]
    values = [(label, value) for label, value in available if value is not None]
    if values:
        peak = max(value for _, value in values)
        summary["inflation"].update({"state": "压力偏高" if peak > 2 else "接近目标", "tone": "weakening" if peak > 2 else "cooling", "detail": "，".join(f"{label}{value:.1f}%" for label, value in values) + "。"})

    nfp, unemployment, earnings = row_value(cards, "nfp", "Non-Farm Employment Change"), row_value(cards, "unemployment", "Unemployment Rate"), row_value(cards, "earnings", "YoY")
    values = [("非农", nfp, "k"), ("失业率", unemployment, "%"), ("时薪同比", earnings, "%")]
    present = [(label, value, suffix) for label, value, suffix in values if value is not None]
    if present:
        state = "保持韧性" if nfp is not None and nfp >= 150 else "温和降温"
        summary["employment"].update({"state": state, "tone": "expanding" if state == "保持韧性" else "cooling", "detail": "，".join(f"{label}{value:+.0f}{suffix}" if label == "非农" else f"{label}{value:.1f}{suffix}" for label, value, suffix in present) + "。"})

    values = [("零售环比", row_value(cards, "retail-sales", "Retail Sales m/m")), ("核心零售环比", row_value(cards, "core-retail-sales", "Core Retail Sales m/m"))]
    present = [(label, value) for label, value in values if value is not None]
    if present:
        state = "消费回升" if all(value >= 0 for _, value in present) else "消费走弱"
        summary["consumption"].update({"state": state, "tone": "expanding" if state == "消费回升" else "weakening", "detail": "，".join(f"{label}{value:+.1f}%" for label, value in present) + "。"})

    manufacturing, services, production = row_value(cards, "ism-manufacturing", "ISM Manufacturing PMI"), row_value(cards, "ism-services", "ISM Services PMI"), row_value(cards, "industrial-production", "Industrial Production m/m")
    values = [("制造业ISM", manufacturing, ""), ("服务业ISM", services, ""), ("工业产出环比", production, "%")]
    present = [(label, value, suffix) for label, value, suffix in values if value is not None]
    if present:
        expanding = all(value >= 50 for _, value, suffix in present if not suffix) and (production is None or production >= 0)
        summary["activity"].update({"state": "保持扩张" if expanding else "动能分化", "tone": "expanding" if expanding else "cooling", "detail": "，".join(f"{label}{value:+.1f}{suffix}" for label, value, suffix in present) + "。"})


def refresh_trends(dashboard: dict, history: dict) -> None:
    for card in card_lookup(dashboard).values():
        primary = next((row for row in card.get("rows", []) if row.get("actual") not in (None, "")), None)
        if primary:
            card["trend"] = trend_from_history(history, card["id"], primary["label"])


def derived_state(dashboard: dict) -> str:
    """Serialize fields calculated from cards/history, excluding run timestamps."""
    payload = {
        "summary": dashboard.get("summary", []),
        "trends": {card["id"]: card.get("trend") for card in card_lookup(dashboard).values()},
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    parser.add_argument("--dashboard", type=Path, default=DEFAULT_DASHBOARD)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    calendar = load_json(args.calendar)
    if not isinstance(calendar, list):
        raise ValueError("Forex Factory calendar must be an array")
    dashboard, migrated = normalize_dashboard(load_json(args.dashboard, {}))
    history = load_json(args.history, {"schemaVersion": "1.0", "observations": []})
    fetched_at = datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()
    updates = sum(apply_released_event(dashboard, history, event, fetched_at) for event in sorted(calendar, key=lambda item: item.get("date", "")) if isinstance(event, dict))
    before_derived_state = derived_state(dashboard)
    refresh_trends(dashboard, history)
    refresh_summary(dashboard)
    derived_changed = derived_state(dashboard) != before_derived_state
    if not updates and not migrated and not derived_changed:
        print("no new released Forex Factory macro values; dashboard unchanged")
        return 0
    dates = [card.get("releaseDate") for card in card_lookup(dashboard).values() if card.get("releaseDate")]
    dashboard["generatedAt"], dashboard["asOf"] = fetched_at, max(dates) if dates else None
    dashboard["dataQuality"]["fetchedAt"] = fetched_at
    if args.dry_run:
        print(f"dry run: would update {updates} Forex Factory dashboard rows")
        return 0
    atomic_write_json(args.dashboard, dashboard)
    atomic_write_json(args.history, history)
    print(f"updated {updates} dashboard rows from released Forex Factory values")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
