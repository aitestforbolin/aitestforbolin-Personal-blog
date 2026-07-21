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
          <h1>AMD Fiscal Second Quarter 2026 Financial Results</h1>
          <time datetime="2026-08-04T17:00:00">Aug 4, 2026 • 2:00 pm PDT</time>
        </body></html>
        """
        event = updater.build_discovered_event(
            self.companies["amd"],
            "AMD Fiscal Second Quarter 2026 Financial Results",
            "https://ir.amd.com/news-events/ir-calendar/detail/example",
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
        curated = json.loads(updater.CURATED_EVENTS.read_text(encoding="utf-8"))
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
        self.assertTrue(any("official allowlist" in error for error in errors))

    def test_ordinal_fiscal_period_has_stable_id(self):
        period, slug = updater.extract_reported_period("NVIDIA 2nd Quarter FY27 Financial Results")
        self.assertEqual(period, "FY2027 Q2")
        self.assertEqual(slug, "fy2027-q2")


if __name__ == "__main__":
    unittest.main()
