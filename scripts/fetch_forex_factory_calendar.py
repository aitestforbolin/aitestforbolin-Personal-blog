#!/usr/bin/env python3
"""Build the U.S. website calendar from Forex Factory's public weekly feed.

This is deliberately a calendar adapter, not a macro-data warehouse. It keeps
only the releases used by the site and retains a still-visible prior snapshot
when the weekly feed is temporarily unavailable.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "us-macro-calendar.json"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_PAGE_URL = "https://www.forexfactory.com/calendar"
FF_ACTUAL_BRIDGE_URL = "https://forex-factory-calendar-probe.laibocszd.chatgpt.site/api/forex-factory-calendar"
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ET, SHANGHAI = ZoneInfo("America/New_York"), ZoneInfo("Asia/Shanghai")
FF_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")

SERIES = {
    "CPI": ("美国CPI / 核心CPI", "inflation", 5, {"CPI m/m": "CPI环比", "CPI y/y": "CPI同比", "Core CPI m/m": "核心CPI环比", "Core CPI y/y": "核心CPI同比"}),
    "PPI": ("美国PPI", "inflation", 3, {"PPI m/m": "PPI环比", "PPI y/y": "PPI同比", "Core PPI m/m": "核心PPI环比", "Core PPI y/y": "核心PPI同比"}),
    "PCE": ("美国PCE / 核心PCE", "inflation", 4, {"Core PCE Price Index m/m": "核心PCE环比", "Core PCE Price Index y/y": "核心PCE同比", "Personal Spending m/m": "实际PCE环比"}),
    "NFP": ("美国非农 / 失业率 / 平均时薪", "jobs", 5, {"Non-Farm Employment Change": "非农", "Unemployment Rate": "失业率", "Average Hourly Earnings m/m": "时薪环比", "Average Hourly Earnings y/y": "时薪同比"}),
    "Retail": ("美国零售销售", "growth", 4, {"Retail Sales m/m": "零售环比", "Core Retail Sales m/m": "核心零售环比"}),
    "GDP": ("美国GDP", "growth", 4, {"Advance GDP q/q": "GDP年化环比", "Prelim GDP q/q": "GDP年化环比", "Final GDP q/q": "GDP年化环比"}),
    "ISM Manufacturing": ("美国ISM制造业PMI", "growth", 3, {"ISM Manufacturing PMI": "ISM制造业PMI"}),
    "ISM Services": ("美国ISM服务业PMI", "growth", 3, {"ISM Services PMI": "ISM服务业PMI"}),
    "JOLTS": ("美国JOLTS职位空缺", "jobs", 3, {"JOLTS Job Openings": "JOLTS职位空缺"}),
    "Industrial Production": ("美国工业产出", "growth", 3, {"Industrial Production m/m": "工业产出环比"}),
    "Michigan": ("密歇根大学消费者信心 / 通胀预期", "consumption", 3, {"Prelim UoM Consumer Sentiment": "消费者信心初值", "Revised UoM Consumer Sentiment": "消费者信心终值", "Prelim UoM Inflation Expectations": "通胀预期初值", "Revised UoM Inflation Expectations": "通胀预期终值"}),
    "Jobless Claims": ("美国初请失业金人数", "jobs", 3, {"Unemployment Claims": "初请失业金人数"}),
    "Philly Fed": ("美国费城联储制造业指数", "growth", 3, {"Philly Fed Manufacturing Index": "费城联储制造业指数"}),
    "FOMC": ("FOMC 利率决议 / 经济预测", "fed", 5, {"Federal Funds Rate": "联邦基金利率", "FOMC Economic Projections": "经济预测", "FOMC Statement": "FOMC声明"}),
    "FOMC Press Conference": ("FOMC 主席新闻发布会", "fed", 5, {"FOMC Press Conference": "新闻发布会"}),
    "FOMC Minutes": ("FOMC 会议纪要", "fed", 4, {"FOMC Meeting Minutes": "会议纪要"}),
    "Treasury Secretary Speaks": ("美国财政部长贝森特讲话", "macro", 3, {"Treasury Sec Bessent Speaks": "讲话"}),
}
TITLE_MAP = {title: (series, label) for series, (_, _, _, titles) in SERIES.items() for title, label in titles.items()}
FF_IMPACT = {"High": ("high", 5), "Medium": ("medium", 3)}


class TextExtractor(HTMLParser):
    def __init__(self): super().__init__(); self.parts = []
    def handle_data(self, data):
        value = " ".join(data.split())
        if value: self.parts.append(value)


def fetch_text(url):
    with urlopen(Request(url, headers={"User-Agent": "personal-site-calendar/2.0 (+https://github.com/)"}), timeout=25) as response:
        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")


def parse_forex_factory(payload):
    raw = json.loads(payload)
    if not isinstance(raw, list): raise ValueError("Forex Factory calendar was not an array")
    grouped = {}
    for row in raw:
        if not isinstance(row, dict) or row.get("country") != "USD" or row.get("impact") not in FF_IMPACT or not isinstance(row.get("date"), str):
            continue
        raw_title = str(row.get("title") or "").strip()
        if not raw_title:
            continue
        mapping = TITLE_MAP.get(raw_title)
        try: moment = datetime.fromisoformat(row["date"])
        except ValueError: continue
        if mapping:
            series, label = mapping
            title_cn, category, _, _ = SERIES[series]
        else:
            series, label = f"FF::{raw_title}", "公布值"
            title_cn, category = raw_title, "macro"
        importance, stars = FF_IMPACT[row["impact"]]
        et, cn = moment.astimezone(ET), moment.astimezone(SHANGHAI)
        key = et.date().isoformat(), series, "" if mapping else et.strftime("%H:%M")
        event = grouped.setdefault(key, {"date": cn.date().isoformat(), "date_et": et.date().isoformat(), "time_et": et.strftime("%H:%M"), "time_shanghai": cn.strftime("%H:%M"), "title": series, "title_cn": title_cn, "period": None, "category": category, "importance": importance, "stars": stars, "source": "Forex Factory", "url": FF_PAGE_URL, "result_source": "Forex Factory 市场日历", "result_url": FF_PAGE_URL, "consensus_source": "Forex Factory 市场日历", "consensus_url": FF_PAGE_URL, "metric_values": [], "release_status": "scheduled"})
        if stars > event["stars"]:
            event["importance"], event["stars"] = importance, stars
        metric = {"label": label, "source_title": raw_title, "actual": row.get("actual") or None, "forecast": row.get("forecast") or None, "previous": row.get("previous") or None, "consensus_source": "Forex Factory 市场日历", "consensus_url": FF_PAGE_URL}
        event["metric_values"].append(metric)
        if metric["actual"] is not None:
            event["release_status"] = "released"; event["released_at"] = et.isoformat(timespec="seconds")
    events = list(grouped.values())
    for event in events:
        for field in ("actual", "forecast", "previous"):
            values = [f"{metric['label']} {metric[field]}" for metric in event["metric_values"] if metric[field] is not None]
            if values: event[field] = " · ".join(values)
    return sorted(events, key=lambda item: (item["date"], item["time_shanghai"], item["title"]))


def rebuild_event_summaries(event):
    for field in ("actual", "forecast", "previous"):
        values = [f"{metric['label']} {metric[field]}" for metric in event.get("metric_values", []) if metric.get(field) is not None]
        if values:
            event[field] = " · ".join(values)
        else:
            event.pop(field, None)


def carry_forward_actuals(events, existing):
    """Never erase a result that a previous successful run already captured."""
    prior = {(event.get("date_et"), event.get("title")): event for event in existing}
    for event in events:
        old = prior.get((event.get("date_et"), event.get("title")))
        if not old:
            continue
        old_metrics = {}
        for metric in old.get("metric_values", []):
            old_metrics[metric.get("source_title") or metric.get("label")] = metric
        copied = False
        for metric in event.get("metric_values", []):
            old_metric = old_metrics.get(metric.get("source_title") or metric.get("label"))
            if not old_metric or metric.get("actual") is not None or old_metric.get("actual") is None:
                continue
            for field in ("actual", "previous", "actual_source", "actual_url"):
                if old_metric.get(field) is not None:
                    metric[field] = old_metric[field]
            copied = True
        if copied:
            event["release_status"] = "released"
            for field in ("released_at", "actual_updated_at", "result_source", "result_url"):
                if old.get(field) is not None:
                    event[field] = old[field]
            rebuild_event_summaries(event)


def ff_day(value):
    day = date.fromisoformat(value)
    return f"{FF_MONTHS[day.month - 1]}{day.day}.{day.year}"


def event_moment(event):
    try:
        return datetime.fromisoformat(f"{event['date_et']}T{event['time_et']}").replace(tzinfo=ET)
    except (KeyError, TypeError, ValueError):
        return None


def expects_actual(metric):
    return metric.get("forecast") is not None or metric.get("previous") is not None


def actual_backfill_days(events, now, lookback_minutes=240):
    earliest = now - timedelta(minutes=lookback_minutes)
    days = set()
    for event in events:
        moment = event_moment(event)
        missing = any(expects_actual(metric) and metric.get("actual") is None for metric in event.get("metric_values", []))
        if moment and earliest <= moment <= now and missing:
            days.add(event["date_et"])
    return sorted(days)


def fetch_actual_bridge(day):
    payload = json.loads(fetch_text(f"{FF_ACTUAL_BRIDGE_URL}?{urlencode({'day': ff_day(day)})}"))
    if not isinstance(payload, dict) or not payload.get("ok") or not isinstance(payload.get("events"), list):
        raise ValueError("Forex Factory Actual bridge returned an invalid payload")
    return payload


def merge_bridge_actuals(events, payloads):
    rows = {}
    for day, payload in payloads.items():
        for row in payload.get("events", []):
            if isinstance(row, dict) and row.get("event"):
                rows.setdefault((day, row["event"]), []).append(row)
    positions = {}
    updated = 0
    for event in events:
        event_updated = False
        for metric in event.get("metric_values", []):
            title = metric.get("source_title")
            candidates = rows.get((event.get("date_et"), title), [])
            position_key = event.get("date_et"), title
            position = positions.get(position_key, 0)
            if not title or position >= len(candidates):
                continue
            row = candidates[position]
            positions[position_key] = position + 1
            if not row.get("actual"):
                continue
            metric["actual"] = row["actual"]
            if row.get("previous"):
                metric["previous"] = row["previous"]
            if metric.get("forecast") is None and row.get("forecast"):
                metric["forecast"] = row["forecast"]
            metric["actual_source"] = "Forex Factory 网页日历"
            metric["actual_url"] = payloads[event["date_et"]].get("source_url") or FF_PAGE_URL
            updated += 1
            event_updated = True
        if event_updated:
            payload = payloads[event["date_et"]]
            event["release_status"] = "released"
            event["released_at"] = payload.get("checked_at") or datetime.now(ET).isoformat(timespec="seconds")
            event["actual_updated_at"] = event["released_at"]
            event["result_source"] = "Forex Factory 网页日历"
            event["result_url"] = payload.get("source_url") or FF_PAGE_URL
            rebuild_event_summaries(event)
    return updated


def fed_decision_dates(html):
    parser = TextExtractor(); parser.feed(html); lines = parser.parts
    months = {name: index for index, name in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
    result, year = set(), None
    for index, value in enumerate(lines[:-1]):
        if value.endswith(" FOMC Meetings") and value[:4].isdigit(): year = int(value[:4]); continue
        if year and value in months:
            match = re.fullmatch(r"(\d{1,2})-(\d{1,2})\*?", lines[index + 1])
            if match: result.add(date(year, months[value], int(match.group(2))).isoformat())
    return result


def validate_fomc(events, fed_html):
    official = fed_decision_dates(fed_html)
    for event in events:
        if event["title"] == "FOMC":
            event["fomc_validation"] = "confirmed" if event["date_et"] in official else "unverified"
            if event["fomc_validation"] == "confirmed":
                event["source"] = "Federal Reserve（FOMC 日期已校验）"; event["url"] = FED_URL


def read_existing(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8")); return value if isinstance(value, list) else []
    except (OSError, ValueError): return []


def retain_window(events, today):
    start, end = today - timedelta(days=2), today + timedelta(days=7)
    kept = []
    for event in events:
        try: day = date.fromisoformat(str(event.get("date_et") or event.get("date"))[:10])
        except (AttributeError, ValueError): continue
        if start <= day <= end: kept.append(event)
    return kept


def retain_released_window(events, today):
    """Keep only recent results absent from a new weekly feed, never old plans."""
    return [event for event in retain_window(events, today)
            if event.get("release_status") == "released"
            and date.fromisoformat(str(event.get("date_et") or event.get("date"))[:10]) < today]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--backfill-actual", action="store_true")
    parser.add_argument("--actual-lookback-minutes", type=int, default=240)
    args = parser.parse_args()
    now = datetime.now(ET)
    existing, today = read_existing(args.output), now.date()
    try:
        if args.offline: raise URLError("offline requested")
        events = parse_forex_factory(fetch_text(FF_URL)); validate_fomc(events, fetch_text(FED_URL))
        if not events: raise ValueError("no whitelisted USD events found")
        carry_forward_actuals(events, existing)
        known = {(item.get("date_et"), item.get("title")) for item in events}
        events.extend(item for item in retain_released_window(existing, today) if (item.get("date_et"), item.get("title")) not in known)
        state = "healthy"
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        events, state = retain_window(existing, today), "stale_snapshot"
        if not events: raise SystemExit(f"Forex Factory unavailable and no valid snapshot exists: {exc}")
        print(f"warning: using previous Forex Factory snapshot: {exc}")
    if args.backfill_actual and not args.offline:
        payloads = {}
        for day in actual_backfill_days(events, now, args.actual_lookback_minutes):
            try:
                payloads[day] = fetch_actual_bridge(day)
            except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                print(f"warning: Actual bridge unavailable for {day}: {exc}")
        if payloads:
            print(f"backfilled {merge_bridge_actuals(events, payloads)} Actual values from Forex Factory webpage")
    for event in events:
        event["calendar_status"] = state
    events.sort(key=lambda item: (item.get("date", ""), item.get("time_shanghai", ""), item.get("title", "")))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(events)} Forex Factory U.S. calendar events ({state})")


if __name__ == "__main__": main()
