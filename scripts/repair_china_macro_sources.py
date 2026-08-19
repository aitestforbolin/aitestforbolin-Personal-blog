#!/usr/bin/env python3
"""Repair China macro source health and use official fallback pages when needed.

The primary updater is intentionally conservative and preserves the last valid data
when an official source cannot be fetched.  This helper runs immediately after it
and addresses two separate failure modes:

1. Source-health metadata is reconciled on every run, even when no macro value
   changed.  This prevents a recovered source from remaining permanently marked as
   failed in ``data/china-macro-calendar.json``.
2. GACC and MOF get independent official fallbacks.  GACC falls back to the English
   Customs statistics pages; MOF falls back to the Treasury Department statistics
   directory under ``gks.mof.gov.cn``.  If a newly published period matches an
   existing blank event, the values are backfilled without deleting history.

Only official ``customs.gov.cn`` and ``mof.gov.cn`` pages are used.  A fallback can
prove that a source is healthy without inventing a release that has not been
published yet.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import update_china_macro_calendar as china


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CHINA_PATH = SITE_ROOT / "data" / "china-macro-calendar.json"
DEFAULT_STATUS_PATH = Path("/tmp/china-macro-status.json")

GACC_ENGLISH_INDEXES = (
    "https://english.customs.gov.cn/Statistics/Statistics?ColumnId=1",
    "https://english.customs.gov.cn/statics/report/preliminary.html",
)
MOF_FALLBACK_INDEXES = (
    "https://gks.mof.gov.cn/tongjishuju/",
    china.MOF_RELEASE_INDEX,
)

MONTH_NUMBERS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

PROVIDER_COUNT = len(china.PROVIDER_LISTINGS)


def page_text(html: str) -> str:
    return " ".join(china.html_to_text(html).split())


def publication_day(text: str) -> str | None:
    patterns = (
        r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})",
        r"(20\d{2})年(\d{1,2})月(\d{1,2})日",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            year, month, day = map(int, match.groups())
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def gacc_period_from_title(title: str) -> str | None:
    match = re.search(
        r"\b(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\.?\s+(20\d{2})\b",
        title,
        re.IGNORECASE,
    )
    if not match:
        return None
    month = MONTH_NUMBERS[match.group(1).lower()]
    return f"{int(match.group(2)):04d}-{month:02d}"


def gacc_usd_summary_title(title: str) -> bool:
    normalized = " ".join(title.split())
    return bool(
        re.search(r"China'?s Total Export\s*&\s*Import Values,", normalized, re.IGNORECASE)
        and re.search(r"\(in USD\)", normalized, re.IGNORECASE)
        and "by Trade Mode" not in normalized
        and "by Country" not in normalized
    )


def numeric_after(text: str, label_pattern: str) -> str | None:
    match = re.search(label_pattern + r"\s+([\d,.]+)", text, re.IGNORECASE)
    return match.group(1).replace(",", "") if match else None


def parse_gacc_english_trade(title: str, html: str, source_url: str) -> tuple[china.Release, str | None]:
    period = gacc_period_from_title(title)
    text = page_text(html)
    if not period:
        period = gacc_period_from_title(text)
    exports = numeric_after(text, r"Total Export(?!\s*&)")
    imports = numeric_after(text, r"Total Import")
    balance = numeric_after(text, r"Export\s*-\s*Import Balance")
    if not period or not exports or not imports or not balance:
        raise ValueError("GACC English summary did not contain period/export/import/balance values")
    release = china.Release(
        group="trade",
        period=period,
        released_at=None,
        source_url=source_url,
        metrics={
            "exports": exports,
            "imports": imports,
            "trade_balance": balance,
        },
    )
    return release, publication_day(text)


def candidate_rank(item: tuple[str, str]) -> tuple[str, str]:
    title, url = item
    period = gacc_period_from_title(title) or "0000-00"
    url_dates = re.findall(r"20\d{6}", url)
    return period, max(url_dates, default="")


def fetch_gacc_fallback(fetcher: Callable[[str], str]) -> tuple[china.Release, str | None, list[str]]:
    errors: list[str] = []
    candidates: list[tuple[str, str]] = []
    for index_url in GACC_ENGLISH_INDEXES:
        try:
            html = fetcher(index_url)
            candidates.extend(
                item
                for item in china.extract_links(html, index_url)
                if gacc_usd_summary_title(item[0])
            )
        except Exception as exc:  # noqa: BLE001 - fallback indexes are independent.
            errors.append(f"{index_url}: {exc}")

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=candidate_rank, reverse=True):
        if item[1] not in seen:
            deduped.append(item)
            seen.add(item[1])

    for title, url in deduped[:6]:
        try:
            return (*parse_gacc_english_trade(title, fetcher(url), url), errors)
        except Exception as exc:  # noqa: BLE001 - one stale/malformed page does not kill fallback.
            errors.append(f"{title}: {exc}")
    raise RuntimeError("GACC official English fallback unavailable: " + "; ".join(errors[:4]))


def mof_candidate_rank(item: tuple[str, str]) -> str:
    dates = re.findall(r"20\d{6}", item[1])
    return max(dates, default="")


def fetch_mof_fallback(fetcher: Callable[[str], str]) -> tuple[china.Release, str | None, list[str]]:
    errors: list[str] = []
    candidates: list[tuple[str, str]] = []
    for index_url in MOF_FALLBACK_INDEXES:
        try:
            html = fetcher(index_url)
            candidates.extend(
                item
                for item in china.extract_links(html, index_url)
                if "财政收支情况" in item[0]
            )
        except Exception as exc:  # noqa: BLE001 - fallback indexes are independent.
            errors.append(f"{index_url}: {exc}")

    deduped: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=mof_candidate_rank, reverse=True):
        if item[1] not in seen:
            deduped.append(item)
            seen.add(item[1])

    for title, url in deduped[:6]:
        try:
            html = fetcher(url)
            text = page_text(html)
            release = china.parse_mof_fiscal(f"{title} {text}", url)
            return release, publication_day(text), errors
        except Exception as exc:  # noqa: BLE001 - try the next official fiscal page.
            errors.append(f"{title}: {exc}")
    raise RuntimeError("MOF official fallback unavailable: " + "; ".join(errors[:4]))


def event_for_release(events: list[dict], release: china.Release) -> dict | None:
    return next(
        (
            event
            for event in events
            if event.get("group") == release.group and event.get("period") == release.period
        ),
        None,
    )


def event_missing_actuals(event: dict | None) -> bool:
    if not event:
        return False
    metrics = event.get("metrics") or []
    return any(metric.get("actual") in (None, "") for metric in metrics)


def apply_date_only_release(
    payload: dict,
    release: china.Release,
    day: str | None,
    retrieved_at: str,
) -> bool:
    event = event_for_release(payload.get("events", []), release)
    should_apply = event is None or event_missing_actuals(event)
    if not should_apply:
        return False

    changed = china.apply_releases(payload["events"], [release], retrieved_at)
    event = event_for_release(payload["events"], release)
    if not event:
        return changed

    if day:
        # The official page exposes the publication date but not a trustworthy clock
        # time.  Keep the public UI date-only; use end-of-day only as the internal
        # retention anchor so the 48-hour window never expires prematurely.
        anchor = f"{day}T23:59:59+08:00"
        if event.get("eventDate") != day:
            event["eventDate"] = day
            changed = True
        if event.get("releasedAt") != anchor:
            event["releasedAt"] = anchor
            changed = True
        if event.get("scheduledAt") is not None:
            event["scheduledAt"] = None
            changed = True
        if event.get("dateStatus") != "confirmed":
            event["dateStatus"] = "confirmed"
            changed = True
        if "expectedWindow" in event:
            event.pop("expectedWindow", None)
            changed = True
    if event.get("releaseStatus") != "released":
        event["releaseStatus"] = "released"
        changed = True
    if event.get("sourceStatus") != "fresh":
        event["sourceStatus"] = "fresh"
        changed = True
    return changed


def read_status(path: Path) -> dict:
    if not path.exists():
        return {
            "status": "stale",
            "updated": False,
            "successfulSources": [],
            "failedSources": {provider: "missing primary status" for provider in china.PROVIDER_LISTINGS},
        }
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value.get("failedSources"), dict):
        value["failedSources"] = {}
    if not isinstance(value.get("successfulSources"), list):
        value["successfulSources"] = []
    return value


def run_repair(
    china_path: Path,
    status_path: Path,
    *,
    fetcher: Callable[[str], str] = china.fetch_text,
    now: datetime | None = None,
) -> dict:
    now = now or datetime.now(timezone.utc)
    retrieved_at = now.isoformat(timespec="seconds")
    payload = json.loads(china_path.read_text(encoding="utf-8"))
    china.validate_payload(payload)
    primary = read_status(status_path)

    failures = dict(primary.get("failedSources") or {})
    successes = set(primary.get("successfulSources") or [])
    repaired: list[str] = []
    repair_errors: dict[str, str] = {}
    data_changed = False

    if "gacc" in failures:
        try:
            release, day, _ = fetch_gacc_fallback(fetcher)
            data_changed = apply_date_only_release(payload, release, day, retrieved_at) or data_changed
            failures.pop("gacc", None)
            successes.add("gacc")
            repaired.append("gacc")
        except Exception as exc:  # noqa: BLE001 - keep the primary failure if fallback also fails.
            repair_errors["gacc"] = str(exc)

    if "mof" in failures:
        try:
            release, day, _ = fetch_mof_fallback(fetcher)
            data_changed = apply_date_only_release(payload, release, day, retrieved_at) or data_changed
            failures.pop("mof", None)
            successes.add("mof")
            repaired.append("mof")
        except Exception as exc:  # noqa: BLE001 - keep the primary failure if fallback also fails.
            repair_errors["mof"] = str(exc)

    if failures:
        run_status = "partial" if successes else "stale"
    else:
        run_status = "healthy" if len(successes) >= PROVIDER_COUNT else primary.get("status", "healthy")
        if run_status in {"partial", "stale"}:
            run_status = "healthy"

    old_health = (
        payload.get("status"),
        tuple(payload.get("failedSources") or []),
    )
    new_health = (run_status, tuple(sorted(failures)))
    health_changed = old_health != new_health

    payload["status"] = run_status
    payload["failedSources"] = sorted(failures)
    if health_changed:
        payload["sourceHealthUpdatedAt"] = retrieved_at
    if data_changed:
        payload["generatedAt"] = retrieved_at
    payload["events"] = sorted(payload["events"], key=china.event_sort_key)
    china.validate_payload(payload)

    if health_changed or data_changed:
        china.write_if_changed(china_path, payload, None)

    primary["status"] = run_status
    primary["successfulSources"] = sorted(successes)
    primary["failedSources"] = failures
    primary["repairedSources"] = repaired
    primary["repairErrors"] = repair_errors
    primary["updated"] = bool(primary.get("updated")) or data_changed or health_changed
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(primary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {
        "status": run_status,
        "failedSources": sorted(failures),
        "repairedSources": repaired,
        "healthChanged": health_changed,
        "dataChanged": data_changed,
        "repairErrors": repair_errors,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--china-path", type=Path, default=DEFAULT_CHINA_PATH)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run_repair(args.china_path, args.status_file)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
