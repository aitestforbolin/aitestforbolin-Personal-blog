import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STANDARD_SECTORS = {
    "XLC",
    "XLY",
    "XLP",
    "XLE",
    "XLF",
    "XLV",
    "XLI",
    "XLB",
    "XLRE",
    "XLK",
    "XLU",
}


class DailyMarketStatusSectorTests(unittest.TestCase):
    def test_fallback_contains_all_standard_sectors(self):
        payload = json.loads(
            (ROOT / "data" / "daily-market-status.json").read_text(encoding="utf-8")
        )
        fallback_ids = {item["id"] for item in payload["fallback"]["markets"]}
        self.assertTrue(STANDARD_SECTORS <= fallback_ids)
        self.assertIn("SOX", fallback_ids)

    def test_page_and_copy_configs_are_complete(self):
        script = (
            ROOT / "daily-market-status" / "daily-market-status.js"
        ).read_text(encoding="utf-8")
        for ticker in STANDARD_SECTORS:
            self.assertGreaterEqual(script.count(f'"{ticker}"'), 2, ticker)
        self.assertIn("SOX（半导体指数·补充）", script)
        self.assertIn("SOX（半导体·补充行业指数）", script)


if __name__ == "__main__":
    unittest.main()
