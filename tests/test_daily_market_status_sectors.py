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

    def test_gold_latest_quote_is_rendered_when_close_anchor_is_missing(self):
        script = (
            ROOT / "daily-market-status" / "daily-market-status.js"
        ).read_text(encoding="utf-8")
        self.assertIn("function goldAssetLine(comparison, compact)", script)
        self.assertIn("16:00 ET固定锚点缺失，未计算日内变动", script)
        self.assertIn('goldAssetLine(comparisons.get("GOLD"), false)', script)
        self.assertIn('goldAssetLine(comparisons.get("GOLD"), true)', script)
        self.assertIn('item.id === "GOLD"', script)

    def test_gold_has_an_independent_pre_close_capture_schedule(self):
        workflow = (
            ROOT / ".github" / "workflows" / "capture-gold-close-backup.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "35,50 19,20 * * 1-5"', workflow)
        self.assertIn("group: market-prices-writer", workflow)
        self.assertIn("python scripts/update_market_prices.py", workflow)


if __name__ == "__main__":
    unittest.main()
