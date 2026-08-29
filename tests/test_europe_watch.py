from __future__ import annotations

import datetime as dt
import importlib.util
import unittest
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_europe_watch.py"
SPEC = importlib.util.spec_from_file_location("europe_watch", SCRIPT_PATH)
assert SPEC and SPEC.loader
news = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(news)


class EuropeWatchTests(unittest.TestCase):
    def test_only_eu_and_germany_are_configured(self):
        registry = news.json.loads(news.SOURCES.read_text(encoding="utf-8"))
        self.assertEqual({source["region"] for source in registry["sources"]}, {"eu", "germany"})
        self.assertTrue(any(source["name"] == "ECB" for source in registry["sources"]))
        self.assertTrue(any(source["name"] == "Destatis" for source in registry["sources"]))

    def test_filter_and_category_reject_low_value_title(self):
        self.assertIsNone(news.classify("Football celebrity wins award", ""))
        self.assertEqual(news.classify("Germany unemployment rate rises", ""), "work_income")

    def test_similar_event_keeps_media_for_readability(self):
        official = {"region":"eu", "title":"EU factory output slows", "official_source":True, "category":"industry", "importance":"important", "published_at":"2026-08-27T00:00:00+00:00"}
        media = {"region":"eu", "title":"EU factory output slows amid weak demand", "official_source":False, "category":"industry", "importance":"important", "published_at":"2026-08-27T01:00:00+00:00"}
        self.assertEqual(news.dedupe([official, media])[0], media)

    def test_empty_collection_does_not_replace_existing_store(self):
        previous = {"items": [{"source_url":"https://example.com/a", "title":"Germany employment data", "title_cn":"德国就业数据", "region":"germany", "importance":"normal", "published_at":"2026-08-27T01:00:00+00:00"}]}
        merged = news.merge_store(previous, [], dt.datetime.fromisoformat("2026-08-27T02:00:00+00:00"))
        self.assertEqual(len(merged), 1)

    def test_snapshot_window_is_fixed_at_0730_shanghai(self):
        start, end = news.snapshot_window(dt.datetime.fromisoformat("2026-08-28T08:00:00+08:00"))
        self.assertEqual(start.isoformat(), "2026-08-26T23:30:00+00:00")
        self.assertEqual(end.isoformat(), "2026-08-27T23:30:00+00:00")

    def test_source_error_is_isolated(self):
        original_sources, original_fetch = news.SOURCES, news.fetch
        fixture = Path(self.id().replace(".", "-"))
        try:
            fixture.write_text('{"sources":[{"region":"eu","name":"Broken","rss_url":"https://bad","official_source":true,"enabled":true},{"region":"germany","name":"Good","rss_url":"https://good","official_source":false,"enabled":true}]}', encoding="utf-8")
            news.SOURCES = fixture
            news.fetch = lambda url: (_ for _ in ()).throw(OSError()) if url.endswith("bad") else b'<rss><channel><item><title>Germany unemployment rises</title><link>https://example.com/job</link><pubDate>Wed, 27 Aug 2026 01:00:00 +0000</pubDate></item></channel></rss>'
            audits, items = news.collect_sources(dt.datetime.fromisoformat("2026-08-27T02:00:00+00:00"))
            self.assertEqual([row["status"] for row in audits], ["error", "ok"])
            self.assertEqual(len(items), 1)
        finally:
            news.SOURCES, news.fetch = original_sources, original_fetch
            fixture.unlink(missing_ok=True)

    def test_workflow_quotes_github_expression_outside_flow_mapping(self):
        workflow = (
            SCRIPT_PATH.parents[1]
            / ".github"
            / "workflows"
            / "update-europe-watch.yml"
        ).read_text(encoding="utf-8")
        self.assertNotIn("env: { MANUAL_SNAPSHOT:", workflow)
        self.assertIn('MANUAL_SNAPSHOT: "${{ inputs.publish_snapshot }}"', workflow)
        self.assertIn(
            "python -m unittest tests/test_europe_watch.py -v", workflow
        )

    def test_health_requires_retained_items_from_both_regions(self):
        rows = [
            {"region": "eu", "title": "EU growth", "source_url": "https://example.com/eu"},
            {"region": "germany", "title": "German jobs", "source_url": "https://example.com/de"},
        ]
        self.assertTrue(news.store_is_healthy(rows))
        self.assertFalse(news.store_is_healthy(rows[:1]))


if __name__ == "__main__":
    unittest.main()
