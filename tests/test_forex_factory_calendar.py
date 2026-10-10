from __future__ import annotations
import importlib.util, json, sys, unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError
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
        self.assertEqual(events[0]["metric_values"][0]["source_title"], "Retail Sales m/m")

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

    def test_bridge_backfills_actual_and_revised_previous(self):
        events = ff.parse_forex_factory(json.dumps([
            {"title": "Retail Sales m/m", "country": "USD", "impact": "High", "date": "2026-09-16T08:30:00-04:00", "actual": "", "forecast": "0.8%", "previous": "-0.6%"},
            {"title": "Core Retail Sales m/m", "country": "USD", "impact": "Medium", "date": "2026-09-16T08:30:00-04:00", "actual": "", "forecast": "0.6%", "previous": "-0.3%"},
        ]))
        payload = {
            "ok": True,
            "checked_at": "2026-09-16T12:38:00Z",
            "source_url": "https://www.forexfactory.com/calendar?day=sep16.2026",
            "events": [
                {"event": "Core Retail Sales m/m", "actual": "1.4%", "forecast": "0.6%", "previous": "-0.2%"},
                {"event": "Retail Sales m/m", "actual": "1.2%", "forecast": "0.8%", "previous": "-0.5%"},
            ],
        }
        self.assertEqual(ff.merge_bridge_actuals(events, {"2026-09-16": payload}), 2)
        metrics = {row["source_title"]: row for row in events[0]["metric_values"]}
        self.assertEqual(metrics["Retail Sales m/m"]["actual"], "1.2%")
        self.assertEqual(metrics["Retail Sales m/m"]["previous"], "-0.5%")
        self.assertEqual(events[0]["release_status"], "released")
        self.assertIn("零售环比 1.2%", events[0]["actual"])

    def test_carry_forward_prevents_actual_from_disappearing(self):
        events = ff.parse_forex_factory(json.dumps([{"title": "Federal Funds Rate", "country": "USD", "impact": "High", "date": "2026-09-16T14:00:00-04:00", "actual": "", "forecast": "4.00%", "previous": "3.75%"}]))
        existing = json.loads(json.dumps(events))
        existing[0]["metric_values"][0]["actual"] = "4.00%"
        existing[0]["release_status"] = "released"
        existing[0]["released_at"] = "2026-09-16T18:08:00Z"
        ff.carry_forward_actuals(events, existing)
        self.assertEqual(events[0]["metric_values"][0]["actual"], "4.00%")
        self.assertEqual(events[0]["release_status"], "released")

    def test_actual_bridge_only_runs_for_recent_released_numeric_events(self):
        events = ff.parse_forex_factory(json.dumps([
            {"title": "CPI m/m", "country": "USD", "impact": "High", "date": "2026-09-17T08:30:00-04:00", "actual": "", "forecast": "0.3%", "previous": "0.2%"},
            {"title": "Treasury Sec Bessent Speaks", "country": "USD", "impact": "Medium", "date": "2026-09-17T09:00:00-04:00", "actual": "", "forecast": "", "previous": ""},
        ]))
        now = datetime(2026, 9, 17, 8, 38, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(ff.actual_backfill_days(events, now, 30), ["2026-09-17"])
        self.assertEqual(ff.actual_backfill_days(events, now.replace(hour=12), 30), [])

    def numeric_event(self, day="2026-10-08"):
        return ff.parse_forex_factory(json.dumps([{"title": "Unemployment Claims", "country": "USD", "impact": "Medium", "date": f"{day}T08:30:00-04:00", "forecast": "200K", "previous": "197K"}]))[0]

    def test_default_backfill_includes_missed_releases_days_later(self):
        event = self.numeric_event()
        now = datetime(2026, 10, 10, 10, tzinfo=ff.ET)
        self.assertEqual(ff.actual_backfill_days([event], now), ["2026-10-08"])
        self.assertEqual(ff.actual_backfill_days([event], now.replace(day=16)), [])
        self.assertEqual(ff.actual_backfill_days([event], now.replace(day=8, hour=8, minute=29)), [])

    def test_rollover_keeps_unresolved_release_but_not_speech_or_future_plan(self):
        event = self.numeric_event()
        speech = dict(event, title="Speech", metric_values=[{"actual": None, "forecast": None, "previous": None}])
        future = self.numeric_event("2026-10-13")
        now = datetime(2026, 10, 12, 10, tzinfo=ff.ET)
        self.assertEqual(ff.retain_pending_actuals([event, speech, future], now), [event])

    def test_partial_release_remains_overdue_until_all_expected_metrics_filled(self):
        event = self.numeric_event()
        event["metric_values"].append({"label": "second", "actual": "1", "previous": "2"})
        now = datetime(2026, 10, 8, 9, 1, tzinfo=ff.ET)
        self.assertEqual(ff.annotate_actual_health([event], now), [event])
        self.assertEqual(event["actual_status"], "overdue")
        self.assertEqual(event["actual_missing"], ["初请失业金人数"])
        event["metric_values"][0]["actual"] = "201K"
        self.assertEqual(ff.annotate_actual_health([event], now), [])
        self.assertEqual(event["actual_status"], "complete")

    def test_grace_period_and_nonnumeric_events_are_not_overdue(self):
        event = self.numeric_event()
        now = datetime(2026, 10, 8, 8, 45, tzinfo=ff.ET)
        self.assertEqual(ff.annotate_actual_health([event], now), [])
        self.assertEqual(event["actual_status"], "pending")
        event["metric_values"] = [{"actual": None, "forecast": None, "previous": None}]
        ff.annotate_actual_health([event], now.replace(hour=10))
        self.assertEqual(event["actual_status"], "not_expected")

    def test_capture_time_does_not_replace_release_time_and_unchanged_result_is_stable(self):
        event = self.numeric_event()
        payload = {"checked_at": "2026-10-10T12:00:00Z", "events": [{"event": "Unemployment Claims", "actual": "201K", "previous": "198K"}]}
        self.assertEqual(ff.merge_bridge_actuals([event], {"2026-10-08": payload}), 1)
        self.assertEqual(event["released_at"], "2026-10-08T08:30:00-04:00")
        self.assertEqual(event["actual_updated_at"], "2026-10-10T12:00:00Z")
        payload["checked_at"] = "2026-10-10T13:00:00Z"
        self.assertEqual(ff.merge_bridge_actuals([event], {"2026-10-08": payload}), 0)
        self.assertEqual(event["actual_updated_at"], "2026-10-10T12:00:00Z")

    def test_health_check_fails_overdue_without_changing_snapshot(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "calendar.json"
            original = json.dumps([self.numeric_event()])
            output.write_text(original)
            with patch.object(sys, "argv", ["ff", "--output", str(output), "--check-actual-health"]), patch.object(ff, "datetime", wraps=datetime) as clock:
                clock.now.return_value = datetime(2026, 10, 10, 10, tzinfo=ff.ET)
                with self.assertRaises(SystemExit) as exc:
                    ff.main()
                self.assertEqual(exc.exception.code, 1)
            self.assertEqual(output.read_text(), original)

    def test_main_recovers_prior_week_gap_and_retries_transient_bridge_failure(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "calendar.json"
            output.write_text(json.dumps([self.numeric_event()]))
            feed = json.dumps([{"title": "CPI m/m", "country": "USD", "impact": "High", "date": "2026-10-13T08:30:00-04:00", "forecast": "0.3%", "previous": "0.2%"}])
            payload = {"ok": True, "events": [{"event": "Unemployment Claims", "actual": "201K"}], "checked_at": "2026-10-12T14:00:00Z"}
            with patch.object(sys, "argv", ["ff", "--output", str(output), "--backfill-actual"]), patch.object(ff, "datetime", wraps=datetime) as clock, patch.object(ff, "fetch_text", side_effect=[feed, ""]), patch.object(ff, "fetch_actual_bridge", side_effect=[URLError("temporary"), payload]) as bridge, patch.object(ff.time, "sleep"):
                clock.now.return_value = datetime(2026, 10, 12, 10, tzinfo=ff.ET)
                ff.main()
            recovered = next(x for x in json.loads(output.read_text()) if x["title"] == "Jobless Claims")
            self.assertEqual(bridge.call_count, 2)
            self.assertEqual(recovered["metric_values"][0]["actual"], "201K")
            self.assertEqual(recovered["actual_status"], "complete")

    def test_main_preserves_gap_and_exposes_source_failure(self):
        with TemporaryDirectory() as tmp:
            output = Path(tmp) / "calendar.json"
            output.write_text(json.dumps([self.numeric_event()]))
            feed = json.dumps([{"title": "CPI m/m", "country": "USD", "impact": "High", "date": "2026-10-13T08:30:00-04:00", "forecast": "0.3%", "previous": "0.2%"}])
            with patch.object(sys, "argv", ["ff", "--output", str(output), "--backfill-actual"]), patch.object(ff, "datetime", wraps=datetime) as clock, patch.object(ff, "fetch_text", side_effect=[feed, ""]), patch.object(ff, "fetch_actual_bridge", side_effect=URLError("blocked")) as bridge, patch.object(ff.time, "sleep"):
                clock.now.return_value = datetime(2026, 10, 12, 10, tzinfo=ff.ET)
                ff.main()
            pending = next(x for x in json.loads(output.read_text()) if x["title"] == "Jobless Claims")
            self.assertEqual(bridge.call_count, 3)
            self.assertEqual(pending["actual_check_status"], "source_unavailable")
            self.assertEqual(pending["actual_status"], "overdue")

if __name__ == "__main__": unittest.main()

