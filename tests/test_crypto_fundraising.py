from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "update_crypto_fundraising.py"
SPEC = importlib.util.spec_from_file_location("crypto_fundraising_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = updater
SPEC.loader.exec_module(updater)

VALID_PAYLOAD = {
    "source": "Crypto-Fundraising",
    "selection": "homepage_recent_fundraising_events",
    "projects": [
        {
            "id": f"ignored-{rank}",
            "source_rank": rank,
            "name": f"Project {rank}",
            "round": "Seed" if rank != 2 else None,
            "announced_month": "2026-09",
            "amount_usd": rank * 1_000_000 if rank != 3 else None,
            "detail_url": f"https://crypto-fundraising.info/projects/project-{rank}/",
        }
        for rank in range(1, 6)
    ],
}


class CryptoFundraisingTests(unittest.TestCase):
    def test_normalizes_the_five_item_bridge_contract(self):
        projects = updater.validate_bridge_payload(VALID_PAYLOAD)
        self.assertEqual([project["source_rank"] for project in projects], [1, 2, 3, 4, 5])
        self.assertEqual(projects[0]["id"], "crypto-fundraising-project-1")
        self.assertIsNone(projects[1]["round"])
        self.assertIsNone(projects[2]["amount_usd"])

    def test_rejects_incomplete_or_duplicate_bridge_data(self):
        incomplete = {**VALID_PAYLOAD, "projects": VALID_PAYLOAD["projects"][:4]}
        with self.assertRaises(updater.BridgeDataError):
            updater.validate_bridge_payload(incomplete)
        duplicate = json.loads(json.dumps(VALID_PAYLOAD))
        duplicate["projects"][4]["detail_url"] = duplicate["projects"][0]["detail_url"]
        with self.assertRaises(updater.BridgeDataError):
            updater.validate_bridge_payload(duplicate)

    def test_marks_new_projects_by_canonical_detail_url(self):
        previous = {
            "projects": [
                {"detail_url": project["detail_url"]}
                for project in VALID_PAYLOAD["projects"]
            ]
        }
        payload = updater.build_payload(VALID_PAYLOAD, previous)
        self.assertEqual([project["is_new"] for project in payload["projects"]], [False] * 5)

        changed = json.loads(json.dumps(VALID_PAYLOAD))
        changed["projects"][0]["detail_url"] = (
            "https://crypto-fundraising.info/projects/new-project/"
        )
        payload = updater.build_payload(changed, previous)
        self.assertTrue(payload["projects"][0]["is_new"])

    def test_stable_event_id_is_not_the_same_as_feed_newness(self):
        projects = updater.validate_bridge_payload(VALID_PAYLOAD)
        self.assertEqual(
            updater.stable_event_id(projects[0]),
            "crypto-fundraising-project-1--2026-09--seed",
        )
        self.assertEqual(
            updater.stable_event_id(projects[1]),
            "crypto-fundraising-project-2--2026-09--round-unknown",
        )

    def test_history_retains_projects_that_leave_the_current_top_five(self):
        first_feed = updater.build_payload(VALID_PAYLOAD, None)
        first_feed["updated_at"] = "2026-09-18T00:30:00+00:00"
        history = updater.build_history_payload(first_feed, None)

        changed_source = json.loads(json.dumps(VALID_PAYLOAD))
        changed_source["projects"][0] = {
            "id": "ignored-new",
            "source_rank": 1,
            "name": "New Project",
            "round": "Seed",
            "announced_month": "2026-09",
            "amount_usd": 9_000_000,
            "detail_url": "https://crypto-fundraising.info/projects/new-project/",
        }
        second_feed = updater.build_payload(changed_source, first_feed)
        second_feed["updated_at"] = "2026-09-18T05:30:00+00:00"
        next_history = updater.build_history_payload(
            second_feed,
            history,
            previous_feed=first_feed,
        )

        event_ids = {event["event_id"] for event in next_history["events"]}
        self.assertIn(
            "crypto-fundraising-project-1--2026-09--seed",
            event_ids,
        )
        self.assertIn(
            "crypto-fundraising-new-project--2026-09--seed",
            event_ids,
        )
        self.assertEqual(len(next_history["events"]), 6)

    def test_history_does_not_duplicate_the_same_event(self):
        feed = updater.build_payload(VALID_PAYLOAD, None)
        feed["updated_at"] = "2026-09-18T00:30:00+00:00"
        history = updater.build_history_payload(feed, None)
        repeated = updater.build_history_payload(feed, history, previous_feed=feed)
        self.assertEqual(len(repeated["events"]), 5)
        self.assertEqual(repeated, history)

    def test_later_round_for_same_project_becomes_a_new_event(self):
        first_feed = updater.build_payload(VALID_PAYLOAD, None)
        first_feed["updated_at"] = "2026-09-18T00:30:00+00:00"
        history = updater.build_history_payload(first_feed, None)

        later_source = json.loads(json.dumps(VALID_PAYLOAD))
        later_source["projects"][0]["round"] = "Series A"
        later_source["projects"][0]["announced_month"] = "2026-10"
        later_feed = updater.build_payload(later_source, first_feed)
        later_feed["updated_at"] = "2026-10-10T05:30:00+00:00"
        next_history = updater.build_history_payload(
            later_feed,
            history,
            previous_feed=first_feed,
        )
        project_one_events = [
            event
            for event in next_history["events"]
            if event["project_id"] == "crypto-fundraising-project-1"
        ]
        self.assertEqual(len(project_one_events), 2)

    def test_bridge_failure_never_creates_a_payload(self):
        with patch.object(
            updater,
            "urlopen",
            side_effect=URLError("bridge unavailable"),
        ), patch.object(updater.time, "sleep"):
            with self.assertRaises(updater.BridgeDataError):
                updater.fetch_bridge_payload()

    def test_published_data_and_frontend_keep_five_item_contract(self):
        payload = json.loads(
            (ROOT / "data" / "crypto-fundraising.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(payload["projects"]), 5)
        self.assertEqual(
            [project["source_rank"] for project in payload["projects"]],
            [1, 2, 3, 4, 5],
        )
        history = json.loads(
            (ROOT / "data" / "crypto-fundraising-history.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertGreaterEqual(len(history["events"]), 5)
        page = (ROOT / "fundraising" / "index.html").read_text(encoding="utf-8")
        frontend = (ROOT / "fundraising" / "fundraising.js").read_text(encoding="utf-8")
        self.assertIn("data-fundraising-list", page)
        self.assertIn("../data/crypto-fundraising.json", frontend)


if __name__ == "__main__":
    unittest.main()
