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

    def test_gold_proxy_is_explicit_and_frontend_uses_dynamic_source(self):
        script = (
            ROOT / "daily-market-status" / "daily-market-status.js"
        ).read_text(encoding="utf-8")
        self.assertIn('"COMEX黄金期货（代理）"', script)
        self.assertIn('stored?.symbol === "GC=F"', script)
        self.assertIn('item.sourceSymbol === "GC=F"', script)

    def test_unverified_static_session_changes_are_hidden_until_live_validation(self):
        script = (
            ROOT / "daily-market-status" / "daily-market-status.js"
        ).read_text(encoding="utf-8")
        self.assertIn('return item?.__changeValidated ? formatPercent(item.changePercent) : "数据核验中"', script)
        self.assertIn("staticSessionChangeValid(item)", script)
        self.assertIn("liveSessionChangeValid(item)", script)
        self.assertIn("copyButton.disabled = !ready", script)

    def test_delayed_capture_schedule_is_disabled(self):
        workflow = (
            ROOT / ".github" / "workflows" / "capture-gold-close-backup.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("schedule:", workflow)
        self.assertIn("workflow_dispatch:", workflow)

    def test_current_fedwatch_snapshot_targets_an_unfinished_meeting(self):
        payload = json.loads(
            (ROOT / "data" / "daily-market-status.json").read_text(encoding="utf-8")
        )
        fed = payload["fedProbability"]
        self.assertEqual(fed["meetingStartDate"], "2026-10-27")
        self.assertEqual(fed["probabilities"], {})
        self.assertEqual(fed["status"], "unavailable")

    def test_frontend_only_renders_verified_structured_fedwatch_data(self):
        script = (ROOT / "daily-market-status" / "daily-market-status.js").read_text(encoding="utf-8")
        self.assertIn("function verifiedFedProbability(fed)", script)
        self.assertIn("meetingEnd < Date.now()", script)
        self.assertIn("下一次 FOMC 概率：数据核验中", script)


if __name__ == "__main__":
    unittest.main()
