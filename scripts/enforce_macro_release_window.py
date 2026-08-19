#!/usr/bin/env python3
"""Backfill due China macro releases and enforce the 48-hour display window.

The primary China updater is deliberately conservative: when an official source is
unavailable it keeps the last valid payload.  That is the right failure mode for
history, but it can leave a newly due event with blank ``actual`` values if an NBS
listing has not been picked up by the normal collector yet.

This helper adds two narrow safeguards:

1. ``backfill-china`` scans the latest official NBS release/listing pages for NBS
   events that are already due and still have missing actual values, then applies
   any matching releases to ``data/china-macro-calendar.json``.
2. ``prune-unified`` removes data-release cards from the unified website payload
   once more than 48 hours have elapsed since ``releasedAt`` (or, when that field
   is unavailable, the scheduled release time).  Policy events and undated/window
   events are left untouched.

Only official NBS pages are used for backfill.  Historical China source data is
never pruned; pruning is limited to the unified display payload so previous values
remain available to future releases.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import update_china_macro_calendar as china


SITE_ROOT = Path(__file__).resolve().parents[1]
CHINA_PATH = SITE_ROOT / "data" / "china-macro-calendar.json"
UNIFIED_PATH = SITE_ROOT / "data" / "macro-calendar.json"
RELEASE_WINDOW_HOURS = 48
BACKFILL_LOOKBACK_DAYS = 7
NBS_LATEST_INDEX = "https://www.stats.gov.cn/sj/zxfbhjd/"

GROUP_TITLE_NEEDLES = {
    "pmi": ("采购经理指数",),
    "prices": ("居民消费价格", "工业生产者出厂价格"),
    "activity": (
        "国民经济运行",
        "规模以上工业增加值",
        "固定资产投资",
        "房地产市场基本情况",
        "社会消费品零售总额",
    ),
    "housing": ("70个大中城市", "商品住宅销售价格变动情况"),
    "profits": ("工业企业利润",),
}


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def event_needs_actuals(event: dict) -> bool:
    metrics = event.get("metrics") or []
    return bool(metrics) and any(metric.get("actual") in (None, "") for metric in metrics)


def due_nbs_targets(events: list[dict], now: datetime) -> set[tuple[str, str]]:
    earliest = now - timedelta(days=BACKFILL_LOOKBACK_DAYS)
    targets: set[tuple[str, str]] = set()
    for event in events:
        group = event.get("group")
        if group not in GROUP_TITLE_NEEDLES or not event_needs_actuals(event):
            continue
        scheduled = parse_timestamp(event.get("scheduledAt"))
        if not scheduled or scheduled > now or scheduled < earliest:
            continue
        period = event.get("period")
        if period:
            targets.add((group, period))
    return targets


def candidate_group(title: str) -> str | None:
    for group, needles in GROUP_TITLE_NEEDLES.items():
        if any(needle in title for needle in needles):
            return group
    return None


def candidate_rank(item: tuple[str, str]) -> str:
    title, url = item
    url_dates = re.findall(r"20\d{6}", url)
    title_dates = re.findall(r"20\d{6}", title)
    return max(url_dates + title_dates, default="")


def collect_targeted_nbs_releases(
    targets: set[tuple[str, str]],
    *,
    fetcher=china.fetch_text,
) -> tuple[list[china.Release], list[str]]:
    if not targets:
        return [], []

    target_groups = {group for group, _ in targets}
    candidates: list[tuple[str, str]] = []
    listing_errors: list[str] = []
    listing_urls = [
        NBS_LATEST_INDEX,
        china.NBS_RELEASE_INDEX,
        china.NBS_INTERPRETATION_INDEX,
    ]
    for listing_url in listing_urls:
        try:
            listing_html = fetcher(listing_url)
            candidates.extend(china.extract_links(listing_html, listing_url))
        except Exception as exc:  # noqa: BLE001 - one official listing may be temporarily unavailable.
            listing_errors.append(f"{listing_url}: {exc}")

    selected: list[tuple[str, str]] = []
    seen: set[str] = set()
    for item in sorted(candidates, key=candidate_rank, reverse=True):
        title, url = item
        group = candidate_group(title)
        if group not in target_groups or url in seen:
            continue
        selected.append(item)
        seen.add(url)
        # The newest summary plus several component releases are enough to cover
        # the currently due period while keeping official-page traffic modest.
        if len(selected) >= 24:
            break

    releases: list[china.Release] = []
    parse_errors: list[str] = []
    for title, url in selected:
        try:
            html = fetcher(url)
            parsed = china.route_release("nbs", title, html, url)
        except Exception as exc:  # noqa: BLE001 - malformed/non-headline pages are skipped.
            parse_errors.append(f"{title}: {exc}")
            continue
        for release in parsed:
            if (release.group, release.period) in targets:
                releases.append(release)

    errors = listing_errors + parse_errors
    return releases, errors


def backfill_china(path: Path, now: datetime) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    china.validate_payload(payload)
    targets = due_nbs_targets(payload.get("events", []), now)
    if not targets:
        return {"targets": [], "matched": [], "updated": False, "errors": []}

    releases, errors = collect_targeted_nbs_releases(targets)
    matched = sorted({(release.group, release.period) for release in releases})
    retrieved_at = now.isoformat(timespec="seconds")
    changed = china.apply_releases(payload["events"], releases, retrieved_at) if releases else False

    if changed:
        payload["events"] = sorted(payload["events"], key=china.event_sort_key)
        payload["generatedAt"] = retrieved_at
        # Do not overwrite the primary updater's source-health status; this helper
        # only records that an official targeted backfill succeeded.
        payload["targetedBackfillAt"] = retrieved_at
        china.validate_payload(payload)
        china.write_if_changed(path, payload, None)

    return {
        "targets": sorted(targets),
        "matched": matched,
        "updated": changed,
        "errors": errors[:5],
    }


def is_policy_event(event: dict) -> bool:
    return event.get("eventType") == "policy_event"


def event_release_anchor(event: dict) -> datetime | None:
    return parse_timestamp(event.get("releasedAt")) or parse_timestamp(event.get("scheduledAt"))


def prune_unified(path: Path, now: datetime) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events")
    if not isinstance(events, list):
        raise ValueError("Unified macro calendar does not contain an events list")

    cutoff = now - timedelta(hours=RELEASE_WINDOW_HOURS)
    kept: list[dict] = []
    removed: list[str] = []
    for event in events:
        if is_policy_event(event):
            kept.append(event)
            continue
        anchor = event_release_anchor(event)
        if anchor is not None and anchor < cutoff:
            removed.append(str(event.get("id") or event.get("title") or "<unknown>"))
            continue
        kept.append(event)

    if removed:
        payload["events"] = kept
        payload["releaseWindowHours"] = RELEASE_WINDOW_HOURS
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"removed": removed, "updated": bool(removed), "remaining": len(kept)}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("backfill-china", "prune-unified"))
    parser.add_argument("--china-path", type=Path, default=CHINA_PATH)
    parser.add_argument("--unified-path", type=Path, default=UNIFIED_PATH)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(timezone.utc)
    if args.command == "backfill-china":
        result = backfill_china(args.china_path, now)
    else:
        result = prune_unified(args.unified_path, now)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
