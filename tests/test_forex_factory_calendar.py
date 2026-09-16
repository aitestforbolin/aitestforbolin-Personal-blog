from __future__ import annotations
import importlib.util, json, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ff_calendar", ROOT / "scripts" / "fetch_forex_factory_calendar.py")
assert spec and spec.loader
ff = importlib.util.module_from_spec(spec); sys.modules[spec.name] = ff; spec.loader.exec_module(ff)

class ForexFactoryCalendarTests(unittest.TestCase):
    def test_groups_retail_rows_and_converts_to_shanghai_time(self):
        events = ff.parse_forex_factory(json.dumps([{"title": "Retail Sales m/m", "country": "USD", "impact": "High", "date": "2026-09-16T08:30:00-04:00", "actual": "0.9%", "forecast": "0.8%", "previous": "-0.6%"}, {"title": "Core Retail Sales m/m", "country": "USD", "impact": "Medium", "date": "2026-09-16T08:30:00-04:00", "actual": "0.7%", "forecast": "0.6%", "previous": "-0.3%"}]))
        self.assertEqual(len(events), 1); self.assertEqual(events[0]["time_shanghai"], "20:30")
        self.assertEqual(events[0]["title_cn"], "美国零售销售"); self.assertEqual(events[0]["release_status"], "released")
        self.assertEqual([row["label"] for row in events[0]["metric_values"]], ["零售环比", "核心零售环比"])

    def test_fed_validation_replaces_fomc_schedule_source(self):
        events = ff.parse_forex_factory(json.dumps([{"title": "Federal Funds Rate", "country": "USD", "impact": "High", "date": "2026-09-16T14:00:00-04:00", "actual": "", "forecast": "4.00%", "previous": "3.75%"}]))
        ff.validate_fomc(events, "<p>2026 FOMC Meetings</p><p>September</p><p>15-16</p><p>Statement</p>")
        self.assertEqual(events[0]["fomc_validation"], "confirmed"); self.assertIn("Federal Reserve", events[0]["source"])

    def test_calendar_accepts_all_medium_and_high_us_events(self):
        rows = [
            {"title": "CPI m/m", "country": "USD", "impact": "High", "date": "2026-09-17T08:30:00-04:00", "actual": "", "forecast": "0.3%", "previous": "0.2%"},
            {"title": "Industrial Production m/m", "country": "USD", "impact": "Medium", "date": "2026-09-18T09:15:00-04:00", "actual": "", "forecast": "0.3%", "previous": "0.2%"},
            {"title": "JOLTS Job Openings", "country": "USD", "impact": "High", "date": "2026-09-18T10:00:00-04:00", "actual": "", "forecast": "7.1M", "previous": "7.2M"},
        ]
        events = ff.parse_forex_factory(json.dumps(rows))
        self.assertEqual([event["title"] for event in events], ["CPI", "Industrial Production", "JOLTS"])

    def test_unmapped_medium_impact_us_event_uses_forex_factory_title(self):
        rows = [{"title": "NFIB Small Business Index", "country": "USD", "impact": "Medium", "date": "2026-09-17T08:30:00-04:00", "actual": "", "forecast": "98.0", "previous": "97.0"}]
        events = ff.parse_forex_factory(json.dumps(rows))
        self.assertEqual(events[0]["title_cn"], "NFIB Small Business Index")
        self.assertEqual(events[0]["metric_values"][0]["label"], "公布值")

    def test_calendar_rejects_low_impact_rows_inside_the_core_whitelist(self):
        rows = [{"title": "CPI m/m", "country": "USD", "impact": "Low", "date": "2026-09-17T08:30:00-04:00", "actual": "", "forecast": "0.3%", "previous": "0.2%"}]
        self.assertEqual(ff.parse_forex_factory(json.dumps(rows)), [])

    def test_snapshot_window_excludes_old_events(self):
        kept = ff.retain_window([{"date_et": "2026-09-14", "title": "CPI"}, {"date_et": "2026-09-10", "title": "CPI"}, {"date_et": "2026-09-23", "title": "CPI"}], ff.date(2026, 9, 16))
        self.assertEqual([row["date_et"] for row in kept], ["2026-09-14", "2026-09-23"])

    def test_successful_feed_never_retains_an_unreleased_legacy_event(self):
        kept = ff.retain_released_window([{"date_et": "2026-09-15", "title": "CPI", "release_status": "released"}, {"date_et": "2026-09-17", "title": "CPI", "release_status": "scheduled"}], ff.date(2026, 9, 16))
        self.assertEqual([row["date_et"] for row in kept], ["2026-09-15"])

if __name__ == "__main__": unittest.main()
