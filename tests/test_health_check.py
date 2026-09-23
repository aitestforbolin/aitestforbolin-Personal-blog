import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from health_check import check


class HealthCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.now = dt.datetime(2026, 9, 23, 13, 0, tzinfo=dt.timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, obj):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj), encoding="utf-8")

    def market(self):
        payload = {"asOf": "2026-09-22"}
        self.put("data/daily-market-status.json", payload)
        self.put("data/daily-market-status/archive/2026-09-22.json", payload)
        self.put("data/run-status.json", {"runDate": "2026-09-23", "status": "success", "asOf": "2026-09-22", "briefingCommit": "a" * 40, "xPostId": "123"})

    def web3(self, payload_status="success", receipt_status="success"):
        self.put("data/crypto-fundraising-trigger.json", {"requestId": "web3-20260923-01", "scheduledAt": "2026-09-23T06:00:00Z"})
        self.put("data/crypto-fundraising-refresh-status.json", {"requestId": "web3-20260923-01", "lineage": {"triggerSha": "abc"}, "stages": {"collection": {"status": "unchanged"}, "validation": {"status": "success"}, "publication": {"status": receipt_status}}})
        payload = {"runDate": "2026-09-23", "executionLineage": {"requestId": "web3-20260923-01", "triggerSha": "abc"}, "executionStatus": {"publication": payload_status}}
        self.put("data/web3-daily-triage.json", payload)
        self.put("data/web3-daily-triage/archive/2026-09-23.json", payload)

    def test_known_web3_mismatch_is_found(self):
        self.market()
        self.web3(payload_status="not_run")
        _, issues = check(self.root, self.now)
        self.assertEqual([x[0] for x in issues], ["web3.display_status"])

    def test_collector_success_without_publication_is_found(self):
        self.market()
        self.web3(receipt_status="not_run")
        _, issues = check(self.root, self.now)
        self.assertEqual([x[0] for x in issues], ["web3.publication_missing"])

    def test_unchanged_is_valid_and_no_trigger_means_no_obligation(self):
        self.market()
        self.web3(payload_status="unchanged", receipt_status="unchanged")
        checked, issues = check(self.root, self.now)
        self.assertEqual(checked, ["market briefing", "web3"])
        self.assertFalse(issues)

    def test_recent_trigger_gets_grace_period(self):
        self.market()
        self.put("data/x-intelligence-trigger.json", {"requestId": "x-20260923-01", "scheduledAt": "2026-09-23T12:40:00Z"})
        checked, issues = check(self.root, self.now)
        self.assertEqual(checked, ["market briefing"])
        self.assertFalse(issues)


if __name__ == "__main__":
    unittest.main()
