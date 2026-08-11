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


def future_events(today: dt.date) -> list[dict]:
    output: list[dict] = []
    macro = load_json(ROOT / "data" / "us-macro-calendar.json", [])
    tech = load_json(ROOT / "data" / "tech-company-events-curated.json", [])
    cutoff = today + dt.timedelta(days=14)
    for row in list(macro if isinstance(macro, list) else []) + list(tech if isinstance(tech, list) else []):
        if not isinstance(row, dict):
            continue
        value = row.get("date") or row.get("date_bjt")
        try:
            day = dt.date.fromisoformat(str(value)[:10])
        except ValueError:
            continue
        if today <= day <= cutoff:
            output.append(row)
    return output


def build_packet() -> dict:
    generated = dt.datetime.now(dt.timezone.utc)
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

    candidates: list[dict] = []
    candidate_errors: list[str] = []
    for ticker in CANDIDATES:
        try:
            candidates.append(fetch_candidate(ticker))
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

    packet = {
        "schemaVersion": 1,
        "generatedAt": generated.isoformat(timespec="seconds"),
        "tradingDate": trading_date,
        "sourceAudit": source_audit,
        "markets": [compact_market(row) for row in markets],
        "breadth": breadth,
        "macroAssets": [
            macro_asset(row, trading_date) for row in markets
            if row.get("id") in {"DXY", "US02Y", "US10Y", "US30Y", "BRN1!", "GOLD", "BTCUSDT"}
        ],
        "fed": {"status": "requires_model_verification", "method": "CME FedWatch"},
        "btcEtf": latest_etf,
        "futureEvents": future_events(generated.date()),
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
