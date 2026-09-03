from __future__ import annotations

import importlib.util
import unittest
from datetime import date
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "repair_us_macro_calendar.py"
SPEC = importlib.util.spec_from_file_location("us_macro_calendar_repair", SCRIPT_PATH)
assert SPEC and SPEC.loader
repair = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(repair)


class UsMacroCalendarRepairTests(unittest.TestCase):
    def test_september_nonfarm_is_restored_as_critical_event(self):
        repaired, added = repair.repair_events([], date(2026, 9, 3))
        event = next(
            item
            for item in repaired
            if item["title"] == "Employment Situation" and item["date"] == "2026-09-04"
        )

        self.assertIn("2026-09-04:Employment Situation", added)
        self.assertEqual(event["title_cn"], "美国非农 / 失业率 / 平均时薪")
        self.assertEqual(event["time_et"], "08:30")
        self.assertEqual(event["time_shanghai"], "20:30")
        self.assertEqual(event["importance"], "critical")
        self.assertEqual(event["stars"], 5)
        self.assertEqual(event["source"], "BLS")
        self.assertEqual(event["url"], "https://www.bls.gov/schedule/news_release/empsit.htm")

    def test_existing_live_event_is_not_overwritten_or_duplicated(self):
        live = repair.make_event("2026-09-04", "08:30", "Employment Situation", "August 2026")
        live["forecast"] = "live value"

        repaired, added = repair.repair_events([live], date(2026, 9, 3))
        matches = [item for item in repaired if item["title"] == "Employment Situation" and item["date"] == "2026-09-04"]

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["forecast"], "live value")
        self.assertNotIn("2026-09-04:Employment Situation", added)

    def test_dst_conversion_is_correct_after_new_york_fall_back(self):
        event = repair.make_event("2026-11-06", "08:30", "Employment Situation", "October 2026")
        self.assertEqual(event["time_shanghai"], "21:30")

    def test_repair_only_adds_rows_inside_rolling_window(self):
        repaired, _ = repair.repair_events([], date(2026, 9, 3))
        dates = {item["date"] for item in repaired}

        self.assertIn("2026-10-02", dates)
        self.assertNotIn("2026-11-06", dates)


if __name__ == "__main__":
    unittest.main()
