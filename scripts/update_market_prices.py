#!/usr/bin/env python3
import datetime as dt
import json
import pathlib
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "market-prices.json"
YAHOO_ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
SYMBOLS = [
    ("BTC-USD", "BTCUSD"),
    ("GC=F", "XAUUSD"),
    ("SPY", "SPY.US"),
    ("QQQ", "QQQ.US"),
    ("DIA", "DIA.US"),
]


def fetch_chart(symbol):
    query = urllib.parse.urlencode(
        {
            "range": "1d",
            "interval": "5m",
        }
    )
    request = urllib.request.Request(
        f"{YAHOO_ENDPOINT.format(symbol=urllib.parse.quote(symbol))}?{query}",
        headers={
            "User-Agent": "Mozilla/5.0 personal-site-market-prices",
        },
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_chart(yahoo_symbol, site_symbol):
    data = fetch_chart(yahoo_symbol)
    result = data["chart"]["result"][0]
    meta = result["meta"]
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
    }


def main():
    rows = [normalize_chart(yahoo_symbol, site_symbol) for yahoo_symbol, site_symbol in SYMBOLS]
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
