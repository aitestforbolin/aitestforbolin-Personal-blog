import datetime as dt
import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "market_packet_trigger.py"
SPEC = importlib.util.spec_from_file_location("market_packet_trigger", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def payload(day=2, hour=20):
    timestamp = int(dt.datetime(2026, 9, day, hour, 0, tzinfo=dt.timezone.utc).timestamp())
    return {
        "symbols": [
            {"symbol": symbol, "points": [{"timestamp": timestamp, "value": 100}]}
            for symbol in ("SPY.US", "QQQ.US", "DIA.US")
        ]
    }


class MarketPacketTriggerTests(unittest.TestCase):
    def test_accepts_complete_same_day_close_during_post_close_window(self):
        now = dt.datetime(2026, 9, 2, 20, 57, tzinfo=dt.timezone.utc)
        self.assertEqual(MODULE.closed_snapshot_date(payload(), now), "2026-09-02")

    def test_rejects_intraday_snapshot(self):
        now = dt.datetime(2026, 9, 2, 20, 57, tzinfo=dt.timezone.utc)
        self.assertIsNone(MODULE.closed_snapshot_date(payload(hour=19), now))

    def test_accepts_delayed_close_on_next_trading_day(self):
        now = dt.datetime(2026, 9, 3, 20, 57, tzinfo=dt.timezone.utc)
        self.assertEqual(MODULE.closed_snapshot_date(payload(day=2), now), "2026-09-02")

    def test_accepts_completed_close_outside_old_post_close_window(self):
        now = dt.datetime(2026, 9, 2, 15, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(MODULE.closed_snapshot_date(payload(), now), "2026-09-02")

    def test_rejects_missing_index_proxy(self):
        now = dt.datetime(2026, 9, 2, 20, 57, tzinfo=dt.timezone.utc)
        value = payload()
        value["symbols"].pop()
        self.assertIsNone(MODULE.closed_snapshot_date(value, now))

    def test_skips_already_complete_canonical_packet(self):
        packet = {
            "tradingDate": "2026-09-02",
            "validation": {"complete": True, "criticalErrors": []},
        }
        self.assertTrue(MODULE.packet_is_complete_for_date(packet, "2026-09-02"))
        packet["validation"]["criticalErrors"] = ["stale"]
        self.assertFalse(MODULE.packet_is_complete_for_date(packet, "2026-09-02"))

    def test_packet_workflow_listens_for_completed_price_updates(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/build-market-briefing-packet.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("workflow_run:", workflow)
        self.assertIn("- Update market prices", workflow)
        self.assertIn("- Capture gold close backup", workflow)
        self.assertIn("python scripts/market_packet_trigger.py", workflow)
        self.assertIn("PREVIOUS_PACKET_PATH: /tmp/previous-market-briefing-packet.json", workflow)

    def test_price_writer_refreshes_from_latest_main_after_push_conflict(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/update-market-prices.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("git switch --detach origin/main", workflow)
        self.assertGreaterEqual(workflow.count("python scripts/update_market_prices.py"), 1)
        self.assertNotIn("git rebase origin/main", workflow)

    def test_backup_writer_also_recomputes_after_push_conflict(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/capture-gold-close-backup.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("git switch --detach origin/main", workflow)
        self.assertNotIn("git rebase origin/main", workflow)

    def test_price_schedule_is_limited_to_close_window(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/update-market-prices.yml"
        ).read_text(encoding="utf-8")
        self.assertIn('cron: "11,41 19-21 * * 1-5"', workflow)


if __name__ == "__main__":
    unittest.main()
