#!/usr/bin/env python3
"""Build and validate the AI, cloud and semiconductor earnings calendar."""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


SITE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = SITE_ROOT / "data" / "tech-company-event-sources.json"
CURATED_EVENTS = SITE_ROOT / "data" / "tech-company-events-curated.json"
DEFAULT_OUTPUT = SITE_ROOT / "data" / "tech-company-events.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_DAYS = 35
REQUEST_TIMEOUT_SECONDS = 12
MAX_RESPONSE_BYTES = 5_000_000
MAX_DETAIL_PAGES_PER_SOURCE = 4
NASDAQ_EARNINGS_URL = "https://api.nasdaq.com/api/calendar/earnings?date={day}"

EVENT_CATEGORIES = {"earnings"}
CONFIRMATION_LEVELS = {"confirmed", "guided", "inferred"}
IMPORTANCE_LEVELS = {"core", "important"}
STATUS_LEVELS = {"scheduled", "changed", "cancelled"}

MONTH_PATTERN = (
    r"January|February|March|April|May|June|July|August|September|October|"
    r"November|December|Jan\.?|Feb\.?|Mar\.?|Apr\.?|Jun\.?|Jul\.?|Aug\.?|"
    r"Sep\.?|Sept\.?|Oct\.?|Nov\.?|Dec\.?"
)
DATE_PATTERN = re.compile(
    rf"\b(?P<month>{MONTH_PATTERN})\s+(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:[,]?\s+(?P<year>20\d{{2}}))?\b",
    re.IGNORECASE,
)
NUMERIC_DATE_PATTERN = re.compile(r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>20\d{2})\b")
TIME_PATTERN = re.compile(
    r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*"
    r"(?P<meridiem>a\.?m\.?|p\.?m\.?)\s*"
    r"(?P<zone>Pacific Time|Eastern Time|Central Time|Mountain Time|PT|PST|PDT|ET|EST|EDT|CT|CST|CDT|MT|MST|MDT)?",
    re.IGNORECASE,
)

EARNINGS_PATTERN = re.compile(
    r"earnings|financial results|financial call|quarterly results|results conference call|"
    r"report.{0,50}(?:fiscal|first|second|third|fourth).{0,30}quarter.{0,30}results",
    re.IGNORECASE,
)

TIMEZONE_ALIASES = {
    "pacific time": "America/Los_Angeles",
    "pt": "America/Los_Angeles",
    "pst": "America/Los_Angeles",
    "pdt": "America/Los_Angeles",
    "eastern time": "America/New_York",
    "et": "America/New_York",
    "est": "America/New_York",
    "edt": "America/New_York",
    "central time": "America/Chicago",
    "ct": "America/Chicago",
    "cst": "America/Chicago",
    "cdt": "America/Chicago",
    "mountain time": "America/Denver",
    "mt": "America/Denver",
    "mst": "America/Denver",
    "mdt": "America/Denver",
}


class PageParser(HTMLParser):
    """Collect links, visible text, and machine-readable time values."""

    def __init__(self) -> None:
        super().__init__()
        self.links: List[Tuple[str, str]] = []
        self.time_values: List[Tuple[str, int, str]] = []
        self._hidden_depth = 0
        self.text_parts: List[str] = []
        self._href: Optional[str] = None
        self._anchor_parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: Sequence[Tuple[str, Optional[str]]]) -> None:
        attributes = dict(attrs)
        if tag.lower() in {"script", "style", "noscript"}:
            self._hidden_depth += 1
        if self._hidden_depth:
            return
        if tag.lower() == "a":
            self._href = attributes.get("href")
            self._anchor_parts = []
        if tag.lower() == "time" and attributes.get("datetime"):
            self.time_values.append((str(attributes["datetime"]), sum(len(part) + 1 for part in self.text_parts), str(attributes.get("itemprop") or "")))

    def handle_data(self, data: str) -> None:
        if self._hidden_depth:
            return
        text = " ".join(data.split())
        if not text:
            return
        self.text_parts.append(text)
        if self._href is not None:
            self._anchor_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript"}:
            self._hidden_depth = max(0, self._hidden_depth - 1)
            return
        if self._hidden_depth:
            return
        if tag.lower() != "a" or self._href is None:
            return
        self.links.append((self._href, " ".join(self._anchor_parts).strip()))
        self._href = None
        self._anchor_parts = []


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "whybolin-personal-site-tech-calendar/1.0 (public-source monitor)",
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise OSError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
        encoding = response.headers.get_content_charset() or "utf-8"
    return body.decode(encoding, errors="replace")


def parse_page(html: str) -> PageParser:
    parser = PageParser()
    parser.feed(html)
    return parser




def is_material_title(title: str) -> bool:
    return bool(EARNINGS_PATTERN.search(" ".join(title.split())))


def normalize_domain(value: str) -> str:
    hostname = (urlparse(value).hostname or "").lower()
    return hostname[4:] if hostname.startswith("www.") else hostname


def domain_allowed(url: str, allowed_domains: Iterable[str]) -> bool:
    hostname = normalize_domain(url)
    return any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains)


def month_number(value: str) -> int:
    cleaned = value.lower().rstrip(".")
    months = {
        "january": 1,
        "jan": 1,
        "february": 2,
        "feb": 2,
        "march": 3,
        "mar": 3,
        "april": 4,
        "apr": 4,
        "may": 5,
        "june": 6,
        "jun": 6,
        "july": 7,
        "jul": 7,
        "august": 8,
        "aug": 8,
        "september": 9,
        "sep": 9,
        "sept": 9,
        "october": 10,
        "oct": 10,
        "november": 11,
        "nov": 11,
        "december": 12,
        "dec": 12,
    }
    return months[cleaned]


def parse_iso_datetime(value: str, default_timezone: str) -> Optional[datetime]:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo(default_timezone))
    return parsed


def natural_date_candidates(text: str, year: int) -> List[Tuple[date, int]]:
    candidates: List[Tuple[date, int]] = []
    for match in DATE_PATTERN.finditer(text):
        try:
            day = date(int(match.group("year") or year), month_number(match.group("month")), int(match.group("day")))
        except ValueError:
            continue
        candidates.append((day, match.start()))
    for match in NUMERIC_DATE_PATTERN.finditer(text):
        try:
            day = date(int(match.group("year")), int(match.group("month")), int(match.group("day")))
        except ValueError:
            continue
        candidates.append((day, match.start()))
    return sorted(set(candidates), key=lambda item: item[1])


def select_event_date(
    parser: PageParser, text: str, default_timezone: str, start: date, end: date
) -> Tuple[Optional[date], Optional[datetime], int]:
    """Use explicit event dates; never substitute a publication or replay date."""
    negative = re.compile(r"(?:replay|available until|archiv|published|posted|released|quarter.{0,25}end)[^.]{0,70}$", re.I)
    positive = re.compile(
        r"(?:will|to)\s+(?:report|announce|release|hold|host|conduct).{0,180}|"
        r"(?:conference call|webcast).{0,100}(?:on|begin|take place|held).{0,40}|"
        r"(?:date|when)\s*:\s*.{0,25}$", re.I,
    )
    for year in sorted({start.year, end.year}):
        for day, position in natural_date_candidates(text, year):
            if not start - timedelta(days=1) <= day <= end:
                continue
            before = text[max(0, position - 200):position]
            if not negative.search(before) and positive.search(before):
                return day, None, position
    for raw_value, position, kind in parser.time_values:
        if kind.lower() in {"datepublished", "datemodified"}:
            continue
        parsed = parse_iso_datetime(raw_value, default_timezone)
        if parsed and (parsed.hour or parsed.minute) and start - timedelta(days=1) <= parsed.date() <= end:
            before = text[max(0, position - 100):position]
            if not negative.search(before):
                return parsed.date(), parsed, position
    return None, None, 0


def time_from_context(text: str, position: int, default_timezone: str) -> Tuple[Optional[time], str]:
    context = text[position : position + 350]
    match = TIME_PATTERN.search(context)
    if not match:
        before = text[max(0, position - 100) : position]
        if not re.search(r"published|posted|released|replay", before, re.I):
            match = TIME_PATTERN.search(before)
    if not match:
        return None, default_timezone

    hour = int(match.group("hour"))
    minute = int(match.group("minute") or 0)
    meridiem = match.group("meridiem").lower().replace(".", "")
    if meridiem == "pm" and hour != 12:
        hour += 12
    if meridiem == "am" and hour == 12:
        hour = 0
    zone_text = (match.group("zone") or "").lower()
    zone_name = TIMEZONE_ALIASES.get(zone_text, default_timezone)
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        return None, default_timezone
    return time(hour, minute), zone_name


def classify_event(title: str, body: str = "") -> Optional[str]:
    # A product page mentioning earnings elsewhere is not an earnings event.
    return "earnings" if is_material_title(title) else None


def extract_reported_period(text: str) -> Tuple[str, str]:
    ordinal_match = re.search(
        r"\b(?P<quarter>[1-4])(?:st|nd|rd|th)\s+Quarter\s+(?P<fiscal>FY\s*)?(?P<year>20\d{2}|\d{2})\b",
        text,
        re.IGNORECASE,
    )
    if ordinal_match:
        year_text = ordinal_match.group("year")
        year = int(year_text) + 2000 if len(year_text) == 2 else int(year_text)
        quarter = ordinal_match.group("quarter")
        fiscal_prefix = "FY" if ordinal_match.group("fiscal") else ""
        return f"{fiscal_prefix}{year} Q{quarter}", f"{fiscal_prefix.lower()}{year}-q{quarter}"

    fiscal_match = re.search(
        r"(?:fiscal(?: year)?\s*)?(?:FY\s*)?(20\d{2}|\d{2})[^A-Za-z0-9]{0,8}"
        r"(?:Q([1-4])|(first|second|third|fourth)[ -]?quarter)",
        text,
        re.IGNORECASE,
    )
    if not fiscal_match:
        fiscal_match = re.search(
            r"(?:Q([1-4])|(first|second|third|fourth))[ -]?(?:quarter)?[^A-Za-z0-9]{0,8}"
            r"(?:FY\s*)?(20\d{2}|\d{2})",
            text,
            re.IGNORECASE,
        )
        if fiscal_match:
            quarter = fiscal_match.group(1) or {
                "first": "1",
                "second": "2",
                "third": "3",
                "fourth": "4",
            }[fiscal_match.group(2).lower()]
            year_text = fiscal_match.group(3)
            year = int(year_text) + 2000 if len(year_text) == 2 else int(year_text)
            label = f"{year} Q{quarter}"
            return label, f"{year}-q{quarter}"

    if fiscal_match:
        year_text = fiscal_match.group(1)
        year = int(year_text) + 2000 if len(year_text) == 2 else int(year_text)
        quarter = fiscal_match.group(2) or {
            "first": "1",
            "second": "2",
            "third": "3",
            "fourth": "4",
        }[fiscal_match.group(3).lower()]
        fiscal_prefix = "FY" if re.search(r"fiscal|\bFY", fiscal_match.group(0), re.IGNORECASE) else ""
        label = f"{fiscal_prefix}{year} Q{quarter}"
        return label, f"{fiscal_prefix.lower()}{year}-q{quarter}"

    return "", "upcoming"




def event_identity_and_name(
    company: Dict[str, Any], title: str, body: str, event_day: date
) -> Tuple[str, str, str]:
    period, slug = extract_reported_period(f"{title} {body[:1200]}")
    name = f"{company['name']} {period} 财报与电话会" if period else f"{company['name']} 财报与电话会"
    return f"{company['id']}-earnings-{slug}", name, period


def market_timing(text: str, exact_time: Optional[time]) -> str:
    lowered = text.lower()
    if "after market close" in lowered or "after the close of the market" in lowered:
        return "after_close"
    if "before market open" in lowered or "before the market opens" in lowered:
        return "before_open"
    return "scheduled_time" if exact_time else "time_tbd"


def build_discovered_event(
    company: Dict[str, Any],
    title: str,
    source_url: str,
    html: str,
    start: date,
    end: date,
) -> Optional[Dict[str, Any]]:
    parser = parse_page(html)
    text = " ".join(parser.text_parts)
    category = classify_event(title, text)
    if not category:
        return None

    event_day, machine_datetime, position = select_event_date(
        parser, text, company["default_timezone"], start, end
    )
    if not event_day:
        return None

    exact_time: Optional[time]
    timezone_name: str
    context_time, context_timezone = time_from_context(text, position, company["default_timezone"])
    if context_time:
        exact_time = context_time
        timezone_name = context_timezone
    elif machine_datetime and (machine_datetime.hour or machine_datetime.minute):
        exact_time = machine_datetime.timetz().replace(tzinfo=None)
        timezone_name = str(machine_datetime.tzinfo or company["default_timezone"])
    else:
        exact_time = None
        timezone_name = company["default_timezone"]

    event_id, event_name, reported_period = event_identity_and_name(
        company, title, text, event_day
    )
    event: Dict[str, Any] = {
        "event_id": event_id,
        "company_id": company["id"],
        "event_category": category,
        "event_name": event_name,
        "reported_period": reported_period,
        "importance": "core",
        "status": "scheduled",
        "confirmation": "confirmed",
        "date_type": "exact",
        "date_bjt": event_day.isoformat(),
        "time_bjt": None,
        "market_timing": market_timing(text, exact_time),
        "original_time": event_day.isoformat(),
        "original_timezone": timezone_name,
        "source_label": company["source_label"],
        "source_url": source_url,
        "source_published_at": None,
    }

    if exact_time:
        local_zone = machine_datetime.tzinfo if machine_datetime and not context_time else ZoneInfo(timezone_name)
        local_dt = datetime.combine(event_day, exact_time, local_zone)
        shanghai_dt = local_dt.astimezone(SHANGHAI)
        event["start_at"] = shanghai_dt.isoformat(timespec="seconds")
        event["date_bjt"] = shanghai_dt.date().isoformat()
        event["time_bjt"] = shanghai_dt.strftime("%H:%M")
        event["original_time"] = f"{event_day.isoformat()} {exact_time.strftime('%H:%M')} {timezone_name}"
    else:
        first = datetime.combine(event_day, time.min, ZoneInfo(timezone_name)).astimezone(SHANGHAI).date()
        last = datetime.combine(event_day, time.max, ZoneInfo(timezone_name)).astimezone(SHANGHAI).date()
        if first != last:
            event.update(date_type="window", confirmation="guided", window_start=first.isoformat(), window_end=last.isoformat())
            event.pop("date_bjt", None)
        else:
            event["date_bjt"] = first.isoformat()
    if not within_horizon(event, start, end):
        return None
    return event




def discover_company_events(
    company: Dict[str, Any], start: date, end: date, source_health: Optional[Dict[str, int]] = None
) -> List[Dict[str, Any]]:
    """Follow only dedicated earnings links on the company's official IR pages."""
    events: List[Dict[str, Any]] = []
    seen_urls = set()
    for discovery_url in company["discovery_urls"]:
        if source_health is not None:
            source_health["checked"] += 1
        try:
            html = fetch_text(discovery_url)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            if source_health is not None:
                source_health["failed"] += 1
            print(f"warning: could not check {company['name']} source {discovery_url}: {exc}", file=sys.stderr)
            continue
        if source_health is not None:
            source_health["successful"] += 1
        detail_pages_checked = 0
        for href, title in parse_page(html).links:
            if not href or not is_material_title(title) or re.search(r"replay|transcript|presentation", title, re.I):
                continue
            event_url = urljoin(discovery_url, href)
            if event_url in seen_urls or not domain_allowed(event_url, company["allowed_domains"]):
                continue
            if urlparse(event_url).path.lower().endswith((".pdf", ".ics")):
                continue
            if detail_pages_checked >= MAX_DETAIL_PAGES_PER_SOURCE:
                break
            seen_urls.add(event_url)
            detail_pages_checked += 1
            try:
                detail_html = fetch_text(event_url)
                event = build_discovered_event(company, title, event_url, detail_html, start, end)
            except (HTTPError, URLError, TimeoutError, OSError) as exc:
                print(f"warning: could not read earnings {event_url}: {exc}", file=sys.stderr)
                continue
            if event:
                events.append(event)
    return events


def normalize_calendar_time(value: Any) -> str:
    text = " ".join(str(value or "").lower().replace("-", " ").split())
    if text == "time pre market":
        return "before_open"
    if text == "time after hours":
        return "after_close"
    if "before" in text and ("open" in text or "market" in text):
        return "before_open"
    if "after" in text and ("close" in text or "market" in text):
        return "after_close"
    return "time_tbd"


def calendar_reported_period(value: Any, event_day: date) -> Tuple[str, str]:
    raw = str(value or "").strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            ending = datetime.strptime(raw, pattern).date()
            return f"截至 {ending.isoformat()} 季度", f"quarter-ended-{ending.isoformat()}"
        except ValueError:
            pass
    quarter = ((event_day.month - 1) // 3) + 1
    return f"{event_day.year} Q{quarter}", f"{event_day.year}-q{quarter}"


def discover_earnings_calendar_events(config: Dict[str, Any], companies: Sequence[Dict[str, Any]], start: date, end: date) -> List[Dict[str, Any]]:
    """Read Nasdaq's public daily earnings calendar and retain tracked symbols only."""
    calendar = config.get("earnings_calendar", {})
    tracked = {company["ticker"].upper(): company for company in companies}
    events: List[Dict[str, Any]] = []
    for offset in range((end - start).days + 1):
        us_day = start + timedelta(days=offset)
        source_url = calendar.get("url_template", NASDAQ_EARNINGS_URL).format(day=us_day.isoformat())
        try:
            payload = json.loads(fetch_text(source_url))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise OSError(f"Nasdaq earnings calendar unavailable for {us_day}: {exc}") from exc
        rows = ((payload.get("data") or {}).get("rows") or [])
        if not isinstance(rows, list):
            raise OSError(f"Nasdaq earnings calendar returned an unexpected payload for {us_day}")
        for row in rows:
            if not isinstance(row, dict):
                continue
            company = tracked.get(str(row.get("symbol") or "").upper())
            if not company:
                continue
            timing = normalize_calendar_time(row.get("time"))
            bjt_day = us_day + timedelta(days=1) if timing == "after_close" else us_day
            period, period_slug = calendar_reported_period(row.get("fiscalQuarterEnding"), us_day)
            events.append({
                "event_id": f"{company['id']}-earnings-{period_slug}", "company_id": company["id"],
                "event_category": "earnings", "event_name": f"{company['name']} {period}财报",
                "reported_period": period, "importance": "core", "status": "scheduled", "confirmation": "inferred",
                "date_type": "exact", "date_bjt": bjt_day.isoformat(), "time_bjt": None, "market_timing": timing,
                "original_time": f"{us_day.isoformat()} {row.get('time') or 'time not supplied'} America/New_York",
                "original_timezone": "America/New_York", "eps_estimate": row.get("epsForecast") or None,
                "revenue_estimate": row.get("revenueForecast") or None,
                "source_label": calendar.get("source_label", "Nasdaq Earnings Calendar"), "source_url": source_url,
                "source_published_at": None,
            })
    return events




def timing_signature(event: Dict[str, Any]) -> Tuple[Any, ...]:
    return (
        event.get("date_type"),
        event.get("start_at"),
        event.get("date_bjt"),
        event.get("time_bjt"),
        event.get("window_start"),
        event.get("window_end"),
        "cancelled" if event.get("status") == "cancelled" else "active",
    )


def event_start_date(event: Dict[str, Any]) -> date:
    value = event.get("date_bjt") or event.get("window_start")
    if not value:
        raise ValueError(f"event {event.get('event_id')} has no start date")
    return date.fromisoformat(value)


def event_end_date(event: Dict[str, Any]) -> date:
    value = event.get("window_end") or event.get("date_bjt") or event.get("window_start")
    if not value:
        raise ValueError(f"event {event.get('event_id')} has no end date")
    return date.fromisoformat(value)


def within_horizon(event: Dict[str, Any], start: date, end: date) -> bool:
    return event_end_date(event) >= start and event_start_date(event) <= end


def preference_score(event: Dict[str, Any]) -> Tuple[int, int]:
    confirmation = {"confirmed": 3, "guided": 2, "inferred": 1}.get(event.get("confirmation"), 0)
    date_type = 1 if event.get("date_type") == "exact" else 0
    return confirmation, date_type


def matching_earnings_event_id(selected: Dict[str, Dict[str, Any]], event: Dict[str, Any]) -> Optional[str]:
    """Find the same earnings release even when calendar and IR use different IDs."""
    if event.get("event_category") != "earnings":
        return None
    for event_id, existing in selected.items():
        if existing.get("event_category") != "earnings" or existing.get("company_id") != event.get("company_id"):
            continue
        if existing.get("reported_period") and existing.get("reported_period") == event.get("reported_period"):
            return event_id
        try:
            if abs((event_start_date(existing) - event_start_date(event)).days) <= 21:
                return event_id
        except (ValueError, TypeError):
            continue
    return None


def merge_events(
    companies: Sequence[Dict[str, Any]],
    curated: Sequence[Dict[str, Any]],
    discovered: Sequence[Dict[str, Any]],
    previous: Sequence[Dict[str, Any]],
    start: date,
    days: int,
    now: datetime,
) -> List[Dict[str, Any]]:
    end = start + timedelta(days=days)
    company_map = {company["id"]: company for company in companies}
    prior_map = {event["event_id"]: event for event in previous if event.get("event_id")}
    selected: Dict[str, Dict[str, Any]] = {}

    for source_events in (previous, curated, discovered):
        for raw_event in source_events:
            event = deepcopy(raw_event)
            event_id = event.get("event_id")
            if not event_id or event.get("company_id") not in company_map:
                continue
            if event.get("event_category") not in EVENT_CATEGORIES:
                continue
            try:
                if not within_horizon(event, start, end):
                    continue
            except (ValueError, TypeError):
                continue
            matching_id = matching_earnings_event_id(selected, event)
            if matching_id:
                event_id = matching_id
                event["event_id"] = matching_id
            current = selected.get(event_id)
            if current is None or preference_score(event) > preference_score(current):
                selected[event_id] = event
            elif (
                preference_score(event) == preference_score(current)
                and timing_signature(event) != timing_signature(current)
            ):
                selected[event_id] = event

    merged: List[Dict[str, Any]] = []
    for event_id, event in selected.items():
        company = company_map[event["company_id"]]
        event["company"] = company["name"]
        event["ticker"] = company["ticker"]
        event["company_group"] = company["group"]
        event["company_group_zh"] = company["group_zh"]

        prior = prior_map.get(event_id)
        changed = prior is not None and timing_signature(prior) != timing_signature(event)
        if changed:
            event["date_changed"] = True
            event["date_changed_at"] = now.isoformat(timespec="seconds")
            event["previous_timing"] = {
                "date_type": prior.get("date_type"),
                "start_at": prior.get("start_at"),
                "date_bjt": prior.get("date_bjt"),
                "time_bjt": prior.get("time_bjt"),
                "window_start": prior.get("window_start"),
                "window_end": prior.get("window_end"),
            }
            event["status"] = "changed"
            event["updated_at"] = now.isoformat(timespec="seconds")
        elif prior:
            for key in ("date_changed", "date_changed_at", "previous_timing"):
                if key in prior:
                    event[key] = deepcopy(prior[key])
            event.setdefault("updated_at", prior.get("updated_at") or now.isoformat(timespec="seconds"))
        else:
            event.setdefault("date_changed", False)
            event.setdefault("updated_at", now.isoformat(timespec="seconds"))

        merged.append(event)

    return sorted(
        merged,
        key=lambda item: (
            event_start_date(item),
            item.get("time_bjt") or "99:99",
            item["company"],
            item["event_name"],
        ),
    )


def all_allowed_domains(config: Dict[str, Any]) -> List[str]:
    domains: List[str] = []
    for company in config["companies"]:
        domains.extend(company.get("allowed_domains", []))
    domains.extend(config.get("earnings_calendar", {}).get("allowed_domains", []))
    return sorted(set(domains))


def validate_event_payload(payload: Dict[str, Any], config: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not payload.get("checked_at"):
        errors.append("checked_at is required")
    companies = config.get("companies", [])
    expected_ids = {company["id"] for company in companies}
    payload_ids = {company.get("id") for company in payload.get("companies", [])}
    if payload_ids != expected_ids:
        errors.append("company universe must contain every configured company")

    allowed_domains = all_allowed_domains(config)
    seen_ids = set()
    seen_semantic = set()
    for index, event in enumerate(payload.get("events", [])):
        label = event.get("event_id") or f"row {index}"
        required = (
            "event_id",
            "company_id",
            "company",
            "ticker",
            "event_category",
            "event_name",
            "importance",
            "status",
            "confirmation",
            "date_type",
            "source_label",
            "source_url",
            "updated_at",
        )
        missing = [key for key in required if event.get(key) in (None, "")]
        if missing:
            errors.append(f"{label}: missing {', '.join(missing)}")
        if label in seen_ids:
            errors.append(f"{label}: duplicate event_id")
        seen_ids.add(label)
        if event.get("company_id") not in expected_ids:
            errors.append(f"{label}: company is outside configured universe")
        if event.get("event_category") not in EVENT_CATEGORIES:
            errors.append(f"{label}: unsupported event category")
        if event.get("confirmation") not in CONFIRMATION_LEVELS:
            errors.append(f"{label}: unsupported confirmation")
        if event.get("importance") not in IMPORTANCE_LEVELS:
            errors.append(f"{label}: unsupported importance")
        if event.get("status") not in STATUS_LEVELS:
            errors.append(f"{label}: unsupported status")
        if event.get("date_type") == "exact":
            if not event.get("date_bjt"):
                errors.append(f"{label}: exact event requires date_bjt")
        elif event.get("date_type") == "window":
            if not event.get("window_start") or not event.get("window_end"):
                errors.append(f"{label}: window event requires window_start and window_end")
            if event.get("confirmation") == "confirmed":
                errors.append(f"{label}: confirmed events must use an exact date")
        else:
            errors.append(f"{label}: date_type must be exact or window")
        try:
            if event_start_date(event) > event_end_date(event):
                errors.append(f"{label}: start date is after end date")
        except (ValueError, TypeError):
            errors.append(f"{label}: invalid ISO date")
        if not domain_allowed(str(event.get("source_url", "")), allowed_domains):
            errors.append(f"{label}: source is not on the configured allowlist")
        semantic_key = (
            event.get("company_id"),
            event.get("event_category"),
            event.get("event_name"),
            timing_signature(event),
        )
        if semantic_key in seen_semantic:
            errors.append(f"{label}: duplicate company/event/date")
        seen_semantic.add(semantic_key)
    return errors


def semantic_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    comparable = deepcopy(payload)
    comparable.pop("updated_at", None)
    comparable.pop("checked_at", None)
    return comparable


def build_payload(
    config: Dict[str, Any],
    events: Sequence[Dict[str, Any]],
    updated_at: str,
    checked_at: Optional[str] = None,
) -> Dict[str, Any]:
    companies = [
        {
            "id": item["id"],
            "name": item["name"],
            "ticker": item["ticker"],
            "group": item["group"],
            "group_zh": item["group_zh"],
        }
        for item in config["companies"]
    ]
    return {
        "schema_version": 1,
        "timezone": "Asia/Shanghai",
        "horizon_days": int(config.get("horizon_days", DEFAULT_DAYS)),
        "checked_at": checked_at or updated_at,
        "updated_at": updated_at,
        "companies": companies,
        "events": list(events),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default=datetime.now(SHANGHAI).date().isoformat())
    parser.add_argument("--days", type=int, default=DEFAULT_DAYS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true", help="Use curated and prior data without network requests.")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    config = load_json(SOURCE_CONFIG)
    start = date.fromisoformat(args.start)
    now = datetime.now(SHANGHAI)

    if args.validate_only:
        payload = load_json(args.output)
        errors = validate_event_payload(payload, config)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        print(f"validated {len(payload.get('events', []))} technology-company events")
        return 0

    curated = load_json(CURATED_EVENTS)
    previous_payload: Dict[str, Any] = {}
    if args.output.exists():
        previous_payload = load_json(args.output)
    previous_events = previous_payload.get("events", [])

    discovered: List[Dict[str, Any]] = []
    source_health = {"checked": 0, "successful": 0, "failed": 0}
    if not args.offline:
        end = start + timedelta(days=args.days)
        def check_company(company):
            health = {"checked": 0, "successful": 0, "failed": 0}
            return discover_company_events(company, start, end, health), health

        with ThreadPoolExecutor(max_workers=6) as pool:
            for company_events, health in pool.map(check_company, config["companies"]):
                discovered.extend(company_events)
                for key in source_health:
                    source_health[key] += health[key]
        nasdaq_ok = False
        try:
            discovered.extend(discover_earnings_calendar_events(config, config["companies"], start, end))
            nasdaq_ok = True
            print("Nasdaq earnings calendar check succeeded")
        except OSError as exc:
            print(f"warning: {exc}; retaining last-known-good earnings events", file=sys.stderr)
        if source_health["successful"] == 0 and not nasdaq_ok:
            print("error: all earnings sources failed; preserving published data", file=sys.stderr)
            return 1
        print(
            "official source checks: "
            f"{source_health['successful']} succeeded, {source_health['failed']} failed"
        )

    events = merge_events(
        config["companies"], curated, discovered, previous_events, start, args.days, now
    )
    previous_updated_at = previous_payload.get("updated_at", now.isoformat(timespec="seconds"))
    checked_at = now.isoformat(timespec="seconds")
    candidate = build_payload(config, events, previous_updated_at, checked_at)
    errors = validate_event_payload(candidate, config)
    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    content_changed = not previous_payload or semantic_payload(previous_payload) != semantic_payload(candidate)
    if content_changed:
        candidate["updated_at"] = checked_at
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    state = "changed" if content_changed else "unchanged"
    mode = "rebuilt from curated data" if args.offline else "checked official sources"
    print(f"{mode}; event content {state} ({len(events)} events)")
    print(f"wrote {len(events)} events to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


