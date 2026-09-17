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
        previous = {"projects": [{"detail_url": project["detail_url"]} for project in VALID_PAYLOAD["projects"]]}
        payload = updater.build_payload(VALID_PAYLOAD, previous)
        self.assertEqual([project["is_new"] for project in payload["projects"]], [False] * 5)
        changed = json.loads(json.dumps(VALID_PAYLOAD))
        changed["projects"][0]["detail_url"] = "https://crypto-fundraising.info/projects/new-project/"
        payload = updater.build_payload(changed, previous)
        self.assertTrue(payload["projects"][0]["is_new"])

    def test_bridge_failure_never_creates_a_payload(self):
        with patch.object(updater, "urlopen", side_effect=URLError("bridge unavailable")), patch.object(updater.time, "sleep"):
            with self.assertRaises(updater.BridgeDataError):
                updater.fetch_bridge_payload()

    def test_published_data_and_frontend_keep_five_item_contract(self):
        payload = json.loads((ROOT / "data" / "crypto-fundraising.json").read_text(encoding="utf-8"))
        self.assertEqual(len(payload["projects"]), 5)
        self.assertEqual([project["source_rank"] for project in payload["projects"]], [1, 2, 3, 4, 5])
        page = (ROOT / "fundraising" / "index.html").read_text(encoding="utf-8")
        frontend = (ROOT / "fundraising" / "fundraising.js").read_text(encoding="utf-8")
        self.assertIn("data-fundraising-list", page)
        self.assertIn("../data/crypto-fundraising.json", frontend)


if __name__ == "__main__":
    unittest.main()
