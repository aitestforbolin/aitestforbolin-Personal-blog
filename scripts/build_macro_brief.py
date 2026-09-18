#!/usr/bin/env python3
"""Build a pre-release Macro Brief for selected U.S. macro events."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from fomc import fedwatch_is_publishable
except ModuleNotFoundError:
    from scripts.fomc import fedwatch_is_publishable


ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_CALENDAR = ROOT / "data" / "macro-calendar.json"
DEFAULT_MARKETS = ROOT / "data" / "market-prices.json"
DEFAULT_DAILY = ROOT / "data" / "daily-market-status.json"
DEFAULT_OUTPUT = ROOT / "data" / "macro-brief.json"
DEFAULT_STATE = ROOT / "data" / "macro-brief-state.json"

BRIEF_WHITELIST = {"CPI", "PPI", "PCE", "NFP", "Retail", "FOMC"}
DEFAULT_CAPTURE_MINUTES = 60
DEFAULT_TARGET_MINUTES = 25
DEFAULT_MAX_WAIT_SECONDS = 35 * 60
WATCH_POINTS = {
    "CPI": ["核心CPI环比是否偏离预期", "核心通胀与整体通胀是否同向", "美元和短端美债是否重新定价利率路径"],
    "PPI": ["核心PPI是否显示上游价格压力", "能源与商品价格是否推高整体数据", "市场是否把变化传导到未来CPI预期"],
    "PCE": ["核心PCE环比是否偏离预期", "消费支出是否仍具韧性", "FedWatch与短端收益率是否同步变化"],
    "NFP": ["新增就业是否偏离预期", "失业率与平均时薪是否给出相反信号", "前值修正是否改变就业趋势"],
    "Retail": ["整体零售与核心零售是否同向", "消费韧性是否强化更高利率预期", "美元、黄金与BTC是否出现一致反应"],
    "FOMC": ["实际利率决定是否符合预期", "声明和经济预测是否改变后续路径", "发布会措辞是否比决定本身更鹰或更鸽"],
}


def load_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def parse_now(value: str | None) -> datetime:
    if not value:
        return datetime.now(SHANGHAI)
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI)
    return parsed.astimezone(SHANGHAI)


def event_key(event: dict) -> str | None:
    legacy = event.get("legacy") if isinstance(event.get("legacy"), dict) else {}
    value = legacy.get("title")
    return value if value in BRIEF_WHITELIST else None


def select_event(events: list[dict], now: datetime, minimum: int, maximum: int, force_next: bool = False):
    candidates = []
    for event in events:
        key = event_key(event)
        scheduled = event.get("scheduledAt")
        if not key or not isinstance(scheduled, str):
            continue
        try:
            moment = datetime.fromisoformat(scheduled).astimezone(SHANGHAI)
        except ValueError:
            continue
        minutes = (moment - now).total_seconds() / 60
        if (force_next and minutes > 0) or minimum <= minutes <= maximum:
            candidates.append((moment, event, key, minutes))
    return min(candidates, key=lambda row: row[0]) if candidates else None


def select_next_eligible_event(events: list[dict], now: datetime):
    """Return the next whitelisted event after *now*, regardless of its window."""
    candidates = []
    for event in events:
        key = event_key(event)
        scheduled = event.get("scheduledAt")
        if not key or not isinstance(scheduled, str):
            continue
        try:
            moment = datetime.fromisoformat(scheduled).astimezone(SHANGHAI)
        except ValueError:
            continue
        minutes = (moment - now).total_seconds() / 60
        if minutes > 0:
            candidates.append((moment, event, key, minutes))
    return min(candidates, key=lambda row: row[0]) if candidates else None


def select_most_recent_eligible_event(events: list[dict], now: datetime):
    """Return the latest whitelisted event at or before *now* for expiry logging."""
    candidates = []
    for event in events:
        key = event_key(event)
        scheduled = event.get("scheduledAt")
        if not key or not isinstance(scheduled, str):
            continue
        try:
            moment = datetime.fromisoformat(scheduled).astimezone(SHANGHAI)
        except ValueError:
            continue
        minutes = (moment - now).total_seconds() / 60
        if minutes <= 0:
            candidates.append((moment, event, key, minutes))
    return max(candidates, key=lambda row: row[0]) if candidates else None


def decide_event_action(
    minutes_until_release: float,
    minimum: int,
    maximum: int,
    capture_minutes: int = DEFAULT_CAPTURE_MINUTES,
    target_minutes: int = DEFAULT_TARGET_MINUTES,
    max_wait_seconds: int = DEFAULT_MAX_WAIT_SECONDS,
) -> tuple[str, int]:
    """Classify one event without side effects and return (action, wait_seconds)."""
    if minutes_until_release <= 0:
        return "expired", 0
    if minimum <= minutes_until_release <= maximum:
        return "generate", 0
    if maximum < minutes_until_release <= capture_minutes:
        wait_seconds = round((minutes_until_release - target_minutes) * 60)
        return "wait", max(0, min(wait_seconds, max_wait_seconds))
    return "too_early", 0


def plan_next_event(
    events: list[dict],
    now: datetime,
    state: dict,
    minimum: int,
    maximum: int,
    capture_minutes: int = DEFAULT_CAPTURE_MINUTES,
    target_minutes: int = DEFAULT_TARGET_MINUTES,
    max_wait_seconds: int = DEFAULT_MAX_WAIT_SECONDS,
    force_next: bool = False,
) -> dict:
    """Plan one Macro Brief run without writing a brief or changing state."""
    selected = select_next_eligible_event(events, now)
    if not selected:
        expired = select_most_recent_eligible_event(events, now)
        if expired:
            scheduled, event, key, minutes = expired
            return {
                "action": "expired",
                "selected": expired,
                "event": event,
                "key": key,
                "scheduled": scheduled,
                "minutesUntilRelease": minutes,
                "waitSeconds": 0,
                "targetAt": None,
            }
        return {"action": "no_eligible_event", "selected": None, "waitSeconds": 0}
    scheduled, event, key, minutes = selected
    if force_next:
        action, wait_seconds = "generate", 0
    else:
        action, wait_seconds = decide_event_action(
            minutes, minimum, maximum, capture_minutes, target_minutes, max_wait_seconds
        )
        if action == "generate" and state.get("lastEventId") == event.get("id"):
            action = "already_sent"
    return {
        "action": action,
        "selected": selected,
        "event": event,
        "key": key,
        "scheduled": scheduled,
        "minutesUntilRelease": minutes,
        "waitSeconds": wait_seconds,
        "targetAt": scheduled.replace(microsecond=0) - timedelta(minutes=target_minutes),
    }


def metric_rows(event: dict) -> list[dict]:
    result = []
    for metric in event.get("metrics", []):
        if not isinstance(metric, dict):
            continue
        forecast, previous = metric.get("forecast"), metric.get("previous")
        if forecast in (None, "") and previous in (None, ""):
            continue
        result.append({
            "label": metric.get("label") or "综合值",
            "forecast": forecast,
            "previous": previous,
            "source": event.get("source"),
            "sourceUrl": metric.get("sourceUrl") or event.get("sourceUrl"),
        })
    return result


def market_snapshot(payload: dict, symbol: str, label: str, unit: str) -> dict:
    row = next((item for item in payload.get("symbols", []) if item.get("symbol") == symbol), None)
    if not row:
        return {"id": symbol, "label": label, "status": "unavailable"}
    value = row.get("close")
    previous = row.get("previousClose", row.get("open"))
    change_percent = None
    if isinstance(value, (int, float)) and isinstance(previous, (int, float)) and previous:
        change_percent = (value - previous) / previous * 100
    return {
        "id": symbol,
        "label": label,
        "value": value,
        "previous": previous,
        "changePercent": change_percent,
        "unit": unit,
        "asOf": " ".join(part for part in (str(row.get("date") or ""), str(row.get("time") or "")) if part),
        "source": row.get("source") or payload.get("source") or "Yahoo Finance",
        "sourceSymbol": row.get("sourceSymbol"),
        "status": "available" if isinstance(value, (int, float)) else "unavailable",
    }


def treasury_snapshot(daily: dict) -> list[dict]:
    anchors = {row.get("id"): row for row in daily.get("macroAnchors", []) if isinstance(row, dict)}
    result = []
    for asset_id, label in (("US02Y", "美国2年期收益率"), ("US10Y", "美国10年期收益率"), ("US30Y", "美国30年期收益率")):
        row = anchors.get(asset_id)
        if not row:
            result.append({"id": asset_id, "label": label, "status": "unavailable", "note": "非盘中数据"})
            continue
        status_text = str(row.get("status") or "")
        as_of = status_text.rsplit("→", 1)[-1].strip() if "→" in status_text else str(daily.get("asOf") or "")
        result.append({
            "id": asset_id,
            "label": label,
            "value": row.get("latest", row.get("anchor")),
            "previous": row.get("previous"),
            "unit": "%",
            "asOf": as_of,
            "source": row.get("provider") or "U.S. Treasury",
            "status": "available" if isinstance(row.get("latest", row.get("anchor")), (int, float)) else "unavailable",
            "note": "美国财政部最近日值，非盘中数据",
        })
    return result


def fed_snapshot(daily: dict) -> dict:
    row = daily.get("fedProbability")
    now = datetime.now(tz=ZoneInfo("Asia/Shanghai"))
    if not fedwatch_is_publishable(row, now):
        reason = row.get("reason") if isinstance(row, dict) else None
        return {"label": "下一次 FOMC 概率：数据核验中", "status": "unavailable",
                "note": reason or "FedWatch 暂不可用 / 数据核验中；未沿用已结束会议的数据"}
    probabilities = row["probabilities"]
    primary = next((item for item in probabilities.values() if isinstance(item, dict) and isinstance(item.get("current"), (int, float))), None)
    if not primary:
        return {"status": "unavailable", "note": "FedWatch 暂不可用 / 数据核验中"}
    return {
        "label": f"{row.get('meetingLabel') or '下一次 FOMC'} {primary.get('label') or '概率'}",
        "value": primary.get("current"),
        "previous": primary.get("previous"),
        "unit": row.get("unit") or "%",
        "asOf": row.get("checkedAt") or daily.get("publishedAt") or daily.get("asOf"),
        "source": row.get("source") or "每日市场早报",
        "sourceUrl": row.get("sourceUrl"),
        "status": "available",
        "note": "已核验下一场尚未结束的 FOMC 会议；不代表事件前即时概率",
    }


def format_value(value, unit="") -> str:
    if value in (None, ""):
        return "暂不可用"
    if isinstance(value, float):
        text = f"{value:,.3f}".rstrip("0").rstrip(".")
    elif isinstance(value, int):
        text = f"{value:,}"
    else:
        text = str(value)
    return text if not unit or unit in text else f"{text}{unit}"


def build_copy_text(payload: dict) -> str:
    event = payload["event"]
    lines = [f"【Macro Brief】{event['title']}", f"公布时间：{event['scheduledAtLabel']}", "", "市场预期："]
    for row in event["metrics"]:
        lines.append(f"- {row['label']}：预期 {format_value(row.get('forecast'))}；前值 {format_value(row.get('previous'))}")
    lines.extend(["", "当前市场："])
    for row in payload["market"]["assets"]:
        lines.append(f"- {row['label']}：{format_value(row.get('value'), row.get('unit', ''))}（{row.get('asOf') or '更新时间未知'}）")
    lines.extend(["", "美债（最近官方日值，非盘中）："])
    for row in payload["market"]["treasuries"]:
        lines.append(f"- {row['label']}：{format_value(row.get('value'), row.get('unit', ''))}")
    fed = payload["market"]["fedWatch"]
    lines.extend(["", f"FedWatch：{fed.get('label', '暂不可用')} {format_value(fed.get('value'), fed.get('unit', ''))}（{fed.get('note', '')}）", "", "观察重点："])
    lines.extend(f"{index}. {item}" for index, item in enumerate(payload["watchPoints"], 1))
    lines.extend(["", f"Brief生成时间：{payload['generatedAt']}", "所有缺失值均标为暂不可用，未使用推测值。"])
    return "\n".join(lines)


def build_payload(event: dict, key: str, scheduled: datetime, now: datetime, markets: dict, daily: dict) -> dict:
    payload = {
        "schemaVersion": 1,
        "status": "ready",
        "generatedAt": now.isoformat(timespec="seconds"),
        "event": {
            "id": event.get("id"),
            "key": key,
            "title": event.get("title"),
            "scheduledAt": scheduled.isoformat(timespec="seconds"),
            "scheduledAtLabel": scheduled.strftime("%Y年%m月%d日 %H:%M（北京时间）"),
            "minutesUntilRelease": round((scheduled - now).total_seconds() / 60),
            "metrics": metric_rows(event),
            "source": event.get("source"),
            "sourceUrl": event.get("sourceUrl"),
            "calendarRetrievedAt": event.get("retrievedAt"),
        },
        "market": {
            "assets": [
                market_snapshot(markets, "XAUUSD", "现货黄金", " USD"),
                market_snapshot(markets, "BTCUSD", "比特币", " USD"),
                market_snapshot(markets, "DXY", "美元指数", ""),
            ],
            "treasuries": treasury_snapshot(daily),
            "fedWatch": fed_snapshot(daily),
        },
        "watchPoints": WATCH_POINTS[key],
        "limitations": ["美债收益率采用美国财政部最近日值，不是盘中报价。", "FedWatch沿用最近一期每日早报，不是事件前即时概率。", "第一版不抓取Actual，也不判断公布后的市场反应。"],
    }
    payload["copyText"] = build_copy_text(payload)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calendar", type=Path, default=DEFAULT_CALENDAR)
    parser.add_argument("--markets", type=Path, default=DEFAULT_MARKETS)
    parser.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--now")
    parser.add_argument("--min-minutes", type=int, default=10)
    parser.add_argument("--max-minutes", type=int, default=30)
    parser.add_argument("--capture-minutes", type=int, default=DEFAULT_CAPTURE_MINUTES)
    parser.add_argument("--target-minutes", type=int, default=DEFAULT_TARGET_MINUTES)
    parser.add_argument("--max-wait-seconds", type=int, default=DEFAULT_MAX_WAIT_SECONDS)
    parser.add_argument("--probe", action="store_true", help="Plan only; never write a Brief or state.")
    parser.add_argument("--trigger-type", default="manual")
    parser.add_argument("--force-next", action="store_true")
    return parser.parse_args()


def log_plan(now: datetime, trigger_type: str, plan: dict, action: str) -> None:
    selected = plan.get("selected")
    print(f"now_beijing={now.isoformat(timespec='seconds')}")
    print(f"now_utc={now.astimezone(timezone.utc).isoformat(timespec='seconds')}")
    print(f"workflow_trigger={trigger_type}")
    if not selected:
        print("next_event=-")
        print("event_id=-")
        print("scheduled_at=-")
        print("minutes_until_release=-")
    else:
        scheduled, event, _, minutes = selected
        print(f"next_event={event.get('title') or '-'}")
        print(f"event_id={event.get('id') or '-'}")
        print(f"scheduled_at={scheduled.isoformat(timespec='seconds')}")
        print(f"minutes_until_release={minutes:.2f}")
    print(f"action={action}")
    if action == "wait":
        print(f"wait_seconds={plan['waitSeconds']}")
        print(f"target_execution_at={plan['targetAt'].isoformat(timespec='seconds')}")


def main() -> int:
    args = parse_args()
    now = parse_now(args.now)
    calendar = load_json(args.calendar, {})
    state = load_json(args.state, {})
    plan = plan_next_event(
        calendar.get("events", []),
        now,
        state,
        args.min_minutes,
        args.max_minutes,
        args.capture_minutes,
        args.target_minutes,
        args.max_wait_seconds,
        args.force_next,
    )
    action = plan["action"]
    if args.probe:
        log_plan(now, args.trigger_type, plan, action)
        print("generated=false")
        print(f"reason={action}")
        return 0
    if action != "generate":
        log_plan(now, args.trigger_type, plan, action)
        print("generated=false")
        print(f"reason={action}")
        return 0
    scheduled, event, key, _ = plan["selected"]
    payload = build_payload(event, key, scheduled, now, load_json(args.markets, {}), load_json(args.daily, {}))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.state.write_text(json.dumps({"lastEventId": event.get("id"), "sentAt": now.isoformat(timespec="seconds")}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log_plan(now, args.trigger_type, plan, "generated")
    print("generated=true")
    print(f"event_id={event.get('id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
