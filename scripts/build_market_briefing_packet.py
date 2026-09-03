#!/usr/bin/env python3
"""Build the machine-collected input packet for the daily market briefing."""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "market-briefing-packet.json"
MARKETS_URL = os.getenv(
    "MARKETS_API_URL",
    "https://cross-asset-pulse.laibocszd.chatgpt.site/api/markets",
)
BREADTH_URL = os.getenv(
    "BREADTH_API_URL",
    "https://cross-asset-pulse.laibocszd.chatgpt.site/api/breadth",
)
REQUIRED_MARKETS = {
    "SPX", "IXIC", "DJI", "SOX",
    "XLK", "XLY", "XLC", "XLV", "XLU", "XLP",
    "XLE", "XLI", "XLB", "XLRE", "XLF",
    "DXY", "US02Y", "US10Y", "US30Y", "BRN1!", "GOLD", "BTCUSDT",
}
REQUIRED_BREADTH = {"SP500", "NASDAQ"}
CANDIDATES = ["NVDA", "AVGO", "AMD", "MU", "AMAT", "LRCX", "MSFT", "AAPL", "AMZN", "GOOGL", "META"]
FIXED_ANCHOR_IDS = {"DXY", "BRN1!", "GOLD", "BTCUSDT"}
TREASURY_IDS = {"US02Y", "US10Y", "US30Y"}
MACRO_IDS = FIXED_ANCHOR_IDS | TREASURY_IDS
SESSION_MARKET_IDS = REQUIRED_MARKETS - MACRO_IDS
YAHOO_ANCHOR_SYMBOLS = {
    "DXY": "DX-Y.NYB",
    "BRN1!": "BZ=F",
    "BTCUSDT": "BTC-USD",
}
EXPECTED_MACRO_SOURCES = {
    "DXY": "Yahoo Finance",
    "US02Y": "U.S. Treasury",
    "US10Y": "U.S. Treasury",
    "US30Y": "U.S. Treasury",
    "BRN1!": "Yahoo Finance",
    "GOLD": "Swissquote",
    "BTCUSDT": "Yahoo Finance",
}
TIMEOUT = 35


def fetch_json(url: str, attempts: int = 3) -> object:
    """Fetch JSON with bounded retries for transient scheduled-run failures."""
    request = Request(url, headers={"User-Agent": "personal-site-market-packet/1.0"})
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with urlopen(request, timeout=TIMEOUT) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    assert last_error is not None
    raise last_error


def load_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def rows_from(payload: object, keys: tuple[str, ...]) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def finite_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number and number not in (float("inf"), float("-inf")) else None


def breadth_quality_issues(rows: list[dict]) -> tuple[list[str], list[str]]:
    """Validate IDs, counts and the published advance-percent calculation."""
    by_id = {str(row.get("id")): row for row in rows if row.get("id")}
    missing = sorted(REQUIRED_BREADTH - set(by_id))
    invalid: list[str] = []
    for breadth_id in sorted(REQUIRED_BREADTH & set(by_id)):
        row = by_id[breadth_id]
        advancers = finite_number(row.get("advancers"))
        decliners = finite_number(row.get("decliners"))
        percent = finite_number(row.get("advancePercent"))
        if advancers is None or decliners is None or percent is None or advancers + decliners <= 0:
            invalid.append(f"{breadth_id}:missing_numeric")
            continue
        expected = advancers / (advancers + decliners) * 100
        if abs(expected - percent) > 0.05:
            invalid.append(f"{breadth_id}:percent_mismatch")
        if str(row.get("status") or "").lower() == "unavailable":
            invalid.append(f"{breadth_id}:unavailable")
    return missing, invalid


def same_date_cached_breadth(packet: object, trading_date: str | None) -> list[dict]:
    """Reuse only a fully validated cache for the exact same trading date."""
    if not isinstance(packet, dict) or packet.get("tradingDate") != trading_date:
        return []
    rows = rows_from(packet.get("breadth"), ())
    missing, invalid = breadth_quality_issues(rows)
    return rows if not missing and not invalid else []


def source_metadata(payload: object) -> dict:
    """Preserve upstream revision and observation time for contract auditing."""
    if not isinstance(payload, dict):
        return {}
    return {
        key: payload[key]
        for key in ("sourceRevision", "fetchedAt")
        if payload.get(key) is not None
    }


def market_date(row: dict) -> str | None:
    for key in ("tradingDate", "date", "asOf"):
        value = row.get(key)
        if isinstance(value, str) and len(value) >= 10:
            return value[:10]
    timestamp = row.get("updatedAt") or row.get("time")
    if isinstance(timestamp, (int, float)):
        if timestamp > 10_000_000_000:
            timestamp /= 1000
        return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).date().isoformat()
    return None


def session_market_date_issues(
    rows: list[dict], trading_date: str | None
) -> list[str]:
    """Require every index/sector observation to belong to one close session."""
    by_id = {str(row.get("id")): row for row in rows if row.get("id")}
    issues: list[str] = []
    for market_id in sorted(SESSION_MARKET_IDS):
        row = by_id.get(market_id)
        if not row:
            continue
        observed = market_date(row)
        if not trading_date or observed != trading_date:
            issues.append(f"{market_id}:{observed or 'missing_date'}")
            continue
        if (
            finite_number(row.get("price")) is None
            or finite_number(row.get("changePercent")) is None
            or str(row.get("status") or "ok").casefold() == "unavailable"
        ):
            issues.append(f"{market_id}:invalid_values")
    return issues


def macro_provider_issues(assets: list[dict]) -> list[str]:
    by_id = {str(asset.get("id")): asset for asset in assets}
    issues: list[str] = []
    for asset_id, expected in EXPECTED_MACRO_SOURCES.items():
        actual = by_id.get(asset_id, {}).get("source")
        if not _same_provider(actual, expected):
            issues.append(f"{asset_id}:{actual or 'missing'}")
    return sorted(issues)


def compact_market(row: dict, trading_date: str | None = None) -> dict:
    keys = (
        "id", "name", "price", "previousClose", "change", "changePercent",
        "currency", "updatedAt", "source", "status", "seriesStatus",
    )
    item = {key: row.get(key) for key in keys if key in row}
    observed_date = market_date(row)
    if observed_date:
        item["observedDate"] = observed_date
    if row.get("id") in SESSION_MARKET_IDS and trading_date:
        item["tradingDate"] = trading_date
    return item


def macro_asset(row: dict, trading_date: str | None) -> dict:
    item = compact_market(row)
    points = row.get("points") if isinstance(row.get("points"), list) else []
    valid = [
        point for point in points
        if isinstance(point, dict)
        and isinstance(point.get("time"), (int, float))
        and isinstance(point.get("value"), (int, float))
    ]
    valid.sort(key=lambda point: point["time"])
    if row.get("id") in TREASURY_IDS:
        # The official curve may be unchanged on consecutive days. Group by
        # data date, not by value, or a flat close incorrectly erases "previous".
        by_date: dict[str, dict] = {}
        for point in valid:
            day = market_date({"updatedAt": point["time"]})
            if not day or (trading_date and day > trading_date):
                continue
            old = by_date.get(day)
            if old is None or point["time"] > old["time"]:
                by_date[day] = {
                    "date": day,
                    "time": point["time"],
                    "value": point["value"],
                }
        days = sorted(by_date)
        current = by_date.get(trading_date) if trading_date else None
        previous_days = [day for day in days if not trading_date or day < trading_date]
        previous = by_date[previous_days[-1]] if previous_days else None
        item["comparison"] = {
            "kind": "official_daily",
            "previous": previous,
            "current": current,
        }
        return item

    by_date: dict[str, dict] = {}
    eastern = ZoneInfo("America/New_York")
    for point in valid:
        timestamp = point["time"] / 1000 if point["time"] > 10_000_000_000 else point["time"]
        moment = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc).astimezone(eastern)
        minutes = moment.hour * 60 + moment.minute
        age = 16 * 60 - minutes
        if 0 <= age <= 60:
            key = moment.date().isoformat()
            existing = by_date.get(key)
            if not existing or point["time"] > existing["observedAt"]:
                by_date[key] = {"value": point["value"], "observedAt": point["time"], "minutesBeforeClose": age}
    anchors = sorted(by_date.items())
    if trading_date:
        anchors = [entry for entry in anchors if entry[0] <= trading_date]
    item["comparison"] = {
        "kind": "16:00_ET",
        "previous": {"date": anchors[-2][0], **anchors[-2][1]} if len(anchors) >= 2 else None,
        "current": {"date": anchors[-1][0], **anchors[-1][1]} if anchors else None,
    }
    return item


def yahoo_intraday_comparison(payload: object, trading_date: str) -> dict:
    """Extract exact same-provider anchors from Yahoo intraday chart data."""
    try:
        result = payload["chart"]["result"][0]
        timestamps = result.get("timestamp") or []
        closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    except (KeyError, IndexError, TypeError):
        return {"kind": "16:00_ET", "previous": None, "current": None}

    eastern = ZoneInfo("America/New_York")
    by_date: dict[str, dict] = {}
    for raw_time, raw_value in zip(timestamps, closes):
        value = finite_number(raw_value)
        if value is None or not isinstance(raw_time, (int, float)):
            continue
        moment = dt.datetime.fromtimestamp(raw_time, tz=dt.timezone.utc).astimezone(eastern)
        minutes_before_close = 16 * 60 - (moment.hour * 60 + moment.minute)
        if not 0 <= minutes_before_close <= 60:
            continue
        day = moment.date().isoformat()
        if day > trading_date:
            continue
        observed_at = int(raw_time * 1000)
        old = by_date.get(day)
        if old is None or observed_at > old["observedAt"]:
            by_date[day] = {
                "date": day,
                "value": value,
                "observedAt": observed_at,
                "minutesBeforeClose": minutes_before_close,
            }

    days = sorted(by_date)
    current = by_date.get(trading_date)
    previous_days = [day for day in days if day < trading_date]
    previous = by_date[previous_days[-1]] if previous_days else None
    return {"kind": "16:00_ET", "previous": previous, "current": current}


def recover_yahoo_anchor(asset: dict, trading_date: str | None) -> bool:
    """Recover a missing fixed anchor without changing the provider contract."""
    asset_id = str(asset.get("id"))
    symbol = YAHOO_ANCHOR_SYMBOLS.get(asset_id)
    if not symbol or not trading_date or not _same_provider(asset.get("source"), "Yahoo Finance"):
        return False
    comparison = asset.get("comparison") if isinstance(asset.get("comparison"), dict) else {}
    if comparison.get("previous") is not None and comparison.get("current") is not None:
        return False
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range=5d&interval=5m&includePrePost=true&events=div%2Csplits"
    )
    recovered = yahoo_intraday_comparison(fetch_json(url), trading_date)
    changed = False
    for key in ("previous", "current"):
        if comparison.get(key) is None and recovered.get(key) is not None:
            comparison[key] = {**recovered[key], "inheritedFrom": "yahoo_intraday_recovery"}
            changed = True
    if changed:
        comparison["kind"] = "16:00_ET"
        asset["comparison"] = comparison
    return changed


def inherit_same_date_gold_latest(
    assets: list[dict], trading_date: str | None, previous_packet: object
) -> bool:
    """Keep a validated same-session Swissquote quote during delayed rebuilds."""
    if (
        not trading_date
        or not isinstance(previous_packet, dict)
        or previous_packet.get("tradingDate") != trading_date
    ):
        return False
    by_id = {str(asset.get("id")): asset for asset in assets}
    gold = by_id.get("GOLD")
    if not isinstance(gold, dict) or market_date(gold) == trading_date:
        return False
    previous_gold = next(
        (
            row for row in previous_packet.get("macroAssets", [])
            if isinstance(row, dict) and row.get("id") == "GOLD"
        ),
        None,
    )
    if (
        not isinstance(previous_gold, dict)
        or not _same_provider(previous_gold.get("source"), "Swissquote")
        or not _same_provider(gold.get("source"), previous_gold.get("source"))
        or finite_number(previous_gold.get("price")) is None
        or market_date(previous_gold) != trading_date
    ):
        return False
    for key in ("price", "updatedAt", "status", "seriesStatus", "observedDate"):
        if key in previous_gold:
            gold[key] = previous_gold[key]
    gold["latestInheritedFrom"] = "same_date_previous_packet"
    return True


def fetch_candidate(symbol: str) -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range=5d&interval=1d&events=div%2Csplits"
    )
    payload = fetch_json(url, attempts=2)
    result = payload["chart"]["result"][0]
    meta = result.get("meta", {})
    closes = result.get("indicators", {}).get("quote", [{}])[0].get("close") or []
    valid = [float(value) for value in closes if value is not None]
    current = valid[-1] if valid else meta.get("regularMarketPrice")
    previous = valid[-2] if len(valid) > 1 else meta.get("chartPreviousClose")
    change = None
    if isinstance(current, (int, float)) and isinstance(previous, (int, float)) and previous:
        change = (current - previous) / previous * 100
    timestamps = result.get("timestamp") or []
    trading_date = None
    if timestamps:
        trading_date = dt.datetime.fromtimestamp(timestamps[-1], tz=dt.timezone.utc).date().isoformat()
    return {
        "ticker": symbol,
        "tradingDate": trading_date,
        "close": current,
        "previousClose": previous,
        "changePercent": change,
        "provider": "Yahoo Finance",
        "providerSymbol": symbol,
        "status": "ok" if change is not None else "incomplete",
    }


def candidate_quote_issues(candidates: list[dict]) -> list[str]:
    return [] if len(candidates) >= 5 else [f"insufficient_candidate_quotes:{len(candidates)}"]


def _event_rows(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    return []


def local_calendar_date(moment: dt.datetime) -> dt.date:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=dt.timezone.utc)
    return moment.astimezone(ZoneInfo("Asia/Shanghai")).date()


def future_events(today: dt.date, root: Path = ROOT) -> list[dict]:
    output: list[dict] = []
    macro = load_json(root / "data" / "us-macro-calendar.json", [])
    tech = load_json(root / "data" / "tech-company-events-curated.json", [])
    cutoff = today + dt.timedelta(days=14)
    seen: set[tuple[str, str]] = set()
    for row in _event_rows(macro) + _event_rows(tech):
        value = row.get("date") or row.get("date_bjt") or row.get("window_start")
        try:
            day = dt.date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            continue
        if today <= day <= cutoff:
            identity = str(row.get("event_id") or row.get("id") or row.get("url") or row.get("title") or "")
            key = (identity, day.isoformat())
            if key not in seen:
                seen.add(key)
                output.append(row)
    return sorted(output, key=lambda row: str(row.get("date") or row.get("date_bjt") or row.get("window_start") or ""))


def _same_provider(left: object, right: object) -> bool:
    return bool(left and right) and str(left).strip().casefold() == str(right).strip().casefold()


def _anchor_date(value: object) -> str | None:
    """Convert an anchor timestamp to its New York trading date."""
    if not isinstance(value, (int, float)):
        return None
    timestamp = value / 1000 if value > 10_000_000_000 else value
    try:
        moment = dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None
    return moment.astimezone(ZoneInfo("America/New_York")).date().isoformat()


def inherit_macro_comparisons(
    assets: list[dict],
    trading_date: str | None,
    previous_packet: object,
    previous_status: object,
) -> tuple[list[str], list[str]]:
    """Fill fixed 16:00 ET anchors without mixing providers or dates."""
    inherited: list[str] = []
    previous_assets: dict[str, dict] = {}
    previous_date = None
    if isinstance(previous_packet, dict):
        previous_date = previous_packet.get("tradingDate")
        previous_assets = {
            str(row.get("id")): row
            for row in previous_packet.get("macroAssets", [])
            if isinstance(row, dict) and row.get("id")
        }

    status_date = previous_status.get("asOf") if isinstance(previous_status, dict) else None
    status_assets = {
        str(row.get("id")): row
        for row in (previous_status.get("macroAnchors", []) if isinstance(previous_status, dict) else [])
        if isinstance(row, dict) and row.get("id")
    }

    for asset in assets:
        asset_id = str(asset.get("id"))
        if asset_id not in FIXED_ANCHOR_IDS:
            continue
        comparison = asset.get("comparison") if isinstance(asset.get("comparison"), dict) else {}

        old_asset = previous_assets.get(asset_id)
        old_current = None
        if isinstance(old_asset, dict):
            old_comparison = old_asset.get("comparison")
            if isinstance(old_comparison, dict):
                old_current = old_comparison.get("current")
        if (
            comparison.get("previous") is None
            and isinstance(old_current, dict)
            and trading_date
            and isinstance(previous_date, str)
            and previous_date < trading_date
            and old_current.get("date") == previous_date
            and isinstance(old_current.get("value"), (int, float))
            and _same_provider(asset.get("source"), old_asset.get("source"))
        ):
            comparison["previous"] = {**old_current, "inheritedFrom": "previous_packet"}
            asset["comparison"] = comparison
            inherited.append(f"{asset_id}:previous_packet")

        old_status = status_assets.get(asset_id)
        if not isinstance(old_status, dict) or not trading_date or not isinstance(status_date, str):
            continue
        if not _same_provider(asset.get("source"), old_status.get("provider")):
            continue

        if status_date == trading_date:
            previous_value = finite_number(old_status.get("previous"))
            previous_time = old_status.get("previousObservedAt") or old_status.get("previousAnchorTime")
            previous_anchor_date = _anchor_date(previous_time)
            if (
                comparison.get("previous") is None
                and previous_value is not None
                and previous_anchor_date
                and previous_anchor_date < trading_date
            ):
                comparison["previous"] = {
                    "date": previous_anchor_date,
                    "value": previous_value,
                    "observedAt": previous_time,
                    "inheritedFrom": "daily_market_status_same_date",
                }
                inherited.append(f"{asset_id}:daily_market_status_same_date_previous")

            current_value = finite_number(old_status.get("anchor"))
            current_time = old_status.get("anchorObservedAt") or old_status.get("anchorTime")
            current_anchor_date = _anchor_date(current_time)
            if (
                comparison.get("current") is None
                and current_value is not None
                and current_anchor_date == trading_date
            ):
                comparison["current"] = {
                    "date": trading_date,
                    "value": current_value,
                    "observedAt": current_time,
                    "inheritedFrom": "daily_market_status_same_date",
                }
                inherited.append(f"{asset_id}:daily_market_status_same_date_current")
            asset["comparison"] = comparison
            continue

        if (
            comparison.get("previous") is None
            and status_date < trading_date
            and isinstance(old_status.get("anchor"), (int, float))
        ):
            comparison["previous"] = {
                "date": status_date,
                "value": old_status["anchor"],
                "observedAt": old_status.get("anchorObservedAt") or old_status.get("anchorTime"),
                "inheritedFrom": "daily_market_status",
            }
            asset["comparison"] = comparison
            inherited.append(f"{asset_id}:daily_market_status")

    gaps = []
    by_id = {str(asset.get("id")): asset for asset in assets}
    for asset_id in sorted(FIXED_ANCHOR_IDS):
        comparison = by_id.get(asset_id, {}).get("comparison")
        if not isinstance(comparison, dict) or comparison.get("previous") is None or comparison.get("current") is None:
            gaps.append(asset_id)
    return inherited, gaps


def treasury_comparison_issues(
    assets: list[dict], trading_date: str | None
) -> list[str]:
    """Require two dated official observations, including the target date."""
    by_id = {str(asset.get("id")): asset for asset in assets}
    issues: list[str] = []
    for asset_id in sorted(TREASURY_IDS):
        comparison = by_id.get(asset_id, {}).get("comparison")
        if not isinstance(comparison, dict):
            issues.append(asset_id)
            continue
        previous = comparison.get("previous")
        current = comparison.get("current")
        if (
            not isinstance(previous, dict)
            or not isinstance(current, dict)
            or finite_number(previous.get("value")) is None
            or finite_number(current.get("value")) is None
            or not trading_date
            or current.get("date") != trading_date
            or not isinstance(previous.get("date"), str)
            or previous["date"] >= trading_date
        ):
            issues.append(asset_id)
    return issues


def fixed_comparison_issues(
    assets: list[dict], trading_date: str | None
) -> list[str]:
    """Reject stale or malformed fixed-close comparisons, even when non-null."""
    by_id = {str(asset.get("id")): asset for asset in assets}
    issues: list[str] = []
    for asset_id in sorted(FIXED_ANCHOR_IDS - {"GOLD"}):
        comparison = by_id.get(asset_id, {}).get("comparison")
        previous = comparison.get("previous") if isinstance(comparison, dict) else None
        current = comparison.get("current") if isinstance(comparison, dict) else None
        if (
            not isinstance(previous, dict)
            or not isinstance(current, dict)
            or finite_number(previous.get("value")) is None
            or finite_number(current.get("value")) is None
            or not trading_date
            or current.get("date") != trading_date
            or not isinstance(previous.get("date"), str)
            or previous["date"] >= trading_date
        ):
            issues.append(asset_id)

    gold = by_id.get("GOLD", {})
    comparison = gold.get("comparison")
    if isinstance(comparison, dict) and comparison.get("current") is not None:
        previous = comparison.get("previous")
        current = comparison.get("current")
        if (
            not isinstance(previous, dict)
            or not isinstance(current, dict)
            or finite_number(previous.get("value")) is None
            or finite_number(current.get("value")) is None
            or not trading_date
            or current.get("date") != trading_date
            or not isinstance(previous.get("date"), str)
            or previous["date"] >= trading_date
        ):
            issues.append("GOLD")
    return issues


def classify_comparison_gaps(
    assets: list[dict], trading_date: str | None, gaps: list[str]
) -> tuple[list[str], list[str]]:
    """Keep a fresh Swissquote gold quote usable without inventing a 16:00 ET anchor."""
    by_id = {str(asset.get("id")): asset for asset in assets}
    critical: list[str] = []
    warnings: list[str] = []
    for asset_id in gaps:
        asset = by_id.get(asset_id, {})
        if (
            asset_id == "GOLD"
            and str(asset.get("source") or "").casefold() == "swissquote"
            and finite_number(asset.get("price")) is not None
            and market_date(asset) == trading_date
        ):
            warnings.append("GOLD:latest_only_no_16:00_ET_anchor")
        else:
            critical.append(asset_id)
    return critical, warnings


def generated_after_close(generated: dt.datetime, trading_date: str | None) -> bool:
    if not trading_date:
        return False
    day = dt.date.fromisoformat(trading_date)
    close = dt.datetime.combine(day, dt.time(16, 0), tzinfo=ZoneInfo("America/New_York"))
    return generated.astimezone(dt.timezone.utc) >= close.astimezone(dt.timezone.utc)


def build_packet(now: dt.datetime | None = None) -> dict:
    generated = now or dt.datetime.now(dt.timezone.utc)
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=dt.timezone.utc)
    source_audit: dict[str, dict] = {}
    critical_errors: list[str] = []
    previous_packet_path = Path(os.getenv("PREVIOUS_PACKET_PATH", str(OUTPUT)))
    previous_packet = load_json(previous_packet_path, {})

    raw_markets: object = {}
    try:
        raw_markets = fetch_json(MARKETS_URL)
        markets = rows_from(raw_markets, ("markets", "data", "items"))
        source_audit["marketsApi"] = {
            "status": "ok", "url": MARKETS_URL, "count": len(markets),
            **source_metadata(raw_markets),
        }
    except Exception as exc:  # Actions must emit a diagnostic packet before failing validation.
        markets = []
        source_audit["marketsApi"] = {"status": "error", "url": MARKETS_URL, "error": type(exc).__name__}
        critical_errors.append("markets_api_unavailable")

    raw_breadth: object = {}
    try:
        raw_breadth = fetch_json(BREADTH_URL)
        breadth = rows_from(raw_breadth, ("breadth", "data", "items"))
        source_audit["breadthApi"] = {
            "status": "ok", "url": BREADTH_URL, "count": len(breadth),
            **source_metadata(raw_breadth),
        }
    except Exception as exc:
        breadth = []
        source_audit["breadthApi"] = {"status": "error", "url": BREADTH_URL, "error": type(exc).__name__}
        critical_errors.append("breadth_api_unavailable")

    market_ids = {str(row.get("id")) for row in markets}
    missing_markets = sorted(REQUIRED_MARKETS - market_ids)
    index_dates = {
        value for value in (
            market_date(row)
            for row in markets
            if row.get("id") in {"SPX", "IXIC", "DJI"}
        ) if value
    }
    trading_date = next(iter(index_dates)) if len(index_dates) == 1 else None
    session_date_issues = session_market_date_issues(markets, trading_date)

    missing_breadth, invalid_breadth = breadth_quality_issues(breadth)
    if missing_breadth or invalid_breadth:
        cached = same_date_cached_breadth(previous_packet, trading_date)
        if cached:
            breadth = cached
            missing_breadth, invalid_breadth = breadth_quality_issues(breadth)
            source_audit["breadthApi"]["fallback"] = "same_date_previous_packet"
            source_audit["breadthApi"]["count"] = len(breadth)
    if missing_markets:
        critical_errors.append("missing_markets:" + ",".join(missing_markets))
    if missing_breadth:
        critical_errors.append("missing_breadth:" + ",".join(missing_breadth))
    if invalid_breadth:
        critical_errors.append("invalid_breadth:" + ",".join(invalid_breadth))
    if len(index_dates) > 1:
        critical_errors.append("index_date_mismatch:" + ",".join(sorted(index_dates)))
    if session_date_issues:
        critical_errors.append("session_market_issues:" + ",".join(session_date_issues))

    if not trading_date:
        critical_errors.append("trading_date_unavailable")
    elif not generated_after_close(generated, trading_date):
        critical_errors.append("packet_generated_before_market_close")

    candidates_by_ticker: dict[str, dict] = {}
    candidate_errors: list[str] = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_candidate, ticker): ticker for ticker in CANDIDATES}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                candidate = future.result()
                candidates_by_ticker[ticker] = candidate
                if candidate.get("status") != "ok":
                    candidate_errors.append(ticker)
            except Exception:
                candidate_errors.append(ticker)
    candidates = [candidates_by_ticker[ticker] for ticker in CANDIDATES if ticker in candidates_by_ticker]
    candidate_errors.sort()
    source_audit["candidateQuotes"] = {
        "status": "ok" if not candidate_errors else "partial",
        "provider": "Yahoo Finance",
        "count": len(candidates),
        "failed": candidate_errors,
        "checkedAt": generated.isoformat(timespec="seconds"),
    }

    etf = load_json(ROOT / "data" / "btc-etf-flow.json", {})
    latest_etf = etf.get("latest") if isinstance(etf, dict) else None
    source_audit["btcEtf"] = {
        "status": "ok" if isinstance(latest_etf, dict) else "missing",
        "provider": etf.get("source") if isinstance(etf, dict) else None,
        "date": latest_etf.get("date") if isinstance(latest_etf, dict) else None,
        "checkedAt": generated.isoformat(timespec="seconds"),
    }

    macro_assets = [
        macro_asset(row, trading_date) for row in markets
        if row.get("id") in {"DXY", "US02Y", "US10Y", "US30Y", "BRN1!", "GOLD", "BTCUSDT"}
    ]
    gold_latest_inherited = inherit_same_date_gold_latest(
        macro_assets, trading_date, previous_packet
    )
    yahoo_recovered: list[str] = []
    yahoo_recovery_errors: list[str] = []
    yahoo_assets = [
        asset for asset in macro_assets
        if str(asset.get("id")) in YAHOO_ANCHOR_SYMBOLS
    ]
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(recover_yahoo_anchor, asset, trading_date): asset
            for asset in yahoo_assets
        }
        for future in as_completed(futures):
            asset = futures[future]
            try:
                if future.result():
                    yahoo_recovered.append(str(asset.get("id")))
            except Exception as exc:
                yahoo_recovery_errors.append(f"{asset.get('id')}:{type(exc).__name__}:{exc}")
    yahoo_recovered.sort()
    yahoo_recovery_errors.sort()
    source_audit["yahooAnchorRecovery"] = {
        "status": "ok" if yahoo_recovered else "error" if yahoo_recovery_errors else "not_needed",
        "recovered": yahoo_recovered,
        "errors": yahoo_recovery_errors,
        "symbols": YAHOO_ANCHOR_SYMBOLS,
    }

    previous_status = load_json(ROOT / "data" / "daily-market-status.json", {})
    inherited, comparison_gaps = inherit_macro_comparisons(
        macro_assets, trading_date, previous_packet, previous_status
    )
    if gold_latest_inherited:
        inherited.append("GOLD:same_date_previous_packet_latest")
    critical_comparison_gaps, comparison_warnings = classify_comparison_gaps(
        macro_assets, trading_date, comparison_gaps
    )
    critical_comparison_gaps = sorted(set(
        critical_comparison_gaps
        + treasury_comparison_issues(macro_assets, trading_date)
        + fixed_comparison_issues(macro_assets, trading_date)
    ))
    provider_issues = macro_provider_issues(macro_assets)
    source_audit["macroComparisons"] = {
        "status": "incomplete" if critical_comparison_gaps else "partial" if comparison_warnings else "ok",
        "inherited": inherited,
        "missing": critical_comparison_gaps,
        "warnings": comparison_warnings,
        "providerIssues": provider_issues,
        "checkedAt": generated.isoformat(timespec="seconds"),
    }
    source_audit["futureEvents"] = {
        "status": "ok",
        "timezone": "Asia/Shanghai",
        "techSource": "data/tech-company-events-curated.json",
        "checkedAt": generated.isoformat(timespec="seconds"),
    }
    if critical_comparison_gaps:
        critical_errors.append("missing_macro_comparisons:" + ",".join(critical_comparison_gaps))
    if provider_issues:
        critical_errors.append("macro_provider_mismatch:" + ",".join(provider_issues))
    critical_errors.extend(candidate_quote_issues(candidates))
    if candidate_errors:
        comparison_warnings.append(
            "candidate_quote_failures:" + ",".join(sorted(set(candidate_errors)))
        )

    breadth = [
        {**row, "tradingDate": trading_date, "dateBasis": "latest_completed_us_session"}
        if trading_date else row
        for row in breadth
    ]

    packet = {
        "schemaVersion": 2,
        "generatedAt": generated.isoformat(timespec="seconds"),
        "tradingDate": trading_date,
        "sourceAudit": source_audit,
        "markets": [compact_market(row, trading_date) for row in markets],
        "breadth": breadth,
        "macroAssets": macro_assets,
        "fed": {"status": "requires_model_verification", "method": "CME FedWatch"},
        "btcEtf": latest_etf,
        "futureEvents": future_events(local_calendar_date(generated)),
        "candidateStocks": candidates,
        "modelTasks": [
            "核验最新完整交易日与异常字段",
            "核验FedWatch概率与本次核验时间",
            "为符合门槛的核心个股补充公司级直接证据",
            "解释市场并生成6—8段观点",
        ],
        "validation": {
            "complete": not critical_errors,
            "criticalErrors": critical_errors,
            "missingMarkets": missing_markets,
            "missingBreadth": missing_breadth,
            "invalidBreadth": invalid_breadth,
            "sessionMarketIssues": session_date_issues,
            "macroProviderIssues": provider_issues,
            "candidateQuoteFailures": candidate_errors,
            "warnings": comparison_warnings,
        },
    }
    return packet


def main() -> int:
    packet = build_packet()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not packet["validation"]["complete"]:
        print("Packet written with validation errors:", packet["validation"]["criticalErrors"])
        return 1
    print(f"Packet ready for {packet['tradingDate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
