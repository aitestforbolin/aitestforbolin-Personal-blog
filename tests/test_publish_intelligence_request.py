from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "publish_intelligence_request.py"
SPEC = importlib.util.spec_from_file_location("publish_intelligence_request", SCRIPT_PATH)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = publisher
SPEC.loader.exec_module(publisher)


class PublishIntelligenceRequestTests(unittest.TestCase):
    def test_sets_string_publication_status_to_success(self):
        payload = {
            "executionStatus": {
                "collection": "unchanged",
                "validation": "success",
                "publication": "not_run",
            }
        }

        publisher.set_payload_publication_status(payload, "success")

        self.assertEqual(payload["executionStatus"]["publication"], "success")

    def test_sets_object_publication_status_to_success(self):
        payload = {
            "executionStatus": {
                "publication": {
                    "status": "not_run",
                    "commitSha": None,
                }
            }
        }

        publisher.set_payload_publication_status(payload, "success")

        self.assertEqual(
            payload["executionStatus"]["publication"]["status"],
            "success",
        )
        self.assertIsNone(
            payload["executionStatus"]["publication"]["commitSha"]
        )

    def test_web3_new_candidates_after_unchanged_collection_are_published(self):
        payload = {"status": "unchanged", "counts": {"new": 5}}
        publisher.normalize_web3_status(payload, "unchanged")
        self.assertEqual(payload["status"], "success")

    def test_web3_verified_zero_candidate_refresh_stays_unchanged(self):
        payload = {"status": "success", "counts": {"new": 0}}
        publisher.normalize_web3_status(payload, "unchanged")
        self.assertEqual(payload["status"], "unchanged")

    def test_web3_changed_source_with_zero_candidates_is_success(self):
        payload = {"counts": {"new": 0}}
        publisher.normalize_web3_status(payload, "success")
        self.assertEqual(payload["status"], "success")


if __name__ == "__main__":
    unittest.main()
