#!/usr/bin/env python3
"""Build the rolling China macro and policy calendar from official schedules."""

from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SITE_ROOT / "data" / "china-macro-calendar.json"
DEFAULT_DAYS = 35
DEFAULT_LOOKBACK_DAYS = 7

NBS_SCHEDULE_URL = (
    "https://www.stats.gov.cn/xw/tjxw/tzgg/202512/"
    "t20251224_1962137.html"
)
NBS_RELEASE_URL = "https://www.stats.gov.cn/sj/zxfb/"
PBC_STATISTICS_URL = "https://www.pbc.gov.cn/diaochatongjisi/116219/index.html"
PBC_LPR_URL = (
    "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/index.html"
)
CUSTOMS_SCHEDULE_URL = (
    "https://www.customs.gov.cn/customs/2026-03/11/"
    "article_2026031116150585435.html"
)
SP_GLOBAL_CALENDAR_URL = "https://www.pmi.spglobal.com/Public/Release/ReleaseDates"
SP_GLOBAL_RATINGDOG_JULY_URL = (
    "https://www.pmi.spglobal.com/Public/Home/PressRelease/"
    "402fe5cf21e94c2d83e7c7b5cc6fe2ea"
)
XINHUA_POLITBURO_JULY_URL = (
    "https://www.news.cn/politics/leaders/20260730/"
    "692072ba72864513854aae87c6a6abc9/c.html"
)

IMPORTANCE_BY_STARS = {
    1: "background",
    2: "low",
    3: "medium",
    4: "high",
    5: "critical",
}
DATE_STATUSES = {"confirmed", "after_confirmed", "window", "tentative"}


def make_event(
    *,
    event_id: str,
    day: str,
    title: str,
    period: str,
    category: str,
    stars: int,
    source: str,
    source_url: str,
    time_shanghai: str = "",
    date_status: str = "confirmed",
    date_end: str | None = None,
    actual: str | None = None,
    forecast: str | None = None,
    previous: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    if stars not in IMPORTANCE_BY_STARS:
        raise ValueError("event stars must be between 1 and 5")
    if date_status not in DATE_STATUSES:
        raise ValueError(f"unsupported date status: {date_status}")

    scheduled_at = None
    if time_shanghai and date_status in {"confirmed", "after_confirmed"}:
        scheduled_at = f"{day}T{time_shanghai}:00+08:00"

    event: dict[str, Any] = {
        "id": event_id,
        "country": "CN",
        "date": day,
        "date_end": date_end or day,
        "dateStatus": date_status,
        "date_status": date_status,
        "scheduledAt": scheduled_at,
        "time_shanghai": time_shanghai,
        "title": title,
        "title_cn": title,
        "period": period,
        "category": category,
        "importance": IMPORTANCE_BY_STARS[stars],
        "stars": stars,
        "source": source,
        "sourceUrl": source_url,
        "url": source_url,
        "metrics": [],
    }
    metric: dict[str, str] = {"name": title}
    for field, value in (
        ("actual", actual),
        ("forecast", forecast),
        ("previous", previous),
    ):
        if value not in (None, ""):
            event[field] = value
            metric[field] = value
    if len(metric) > 1:
        event["metrics"] = [metric]
    if note:
        event["note"] = note

    if actual not in (None, "") or date_status == "after_confirmed":
        event["release_status"] = "released"
        event["releasedAt"] = scheduled_at
    else:
        event["release_status"] = "scheduled"
        event["releasedAt"] = None
    return event


CHINA_RELEASES_2026 = [
    make_event(
        event_id="CN-2026-07-industrial-profits",
        day="2026-07-27",
        time_shanghai="09:30",
        title="中国规模以上工业企业利润",
        period="2026年1—6月",
        category="profits",
        stars=3,
        source="国家统计局",
        source_url=NBS_RELEASE_URL,
        actual="同比 +18.7%",
    ),
    make_event(
        event_id="CN-2026-07-politburo-economy",
        day="2026-07-30",
        title="中共中央政治局经济形势与经济工作会议",
        period="2026年下半年经济工作",
        category="policy",
        stars=5,
        source="新华社",
        source_url=XINHUA_POLITBURO_JULY_URL,
        date_status="after_confirmed",
        note="会议日期在会后由新华社确认，不作为提前公布的确定日程。",
    ),
    make_event(
        event_id="CN-2026-07-official-manufacturing-pmi",
        day="2026-07-31",
        time_shanghai="09:30",
        title="中国官方制造业 PMI",
        period="2026年7月",
        category="pmi",
        stars=5,
        source="国家统计局",
        source_url=(
            "https://www.stats.gov.cn/sj/zxfb/202607/"
            "t20260731_1964253.html"
        ),
        actual="49.2",
        previous="50.3",
    ),
    make_event(
        event_id="CN-2026-07-official-nonmanufacturing-pmi",
        day="2026-07-31",
        time_shanghai="09:30",
        title="中国官方非制造业 PMI",
        period="2026年7月",
        category="pmi",
        stars=4,
        source="国家统计局",
        source_url=(
            "https://www.stats.gov.cn/sj/zxfb/202607/"
            "t20260731_1964253.html"
        ),
        actual="49.0",
        previous="50.2",
    ),
    make_event(
        event_id="CN-2026-07-ratingdog-manufacturing-pmi",
        day="2026-08-03",
        time_shanghai="09:45",
        title="中国 RatingDog 制造业 PMI",
        period="2026年7月",
        category="pmi",
        stars=4,
        source="S&P Global PMI",
        source_url=SP_GLOBAL_RATINGDOG_JULY_URL,
        actual="50.9",
        forecast="51.5",
        previous="51.7",
    ),
    make_event(
        event_id="CN-2026-07-ratingdog-services-pmi",
        day="2026-08-05",
        time_shanghai="09:45",
        title="中国 RatingDog 服务业 PMI",
        period="2026年7月",
        category="pmi",
        stars=4,
        source="S&P Global PMI",
        source_url=SP_GLOBAL_CALENDAR_URL,
    ),
    make_event(
        event_id="CN-2026-07-trade",
        day="2026-08-07",
        time_shanghai="11:00",
        title="中国进出口与贸易差额",
        period="2026年7月",
        category="trade",
        stars=4,
        source="海关总署",
        source_url=CUSTOMS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-07-cpi-ppi",
        day="2026-08-09",
        time_shanghai="09:30",
        title="中国 CPI / PPI",
        period="2026年7月",
        category="inflation",
        stars=5,
        source="国家统计局",
        source_url=NBS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-07-credit-window",
        day="2026-08-10",
        date_end="2026-08-17",
        title="中国新增社融 / 人民币贷款 / M2",
        period="2026年7月",
        category="credit",
        stars=5,
        source="中国人民银行",
        source_url=PBC_STATISTICS_URL,
        date_status="window",
        note="人民银行未预告精确发布日期；按月中常见发布节奏设置观察窗口。",
    ),
    make_event(
        event_id="CN-2026-07-70-city-prices",
        day="2026-08-14",
        time_shanghai="09:30",
        title="中国 70 城商品住宅销售价格",
        period="2026年7月",
        category="housing",
        stars=3,
        source="国家统计局",
        source_url=NBS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-07-activity",
        day="2026-08-17",
        time_shanghai="10:00",
        title="中国工业增加值 / 社零 / 固投",
        period="2026年7月",
        category="growth",
        stars=5,
        source="国家统计局",
        source_url=NBS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-08-lpr",
        day="2026-08-20",
        time_shanghai="09:00",
        title="中国贷款市场报价利率（LPR）",
        period="2026年8月",
        category="rates",
        stars=5,
        source="中国人民银行",
        source_url=PBC_LPR_URL,
    ),
    make_event(
        event_id="CN-2026-07-industrial-profits-next",
        day="2026-08-27",
        time_shanghai="09:30",
        title="中国规模以上工业企业利润",
        period="2026年1—7月",
        category="profits",
        stars=3,
        source="国家统计局",
        source_url=NBS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-08-official-manufacturing-pmi",
        day="2026-08-31",
        time_shanghai="09:30",
        title="中国官方制造业 PMI",
        period="2026年8月",
        category="pmi",
        stars=5,
        source="国家统计局",
        source_url=NBS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-08-official-nonmanufacturing-pmi",
        day="2026-08-31",
        time_shanghai="09:30",
        title="中国官方非制造业 PMI",
        period="2026年8月",
        category="pmi",
        stars=4,
        source="国家统计局",
        source_url=NBS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-08-ratingdog-manufacturing-pmi",
        day="2026-09-01",
        time_shanghai="09:45",
        title="中国 RatingDog 制造业 PMI",
        period="2026年8月",
        category="pmi",
        stars=4,
        source="S&P Global PMI",
        source_url=SP_GLOBAL_CALENDAR_URL,
    ),
    make_event(
        event_id="CN-2026-08-ratingdog-services-pmi",
        day="2026-09-03",
        time_shanghai="09:45",
        title="中国 RatingDog 服务业 PMI",
        period="2026年8月",
        category="pmi",
        stars=4,
        source="S&P Global PMI",
        source_url=SP_GLOBAL_CALENDAR_URL,
    ),
    make_event(
        event_id="CN-2026-Q3-gdp",
        day="2026-10-19",
        time_shanghai="10:00",
        title="中国季度 GDP / 工业增加值 / 社零 / 固投",
        period="2026年三季度",
        category="growth",
        stars=5,
        source="国家统计局",
        source_url=NBS_SCHEDULE_URL,
    ),
    make_event(
        event_id="CN-2026-12-politburo-window",
        day="2026-12-01",
        date_end="2026-12-07",
        title="中共中央政治局经济工作会议观察窗口",
        period="2027年经济工作定调",
        category="policy",
        stars=5,
        source="新华社 / 中国政府网",
        source_url="https://www.gov.cn/yaowen/",
        date_status="window",
        note="仅按往年惯例设置观察窗口，精确日期待会后官方确认。",
    ),
    make_event(
        event_id="CN-2026-central-economic-work-conference-window",
        day="2026-12-08",
        date_end="2026-12-12",
        title="中央经济工作会议观察窗口",
        period="2027年经济工作部署",
        category="policy",
        stars=5,
        source="新华社 / 中国政府网",
        source_url="https://www.gov.cn/yaowen/",
        date_status="window",
        note="仅按惯例设置观察窗口，不代表官方已公布日期。",
    ),
]


def build_calendar(start: date, days: int) -> list[dict[str, Any]]:
    end = start + timedelta(days=days)
    events = []
    for event in CHINA_RELEASES_2026:
        event_start = date.fromisoformat(str(event["date"]))
        event_end = date.fromisoformat(str(event.get("date_end", event["date"])))
        if event_end >= start and event_start <= end:
            events.append(dict(event))
    return sorted(
        events,
        key=lambda item: (
            str(item["date"]),
            str(item.get("time_shanghai") or "99:99"),
            str(item["title"]),
        ),
    )


def merge_existing_values(
    events: list[dict[str, Any]],
    output_path: Path,
) -> list[dict[str, Any]]:
    if not output_path.exists():
        return events
    try:
        existing = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return events
    if not isinstance(existing, list):
        return events

    existing_by_id = {
        item.get("id"): item
        for item in existing
        if isinstance(item, dict) and item.get("id")
    }
    carry_fields = (
        "actual",
        "forecast",
        "previous",
        "metrics",
        "release_status",
        "releasedAt",
    )
    for event in events:
        prior = existing_by_id.get(event.get("id"))
        if not prior:
            continue
        for field in carry_fields:
            if event.get(field) in (None, "", []) and prior.get(field) not in (
                None,
                "",
                [],
            ):
                event[field] = prior[field]
    return events


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
        help="Number of recent Beijing-calendar days to retain.",
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    reference_date = date.fromisoformat(args.start)
    start = reference_date - timedelta(days=args.lookback_days)
    events = build_calendar(start, args.days + args.lookback_days)
    events = merge_existing_values(events, args.output)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(events)} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
