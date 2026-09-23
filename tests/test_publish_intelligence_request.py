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


if __name__ == "__main__":
    unittest.main()
