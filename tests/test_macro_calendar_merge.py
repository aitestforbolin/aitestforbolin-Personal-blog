from __future__ import annotations
import importlib.util, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("macro_calendar_merger", ROOT / "scripts" / "merge_macro_calendars.py")
assert spec and spec.loader
merger = importlib.util.module_from_spec(spec); sys.modules[spec.name] = merger; spec.loader.exec_module(merger)

class MacroCalendarMergeTests(unittest.TestCase):
    def test_merge_publishes_us_only_with_metrics(self):
        payload = merger.build_payload([{"date": "2026-09-16", "time_shanghai": "20:30", "title": "Retail", "title_cn": "美国零售销售", "category": "growth", "importance": "high", "stars": 4, "source": "Forex Factory", "url": "https://www.forexfactory.com/calendar", "metric_values": [{"label": "零售环比", "actual": None, "forecast": "0.8%", "previous": "-0.6%"}]}])
        merger.validate(payload)
        self.assertEqual(payload["schemaVersion"], 2)
        self.assertEqual(payload["events"][0]["country"], "US")
        self.assertEqual(payload["events"][0]["metrics"][0]["forecast"], "0.8%")

    def test_validator_rejects_non_us_event(self):
        with self.assertRaises(ValueError): merger.validate({"events": [{"country": "CN", "scheduledAt": "2026-09-16T20:30:00+08:00", "id": "cn"}]})

    def test_overdue_actual_is_partial_and_survives_normalization(self):
        event = {"date": "2026-10-08", "time_shanghai": "20:30", "title": "Jobless Claims", "calendar_status": "healthy", "actual_status": "overdue", "actual_missing": ["初请失业金人数"]}
        payload = merger.build_payload([event])
        self.assertEqual(payload["status"], "partial")
        self.assertEqual(payload["health"]["US"]["status"], "partial")
        self.assertEqual(payload["events"][0]["actualMissing"], ["初请失业金人数"])
        event["calendar_status"] = "stale_snapshot"
        self.assertEqual(merger.build_payload([event])["status"], "stale")

if __name__ == "__main__": unittest.main()

