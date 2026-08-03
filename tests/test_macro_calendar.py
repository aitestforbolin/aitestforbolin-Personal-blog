from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "build_macro_calendar.py"
)
SPEC = importlib.util.spec_from_file_location("macro_calendar_builder", SCRIPT_PATH)
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class CombinedMacroCalendarTests(unittest.TestCase):
    def test_combined_calendar_normalizes_country_and_source_fields(self):
        us = [
            {
                "date": "2026-08-07",
                "time_shanghai": "20:30",
                "title": "Employment Situation",
                "title_cn": "美国非农",
                "source": "BLS",
                "url": "https://www.bls.gov/",
                "stars": 5,
                "actual": "100K",
            }
        ]
        china = [
            {
                "id": "CN-test",
                "country": "CN",
                "date": "2026-08-10",
                "date_end": "2026-08-17",
                "dateStatus": "window",
                "time_shanghai": "",
                "title": "中国金融数据",
                "title_cn": "中国金融数据",
                "source": "中国人民银行",
                "sourceUrl": "https://www.pbc.gov.cn/",
                "stars": 5,
                "metrics": [],
            }
        ]

        events = builder.build_calendar(us, china)
        self.assertEqual({event["country"] for event in events}, {"US", "CN"})
        self.assertTrue(all(event["id"] for event in events))
        self.assertTrue(all(event["sourceUrl"] for event in events))

        us_event = next(event for event in events if event["country"] == "US")
        self.assertEqual(us_event["dateStatus"], "confirmed")
        self.assertEqual(us_event["scheduledAt"], "2026-08-07T20:30:00+08:00")
        self.assertEqual(us_event["metrics"][0]["actual"], "100K")

        cn_event = next(event for event in events if event["country"] == "CN")
        self.assertEqual(cn_event["dateStatus"], "window")
        self.assertIsNone(cn_event["scheduledAt"])


if __name__ == "__main__":
    unittest.main()

