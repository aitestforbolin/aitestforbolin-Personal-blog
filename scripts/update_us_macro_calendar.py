#!/usr/bin/env python3
"""Build the static U.S. macro calendar JSON for the personal site."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from http.client import IncompleteRead
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SITE_ROOT / "data" / "us-macro-calendar.json"
DEFAULT_DAYS = 35
DEFAULT_LOOKBACK_DAYS = 3

BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BLS_MONTH_URL = "https://www.bls.gov/schedule/{year}/{month:02d}_sched.htm"
BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
FED_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CENSUS_CALENDAR_URL = "https://www.census.gov/economic-indicators/"
CENSUS_M3_SCHEDULE_URL = "https://www.census.gov/manufacturing/m3/release_schedule.html"
FRED_CORE_CAPITAL_GOODS_URL = "https://fred.stlouisfed.org/series/NEWORDER"
ISM_REPORTS_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"
SP_GLOBAL_PMI_CALENDAR_URL = "https://www.pmi.spglobal.com/Public/Release/ReleaseDates"
SP_GLOBAL_RESULT_URLS = {
    "manufacturing": (
        "https://www.investing.com/economic-calendar/"
        "united-states-manufacturing-purchasing-managers-index-%28pmi%29-829"
    ),
    "services": (
        "https://www.investing.com/economic-calendar/"
        "united-states-services-purchasing-managers-index-%28pmi%29-1062"
    ),
}
FOREX_FACTORY_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FOREX_FACTORY_SOURCE_URL = "https://www.forexfactory.com/calendar"

EVENT_SOURCE_FALLBACKS = {
    "美国JOLTS职位空缺": ("https://fred.stlouisfed.org/series/JTSJOL", "FRED 备用"),
    "美国非农 / 失业率 / 平均时薪": (
        "https://fred.stlouisfed.org/release?rid=50",
        "FRED 备用",
    ),
    "美国CPI / 核心CPI": ("https://fred.stlouisfed.org/release?rid=10", "FRED 备用"),
    "美国PPI": ("https://fred.stlouisfed.org/release?rid=46", "FRED 备用"),
    "美国零售销售": ("https://fred.stlouisfed.org/release?rid=9", "FRED 备用"),
    "美国耐用品订单 / 核心资本品订单": (
        FRED_CORE_CAPITAL_GOODS_URL,
        "FRED 备用",
    ),
    "美国S&P Global制造业PMI初值": (SP_GLOBAL_PMI_CALENDAR_URL, "S&P 日历备用"),
    "美国S&P Global服务业PMI初值": (SP_GLOBAL_PMI_CALENDAR_URL, "S&P 日历备用"),
}

FOREX_FACTORY_SERIES = {
    "FOMC 利率决议": (("", ("Federal Funds Rate",)),),
    "美国GDP": (("", ("Advance GDP q/q", "Prelim GDP q/q", "Final GDP q/q")),),
    "美国PCE / 核心PCE": (("", ("Core PCE Price Index m/m",)),),
    "美国ISM制造业PMI": (("", ("ISM Manufacturing PMI",)),),
    "美国JOLTS职位空缺": (("", ("JOLTS Job Openings",)),),
    "美国ISM服务业PMI": (("", ("ISM Services PMI",)),),
    "美国非农 / 失业率 / 平均时薪": (
        ("非农", ("Non-Farm Employment Change",)),
        ("失业率", ("Unemployment Rate",)),
        ("时薪", ("Average Hourly Earnings m/m",)),
    ),
    "美国CPI / 核心CPI": (
        ("CPI同比", ("CPI y/y",)),
        ("CPI环比", ("CPI m/m",)),
        ("核心CPI环比", ("Core CPI m/m",)),
        ("核心CPI同比", ("Core CPI y/y",)),
    ),
    "美国PPI": (
        ("PPI", ("PPI m/m",)),
        ("核心PPI", ("Core PPI m/m",)),
    ),
    "美国零售销售": (
        ("零售", ("Retail Sales m/m",)),
        ("核心零售", ("Core Retail Sales m/m",)),
    ),
    "美国耐用品订单 / 核心资本品订单": (
        ("耐用品", ("Durable Goods Orders m/m",)),
        ("核心耐用品", ("Core Durable Goods Orders m/m",)),
    ),
    "美国S&P Global制造业PMI初值": (("", ("Flash Manufacturing PMI",)),),
    "美国S&P Global服务业PMI初值": (("", ("Flash Services PMI",)),),
}

# Once a release is published, retain its official result even if the market
# calendar feed is unavailable. These entries also ensure the site links to the
# specific BLS report instead of leaving a completed item pointed at a schedule.
OFFICIAL_RELEASE_OVERRIDES = {
    ("2026-08-12", "08:30", "Consumer Price Index"): {
        "metric_values": [
            {"label": "CPI同比", "actual": "3.4%", "forecast": "3.4%", "previous": "3.5%"},
            {"label": "CPI环比", "actual": "0.1%", "forecast": "0.1%", "previous": "-0.4%"},
            {"label": "核心CPI环比", "actual": "0.2%", "forecast": "0.2%", "previous": "0.0%"},
            {"label": "核心CPI同比", "actual": "2.5%", "forecast": "2.5%", "previous": "2.6%"},
        ],
        "actual": "CPI同比 3.4% · CPI环比 0.1% · 核心CPI环比 0.2% · 核心CPI同比 2.5%",
        "forecast": "CPI同比 3.4% · CPI环比 0.1% · 核心CPI环比 0.2% · 核心CPI同比 2.5%",
        "previous": "CPI同比 3.5% · CPI环比 -0.4% · 核心CPI环比 0.0% · 核心CPI同比 2.6%",
        "url": "https://www.bls.gov/news.release/archives/cpi_08122026.htm",
        "result_source": "BLS 2026年7月CPI报告",
        "result_url": "https://www.bls.gov/news.release/archives/cpi_08122026.htm",
        "release_status": "released",
        "released_at": "2026-08-12T08:30:00-04:00",
    },
    ("2026-08-13", "08:30", "Producer Price Index"): {
        "metric_values": [
            {"label": "PPI环比", "actual": "0.0%", "forecast": "0.2%", "previous": "-0.3%"},
            {
                "label": "核心PPI环比",
                "actual": "0.4%",
                "forecast": "0.3%",
                "previous": "0.2%",
            },
        ],
        "actual": "PPI环比 0.0% · 核心PPI环比 0.4%",
        "forecast": "PPI环比 0.2% · 核心PPI环比 0.3%",
        "previous": "PPI环比 -0.3% · 核心PPI环比 0.2%",
        "url": "https://www.bls.gov/news.release/archives/ppi_08132026.htm",
        "result_source": "BLS 2026年7月PPI报告",
        "result_url": "https://www.bls.gov/news.release/archives/ppi_08132026.htm",
        "release_status": "released",
        "released_at": "2026-08-13T08:30:00-04:00",
    },
}

US_RELEASE_HOLIDAYS = {
    "2026-01-01",
    "2026-01-19",
    "2026-02-16",
    "2026-05-25",
    "2026-06-19",
    "2026-07-03",
    "2026-09-07",
    "2026-11-26",
    "2026-12-25",
}

EVENT_RULES = [
    {
        "needle": "Consumer Price Index",
        "title_cn": "美国CPI / 核心CPI",
        "category": "inflation",
        "importance": "critical",
        "stars": 5,
    },
    {
        "needle": "Producer Price Index",
        "title_cn": "美国PPI",
        "category": "inflation",
        "importance": "medium",
        "stars": 3,
    },
    {
        "needle": "Employment Situation",
        "title_cn": "美国非农 / 失业率 / 平均时薪",
        "category": "jobs",
        "importance": "critical",
        "stars": 5,
    },
    {
        "needle": "Job Openings and Labor Turnover",
        "title_cn": "美国JOLTS职位空缺",
        "category": "jobs",
        "importance": "medium",
        "stars": 3,
    },
    {
        "needle": "Personal Income and Outlays",
        "title_cn": "美国PCE / 核心PCE",
        "category": "inflation",
        "importance": "high",
        "stars": 4,
    },
    {
        "needle": "GDP",
        "title_cn": "美国GDP",
        "category": "growth",
        "importance": "high",
        "stars": 4,
    },
    {
        "needle": "Advance Monthly Sales for Retail and Food Services",
        "title_cn": "美国零售销售",
        "category": "growth",
        "importance": "high",
        "stars": 4,
    },
]

FOMC_MEETINGS = [
    ("2026-06-17", "June 2026 meeting", True),
    ("2026-07-29", "July 2026 meeting", False),
    ("2026-09-16", "September 2026 meeting", True),
    ("2026-10-28", "October 2026 meeting", False),
    ("2026-12-09", "December 2026 meeting", True),
]

FOMC_MINUTES_RELEASES = [
    ("2026-07-08", "June 2026 meeting"),
    ("2026-08-19", "July 2026 meeting"),
    ("2026-10-07", "September 2026 meeting"),
    ("2026-11-18", "October 2026 meeting"),
]

# Census does not expose a simple static JSON endpoint on the briefing page.
# Keep the core retail-sales release dates here as a stable fallback.
CENSUS_RETAIL_RELEASES = [
    ("2026-06-17", "May 2026"),
    ("2026-07-16", "June 2026"),
    ("2026-08-14", "July 2026"),
]

# Stable fallback for the Census M3 advance durable-goods schedule. The online
# updater reads the official release table first; these dates keep the calendar
# complete if Census is temporarily unavailable.
CENSUS_DURABLE_GOODS_RELEASES = [
    ("2026-07-27", "June 2026"),
    ("2026-08-26", "July 2026"),
    ("2026-09-25", "August 2026"),
    ("2026-10-27", "September 2026"),
    ("2026-11-25", "October 2026"),
    ("2026-12-23", "November 2026"),
]

BLS_FALLBACK_RELEASES = [
    ("2026-06-30", "10:00", "Job Openings and Labor Turnover Survey", "May 2026"),
    ("2026-07-02", "08:30", "Employment Situation", "June 2026"),
    ("2026-07-14", "08:30", "Consumer Price Index", "June 2026"),
    ("2026-07-15", "08:30", "Producer Price Index", "June 2026"),
    ("2026-08-04", "10:00", "Job Openings and Labor Turnover Survey", "June 2026"),
    ("2026-08-07", "08:30", "Employment Situation", "July 2026"),
    ("2026-08-12", "08:30", "Consumer Price Index", "July 2026"),
    ("2026-08-13", "08:30", "Producer Price Index", "July 2026"),
]

BEA_FALLBACK_RELEASES = [
    (
        "2026-07-30",
        "08:30",
        "Personal Income and Outlays, June 2026",
        "June 2026",
        "美国PCE / 核心PCE",
    ),
    (
        "2026-07-30",
        "08:30",
        "GDP (Advance Estimate), 2nd Quarter 2026",
        "2nd Quarter 2026",
        "美国GDP",
    ),
    (
        "2026-08-26",
        "08:30",
        "GDP (Second Estimate) and Corporate Profits, 2nd Quarter 2026",
        "2nd Quarter 2026",
        "美国GDP",
    ),
    (
        "2026-08-26",
        "08:30",
        "Personal Income and Outlays, July 2026",
        "July 2026",
        "美国PCE / 核心PCE",
    ),
]

# S&P Global publishes its Flash U.S. manufacturing and services PMI together.
# Its public release calendar is protected by anti-bot checks, so keep the
# official 2026 dates here and refresh the list when S&P publishes a new year.
SP_GLOBAL_FLASH_RELEASES = [
    {
        "date": "2026-07-24",
        "period": "July 2026",
        "url": (
            "https://www.pmi.spglobal.com/Public/Home/PressRelease/"
            "04dad02019414e5ebc89ec6a04b300bd"
        ),
        "manufacturing": {
            "actual": "53.8",
            "forecast": "54.4",
            "previous": "53.9",
        },
        "services": {
            "actual": "53.6",
            "forecast": "51.3",
            "previous": "51.2",
        },
    },
    {"date": "2026-08-21", "period": "August 2026"},
    {"date": "2026-09-23", "period": "September 2026"},
    {"date": "2026-10-23", "period": "October 2026"},
    {"date": "2026-11-23", "period": "November 2026"},
    {"date": "2026-12-16", "period": "December 2026"},
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "personal-site-macro-calendar/1.0 (+https://github.com/)",
        },
    )
    with urlopen(request, timeout=20) as response:
        body = response.read()
        encoding = response.headers.get_content_charset() or "utf-8"
    return body.decode(encoding, errors="replace")


def html_text_lines(html: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(html)
    return parser.parts


def match_rule(title: str) -> dict[str, str] | None:
    for rule in EVENT_RULES:
        needle = rule["needle"].lower()
        normalized_title = title.lower()
        if needle in normalized_title:
            return rule
        if needle == "gdp" and "gross domestic product" in normalized_title:
            return rule
    return None


def shanghai_fields(day: date, eastern_time: str) -> tuple[str, str]:
    hour, minute = [int(part) for part in eastern_time.split(":")]
    eastern_dt = datetime.combine(
        day,
        time(hour, minute),
        tzinfo=ZoneInfo("America/New_York"),
    )
    shanghai_dt = eastern_dt.astimezone(ZoneInfo("Asia/Shanghai"))
    return shanghai_dt.date().isoformat(), shanghai_dt.strftime("%H:%M")


def clean_ics_value(value: str) -> str:
    return value.replace("\\,", ",").replace("\\n", " ").strip()


def unfold_ics(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        if raw_line.startswith((" ", "\t")) and lines:
            lines[-1] += raw_line[1:]
        else:
            lines.append(raw_line)
    return lines


def parse_ics_datetime(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1]
    for fmt in ("%Y%m%dT%H%M%S", "%Y%m%dT%H%M", "%Y%m%d"):
        try:
            parsed = datetime.strptime(value, fmt)
            if fmt == "%Y%m%d":
                return datetime.combine(parsed.date(), time(8, 30))
            return parsed
        except ValueError:
            continue
    return None


def parse_period(title: str) -> str:
    match = re.search(
        r"((January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})",
        title,
    )
    if match:
        return match.group(1)
    match = re.search(r"((First|Second|Third|Fourth)\s+Quarter\s+\d{4})", title)
    if match:
        return match.group(1)
    match = re.search(r"(\d(?:st|nd|rd|th)\s+Quarter\s+\d{4})", title)
    if match:
        return match.group(1)
    return ""


def make_event(
    *,
    day: date,
    eastern_time: str,
    title: str,
    title_cn: str,
    period: str,
    category: str,
    source: str,
    url: str,
    importance: str | None = None,
    stars: int = 3,
) -> dict[str, str]:
    if not 1 <= stars <= 5:
        raise ValueError("event stars must be between 1 and 5")

    if importance is None:
        importance = {
            1: "background",
            2: "low",
            3: "medium",
            4: "high",
            5: "critical",
        }[stars]

    shanghai_date, shanghai_time = shanghai_fields(day, eastern_time)
    event = {
        "date": shanghai_date,
        "time_et": eastern_time,
        "time_shanghai": shanghai_time,
        "title": title,
        "title_cn": title_cn,
        "period": period,
        "category": category,
        "importance": importance,
        "stars": stars,
        "source": source,
        "url": url,
    }
    if shanghai_date != day.isoformat():
        event["date_et"] = day.isoformat()

    fallback = EVENT_SOURCE_FALLBACKS.get(title_cn)
    if fallback and url != fallback[0]:
        event["fallback_url"] = fallback[0]
        event["fallback_label"] = fallback[1]
    return event


def parse_bls_events(start: date, end: date) -> list[dict[str, str]]:
    try:
        return parse_bls_ics_events(start, end)
    except (URLError, TimeoutError, OSError, ValueError, IncompleteRead):
        try:
            return parse_bls_month_pages(start, end)
        except (URLError, TimeoutError, OSError, ValueError, IncompleteRead):
            return bls_fallback_events(start, end)


def parse_bls_ics_events(start: date, end: date) -> list[dict[str, str]]:
    text = fetch_text(BLS_ICS_URL)
    events: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for line in unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {}
            continue
        if line == "END:VEVENT":
            if current:
                title = clean_ics_value(current.get("SUMMARY", ""))
                rule = match_rule(title)
                starts_at = parse_ics_datetime(current.get("DTSTART", ""))
                if rule and starts_at and start <= starts_at.date() <= end:
                    events.append(
                        make_event(
                            day=starts_at.date(),
                            eastern_time=starts_at.strftime("%H:%M"),
                            title=rule["needle"],
                            title_cn=rule["title_cn"],
                            period=parse_period(title),
                            category=rule["category"],
                            source="BLS",
                            url="https://www.bls.gov/schedule/news_release/",
                            importance=rule["importance"],
                            stars=rule["stars"],
                        )
                    )
            current = None
            continue
        if current is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.split(";", 1)[0]
        if key in {"SUMMARY", "DTSTART"}:
            current[key] = value

    return events


def month_starts(start: date, end: date) -> list[date]:
    cursor = date(start.year, start.month, 1)
    months = []
    while cursor <= end:
        months.append(cursor)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return months


def shifted_month(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = (year * 12) + (month - 1) + offset
    return month_index // 12, (month_index % 12) + 1


def add_month(year: int, month: int, offset: int) -> tuple[int, int]:
    month_index = (year * 12) + (month - 1) + offset
    return month_index // 12, (month_index % 12) + 1


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day.isoformat() not in US_RELEASE_HOLIDAYS


def nth_business_day(year: int, month: int, position: int) -> date:
    cursor = date(year, month, 1)
    found = 0

    while cursor.month == month:
        if is_business_day(cursor):
            found += 1
            if found == position:
                return cursor
        cursor += timedelta(days=1)

    raise ValueError(f"month {year}-{month:02d} has fewer than {position} business days")


def parse_bls_month_pages(start: date, end: date) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []

    for month_start in month_starts(start, end):
        url = BLS_MONTH_URL.format(year=month_start.year, month=month_start.month)
        lines = html_text_lines(fetch_text(url))
        try:
            begin = next(i for i, line in enumerate(lines) if re.match(r"^#\s+\w+\s+\d{4}$", line))
            finish = next(i for i, line in enumerate(lines[begin:], begin) if line.startswith("NOTE:"))
        except StopIteration:
            continue

        body = lines[begin:finish]
        day_indices = [i for i, line in enumerate(body) if re.match(r"^\d{1,2}$", line)]
        if not day_indices:
            continue

        offset = -1 if int(body[day_indices[0]]) > 7 else 0
        previous_day = int(body[day_indices[0]])

        for position, day_index in enumerate(day_indices):
            day_number = int(body[day_index])
            if position > 0 and day_number < previous_day:
                offset += 1
            previous_day = day_number

            event_year, event_month = shifted_month(month_start.year, month_start.month, offset)
            try:
                event_day = date(event_year, event_month, day_number)
            except ValueError:
                continue

            next_day_index = day_indices[position + 1] if position + 1 < len(day_indices) else len(body)
            details = body[day_index + 1 : next_day_index]
            j = 0
            while j + 2 < len(details):
                title = details[j]
                period = details[j + 1]
                time_text = details[j + 2]
                rule = match_rule(title)
                if rule and re.match(r"^\d{1,2}:\d{2}\s+[AP]M$", time_text):
                    eastern_time = datetime.strptime(time_text, "%I:%M %p").strftime("%H:%M")
                    if start <= event_day <= end:
                        events.append(
                            make_event(
                                day=event_day,
                                eastern_time=eastern_time,
                                title=rule["needle"],
                                title_cn=rule["title_cn"],
                                period=period,
                                category=rule["category"],
                                source="BLS",
                                url="https://www.bls.gov/schedule/news_release/",
                                importance=rule["importance"],
                                stars=rule["stars"],
                            )
                        )
                    j += 3
                else:
                    j += 1

    return events


def bls_fallback_events(start: date, end: date) -> list[dict[str, str]]:
    events = []
    for day_text, eastern_time, title, period in BLS_FALLBACK_RELEASES:
        day = date.fromisoformat(day_text)
        rule = match_rule(title)
        if rule and start <= day <= end:
            events.append(
                make_event(
                    day=day,
                    eastern_time=eastern_time,
                    title=rule["needle"],
                    title_cn=rule["title_cn"],
                    period=period,
                    category=rule["category"],
                    source="BLS",
                    url="https://www.bls.gov/schedule/news_release/",
                    importance=rule["importance"],
                    stars=rule["stars"],
                )
            )
    return events


def parse_bea_events(start: date, end: date) -> list[dict[str, str]]:
    lines = html_text_lines(fetch_text(BEA_SCHEDULE_URL))
    events: list[dict[str, str]] = []
    month = None
    i = 0

    while i < len(lines):
        date_match = re.match(
            r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})$",
            lines[i],
        )
        if date_match:
            month = date_match.group(1)
            day_num = int(date_match.group(2))
            if i + 4 < len(lines):
                time_text = lines[i + 1]
                title = lines[i + 4] if lines[i + 2 : i + 4] == ["N", "ews"] else lines[i + 3]
                rule = match_rule(title)
                if rule and re.match(r"^\d{1,2}:\d{2}\s+[AP]M$", time_text):
                    day = datetime.strptime(f"{month} {day_num} 2026", "%B %d %Y").date()
                    eastern_time = datetime.strptime(time_text, "%I:%M %p").strftime("%H:%M")
                    if start <= day <= end:
                        title_cn = "美国GDP" if "GDP" in title else rule["title_cn"]
                        events.append(
                            make_event(
                                day=day,
                                eastern_time=eastern_time,
                                title=title,
                                title_cn=title_cn,
                                period=parse_period(title),
                                category=rule["category"],
                                source="BEA",
                                url=BEA_SCHEDULE_URL,
                                importance=rule["importance"],
                                stars=rule["stars"],
                            )
                        )
                i += 5
                continue
        i += 1

    return events


def bea_fallback_events(start: date, end: date) -> list[dict[str, str]]:
    events = []
    for day_text, eastern_time, title, period, title_cn in BEA_FALLBACK_RELEASES:
        day = date.fromisoformat(day_text)
        rule = match_rule(title)
        if rule and start <= day <= end:
            events.append(
                make_event(
                    day=day,
                    eastern_time=eastern_time,
                    title=title,
                    title_cn=title_cn,
                    period=period,
                    category=rule["category"],
                    source="BEA",
                    url=BEA_SCHEDULE_URL,
                    importance=rule["importance"],
                    stars=rule["stars"],
                )
            )
    return events


def fomc_events(start: date, end: date) -> list[dict[str, str]]:
    events = []
    for day_text, period, has_sep in FOMC_MEETINGS:
        day = date.fromisoformat(day_text)
        if start <= day <= end:
            title_cn = "FOMC 利率决议"
            if has_sep:
                title_cn += " / 点阵图"
            events.append(
                make_event(
                    day=day,
                    eastern_time="14:00",
                    title="FOMC Policy Decision",
                    title_cn=title_cn,
                    period=period,
                    category="fed",
                    source="Federal Reserve",
                    url=FED_CALENDAR_URL,
                    stars=5,
                )
            )
            events.append(
                make_event(
                    day=day,
                    eastern_time="14:30",
                    title="FOMC Chair Press Conference",
                    title_cn="FOMC 主席发布会",
                    period=period,
                    category="fed",
                    source="Federal Reserve",
                    url=FED_CALENDAR_URL,
                    stars=5,
                )
            )
    for day_text, period in FOMC_MINUTES_RELEASES:
        day = date.fromisoformat(day_text)
        if start <= day <= end:
            events.append(
                make_event(
                    day=day,
                    eastern_time="14:00",
                    title="FOMC Meeting Minutes",
                    title_cn="FOMC 会议纪要",
                    period=period,
                    category="fed",
                    source="Federal Reserve",
                    url=FED_CALENDAR_URL,
                    stars=3,
                )
            )
    return events


def census_retail_events(start: date, end: date) -> list[dict[str, str]]:
    events = []
    for day_text, period in CENSUS_RETAIL_RELEASES:
        day = date.fromisoformat(day_text)
        if start <= day <= end:
            events.append(
                make_event(
                    day=day,
                    eastern_time="08:30",
                    title="Advance Monthly Sales for Retail and Food Services",
                    title_cn="美国零售销售",
                    period=period,
                    category="growth",
                    source="Census",
                    url=CENSUS_CALENDAR_URL,
                    stars=4,
                )
            )
    return events


def durable_goods_event(day: date, period: str) -> dict[str, str]:
    event = make_event(
        day=day,
        eastern_time="08:30",
        title="Advance Report on Durable Goods and Advance Total Manufacturing",
        title_cn="美国耐用品订单 / 核心资本品订单",
        period=period,
        category="growth",
        source="Census",
        url=CENSUS_M3_SCHEDULE_URL,
        stars=3,
    )
    event["fallback_url"] = FRED_CORE_CAPITAL_GOODS_URL
    event["fallback_label"] = "FRED 备用"
    return event


def parse_census_durable_goods_events(start: date, end: date) -> list[dict[str, str]]:
    lines = html_text_lines(fetch_text(CENSUS_M3_SCHEDULE_URL))
    events: list[dict[str, str]] = []
    period_pattern = re.compile(
        r"^(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}$"
    )
    date_pattern = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")

    for index, period in enumerate(lines):
        if not period_pattern.match(period):
            continue

        release_text = next(
            (line for line in lines[index + 1 : index + 5] if date_pattern.match(line)),
            None,
        )
        if not release_text:
            continue

        day = datetime.strptime(release_text, "%m/%d/%Y").date()
        if start <= day <= end:
            events.append(durable_goods_event(day, period))

    return events


def census_durable_goods_fallback_events(start: date, end: date) -> list[dict[str, str]]:
    events = []
    for day_text, period in CENSUS_DURABLE_GOODS_RELEASES:
        day = date.fromisoformat(day_text)
        if start <= day <= end:
            events.append(durable_goods_event(day, period))
    return events


def ism_events(start: date, end: date) -> list[dict[str, str]]:
    events = []
    cursor = date(start.year, start.month, 1)

    while cursor <= end:
        year, month = cursor.year, cursor.month
        period_year, period_month = add_month(year, month, -1)
        period = date(period_year, period_month, 1).strftime("%B %Y")
        releases = [
            (
                nth_business_day(year, month, 1),
                "Manufacturing PMI Report on Business",
                "美国ISM制造业PMI",
            ),
            (
                nth_business_day(year, month, 3),
                "Services PMI Report on Business",
                "美国ISM服务业PMI",
            ),
        ]

        for day, title, title_cn in releases:
            if start <= day <= end:
                events.append(
                    make_event(
                        day=day,
                        eastern_time="10:00",
                        title=title,
                        title_cn=title_cn,
                        period=period,
                        category="growth",
                        source="ISM",
                        url=ISM_REPORTS_URL,
                    )
                )

        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    return events


def parse_forex_factory_calendar(payload: str) -> list[dict[str, str]]:
    """Normalize the public weekly calendar used for consensus and prior values."""
    parsed = json.loads(payload)
    if not isinstance(parsed, list):
        raise ValueError("Forex Factory calendar was not a list")

    events: list[dict[str, str]] = []
    eastern = ZoneInfo("America/New_York")
    for item in parsed:
        if not isinstance(item, dict) or item.get("country") != "USD":
            continue
        title = item.get("title")
        timestamp = item.get("date")
        if not isinstance(title, str) or not isinstance(timestamp, str):
            continue
        released_at = datetime.fromisoformat(timestamp)
        normalized = {
            "title": title,
            "date_et": released_at.astimezone(eastern).date().isoformat(),
        }
        for field in ("actual", "forecast", "previous"):
            value = item.get(field)
            if value not in (None, ""):
                normalized[field] = str(value)
        events.append(normalized)
    return events


def enrich_events_with_market_values(
    events: list[dict[str, str]],
    market_events: list[dict[str, str]],
) -> None:
    """Add actual, consensus and prior values to matching calendar events."""
    lookup = {
        (item["date_et"], item["title"]): item
        for item in market_events
        if item.get("date_et") and item.get("title")
    }

    for event in events:
        series = FOREX_FACTORY_SERIES.get(event.get("title_cn", ""))
        if not series:
            continue
        event_day = event.get("date_et", event["date"])
        matched = False

        metric_values: list[dict[str, str | None]] = []
        for label, candidate_titles in series:
            market_item = next(
                (
                    lookup[(event_day, candidate)]
                    for candidate in candidate_titles
                    if (event_day, candidate) in lookup
                ),
                None,
            )
            if not market_item:
                continue
            metric = {
                "label": label or "综合值",
                "actual": market_item.get("actual"),
                "forecast": market_item.get("forecast"),
                "previous": market_item.get("previous"),
            }
            if any(metric[field] not in (None, "") for field in ("actual", "forecast", "previous")):
                metric_values.append(metric)

        if metric_values:
            event["metric_values"] = metric_values
            for field in ("actual", "forecast", "previous"):
                parts = [
                    (
                        str(metric[field])
                        if metric["label"] == "综合值"
                        else f"{metric['label']} {metric[field]}"
                    )
                    for metric in metric_values
                    if metric[field] not in (None, "")
                ]
                if parts:
                    event[field] = " · ".join(parts)
            matched = True

        if matched:
            event["result_source"] = "Forex Factory 市场日历"
            event["result_url"] = FOREX_FACTORY_SOURCE_URL
            if event.get("actual"):
                event["release_status"] = "released"


def parse_investing_latest_release(html: str) -> dict[str, object]:
    """Extract the latest structured occurrence from an Investing.com page."""
    marker = '"closestOccurrences":{"latest_release":'
    marker_position = html.find(marker)
    if marker_position < 0:
        raise ValueError("latest release data was not found")

    payload_position = marker_position + len(marker)
    payload, _ = json.JSONDecoder().raw_decode(html, payload_position)
    if not isinstance(payload, dict):
        raise ValueError("latest release data was not an object")
    return payload


def format_release_value(value: object, precision: object) -> str:
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        if isinstance(precision, int) and precision >= 0:
            return f"{value:.{precision}f}"
        return str(value)
    return str(value)


def fetch_sp_global_flash_results() -> dict[str, dict[str, str]]:
    """Fetch the latest preliminary PMI values used to enrich flash events."""
    results: dict[str, dict[str, str]] = {}

    for series_key, url in SP_GLOBAL_RESULT_URLS.items():
        try:
            latest = parse_investing_latest_release(fetch_text(url))
            if latest.get("preliminary") is not True:
                continue

            occurrence_time = latest.get("occurrence_time")
            if not isinstance(occurrence_time, str):
                raise ValueError("latest release has no occurrence time")

            release_day = datetime.fromisoformat(
                occurrence_time.replace("Z", "+00:00")
            ).date()
            values = {
                "date": release_day.isoformat(),
                "result_source": "Investing.com",
                "result_url": url,
            }
            precision = latest.get("precision")
            for field in ("actual", "forecast", "previous"):
                value = latest.get(field)
                if value is not None:
                    values[field] = format_release_value(value, precision)

            if values.get("actual"):
                results[series_key] = values
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(
                f"warning: skipped S&P Global {series_key} results: {exc}",
                file=sys.stderr,
            )

    return results


def sp_global_flash_events(
    start: date,
    end: date,
    fetched_results: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    events = []
    series = (
        (
            "manufacturing",
            "S&P Global Flash US Manufacturing PMI",
            "美国S&P Global制造业PMI初值",
        ),
        (
            "services",
            "S&P Global Flash US Services PMI",
            "美国S&P Global服务业PMI初值",
        ),
    )

    for release in SP_GLOBAL_FLASH_RELEASES:
        day = date.fromisoformat(str(release["date"]))
        if not start <= day <= end:
            continue

        for series_key, title, title_cn in series:
            event = make_event(
                day=day,
                eastern_time="09:45",
                title=title,
                title_cn=title_cn,
                period=str(release["period"]),
                category="growth",
                source="S&P Global",
                url=str(release.get("url", SP_GLOBAL_PMI_CALENDAR_URL)),
            )
            values = release.get(series_key, {})
            fetched_values = (fetched_results or {}).get(series_key, {})
            if fetched_values.get("date") == release["date"]:
                values = {**values, **fetched_values}
            if isinstance(values, dict):
                for field in (
                    "actual",
                    "forecast",
                    "previous",
                    "result_source",
                    "result_url",
                ):
                    value = values.get(field)
                    if value not in (None, ""):
                        event[field] = str(value)
            if event.get("actual"):
                event["release_status"] = "released"
            events.append(event)

    return events


def dedupe(events: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str, str]] = set()
    unique = []
    for event in sorted(events, key=lambda item: (item["date"], item["time_et"], item["title"])):
        key = (event["date"], event["time_et"], event["title"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def build_calendar(start: date, days: int, offline: bool) -> list[dict[str, str]]:
    end = start + timedelta(days=days)
    events: list[dict[str, str]] = []
    sp_global_results: dict[str, dict[str, str]] = {}

    if offline:
        events.extend(bls_fallback_events(start, end))
        events.extend(bea_fallback_events(start, end))
        events.extend(census_durable_goods_fallback_events(start, end))
    else:
        sp_global_results = fetch_sp_global_flash_results()
        for name, parser in (("BLS", parse_bls_events), ("BEA", parse_bea_events)):
            try:
                parsed_events = parser(start, end)
                events.extend(parsed_events)
                if name == "BLS" and not parsed_events:
                    events.extend(bls_fallback_events(start, end))
                if name == "BEA" and not parsed_events:
                    events.extend(bea_fallback_events(start, end))
            except (URLError, TimeoutError, OSError, ValueError, IncompleteRead) as exc:
                print(f"warning: skipped {name}: {exc}", file=sys.stderr)
                if name == "BLS":
                    events.extend(bls_fallback_events(start, end))
                if name == "BEA":
                    events.extend(bea_fallback_events(start, end))

        try:
            census_events = parse_census_durable_goods_events(start, end)
            events.extend(census_events)
            if not census_events:
                events.extend(census_durable_goods_fallback_events(start, end))
        except (URLError, TimeoutError, OSError, ValueError, IncompleteRead) as exc:
            print(f"warning: skipped Census M3: {exc}", file=sys.stderr)
            events.extend(census_durable_goods_fallback_events(start, end))

    events.extend(fomc_events(start, end))
    events.extend(census_retail_events(start, end))
    events.extend(ism_events(start, end))
    events.extend(sp_global_flash_events(start, end, sp_global_results))

    if not offline:
        try:
            market_events = parse_forex_factory_calendar(
                fetch_text(FOREX_FACTORY_CALENDAR_URL)
            )
            enrich_events_with_market_values(events, market_events)
        except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"warning: skipped market reference values: {exc}", file=sys.stderr)

    return dedupe(events)


def merge_existing_reference_values(
    events: list[dict[str, str]],
    output_path: Path,
) -> list[dict[str, str]]:
    """Keep previously collected values until a fresher feed replaces them."""
    if not output_path.exists():
        return events
    try:
        existing = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return events
    if not isinstance(existing, list):
        return events

    existing_by_key = {
        (item.get("date"), item.get("time_et"), item.get("title")): item
        for item in existing
        if isinstance(item, dict)
    }
    carry_fields = (
        "actual",
        "forecast",
        "previous",
        "result_source",
        "result_url",
        "release_status",
    )
    for event in events:
        prior = existing_by_key.get(
            (event.get("date"), event.get("time_et"), event.get("title"))
        )
        if not prior:
            continue
        for field in carry_fields:
            if event.get(field) in (None, "") and prior.get(field) not in (None, ""):
                event[field] = str(prior[field])
    return events


def apply_official_release_overrides(events: list[dict[str, str]]) -> None:
    """Apply verified BLS outcomes after any live-feed or cache fallback."""
    for event in events:
        key = (event.get("date"), event.get("time_et"), event.get("title"))
        override = OFFICIAL_RELEASE_OVERRIDES.get(key)
        if override:
            event.update(override)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        default=date.today().isoformat(),
        help="Reference date used for the rolling calendar window (YYYY-MM-DD).",
    )
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Number of recently published calendar days to retain.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    reference_date = date.fromisoformat(args.start)
    start = reference_date - timedelta(days=args.lookback_days)
    events = build_calendar(
        start,
        args.days + args.lookback_days,
        args.offline,
    )
    events = merge_existing_reference_values(events, args.output)
    apply_official_release_overrides(events)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(events)} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
