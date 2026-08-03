from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


updater = load_module(
    "china_macro_for_merge_tests",
    ROOT / "scripts" / "update_china_macro_calendar.py",
)
merger = load_module(
    "macro_calendar_merger",
    ROOT / "scripts" / "merge_macro_calendars.py",
)


class MacroCalendarMergeTests(unittest.TestCase):
    def test_policy_events_keep_confirmed_date_without_inventing_meeting_time(self):
        policy = json.loads(
            (ROOT / "data" / "china-policy-events.json").read_text(encoding="utf-8")
        )
        merger.validate_policy_payload(policy)
        china = {
            "status": "healthy",
            "events": [
                updater.make_event(
                    "prices",
                    "2026-07",
                    scheduled_at="2026-08-09T09:30:00+08:00",
                )
            ],
        }
        us = [
            {
                "date": "2026-08-08",
                "time_shanghai": "20:30",
                "title": "Example",
                "title_cn": "美国示例",
                "source": "Official",
                "url": "https://www.bls.gov/",
            }
        ]
        payload = merger.build_payload(
            us, china, "2026-08-03T00:00:00Z", policy
        )
        meeting = next(
            event
            for event in payload["events"]
            if event["id"] == "cn-policy-politburo-economy-2026-07-30"
        )
        self.assertEqual(meeting["eventType"], "policy_event")
        self.assertEqual(meeting["eventDate"], "2026-07-30")
        self.assertIsNone(meeting["scheduledAt"])
        self.assertIn("未公开具体召开时刻", meeting["scheduleNote"])

    def test_policy_validator_rejects_aggregator_source(self):
        policy = json.loads(
            (ROOT / "data" / "china-policy-events.json").read_text(encoding="utf-8")
        )
        policy["events"][0]["sourceUrl"] = "https://example.com/calendar"
        with self.assertRaises(ValueError):
            merger.validate_policy_payload(policy)

    def test_legacy_us_fields_are_preserved_without_overwriting_normalized_title(self):
        legacy = {
            "date": "2026-08-12",
            "time_shanghai": "20:30",
            "title": "Consumer Price Index",
            "title_cn": "美国CPI / 核心CPI",
            "period": "July 2026",
            "category": "inflation",
            "importance": "critical",
            "stars": 5,
            "source": "BLS",
            "url": "https://www.bls.gov/schedule/news_release/",
            "forecast": "0.2%",
            "previous": "0.1%",
        }
        event = merger.normalize_us_event(legacy)
        self.assertEqual(event["country"], "US")
        self.assertEqual(event["title"], "美国CPI / 核心CPI")
        self.assertEqual(event["legacy"], legacy)
        self.assertEqual(event["metrics"][0]["forecast"], "0.2%")

    def test_unified_merge_keeps_one_event_for_multi_metric_china_release(self):
        china = {
            "status": "static_sample",
            "failedSources": [],
            "events": updater.build_static_calendar(),
        }
        us = [
            {
                "date": "2026-08-03",
                "time_shanghai": "22:00",
                "title": "ISM Manufacturing",
                "title_cn": "美国ISM制造业PMI",
                "source": "ISM",
                "url": "https://www.ismworld.org/",
            }
        ]
        payload = merger.build_payload(us, china, "2026-08-02T00:00:00Z")
        activity = [event for event in payload["events"] if event.get("group") == "activity"]
        self.assertGreater(len(activity), 0)
        self.assertTrue(all(len(event["metrics"]) == 5 for event in activity))
        self.assertEqual(len({event["id"] for event in payload["events"]}), len(payload["events"]))

    def test_merge_sorts_china_and_us_by_beijing_time(self):
        china_event = updater.make_event(
            "prices",
            "2026-07",
            scheduled_at="2026-08-09T09:30:00+08:00",
        )
        china = {"status": "healthy", "events": [china_event]}
        us = [
            {
                "date": "2026-08-08",
                "time_shanghai": "20:30",
                "title": "Example",
                "title_cn": "美国示例",
                "source": "Official",
                "url": "https://www.bls.gov/",
            }
        ]
        payload = merger.build_payload(us, china, "2026-08-02T00:00:00Z")
        self.assertEqual([event["country"] for event in payload["events"]], ["US", "CN"])

    def test_validator_rejects_unsorted_or_single_country_payload(self):
        china = updater.make_event(
            "prices",
            "2026-07",
            scheduled_at="2026-08-09T09:30:00+08:00",
        )
        payload = {
            "events": [china],
        }
        with self.assertRaises(ValueError):
            merger.validate_unified(payload)


if __name__ == "__main__":
    unittest.main()
