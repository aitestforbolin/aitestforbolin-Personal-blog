#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
import statistics
import time
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "market-prices.json"
YAHOO_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SWISSQUOTE_XAUUSD_ENDPOINT = (
    "https://forex-data-feed.swissquote.com/"
    "public-quotes/bboquotes/instrument/XAU/USD"
)
HISTORY_RETENTION = dt.timedelta(days=31)
SYMBOLS = [
    ("BTC-USD", "BTCUSD"),
    ("SPY", "SPY.US"),
    ("QQQ", "QQQ.US"),
    ("DIA", "DIA.US"),
]


def fetch_json(url, attempts=3):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 personal-site-market-prices"},
    )
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(attempt * 2)
    raise last_error


def fetch_chart(symbol):
    query = urllib.parse.urlencode(
        {
            "range": "1d",
            "interval": "5m",
        }
    )
    return fetch_json(
        f"{YAHOO_ENDPOINT.format(symbol=urllib.parse.quote(symbol))}?{query}"
    )


def load_previous_xau_points():
    try:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    for row in payload.get("symbols", []):
        if row.get("symbol") != "XAUUSD" or row.get("sourceSymbol") != "XAU/USD":
            continue
        return [
            point
            for point in row.get("points", [])
            if isinstance(point.get("timestamp"), int)
            and isinstance(point.get("value"), (int, float))
        ]
    return []


def normalize_xauusd():
    payload = fetch_json(SWISSQUOTE_XAUUSD_ENDPOINT)
    quotes = []
    timestamps = []
    for venue in payload if isinstance(payload, list) else []:
        timestamp = venue.get("ts")
        prices = venue.get("spreadProfilePrices") or []
        prime = next(
            (item for item in prices if item.get("spreadProfile") == "prime"),
            prices[0] if prices else None,
        )
        if not prime:
            continue
        bid = prime.get("bid")
        ask = prime.get("ask")
        if not isinstance(bid, (int, float)) or not isinstance(ask, (int, float)):
            continue
        quotes.append((float(bid) + float(ask)) / 2)
        if isinstance(timestamp, (int, float)):
            timestamps.append(int(timestamp))
    if not quotes or not timestamps:
        raise ValueError("Swissquote XAU/USD quote unavailable")

    timestamp_ms = max(timestamps)
    price = round(statistics.median(quotes), 3)
    moment = dt.datetime.fromtimestamp(timestamp_ms / 1000, tz=dt.timezone.utc)
    cutoff = int((moment - HISTORY_RETENTION).timestamp())
    points_by_timestamp = {
        int(point["timestamp"]): point
        for point in load_previous_xau_points()
        if int(point["timestamp"]) >= cutoff
    }
    timestamp_seconds = timestamp_ms // 1000
    points_by_timestamp[timestamp_seconds] = {
        "time": moment.strftime("%H:%M"),
        "timestamp": timestamp_seconds,
        "value": price,
    }
    points = [points_by_timestamp[key] for key in sorted(points_by_timestamp)]
    today_points = [
        point["value"]
        for point in points
        if dt.datetime.fromtimestamp(point["timestamp"], tz=dt.timezone.utc).date()
        == moment.date()
    ]
    previous = points[-2]["value"] if len(points) >= 2 else price
    return {
        "symbol": "XAUUSD",
        "date": moment.strftime("%Y-%m-%d"),
        "time": moment.strftime("%H:%M UTC"),
        "open": today_points[0] if today_points else price,
        "high": max(today_points, default=price),
        "low": min(today_points, default=price),
        "close": price,
        "previousClose": previous,
        "volume": "N/D",
        "source": "Swissquote",
        "sourceSymbol": "XAU/USD",
        "points": points,
    }


def normalize_chart(yahoo_symbol, site_symbol):
    data = fetch_chart(yahoo_symbol)
    result = data["chart"]["result"][0]
    meta = result["meta"]
    timestamps = result.get("timestamp") or []
    closes = (
        result.get("indicators", {})
        .get("quote", [{}])[0]
        .get("close")
        or []
    )
    timestamp = meta.get("regularMarketTime") or result.get("timestamp", [None])[-1]
    price = meta.get("regularMarketPrice")
    previous_close = (
        meta.get("chartPreviousClose")
        or meta.get("previousClose")
        or meta.get("regularMarketPreviousClose")
    )

    if timestamp:
        moment = dt.datetime.fromtimestamp(int(timestamp), tz=dt.timezone.utc)
        date = moment.strftime("%Y-%m-%d")
        time = moment.strftime("%H:%M UTC")
    else:
        date = ""
        time = ""

    points = []
    for point_timestamp, close in zip(timestamps, closes):
        if close is None:
            continue
        point_moment = dt.datetime.fromtimestamp(int(point_timestamp), tz=dt.timezone.utc)
        points.append(
            {
                "time": point_moment.strftime("%H:%M"),
                "timestamp": int(point_timestamp),
                "value": close,
            }
        )

    if not points and price is not None:
        points.append(
            {
                "time": time.replace(" UTC", ""),
                "timestamp": int(timestamp) if timestamp else None,
                "value": price,
            }
        )

    return {
        "symbol": site_symbol,
        "date": date,
        "time": time,
        "open": previous_close,
        "high": meta.get("regularMarketDayHigh", price),
        "low": meta.get("regularMarketDayLow", price),
        "close": price,
        "volume": meta.get("regularMarketVolume", "N/D"),
        "sourceSymbol": yahoo_symbol,
        "points": points[-96:],
    }


def main():
    rows = [normalize_chart(yahoo_symbol, site_symbol) for yahoo_symbol, site_symbol in SYMBOLS]
    rows.insert(1, normalize_xauusd())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(
            {
                "source": "yahoo-finance-chart",
                "symbols": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
