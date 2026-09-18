from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_tech_company_events.py"
SPEC = importlib.util.spec_from_file_location("tech_events_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class TechCompanyEventTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(updater.SOURCE_CONFIG.read_text(encoding="utf-8"))
        cls.companies = {item["id"]: item for item in cls.config["companies"]}

    def test_summer_time_converts_to_next_beijing_day(self):
        html = """
        <html><body>
          <h1>Apple Third Quarter 2026 Financial Results</h1>
          <p>Apple will report Third Quarter 2026 Financial Results on July 30, 2026,
          after market close. The webcast begins at 2:00 p.m. Pacific Time.</p>
        </body></html>
        """
        event = updater.build_discovered_event(
            self.companies["apple"],
            "Apple Third Quarter 2026 Financial Results",
            "https://investor.apple.com/",
            html,
            date(2026, 7, 21),
            date(2026, 8, 25),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["date_bjt"], "2026-07-31")
        self.assertEqual(event["time_bjt"], "05:00")
        self.assertEqual(event["market_timing"], "after_close")

    def test_tracking_universe_matches_requested_symbols(self):
        self.assertEqual(
            [company["ticker"] for company in self.config["companies"]],
            ["META", "NVDA", "AMZN", "GOOGL", "AAPL", "JPM", "MSFT", "WMT", "MU", "SNDK"],
        )
        self.assertEqual(len(self.companies), 10)

    def test_standard_time_converts_with_sixteen_hour_offset(self):
        html = """
        <html><body>
          <h1>Apple First Quarter FY2027 Financial Results</h1>
          <p>The webcast will take place on December 10, 2026 at 2:00 p.m. PT.</p>
        </body></html>
        """
        event = updater.build_discovered_event(
            self.companies["apple"],
            "Apple First Quarter FY2027 Financial Results",
            "https://investor.apple.com/",
            html,
            date(2026, 12, 1),
            date(2027, 1, 5),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["date_bjt"], "2026-12-11")
        self.assertEqual(event["time_bjt"], "06:00")

    def test_visible_timezone_wins_over_naive_machine_time(self):
        html = """
        <html><body>
          <h1>NVIDIA Fiscal Second Quarter 2026 Financial Results</h1>
          <time datetime="2026-08-04T17:00:00">Aug 4, 2026 • 2:00 pm PDT</time>
        </body></html>
        """
        event = updater.build_discovered_event(
            self.companies["nvidia"],
            "NVIDIA Fiscal Second Quarter 2026 Financial Results",
            "https://investor.nvidia.com/events-and-presentations/default.aspx",
            html,
            date(2026, 7, 21),
            date(2026, 8, 25),
        )
        self.assertIsNotNone(event)
        self.assertEqual(event["date_bjt"], "2026-08-05")
        self.assertEqual(event["time_bjt"], "05:00")

    def test_window_overlap_is_included_at_horizon_boundary(self):
        event = {
            "event_id": "test-window",
            "window_start": "2026-08-25",
            "window_end": "2026-09-04",
        }
        self.assertTrue(
            updater.within_horizon(event, date(2026, 7, 21), date(2026, 8, 25))
        )

    def test_date_change_preserves_previous_timing(self):
        previous = {
            "event_id": "apple-earnings-2026-q3",
            "company_id": "apple",
            "event_category": "earnings",
            "event_name": "Apple 财报",
            "reported_period": "2026 Q3",
            "importance": "core",
            "status": "scheduled",
            "confirmation": "inferred",
            "date_type": "window",
            "window_start": "2026-07-30",
            "window_end": "2026-08-06",
            "market_timing": "time_tbd",
            "source_label": "Apple Investor Relations",
            "source_url": "https://investor.apple.com/",
            "updated_at": "2026-07-20T08:00:00+08:00",
        }
        confirmed = deepcopy(previous)
        confirmed.update(
            {
                "confirmation": "confirmed",
                "date_type": "exact",
                "date_bjt": "2026-08-01",
                "time_bjt": "05:00",
                "start_at": "2026-08-01T05:00:00+08:00",
            }
        )
        confirmed.pop("window_start")
        confirmed.pop("window_end")
        now = datetime(2026, 7, 22, 8, 15, tzinfo=ZoneInfo("Asia/Shanghai"))
        merged = updater.merge_events(
            list(self.companies.values()),
            [],
            [confirmed],
            [previous],
            date(2026, 7, 22),
            35,
            now,
        )
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["date_changed"])
        self.assertEqual(merged[0]["status"], "changed")
        self.assertEqual(merged[0]["previous_timing"]["window_start"], "2026-07-30")

    def test_validator_rejects_non_official_source(self):
        curated = [{
            "event_id": "nvidia-earnings-test",
            "company_id": "nvidia",
            "event_category": "earnings",
            "event_name": "NVIDIA 财报",
            "importance": "core",
            "status": "scheduled",
            "confirmation": "confirmed",
            "date_type": "exact",
            "date_bjt": "2026-07-30",
            "time_bjt": "05:00",
            "market_timing": "after_close",
            "source_label": "NVIDIA Investor Relations",
            "source_url": "https://investor.nvidia.com/",
            "updated_at": "2026-07-21T08:15:00+08:00",
        }]
        events = updater.merge_events(
            list(self.companies.values()),
            curated,
            [],
            [],
            date(2026, 7, 21),
            35,
            datetime(2026, 7, 21, 8, 15, tzinfo=ZoneInfo("Asia/Shanghai")),
        )
        payload = updater.build_payload(self.config, events, "2026-07-21T08:15:00+08:00")
        payload["events"][0]["source_url"] = "https://example.com/unofficial"
        errors = updater.validate_event_payload(payload, self.config)
        self.assertTrue(any("configured allowlist" in error for error in errors))

    def test_nasdaq_calendar_builds_tracked_earnings_with_estimates_and_bjt_timing(self):
        config = deepcopy(self.config)
        config["earnings_calendar"]["url_template"] = "https://example.test/earnings?date={day}"
        original = updater.fetch_text
        updater.fetch_text = lambda url: json.dumps({"data": {"rows": [{"symbol": "JPM", "time": "Before Market Open", "epsForecast": "5.12", "revenueForecast": "46.2B", "fiscalQuarterEnding": "09/30/2026"}]}})
        try:
            events = updater.discover_earnings_calendar_events(config, list(self.companies.values()), date(2026, 10, 13), date(2026, 10, 13))
        finally:
            updater.fetch_text = original
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["company_id"], "jpmorgan_chase")
        self.assertEqual(events[0]["market_timing"], "before_open")
        self.assertEqual(events[0]["date_bjt"], "2026-10-13")
        self.assertEqual(events[0]["eps_estimate"], "5.12")
        self.assertEqual(events[0]["revenue_estimate"], "46.2B")
        self.assertEqual(events[0]["confirmation"], "inferred")

    def test_confirmed_official_earnings_replaces_matching_nasdaq_inference(self):
        inferred = {
            "event_id": "jpmorgan_chase-earnings-quarter-ended-2026-09-30",
            "company_id": "jpmorgan_chase", "event_category": "earnings", "event_name": "JPMorgan Chase 财报",
            "reported_period": "截至 2026-09-30 季度", "importance": "core", "status": "scheduled",
            "confirmation": "inferred", "date_type": "exact", "date_bjt": "2026-10-13", "market_timing": "before_open",
            "source_label": "Nasdaq Earnings Calendar", "source_url": "https://api.nasdaq.com/api/calendar/earnings?date=2026-10-13",
        }
        official = deepcopy(inferred)
        official.update({"event_id": "jpmorgan_chase-earnings-2026-q3", "confirmation": "confirmed", "time_bjt": "20:30", "source_label": "JPMorgan Chase Investor Relations", "source_url": "https://www.jpmorganchase.com/ir/events"})
        events = updater.merge_events(list(self.companies.values()), [official], [inferred], [], date(2026, 9, 18), 35, datetime(2026, 9, 18, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["confirmation"], "confirmed")
        self.assertEqual(events[0]["source_label"], "JPMorgan Chase Investor Relations")

    def test_ordinal_fiscal_period_has_stable_id(self):
        period, slug = updater.extract_reported_period("NVIDIA 2nd Quarter FY27 Financial Results")
        self.assertEqual(period, "FY2027 Q2")
        self.assertEqual(slug, "fy2027-q2")

    def test_report_fiscal_quarter_results_is_an_earnings_event(self):
        title = "Micron Technology to Report Fiscal Fourth Quarter Results on September 30, 2026"
        self.assertTrue(updater.is_material_title(title))
        self.assertEqual(updater.classify_event(title), "earnings")

    def test_checked_at_does_not_change_event_semantics(self):
        first = updater.build_payload(self.config, [], "2026-09-03T16:18:40+08:00", "2026-09-16T05:50:00+08:00")
        second = updater.build_payload(self.config, [], "2026-09-03T16:18:40+08:00", "2026-09-17T05:50:00+08:00")
        self.assertEqual(updater.semantic_payload(first), updater.semantic_payload(second))

    def test_validator_requires_last_check_time(self):
        payload = updater.build_payload(self.config, [], "2026-09-03T16:18:40+08:00")
        payload.pop("checked_at")
        errors = updater.validate_event_payload(payload, self.config)
        self.assertIn("checked_at is required", errors)


if __name__ == "__main__":
    unittest.main()
