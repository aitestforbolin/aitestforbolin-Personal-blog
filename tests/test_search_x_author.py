from __future__ import annotations

import unittest

from scripts.search_x_author import (
    build_query,
    normalize,
    normalize_username,
    parse_keywords,
    parse_request_payload,
)


class SearchXAuthorTests(unittest.TestCase):
    def test_username_accepts_at_prefix(self):
        self.assertEqual(normalize_username("@alice_123"), "alice_123")

    def test_username_rejects_invalid_value(self):
        with self.assertRaises(ValueError):
            normalize_username("bad user")

    def test_keywords_merge_cli_and_csv_without_duplicates(self):
        self.assertEqual(
            parse_keywords(["airdrop", "points"], "points, agent trading,"),
            ["airdrop", "points", "agent trading"],
        )

    def test_build_query_any_keywords_and_excludes_replies(self):
        query = build_query(
            "alice",
            ["airdrop", "agent trading"],
            match="any",
            since_time=123456,
            include_replies=False,
        )
        self.assertEqual(
            query,
            'from:alice (airdrop OR "agent trading") -filter:replies since_time:123456',
        )

    def test_build_query_all_keywords_and_includes_replies(self):
        query = build_query(
            "@alice",
            ["airdrop", "points"],
            match="all",
            since_time=123456,
            include_replies=True,
        )
        self.assertEqual(query, "from:alice airdrop points since_time:123456")

    def test_request_payload_supports_chat_trigger_shape(self):
        config = parse_request_payload(
            {
                "requestId": "study-agent-001",
                "username": "@alice",
                "keywords": ["agent", "profit"],
                "days": 90,
                "match": "any",
                "includeReplies": True,
                "maxResults": 50,
            }
        )
        self.assertEqual(config["username"], "alice")
        self.assertEqual(config["keywords"], ["agent", "profit"])
        self.assertEqual(config["days"], 90)
        self.assertTrue(config["include_replies"])
        self.assertEqual(config["max_results"], 50)
        self.assertEqual(config["request_id"], "study-agent-001")

    def test_normalize_extracts_core_fields(self):
        row = normalize(
            {
                "id_str": "123",
                "tweet_created_at": "2026-09-24T00:00:00Z",
                "full_text": "Agent opportunity",
                "favorite_count": 10,
                "reply_count": 2,
                "retweet_count": 3,
                "quote_count": 1,
                "views_count": 100,
                "user": {"screen_name": "alice", "name": "Alice"},
                "entities": {
                    "urls": [
                        {
                            "expanded_url": "https://example.com/research",
                            "url": "https://t.co/x",
                        }
                    ]
                },
            }
        )
        self.assertEqual(row["tweet_id"], "123")
        self.assertEqual(row["author"]["username"], "alice")
        self.assertEqual(row["text"], "Agent opportunity")
        self.assertEqual(row["url"], "https://x.com/alice/status/123")
        self.assertEqual(row["engagement"]["views"], 100)
        self.assertEqual(row["external_urls"], ["https://example.com/research"])


if __name__ == "__main__":
    unittest.main()
