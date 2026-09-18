"""FOMC meeting identity and FedWatch freshness rules shared by briefing jobs."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


NEW_YORK = ZoneInfo("America/New_York")

# Meeting end timestamps are the scheduled policy-decision time in New York.
# Keeping the year in the record (rather than selecting a month) makes the
# December-to-January rollover deterministic. Refresh this official schedule
# when the Federal Reserve publishes an additional calendar year.
FOMC_MEETINGS = (
    ("2026-01-27", "2026-01-28T14:00:00-05:00"), ("2026-03-17", "2026-03-18T14:00:00-04:00"),
    ("2026-04-28", "2026-04-29T14:00:00-04:00"), ("2026-06-16", "2026-06-17T14:00:00-04:00"),
    ("2026-07-28", "2026-07-29T14:00:00-04:00"), ("2026-09-15", "2026-09-16T14:00:00-04:00"),
    ("2026-10-27", "2026-10-28T14:00:00-04:00"), ("2026-12-08", "2026-12-09T14:00:00-05:00"),
    ("2027-01-26", "2027-01-27T14:00:00-05:00"), ("2027-03-16", "2027-03-17T14:00:00-04:00"),
    ("2027-04-27", "2027-04-28T14:00:00-04:00"), ("2027-06-08", "2027-06-09T14:00:00-04:00"),
    ("2027-07-27", "2027-07-28T14:00:00-04:00"), ("2027-09-14", "2027-09-15T14:00:00-04:00"),
    ("2027-10-26", "2027-10-27T14:00:00-04:00"), ("2027-12-07", "2027-12-08T14:00:00-05:00"),
    ("2028-01-25", "2028-01-26T14:00:00-05:00"),
)


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str): return None
    try: parsed = datetime.fromisoformat(value)
    except ValueError: return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=NEW_YORK)


def meeting_label(start_date: str, end_timestamp: str) -> str:
    end = parse_timestamp(end_timestamp)
    if end is None: return "FOMC 会议日期待核验"
    start = datetime.fromisoformat(start_date).date()
    return f"{start.year}年{start.month}月FOMC（{start.month}月{start.day}日—{end.month}月{end.day}日）"


def next_unfinished_fomc(now: datetime) -> dict | None:
    """Return the first meeting whose decision time has not passed."""
    if now.tzinfo is None: now = now.replace(tzinfo=NEW_YORK)
    for start_date, end_timestamp in FOMC_MEETINGS:
        end = parse_timestamp(end_timestamp)
        if end and end >= now.astimezone(end.tzinfo):
            return {"meetingStartDate": start_date, "meetingEndDate": end_timestamp,
                    "meetingLabel": meeting_label(start_date, end_timestamp)}
    return None


def build_fedwatch_target(now: datetime) -> dict:
    meeting = next_unfinished_fomc(now); checked_at = now.isoformat(timespec="seconds")
    if not meeting:
        return {"status": "unavailable", "reason": "无法确定下一场尚未结束的 FOMC 会议",
                "checkedAt": checked_at, "probabilities": {}, "source": "CME FedWatch"}
    return {**meeting, "status": "requires_model_verification",
            "reason": "须核验该场会议对应的 CME FedWatch 概率；禁止使用已结束会议的数据",
            "checkedAt": checked_at, "probabilities": {}, "source": "CME FedWatch"}


def fedwatch_is_stale(row: object, now: datetime) -> bool:
    """A missing, malformed, or already-ended meeting is never publishable."""
    if not isinstance(row, dict): return True
    end = parse_timestamp(row.get("meetingEndDate"))
    if end is None: return True
    if now.tzinfo is None: now = now.replace(tzinfo=NEW_YORK)
    return end < now.astimezone(end.tzinfo)


def fedwatch_is_publishable(row: object, now: datetime) -> bool:
    return (isinstance(row, dict) and row.get("status") == "available"
            and not fedwatch_is_stale(row, now) and isinstance(row.get("probabilities"), dict)
            and bool(row["probabilities"]))
