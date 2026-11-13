from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch


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
            ["MSFT", "AMZN", "GOOGL", "ORCL", "META", "CRWV", "NBIS", "NVDA", "AMD", "AVGO", "MRVL", "TSM", "MU", "SNDK", "WDC", "ANET", "LITE", "COHR", "DELL", "SMCI", "AAPL"],
        )
        self.assertEqual(len(self.companies), 21)

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

    def test_official_discovery_follows_earnings_and_ignores_product_events(self):
        company = deepcopy(self.companies["nvidia"])
        listing = "https://investor.nvidia.com/events"
        company["discovery_urls"] = [listing]
        pages = {
            listing: '<a href="/earnings">NVIDIA FY2027 Third Quarter Financial Results</a><a href="/gtc">NVIDIA GTC</a>',
            "https://investor.nvidia.com/earnings": '<p>NVIDIA will host a conference call on November 17, 2026 at 2:00 p.m. PT.</p>',
        }
        with patch.object(updater, "fetch_text", side_effect=lambda url: pages[url]) as fetch:
            events = updater.discover_company_events(company, date(2026, 11, 13), date(2026, 12, 18))
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["date_bjt"], "2026-11-18")
        self.assertEqual(events[0]["time_bjt"], "06:00")
        self.assertEqual(events[0]["event_category"], "earnings")

    def test_announcement_timestamp_does_not_replace_the_call_time(self):
        html = '''<time itemprop="datePublished" datetime="2026-11-13T08:00:00-06:00">Published November 13, 2026 at 8:00 a.m. CST</time>
        <p>Dell will conduct a conference call on November 24, 2026 at 3:30 p.m. CST.</p>
        <p>A replay is available until December 8, 2026.</p>'''
        event = updater.build_discovered_event(self.companies["dell"], "Dell Third Quarter Financial Results", "https://investors.delltechnologies.com/news", html, date(2026, 11, 13), date(2026, 12, 18))
        self.assertEqual((event["date_bjt"], event["time_bjt"]), ("2026-11-25", "05:30"))

    def test_replay_deadline_alone_is_not_a_scheduled_earnings_date(self):
        event = updater.build_discovered_event(self.companies["marvell"], "Q3 2027 Marvell Earnings Conference Call", "https://investor.marvell.com/event", '<p>A replay of the call is available until December 8, 2026.</p>', date(2026, 11, 13), date(2026, 12, 18))
        self.assertIsNone(event)

    def test_announcement_without_year_uses_the_event_window(self):
        event = updater.build_discovered_event(self.companies["nvidia"], "NVIDIA Third Quarter Financial Results", "https://investor.nvidia.com/event", '<p>NVIDIA will host a conference call on November 17 at 2 p.m. PT.</p>', date(2026, 11, 13), date(2026, 12, 18))
        self.assertEqual((event["date_bjt"], event["time_bjt"]), ("2026-11-18", "06:00"))

    def test_first_beijing_day_can_be_the_previous_local_day(self):
        event = updater.build_discovered_event(self.companies["nvidia"], "NVIDIA Financial Results", "https://investor.nvidia.com/event", '<p>NVIDIA will host a conference call on November 17, 2026 at 2 p.m. PT.</p>', date(2026, 11, 18), date(2026, 11, 18))
        self.assertEqual(event["date_bjt"], "2026-11-18")

    def test_offset_aware_event_time_keeps_its_explicit_timezone(self):
        event = updater.build_discovered_event(self.companies["marvell"], "Marvell Earnings Call", "https://investor.marvell.com/event", '<time datetime="2026-12-01T17:30:00-05:00">Dec 1, 2026</time>', date(2026, 11, 13), date(2026, 12, 18))
        self.assertEqual((event["date_bjt"], event["time_bjt"]), ("2026-12-02", "06:30"))

    def test_date_only_us_guidance_does_not_guess_a_beijing_clock(self):
        event = updater.build_discovered_event(self.companies["oracle"], "Oracle FY2027 Q2 Earnings", "https://investor.oracle.com/event", '<p>Oracle will announce earnings on December 14, 2026.</p>', date(2026, 11, 13), date(2026, 12, 18))
        self.assertEqual(event["confirmation"], "guided")
        self.assertEqual((event["window_start"], event["window_end"]), ("2026-12-14", "2026-12-15"))
        self.assertIsNone(event["time_bjt"])
        self.assertNotIn("date_bjt", event)

    def test_script_text_is_not_used_as_event_evidence(self):
        event = updater.build_discovered_event(self.companies["marvell"], "Marvell Earnings Call", "https://investor.marvell.com/event", '<script>will host a conference call on November 30, 2026 at 8 p.m. PT</script><p>Marvell will host a conference call on Dec 1, 2026 at 1:30 p.m. PT.</p>', date(2026, 11, 13), date(2026, 12, 18))
        self.assertEqual((event["date_bjt"], event["time_bjt"]), ("2026-12-02", "05:30"))

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
        updater.fetch_text = lambda url: json.dumps({"data": {"rows": [{"symbol": "AVGO", "time": "Before Market Open", "epsForecast": "5.12", "revenueForecast": "46.2B", "fiscalQuarterEnding": "09/30/2026"}]}})
        try:
            events = updater.discover_earnings_calendar_events(config, list(self.companies.values()), date(2026, 10, 13), date(2026, 10, 13))
        finally:
            updater.fetch_text = original
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["company_id"], "broadcom")
        self.assertEqual(events[0]["market_timing"], "before_open")
        self.assertEqual(events[0]["date_bjt"], "2026-10-13")
        self.assertEqual(events[0]["eps_estimate"], "5.12")
        self.assertEqual(events[0]["revenue_estimate"], "46.2B")
        self.assertEqual(events[0]["confirmation"], "inferred")

    def test_confirmed_official_earnings_replaces_matching_nasdaq_inference(self):
        inferred = {
            "event_id": "broadcom-earnings-quarter-ended-2026-09-30",
            "company_id": "broadcom", "event_category": "earnings", "event_name": "Broadcom 财报",
            "reported_period": "截至 2026-09-30 季度", "importance": "core", "status": "scheduled",
            "confirmation": "inferred", "date_type": "exact", "date_bjt": "2026-10-13", "market_timing": "before_open",
            "source_label": "Nasdaq Earnings Calendar", "source_url": "https://api.nasdaq.com/api/calendar/earnings?date=2026-10-13",
        }
        official = deepcopy(inferred)
        official.update({"event_id": "broadcom-earnings-2026-q3", "confirmation": "confirmed", "time_bjt": "20:30", "source_label": "Broadcom Investor Relations", "source_url": "https://investors.broadcom.com/"})
        events = updater.merge_events(list(self.companies.values()), [official], [inferred], [], date(2026, 9, 18), 35, datetime(2026, 9, 18, tzinfo=ZoneInfo("Asia/Shanghai")))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["confirmation"], "confirmed")
        self.assertEqual(events[0]["source_label"], "Broadcom Investor Relations")

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

    def test_removed_companies_and_non_earnings_do_not_survive_refresh(self):
        now = datetime(2026, 11, 13, tzinfo=ZoneInfo("Asia/Shanghai"))
        prior = [
            {"event_id": "walmart-earnings", "company_id": "walmart", "event_category": "earnings", "date_bjt": "2026-11-19"},
            {"event_id": "nvidia-product", "company_id": "nvidia", "event_category": "product_event", "date_bjt": "2026-11-19"},
        ]
        self.assertEqual(updater.merge_events(list(self.companies.values()), prior, prior, prior, date(2026, 11, 13), 35, now), [])

    def test_nasdaq_icon_timing_uses_next_beijing_day(self):
        self.assertEqual(updater.normalize_calendar_time("time-pre-market"), "before_open")
        self.assertEqual(updater.normalize_calendar_time("time-after-hours"), "after_close")
        original = updater.fetch_text
        updater.fetch_text = lambda url: json.dumps({"data": {"rows": [{"symbol": "DELL", "time": "time-after-hours"}, {"symbol": "WMT", "time": "time-pre-market"}]}})
        try:
            events = updater.discover_earnings_calendar_events(self.config, list(self.companies.values()), date(2026, 11, 24), date(2026, 11, 24))
        finally:
            updater.fetch_text = original
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["company_id"], "dell")
        self.assertEqual(events[0]["date_bjt"], "2026-11-25")


if __name__ == "__main__":
    unittest.main()


