#!/usr/bin/env python3
"""Build the static Bitcoin ETF flow JSON for the personal site."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode
from urllib.error import URLError
from urllib.request import Request, urlopen


SITE_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = SITE_ROOT / "data" / "btc-etf-flow.json"
FARSIDE_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"
BINANCE_URL = "https://data-api.binance.vision/api/v3/klines"
FETCH_TIMEOUT = 90
FETCH_RETRIES = 3
MAX_OUTPUT_ROWS = 45
FUNDS = [
    "IBIT",
    "FBTC",
    "BITB",
    "ARKB",
    "BTCO",
    "EZBC",
    "BRRR",
    "HODL",
    "BTCW",
    "MSBT",
    "GBTC",
    "BTC",
]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


def fetch_text(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "personal-site-btc-etf-flow/1.0 (+https://github.com/)",
        },
    )
    last_error: Exception | None = None
    for _ in range(FETCH_RETRIES):
        try:
            with urlopen(request, timeout=FETCH_TIMEOUT) as response:
                body = response.read()
                encoding = response.headers.get_content_charset() or "utf-8"
            return body.decode(encoding, errors="replace")
        except (TimeoutError, URLError) as error:
            last_error = error
    raise RuntimeError(f"Could not fetch {url}") from last_error


def html_text_lines(html: str) -> list[str]:
    parser = TextExtractor()
    parser.feed(html)
    return parser.parts


def parse_money(value: str) -> float | None:
    text = value.strip()
    if text in {"", "-"}:
        return None

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]

    text = text.replace(",", "")
    try:
        parsed = float(text)
    except ValueError:
        return None

    return -parsed if negative else parsed


def parse_date(value: str) -> str | None:
    try:
        return datetime.strptime(value, "%d %b %Y").date().isoformat()
    except ValueError:
        return None


def parse_farside_rows(lines: list[str]) -> list[dict[str, object]]:
    try:
        start = lines.index("Date")
    except ValueError as exc:
        raise RuntimeError("Could not find Farside ETF flow table header") from exc

    rows: list[dict[str, object]] = []
    index = start + 1
    while index < len(lines) and lines[index] != "Total":
        index += 1
    index += 1

    columns = FUNDS + ["Total"]
    while index < len(lines):
        date_value = parse_date(lines[index])
        if not date_value:
            break

        values = lines[index + 1 : index + 1 + len(columns)]
        if len(values) < len(columns):
            break

        fund_values = {
            fund: parse_money(value) for fund, value in zip(FUNDS, values[: len(FUNDS)])
        }
        total = parse_money(values[-1])
        rows.append(
            {
                "date": date_value,
                "funds": fund_values,
                "total": total,
            }
        )
        index += 1 + len(columns)

    if not rows:
        raise RuntimeError("Farside ETF flow table was empty")

    return sorted(rows, key=lambda row: str(row["date"]), reverse=True)


def fetch_btc_prices(start_date: str) -> dict[str, float]:
    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
    params = urlencode(
        {
            "symbol": "BTCUSDT",
            "interval": "1d",
            "startTime": int(start_dt.timestamp() * 1000),
            "limit": 1000,
        }
    )
    try:
        html = fetch_text(f"{BINANCE_URL}?{params}")
        rows = json.loads(html)
    except Exception:
        return {}

    prices: dict[str, float] = {}
    for row in rows:
        try:
            day = datetime.fromtimestamp(row[0] / 1000, tz=timezone.utc).date().isoformat()
            prices[day] = float(row[4])
        except (TypeError, ValueError, IndexError):
            continue
    return prices


def add_btc_prices(rows: list[dict[str, object]]) -> None:
    oldest = str(rows[-1]["date"])
    prices = fetch_btc_prices(oldest)
    for row in rows:
        price = prices.get(str(row["date"]))
        if price is not None:
            row["btc_price"] = price


def rolling_sum(rows: list[dict[str, object]], size: int) -> float:
    return round(
        sum(float(row["total"] or 0) for row in rows[:size]),
        1,
    )


def build_payload() -> dict[str, object]:
    html = fetch_text(FARSIDE_URL)
    rows = parse_farside_rows(html_text_lines(html))
    add_btc_prices(rows)
    latest = rows[0]
    output_rows = rows[:MAX_OUTPUT_ROWS]
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Farside Investors",
        "source_url": FARSIDE_URL,
        "unit": "US$m",
        "funds": FUNDS,
        "latest": {
            "date": latest["date"],
            "total": latest["total"],
            "seven_day_total": rolling_sum(rows, 7),
            "thirty_day_total": rolling_sum(rows, 30),
        },
        "rows": output_rows,
    }


def main() -> None:
    payload = build_payload()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
