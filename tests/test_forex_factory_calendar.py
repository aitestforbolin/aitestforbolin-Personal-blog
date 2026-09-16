from __future__ import annotations
import importlib.util, json, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ff_calendar", ROOT / "scripts" / "fetch_forex_factory_calendar.py")
assert spec and spec.loader
ff = importlib.util.module_from_spec(spec); sys.modules[spec.name] = ff; spec.loader.exec_module(ff)

class ForexFactoryCalendarTests(unittest.TestCase):
    def test_groups_retail_rows_and_converts_to_shanghai_time(self):
        events = ff.parse_forex_factory(json.dumps([{"title": "Retail Sales m/m", "country": "USD", "date": "2026-09-16T08:30:00-04:00", "actual": "0.9%", "forecast": "0.8%", "previous": "-0.6%"}, {"title": "Core Retail Sales m/m", "country": "USD", "date": "2026-09-16T08:30:00-04:00", "actual": "0.7%", "forecast": "0.6%", "previous": "-0.3%"}]))
        self.assertEqual(len(events), 1); self.assertEqual(events[0]["time_shanghai"], "20:30")
        self.assertEqual(events[0]["title_cn"], "美国零售销售"); self.assertEqual(events[0]["release_status"], "released")
        self.assertEqual([row["label"] for row in events[0]["metric_values"]], ["零售环比", "核心零售环比"])

    def test_fed_validation_replaces_fomc_schedule_source(self):
        events = ff.parse_forex_factory(json.dumps([{"title": "Federal Funds Rate", "country": "USD", "date": "2026-09-16T14:00:00-04:00", "actual": "", "forecast": "4.00%", "previous": "3.75%"}]))
        ff.validate_fomc(events, "<p>2026 FOMC Meetings</p><p>September</p><p>15-16</p><p>Statement</p>")
        self.assertEqual(events[0]["fomc_validation"], "confirmed"); self.assertIn("Federal Reserve", events[0]["source"])

    def test_snapshot_window_excludes_old_events(self):
        kept = ff.retain_window([{"date_et": "2026-09-14"}, {"date_et": "2026-09-10"}, {"date_et": "2026-09-23"}], ff.date(2026, 9, 16))
        self.assertEqual([row["date_et"] for row in kept], ["2026-09-14", "2026-09-23"])

    def test_successful_feed_never_retains_an_unreleased_legacy_event(self):
        kept = ff.retain_released_window([{"date_et": "2026-09-15", "release_status": "released"}, {"date_et": "2026-09-17", "release_status": "scheduled"}], ff.date(2026, 9, 16))
        self.assertEqual([row["date_et"] for row in kept], ["2026-09-15"])

if __name__ == "__main__": unittest.main()
