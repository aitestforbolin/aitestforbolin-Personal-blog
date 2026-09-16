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
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "us-macro-calendar.json"
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FF_PAGE_URL = "https://www.forexfactory.com/calendar"
FED_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
ET, SHANGHAI = ZoneInfo("America/New_York"), ZoneInfo("Asia/Shanghai")

SERIES = {
    "CPI": ("美国CPI / 核心CPI", "inflation", 5, {"CPI m/m": "CPI环比", "CPI y/y": "CPI同比", "Core CPI m/m": "核心CPI环比", "Core CPI y/y": "核心CPI同比"}),
    "PPI": ("美国PPI", "inflation", 3, {"PPI m/m": "PPI环比", "PPI y/y": "PPI同比", "Core PPI m/m": "核心PPI环比", "Core PPI y/y": "核心PPI同比"}),
    "PCE": ("美国PCE / 核心PCE", "inflation", 4, {"Core PCE Price Index m/m": "核心PCE环比", "Core PCE Price Index y/y": "核心PCE同比", "Personal Spending m/m": "实际PCE环比"}),
    "NFP": ("美国非农 / 失业率 / 平均时薪", "jobs", 5, {"Non-Farm Employment Change": "非农", "Unemployment Rate": "失业率", "Average Hourly Earnings m/m": "时薪环比", "Average Hourly Earnings y/y": "时薪同比"}),
    "Retail": ("美国零售销售", "growth", 4, {"Retail Sales m/m": "零售环比", "Core Retail Sales m/m": "核心零售环比"}),
    "FOMC": ("FOMC 利率决议 / 经济预测", "fed", 5, {"Federal Funds Rate": "联邦基金利率", "FOMC Economic Projections": "经济预测", "FOMC Statement": "FOMC声明"}),
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
        mapping = TITLE_MAP.get(str(row.get("title") or "")) if isinstance(row, dict) and row.get("country") == "USD" and row.get("impact") in FF_IMPACT else None
        if not mapping or not isinstance(row.get("date"), str): continue
        try: moment = datetime.fromisoformat(row["date"])
        except ValueError: continue
        series, label = mapping; title_cn, category, _, _ = SERIES[series]
        importance, stars = FF_IMPACT[row["impact"]]
        et, cn = moment.astimezone(ET), moment.astimezone(SHANGHAI)
        key = et.date().isoformat(), series
        event = grouped.setdefault(key, {"date": cn.date().isoformat(), "date_et": et.date().isoformat(), "time_et": et.strftime("%H:%M"), "time_shanghai": cn.strftime("%H:%M"), "title": series, "title_cn": title_cn, "period": None, "category": category, "importance": importance, "stars": stars, "source": "Forex Factory", "url": FF_PAGE_URL, "result_source": "Forex Factory 市场日历", "result_url": FF_PAGE_URL, "consensus_source": "Forex Factory 市场日历", "consensus_url": FF_PAGE_URL, "metric_values": [], "release_status": "scheduled"})
        if stars > event["stars"]:
            event["importance"], event["stars"] = importance, stars
        metric = {"label": label, "actual": row.get("actual") or None, "forecast": row.get("forecast") or None, "previous": row.get("previous") or None, "consensus_source": "Forex Factory 市场日历", "consensus_url": FF_PAGE_URL}
        event["metric_values"].append(metric)
        if metric["actual"] is not None:
            event["release_status"] = "released"; event["released_at"] = et.isoformat(timespec="seconds")
    events = list(grouped.values())
    for event in events:
        for field in ("actual", "forecast", "previous"):
            values = [f"{metric['label']} {metric[field]}" for metric in event["metric_values"] if metric[field] is not None]
            if values: event[field] = " · ".join(values)
    return sorted(events, key=lambda item: (item["date"], item["time_shanghai"], item["title"]))


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
        if event.get("title") not in SERIES:
            continue
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
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT); parser.add_argument("--offline", action="store_true"); args = parser.parse_args()
    existing, today = read_existing(args.output), datetime.now(ET).date()
    try:
        if args.offline: raise URLError("offline requested")
        events = parse_forex_factory(fetch_text(FF_URL)); validate_fomc(events, fetch_text(FED_URL))
        if not events: raise ValueError("no whitelisted USD events found")
        known = {(item.get("date_et"), item.get("title")) for item in events}
        events.extend(item for item in retain_released_window(existing, today) if (item.get("date_et"), item.get("title")) not in known)
        state = "healthy"
    except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        events, state = retain_window(existing, today), "stale_snapshot"
        if not events: raise SystemExit(f"Forex Factory unavailable and no valid snapshot exists: {exc}")
        print(f"warning: using previous Forex Factory snapshot: {exc}")
    for event in events:
        event["calendar_status"] = state
    events.sort(key=lambda item: (item.get("date", ""), item.get("time_shanghai", ""), item.get("title", "")))
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(events)} Forex Factory U.S. calendar events ({state})")


if __name__ == "__main__": main()
