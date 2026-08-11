import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_market_briefing_packet.py"
SPEC = importlib.util.spec_from_file_location("market_packet", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_rows_from_supported_shapes():
    rows = [{"id": "SPX"}]
    assert MODULE.rows_from(rows, ("markets",)) == rows
    assert MODULE.rows_from({"markets": rows}, ("markets",)) == rows
    assert MODULE.rows_from({"data": rows}, ("markets", "data")) == rows


def test_market_date_accepts_iso_and_milliseconds():
    assert MODULE.market_date({"tradingDate": "2026-08-10"}) == "2026-08-10"
    assert MODULE.market_date({"updatedAt": 1786320000000}) == "2026-08-10"


def test_required_sector_contract_is_complete():
    sectors = {"XLK", "XLY", "XLC", "XLV", "XLU", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLF"}
    assert sectors <= MODULE.REQUIRED_MARKETS
    assert "SOX" in MODULE.REQUIRED_MARKETS


def test_compact_market_drops_history_points():
    row = {"id": "SPX", "price": 10, "changePercent": 1, "points": [{"time": 1, "value": 9}]}
    compact = MODULE.compact_market(row)
    assert compact == {"id": "SPX", "price": 10, "changePercent": 1}
