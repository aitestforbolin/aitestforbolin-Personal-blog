import importlib.util
import json
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "update_market_prices.py"
SPEC = importlib.util.spec_from_file_location("update_market_prices", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_xauusd_uses_swissquote_midpoint_and_drops_old_futures(monkeypatch):
    monkeypatch.setattr(
        MODULE,
        "fetch_json",
        lambda _url: [
            {
                "ts": 1_787_016_119_375,
                "spreadProfilePrices": [
                    {"spreadProfile": "prime", "bid": 4422.4, "ask": 4423.0}
                ],
            },
            {
                "ts": 1_787_016_119_375,
                "spreadProfilePrices": [
                    {"spreadProfile": "prime", "bid": 4422.5, "ask": 4422.9}
                ],
            },
        ],
    )
    monkeypatch.setattr(MODULE, "load_previous_xau_points", lambda: [])

    row = MODULE.normalize_xauusd()

    assert row["source"] == "Swissquote"
    assert row["sourceSymbol"] == "XAU/USD"
    assert row["close"] == 4422.7
    assert len(row["points"]) == 1


def test_previous_history_accepts_only_xauusd_spot(tmp_path, monkeypatch):
    output = tmp_path / "market-prices.json"
    output.write_text(
        '{"symbols": [{"symbol": "XAUUSD", "sourceSymbol": "GC=F", '
        '"points": [{"timestamp": 1, "value": 4400}]}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(MODULE, "OUTPUT", output)

    assert MODULE.load_previous_xau_points() == []


def test_fetch_json_retries_transient_failure_without_duplicate_write(monkeypatch):
    response = mock.MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({"ok": True}).encode()
    opener = mock.Mock(side_effect=[OSError("temporary"), response])
    monkeypatch.setattr(MODULE.urllib.request, "urlopen", opener)
    monkeypatch.setattr(MODULE.time, "sleep", lambda _seconds: None)

    assert MODULE.fetch_json("https://example.test/data") == {"ok": True}
    assert opener.call_count == 2
