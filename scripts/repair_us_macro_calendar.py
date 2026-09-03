#!/usr/bin/env python3
"""Repair missing core BLS releases in the rolling U.S. macro calendar.

The primary updater prefers live BLS feeds. This repair layer keeps a small,
officially verified 2026 schedule for the site's core BLS series so a partial or
blocked BLS feed cannot silently remove a critical release such as nonfarm
payrolls from the calendar.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SITE_ROOT / "data" / "us-macro-calendar.json"
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_FORWARD_DAYS = 35

SERIES = {
    "Employment Situation": {
        "title_cn": "美国非农 / 失业率 / 平均时薪",
        "category": "jobs",
        "importance": "critical",
        "stars": 5,
        "url": "https://www.bls.gov/schedule/news_release/empsit.htm",
        "fallback_url": "https://fred.stlouisfed.org/release?rid=50",
        "fallback_label": "FRED 备用",
    },
    "Consumer Price Index": {
        "title_cn": "美国CPI / 核心CPI",
        "category": "inflation",
        "importance": "critical",
        "stars": 5,
        "url": "https://www.bls.gov/schedule/news_release/cpi.htm",
        "fallback_url": "https://fred.stlouisfed.org/release?rid=10",
        "fallback_label": "FRED 备用",
    },
    "Producer Price Index": {
        "title_cn": "美国PPI",
        "category": "inflation",
        "importance": "medium",
        "stars": 3,
        "url": "https://www.bls.gov/schedule/news_release/ppi.htm",
        "fallback_url": "https://fred.stlouisfed.org/release?rid=46",
        "fallback_label": "FRED 备用",
    },
    "Job Openings and Labor Turnover Survey": {
        "title_cn": "美国JOLTS职位空缺",
        "category": "jobs",
        "importance": "medium",
        "stars": 3,
        "url": "https://www.bls.gov/schedule/news_release/jolts.htm",
        "fallback_url": "https://fred.stlouisfed.org/series/JTSJOL",
        "fallback_label": "FRED 备用",
    },
}

# Dates and times below are copied from the official BLS 2026 release schedule.
# The live feed remains primary; these rows are only inserted when the primary
# calendar omitted the corresponding release.
OFFICIAL_BLS_2026 = [
    ("2026-09-01", "10:00", "Job Openings and Labor Turnover Survey", "July 2026"),
    ("2026-09-04", "08:30", "Employment Situation", "August 2026"),
    ("2026-09-10", "08:30", "Producer Price Index", "August 2026"),
    ("2026-09-11", "08:30", "Consumer Price Index", "August 2026"),
    ("2026-09-29", "10:00", "Job Openings and Labor Turnover Survey", "August 2026"),
    ("2026-10-02", "08:30", "Employment Situation", "September 2026"),
    ("2026-10-14", "08:30", "Consumer Price Index", "September 2026"),
    ("2026-10-15", "08:30", "Producer Price Index", "September 2026"),
    ("2026-11-03", "10:00", "Job Openings and Labor Turnover Survey", "September 2026"),
    ("2026-11-06", "08:30", "Employment Situation", "October 2026"),
    ("2026-11-10", "08:30", "Consumer Price Index", "October 2026"),
    ("2026-11-13", "08:30", "Producer Price Index", "October 2026"),
    ("2026-12-01", "10:00", "Job Openings and Labor Turnover Survey", "October 2026"),
    ("2026-12-04", "08:30", "Employment Situation", "November 2026"),
    ("2026-12-10", "08:30", "Consumer Price Index", "November 2026"),
    ("2026-12-15", "08:30", "Producer Price Index", "November 2026"),
]


def shanghai_fields(day: date, eastern_time: str) -> tuple[str, str]:
    hour, minute = (int(part) for part in eastern_time.split(":"))
    eastern = datetime.combine(
        day,
        time(hour, minute),
        tzinfo=ZoneInfo("America/New_York"),
    )
    shanghai = eastern.astimezone(ZoneInfo("Asia/Shanghai"))
    return shanghai.date().isoformat(), shanghai.strftime("%H:%M")


def make_event(day_text: str, eastern_time: str, title: str, period: str) -> dict:
    day = date.fromisoformat(day_text)
    config = SERIES[title]
    shanghai_date, shanghai_time = shanghai_fields(day, eastern_time)
    event = {
        "date": shanghai_date,
        "time_et": eastern_time,
        "time_shanghai": shanghai_time,
        "title": title,
        "title_cn": config["title_cn"],
        "period": period,
        "category": config["category"],
        "importance": config["importance"],
        "stars": config["stars"],
        "source": "BLS",
        "url": config["url"],
        "fallback_url": config["fallback_url"],
        "fallback_label": config["fallback_label"],
    }
    if shanghai_date != day_text:
        event["date_et"] = day_text
    return event


def repair_events(events: list[dict], reference_date: date) -> tuple[list[dict], list[str]]:
    start = reference_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)
    end = reference_date + timedelta(days=DEFAULT_FORWARD_DAYS)
    existing = {
        (str(item.get("date")), str(item.get("time_et")), str(item.get("title")))
        for item in events
        if isinstance(item, dict)
    }
    repaired = list(events)
    added: list[str] = []

    for day_text, eastern_time, title, period in OFFICIAL_BLS_2026:
        day = date.fromisoformat(day_text)
        if not start <= day <= end:
            continue
        candidate = make_event(day_text, eastern_time, title, period)
        key = (candidate["date"], candidate["time_et"], candidate["title"])
        if key in existing:
            continue
        repaired.append(candidate)
        existing.add(key)
        added.append(f"{day_text}:{title}")

    repaired.sort(
        key=lambda item: (
            str(item.get("date", "")),
            str(item.get("time_shanghai", item.get("time_et", ""))),
            str(item.get("title", "")),
        )
    )
    return repaired, added


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=date.today().isoformat(), help="Reference date (YYYY-MM-DD).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        events = json.loads(args.output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"cannot repair U.S. macro calendar: {exc}")
    if not isinstance(events, list):
        raise SystemExit("cannot repair U.S. macro calendar: root must be a list")

    repaired, added = repair_events(events, date.fromisoformat(args.date))
    if added:
        args.output.write_text(json.dumps(repaired, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("repaired missing BLS releases: " + ", ".join(added))
    else:
        print("BLS core release coverage is complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
