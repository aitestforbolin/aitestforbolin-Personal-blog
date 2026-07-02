#!/usr/bin/env python3
"""Build the static U.S. macro calendar JSON for the personal site."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SITE_ROOT / "data" / "us-macro-calendar.json"
EASTERN_TO_SHANGHAI_HOURS = 12
DEFAULT_DAYS = 35

BLS_ICS_URL = "https://www.bls.gov/schedule/news_release/bls.ics"
BLS_MONTH_URL = "https://www.bls.gov/schedule/{year}/{month:02d}_sched.htm"
BEA_SCHEDULE_URL = "https://www.bea.gov/news/schedule"
FED_CALENDAR_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
CENSUS_CALENDAR_URL = "https://www.census.gov/economic-indicators/"
ISM_REPORTS_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"
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
        "importance": "high",
    },
    {
        "needle": "Producer Price Index",
        "title_cn": "美国PPI",
        "category": "inflation",
        "importance": "high",
    },
    {
        "needle": "Employment Situation",
        "title_cn": "美国非农 / 失业率 / 平均时薪",
        "category": "jobs",
        "importance": "high",
    },
    {
        "needle": "Job Openings and Labor Turnover",
        "title_cn": "美国JOLTS职位空缺",
        "category": "jobs",
        "importance": "high",
    },
    {
        "needle": "Personal Income and Outlays",
        "title_cn": "美国PCE / 核心PCE",
        "category": "inflation",
        "importance": "high",
    },
    {
        "needle": "GDP",
        "title_cn": "美国GDP",
        "category": "growth",
        "importance": "high",
    },
    {
        "needle": "Advance Monthly Sales for Retail and Food Services",
        "title_cn": "美国零售销售",
        "category": "growth",
        "importance": "high",
    },
]

FOMC_MEETINGS = [
    ("2026-06-17", "June 2026 meeting", True),
    ("2026-07-29", "July 2026 meeting", False),
    ("2026-09-16", "September 2026 meeting", True),
    ("2026-10-28", "October 2026 meeting", False),
    ("2026-12-09", "December 2026 meeting", True),
]

# Census does not expose a simple static JSON endpoint on the briefing page.
# Keep the core retail-sales release dates here as a stable fallback.
CENSUS_RETAIL_RELEASES = [
    ("2026-06-17", "May 2026"),
    ("2026-07-16", "June 2026"),
    ("2026-08-14", "July 2026"),
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
        "Personal Income and Outlays",
        "June 2026",
        "美国PCE / 核心PCE",
    ),
    (
        "2026-07-30",
        "08:30",
        "Gross Domestic Product, 2nd Quarter 2026 (Advance Estimate)",
        "Q2 2026",
        "美国GDP",
    ),
    (
        "2026-08-27",
        "08:30",
        "Gross Domestic Product, 2nd Quarter 2026 (Second Estimate)",
        "Q2 2026",
        "美国GDP",
    ),
    (
        "2026-08-28",
        "08:30",
        "Personal Income and Outlays",
        "July 2026",
        "美国PCE / 核心PCE",
    ),
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
        if rule["needle"].lower() in title.lower():
            return rule
    return None


def shanghai_fields(day: date, eastern_time: str) -> tuple[str, str]:
    hour, minute = [int(part) for part in eastern_time.split(":")]
    eastern_dt = datetime.combine(day, time(hour, minute))
    shanghai_dt = eastern_dt + timedelta(hours=EASTERN_TO_SHANGHAI_HOURS)
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
    importance: str = "high",
) -> dict[str, str]:
    shanghai_date, shanghai_time = shanghai_fields(day, eastern_time)
    event = {
        "date": day.isoformat(),
        "time_et": eastern_time,
        "time_shanghai": shanghai_time,
        "title": title,
        "title_cn": title_cn,
        "period": period,
        "category": category,
        "importance": importance,
        "source": source,
        "url": url,
    }
    if shanghai_date != day.isoformat():
        event["date_shanghai"] = shanghai_date
    return event


def parse_bls_events(start: date, end: date) -> list[dict[str, str]]:
    try:
        return parse_bls_ics_events(start, end)
    except (URLError, TimeoutError, OSError, ValueError):
        try:
            return parse_bls_month_pages(start, end)
        except (URLError, TimeoutError, OSError, ValueError):
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
                )
            )
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

    if offline:
        events.extend(bls_fallback_events(start, end))
        events.extend(bea_fallback_events(start, end))
    else:
        for name, parser in (("BLS", parse_bls_events), ("BEA", parse_bea_events)):
            try:
                parsed_events = parser(start, end)
                events.extend(parsed_events)
                if name == "BLS" and not parsed_events:
                    events.extend(bls_fallback_events(start, end))
                if name == "BEA" and not parsed_events:
                    events.extend(bea_fallback_events(start, end))
            except (URLError, TimeoutError, OSError, ValueError) as exc:
                print(f"warning: skipped {name}: {exc}", file=sys.stderr)
                if name == "BLS":
                    events.extend(bls_fallback_events(start, end))
                if name == "BEA":
                    events.extend(bea_fallback_events(start, end))

    events.extend(fomc_events(start, end))
    events.extend(census_retail_events(start, end))
    events.extend(ism_events(start, end))
    return dedupe(events)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=date.today().isoformat())
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()

    start = date.fromisoformat(args.start)
    events = build_calendar(start, args.days, args.offline)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(events)} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
