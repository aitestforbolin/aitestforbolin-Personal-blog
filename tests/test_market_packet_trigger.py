import datetime as dt
import importlib.util
import unittest
from unittest import mock
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
    def recovery_status(self, **changes):
        return {
            "runDate": "2026-11-10", "asOf": "2026-11-09",
            "status": "failed", "stage": "packet",
            "reasonCode": "packet_wrong_session", "briefingCommit": None,
            **changes,
        }

    def test_requests_recovery_for_current_packet_failure(self):
        now = dt.datetime(2026, 11, 10, 1, tzinfo=dt.timezone.utc)
        self.assertTrue(MODULE.packet_recovery_requested(
            self.recovery_status(), {"tradingDate": "2026-11-06"}, now))
        self.assertTrue(MODULE.packet_recovery_requested(
            self.recovery_status(reasonCode="packet_missing"), {}, now))

    def test_recovery_preserves_terminal_and_downstream_status(self):
        now = dt.datetime(2026, 11, 10, 1, tzinfo=dt.timezone.utc)
        for changes in [
            {"runDate": "2026-11-09"}, {"status": "success"},
            {"status": "no_new_session"}, {"stage": "x"}, {"stage": "email"},
            {"briefingCommit": "already-published"}, {"asOf": "2026-11-10"},
            {"asOf": "invalid"}, {"reasonCode": "x_publish_failed"},
        ]:
            with self.subTest(changes=changes):
                self.assertFalse(MODULE.packet_recovery_requested(
                    self.recovery_status(**changes), {}, now))

    def test_recovery_skips_repaired_or_newer_packet(self):
        now = dt.datetime(2026, 11, 10, 1, tzinfo=dt.timezone.utc)
        for packet in [
            {"tradingDate": "2026-11-09", "validation": {
                "complete": True, "criticalErrors": []}},
            {"tradingDate": "2026-11-10"},
        ]:
            self.assertFalse(MODULE.packet_recovery_requested(
                self.recovery_status(), packet, now))

    def test_recovery_does_not_rebuild_a_stale_close_snapshot(self):
        status = self.recovery_status()
        with mock.patch.dict(MODULE.os.environ, {"PACKET_RECOVERY": "true"}), \
             mock.patch.object(MODULE, "packet_recovery_requested", return_value=True), \
             mock.patch.object(MODULE, "load_json", side_effect=[{}, status, {}]), \
             mock.patch.object(MODULE, "closed_snapshot_date", return_value="2026-11-06"):
            self.assertEqual(MODULE.main(), 1)

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
        self.assertNotIn("- Capture gold close backup", workflow)
        self.assertIn("python scripts/market_packet_trigger.py", workflow)
        self.assertIn("PREVIOUS_PACKET_PATH: /tmp/previous-market-briefing-packet.json", workflow)
        self.assertNotIn("data/daily-market-status.json", workflow)
        self.assertIn('cron: "35 22 * * 1-5"', workflow)

    def test_incomplete_packet_is_preserved_without_replacing_canonical(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/build-market-briefing-packet.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("continue-on-error: true", workflow)
        self.assertIn("steps.packet_build.outcome == 'success'", workflow)
        self.assertIn("Upload failed packet diagnostics", workflow)
        self.assertIn("canonical packet was not changed", workflow)
        self.assertIn("Enforce packet validation result", workflow)

    def test_scheduled_fallback_uses_the_same_complete_packet_gate(self):
        workflow = (
            Path(__file__).parents[1]
            / ".github/workflows/build-market-briefing-packet.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn('[ "$EVENT_NAME" = "schedule" ]', workflow)
        self.assertIn("|| python scripts/market_packet_trigger.py", workflow)

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

