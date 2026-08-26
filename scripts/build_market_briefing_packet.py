#!/usr/bin/env python3
"""Build the machine-collected input packet for the daily market briefing."""

from __future__ import annotations

import datetime as dt
import json
import os
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
TIMEOUT = 35


def fetch_json(url: str) -> object:
    request = Request(url, headers={"User-Agent": "personal-site-market-packet/1.0"})
    with urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


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


def compact_market(row: dict) -> dict:
    keys = (
        "id", "name", "price", "previousClose", "change", "changePercent",
        "currency", "updatedAt", "source", "status", "seriesStatus",
    )
    return {key: row.get(key) for key in keys if key in row}


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
    if row.get("id") in {"US02Y", "US10Y", "US30Y"}:
        daily = []
        for point in valid:
            if not daily or daily[-1]["value"] != point["value"]:
                daily.append({"time": point["time"], "value": point["value"]})
        item["comparison"] = {
            "kind": "official_daily",
            "previous": daily[-2] if len(daily) >= 2 else None,
            "current": daily[-1] if daily else None,
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


def fetch_candidate(symbol: str) -> dict:
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{symbol}?range=5d&interval=1d&events=div%2Csplits"
    )
    payload = fetch_json(url)
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
    tech = load_json(root / "data" / "tech-company-events.json", {})
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


def inherit_macro_comparisons(
    assets: list[dict],
    trading_date: str | None,
    previous_packet: object,
    previous_status: object,
) -> tuple[list[str], list[str]]:
    """Fill fixed 16:00 ET previous anchors without mixing providers or dates."""
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
        if comparison.get("previous") is not None:
            continue

        old_asset = previous_assets.get(asset_id)
        old_current = None
        if isinstance(old_asset, dict):
            old_comparison = old_asset.get("comparison")
            if isinstance(old_comparison, dict):
                old_current = old_comparison.get("current")
        if (
            isinstance(old_current, dict)
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
            continue

        old_status = status_assets.get(asset_id)
        if (
            isinstance(old_status, dict)
            and trading_date
            and isinstance(status_date, str)
            and status_date < trading_date
            and isinstance(old_status.get("anchor"), (int, float))
            and _same_provider(asset.get("source"), old_status.get("provider"))
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

    try:
        raw_markets = fetch_json(MARKETS_URL)
        markets = rows_from(raw_markets, ("markets", "data", "items"))
        source_audit["marketsApi"] = {"status": "ok", "url": MARKETS_URL, "count": len(markets)}
    except Exception as exc:  # Actions must emit a diagnostic packet before failing validation.
        markets = []
        source_audit["marketsApi"] = {"status": "error", "url": MARKETS_URL, "error": type(exc).__name__}
        critical_errors.append("markets_api_unavailable")

    try:
        raw_breadth = fetch_json(BREADTH_URL)
        breadth = rows_from(raw_breadth, ("breadth", "data", "items"))
        source_audit["breadthApi"] = {"status": "ok", "url": BREADTH_URL, "count": len(breadth)}
    except Exception as exc:
        breadth = []
        source_audit["breadthApi"] = {"status": "error", "url": BREADTH_URL, "error": type(exc).__name__}
        critical_errors.append("breadth_api_unavailable")

    market_ids = {str(row.get("id")) for row in markets}
    breadth_ids = {str(row.get("id")) for row in breadth}
    missing_markets = sorted(REQUIRED_MARKETS - market_ids)
    missing_breadth = sorted(REQUIRED_BREADTH - breadth_ids)
    if missing_markets:
        critical_errors.append("missing_markets:" + ",".join(missing_markets))
    if missing_breadth:
        critical_errors.append("missing_breadth:" + ",".join(missing_breadth))

    dates = [market_date(row) for row in markets if row.get("id") in {"SPX", "IXIC", "DJI"}]
    trading_date = min((value for value in dates if value), default=None)
    if not trading_date:
        critical_errors.append("trading_date_unavailable")
    elif not generated_after_close(generated, trading_date):
        critical_errors.append("packet_generated_before_market_close")

    candidates: list[dict] = []
    candidate_errors: list[str] = []
    for ticker in CANDIDATES:
        try:
            candidate = fetch_candidate(ticker)
            candidates.append(candidate)
            if candidate.get("status") != "ok":
                candidate_errors.append(ticker)
        except Exception:
            candidate_errors.append(ticker)
    source_audit["candidateQuotes"] = {
        "status": "ok" if not candidate_errors else "partial",
        "provider": "Yahoo Finance",
        "count": len(candidates),
        "failed": candidate_errors,
    }

    etf = load_json(ROOT / "data" / "btc-etf-flow.json", {})
    latest_etf = etf.get("latest") if isinstance(etf, dict) else None
    source_audit["btcEtf"] = {
        "status": "ok" if isinstance(latest_etf, dict) else "missing",
        "provider": etf.get("source") if isinstance(etf, dict) else None,
        "date": latest_etf.get("date") if isinstance(latest_etf, dict) else None,
    }

    macro_assets = [
        macro_asset(row, trading_date) for row in markets
        if row.get("id") in {"DXY", "US02Y", "US10Y", "US30Y", "BRN1!", "GOLD", "BTCUSDT"}
    ]
    previous_packet_path = Path(os.getenv("PREVIOUS_PACKET_PATH", str(OUTPUT)))
    previous_packet = load_json(previous_packet_path, {})
    previous_status = load_json(ROOT / "data" / "daily-market-status.json", {})
    inherited, comparison_gaps = inherit_macro_comparisons(
        macro_assets, trading_date, previous_packet, previous_status
    )
    source_audit["macroComparisons"] = {
        "status": "ok" if not comparison_gaps else "incomplete",
        "inherited": inherited,
        "missing": comparison_gaps,
    }
    source_audit["futureEvents"] = {
        "timezone": "Asia/Shanghai",
        "techSource": "data/tech-company-events.json",
    }
    if comparison_gaps:
        critical_errors.append("missing_macro_comparisons:" + ",".join(comparison_gaps))
    if candidate_errors:
        critical_errors.append("candidate_quote_failures:" + ",".join(sorted(set(candidate_errors))))

    packet = {
        "schemaVersion": 2,
        "generatedAt": generated.isoformat(timespec="seconds"),
        "tradingDate": trading_date,
        "sourceAudit": source_audit,
        "markets": [compact_market(row) for row in markets],
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
            "candidateQuoteFailures": candidate_errors,
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
