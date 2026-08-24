from __future__ import annotations

import datetime as dt
import importlib.util
import json
import unittest
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "fetch_life_society_news.py"
)
SPEC = importlib.util.spec_from_file_location("life_society_news", SCRIPT_PATH)
assert SPEC and SPEC.loader
news = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(news)


class LifeSocietyNewsTests(unittest.TestCase):
    def test_germany_has_both_tagesschau_and_the_local_sources(self):
        sources = json.loads(news.SOURCES.read_text(encoding="utf-8"))["sources"]
        germany = {
            source["outlet"]: source
            for source in sources
            if source["country"] == "德国" and source["enabled"]
        }

        self.assertEqual(set(germany), {"Tagesschau", "The Local Germany"})
        self.assertEqual(
            germany["The Local Germany"]["rssUrl"],
            "https://feeds.thelocal.com/rss/builder/de",
        )

    def test_snapshot_window_uses_today_after_0730_in_shanghai(self):
        now = dt.datetime.fromisoformat("2026-08-22T09:56:00+08:00")

        start, end = news.snapshot_window(now)

        self.assertEqual(start.isoformat(), "2026-08-20T23:30:00+00:00")
        self.assertEqual(end.isoformat(), "2026-08-21T23:30:00+00:00")

    def test_snapshot_window_uses_previous_day_before_0730_in_shanghai(self):
        now = dt.datetime.fromisoformat("2026-08-22T07:29:59+08:00")

        _, end = news.snapshot_window(now)

        self.assertEqual(end.isoformat(), "2026-08-20T23:30:00+00:00")

    def test_delayed_run_publishes_stale_snapshot(self):
        now = dt.datetime.fromisoformat("2026-08-22T09:56:00+08:00")
        existing = {"asOf": "2026-08-21T07:30:00+08:00"}

        self.assertTrue(news.snapshot_is_due(existing, now))

    def test_existing_today_snapshot_is_not_published_again(self):
        now = dt.datetime.fromisoformat("2026-08-22T11:13:00+08:00")
        existing = {"asOf": "2026-08-22T07:30:00+08:00"}

        self.assertFalse(news.snapshot_is_due(existing, now))

    def test_missing_snapshot_is_due(self):
        now = dt.datetime.fromisoformat("2026-08-22T09:56:00+08:00")

        self.assertTrue(news.snapshot_is_due({}, now))

    def test_snapshot_only_includes_the_previous_24_hours(self):
        now = dt.datetime.fromisoformat("2026-08-22T09:56:00+08:00")
        store = {
            "items": [
                {
                    "url": "https://example.com/before",
                    "publishedAt": "2026-08-20T23:29:59+00:00",
                },
                {
                    "url": "https://example.com/included",
                    "publishedAt": "2026-08-20T23:30:00+00:00",
                },
                {
                    "url": "https://example.com/after",
                    "publishedAt": "2026-08-21T23:30:00+00:00",
                },
            ]
        }

        snapshot = news.build_snapshot(store, now)

        self.assertEqual(snapshot["asOf"], "2026-08-22T07:30:00+08:00")
        self.assertEqual(
            [item["url"] for item in snapshot["items"]],
            ["https://example.com/included"],
        )


if __name__ == "__main__":
    unittest.main()
