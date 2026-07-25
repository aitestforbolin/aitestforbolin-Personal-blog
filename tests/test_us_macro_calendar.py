from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "update_us_macro_calendar.py"
)
SPEC = importlib.util.spec_from_file_location("us_macro_calendar_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class UsMacroCalendarTests(unittest.TestCase):
    def test_investing_latest_release_parser_reads_flash_values(self):
        html = (
            '<script>{"closestOccurrences":{"latest_release":'
            '{"actual":53.8,"forecast":54.4,'
            '"occurrence_time":"2026-07-24T13:45:00Z",'
            '"precision":1,"preliminary":true,"previous":53.9},'
            '"next_release":{}}}</script>'
        )

        latest = updater.parse_investing_latest_release(html)

        self.assertEqual(latest["actual"], 53.8)
        self.assertEqual(latest["forecast"], 54.4)
        self.assertEqual(latest["previous"], 53.9)
        self.assertTrue(latest["preliminary"])

    def test_fetched_flash_values_override_static_values_for_matching_date(self):
        events = updater.sp_global_flash_events(
            date(2026, 7, 24),
            date(2026, 7, 24),
            {
                "manufacturing": {
                    "date": "2026-07-24",
                    "actual": "54.0",
                    "forecast": "53.0",
                    "previous": "52.0",
                    "result_source": "Investing.com",
                    "result_url": "https://example.com/manufacturing",
                }
            },
        )

        manufacturing = next(
            event for event in events if "Manufacturing" in event["title"]
        )
        services = next(event for event in events if "Services" in event["title"])

        self.assertEqual(manufacturing["actual"], "54.0")
        self.assertEqual(manufacturing["result_source"], "Investing.com")
        self.assertEqual(services["actual"], "53.6")

    def test_sp_global_flash_release_includes_both_july_results(self):
        events = updater.sp_global_flash_events(
            date(2026, 7, 24),
            date(2026, 7, 24),
        )

        self.assertEqual(len(events), 2)
        by_title = {event["title"]: event for event in events}

        manufacturing = by_title["S&P Global Flash US Manufacturing PMI"]
        self.assertEqual(manufacturing["time_shanghai"], "21:45")
        self.assertEqual(manufacturing["actual"], "53.8")
        self.assertEqual(manufacturing["forecast"], "54.4")
        self.assertEqual(manufacturing["previous"], "53.9")

        services = by_title["S&P Global Flash US Services PMI"]
        self.assertEqual(services["time_shanghai"], "21:45")
        self.assertEqual(services["actual"], "53.6")
        self.assertEqual(services["forecast"], "51.3")
        self.assertEqual(services["previous"], "51.2")

    def test_eastern_time_conversion_handles_daylight_and_standard_time(self):
        self.assertEqual(
            updater.shanghai_fields(date(2026, 8, 21), "09:45"),
            ("2026-08-21", "21:45"),
        )
        self.assertEqual(
            updater.shanghai_fields(date(2026, 11, 23), "09:45"),
            ("2026-11-23", "22:45"),
        )

    def test_offline_bea_fallback_keeps_gdp_release(self):
        events = updater.bea_fallback_events(
            date(2026, 7, 25),
            date(2026, 8, 1),
        )
        self.assertTrue(
            any(event["title_cn"] == "美国GDP" for event in events),
        )

    def test_cli_retains_three_recent_days_and_future_flash_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "calendar.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--start",
                    "2026-07-25",
                    "--offline",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            events = json.loads(output.read_text(encoding="utf-8"))

        titles_by_date = {
            (event["date"], event["title"])
            for event in events
        }
        self.assertIn(
            ("2026-07-24", "S&P Global Flash US Manufacturing PMI"),
            titles_by_date,
        )
        self.assertIn(
            ("2026-07-24", "S&P Global Flash US Services PMI"),
            titles_by_date,
        )
        self.assertIn(
            ("2026-08-21", "S&P Global Flash US Manufacturing PMI"),
            titles_by_date,
        )


if __name__ == "__main__":
    unittest.main()
