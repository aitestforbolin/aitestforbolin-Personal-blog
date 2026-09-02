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

    def test_rejects_old_close_on_next_trading_day(self):
        now = dt.datetime(2026, 9, 3, 20, 57, tzinfo=dt.timezone.utc)
        self.assertIsNone(MODULE.closed_snapshot_date(payload(day=2), now))

    def test_rejects_event_outside_post_close_window(self):
        now = dt.datetime(2026, 9, 2, 15, 0, tzinfo=dt.timezone.utc)
        self.assertIsNone(MODULE.closed_snapshot_date(payload(), now))

    def test_rejects_missing_index_proxy(self):
        now = dt.datetime(2026, 9, 2, 20, 57, tzinfo=dt.timezone.utc)
        value = payload()
        value["symbols"].pop()
        self.assertIsNone(MODULE.closed_snapshot_date(value, now))


if __name__ == "__main__":
    unittest.main()
