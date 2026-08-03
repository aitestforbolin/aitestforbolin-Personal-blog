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
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "update_china_macro_calendar.py"
)
SPEC = importlib.util.spec_from_file_location("china_macro_calendar_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


class ChinaMacroCalendarTests(unittest.TestCase):
    def test_august_window_covers_core_monthly_releases(self):
        events = updater.build_calendar(date(2026, 8, 3), 35)
        titles = {event["title"] for event in events}
        expected = {
            "中国 RatingDog 制造业 PMI",
            "中国 RatingDog 服务业 PMI",
            "中国进出口与贸易差额",
            "中国 CPI / PPI",
            "中国新增社融 / 人民币贷款 / M2",
            "中国 70 城商品住宅销售价格",
            "中国工业增加值 / 社零 / 固投",
            "中国贷款市场报价利率（LPR）",
            "中国规模以上工业企业利润",
            "中国官方制造业 PMI",
            "中国官方非制造业 PMI",
        }
        self.assertTrue(expected.issubset(titles), expected - titles)

    def test_seven_day_lookback_retains_july_politburo_meeting(self):
        self.assertEqual(updater.DEFAULT_LOOKBACK_DAYS, 7)
        events = updater.build_calendar(date(2026, 7, 27), 42)
        meeting = next(
            event
            for event in events
            if event["id"] == "CN-2026-07-politburo-economy"
        )
        self.assertEqual(meeting["date"], "2026-07-30")
        self.assertEqual(meeting["dateStatus"], "after_confirmed")
        self.assertEqual(meeting["release_status"], "released")
        self.assertIn("news.cn", meeting["sourceUrl"])

    def test_financial_data_is_an_explicit_tentative_window(self):
        events = updater.build_calendar(date(2026, 8, 3), 35)
        credit = next(
            event
            for event in events
            if event["id"] == "CN-2026-07-credit-window"
        )
        self.assertEqual(credit["date"], "2026-08-10")
        self.assertEqual(credit["date_end"], "2026-08-17")
        self.assertEqual(credit["dateStatus"], "window")
        self.assertIsNone(credit["scheduledAt"])
        self.assertEqual(credit["time_shanghai"], "")

    def test_ratingdog_screenshot_values_are_preserved(self):
        events = updater.build_calendar(date(2026, 8, 3), 1)
        manufacturing = next(
            event
            for event in events
            if event["id"] == "CN-2026-07-ratingdog-manufacturing-pmi"
        )
        self.assertEqual(manufacturing["actual"], "50.9")
        self.assertEqual(manufacturing["previous"], "51.7")
        self.assertEqual(manufacturing["forecast"], "51.5")
        self.assertEqual(manufacturing["time_shanghai"], "09:45")
        self.assertIn("pmi.spglobal.com", manufacturing["sourceUrl"])

    def test_quarterly_gdp_and_policy_windows_are_in_the_source_calendar(self):
        october = updater.build_calendar(date(2026, 10, 1), 35)
        self.assertTrue(
            any(event["id"] == "CN-2026-Q3-gdp" for event in october)
        )
        december = updater.build_calendar(date(2026, 12, 1), 14)
        policy = [event for event in december if event["category"] == "policy"]
        self.assertGreaterEqual(len(policy), 2)
        self.assertTrue(all(event["dateStatus"] == "window" for event in policy))

    def test_cli_writes_valid_json_with_lookback_and_horizon(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "china.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT_PATH),
                    "--start",
                    "2026-08-03",
                    "--output",
                    str(output),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            events = json.loads(output.read_text(encoding="utf-8"))
        self.assertTrue(
            any(event["date"] == "2026-07-30" for event in events)
        )
        self.assertTrue(
            any(event["date"] == "2026-09-03" for event in events)
        )


if __name__ == "__main__":
    unittest.main()

