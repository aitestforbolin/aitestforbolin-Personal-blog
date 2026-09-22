from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.execution_receipt import (
    lineage_for_payload,
    new_receipt,
    set_collection,
    set_validation,
    trigger_context,
    validate_receipt,
)


class ExecutionReceiptTests(unittest.TestCase):
    def make_trigger(self, directory: str, **overrides) -> Path:
        path = Path(directory) / "trigger.json"
        payload = {
            "schemaVersion": 1,
            "requestId": "dispatcher-x-2026-09-21-01",
            "requestedAt": "2026-09-21T05:12:00Z",
            **overrides,
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_lineage_uses_github_sha_and_does_not_promote_requested_at(self):
        with tempfile.TemporaryDirectory() as directory:
            trigger = self.make_trigger(directory)
            with patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_NAME": "push",
                    "GITHUB_RUN_ID": "123",
                    "GITHUB_RUN_ATTEMPT": "2",
                    "GITHUB_SHA": "a" * 40,
                },
                clear=False,
            ):
                context = trigger_context(trigger, "x-intelligence")

        self.assertEqual(context["requestId"], "dispatcher-x-2026-09-21-01")
        self.assertEqual(context["triggerSha"], "a" * 40)
        self.assertIsNone(context["scheduledAt"])
        self.assertEqual(context["legacyRequestedAt"], "2026-09-21T05:12:00Z")

    def test_receipt_keeps_all_timestamps_and_stage_outcomes(self):
        context = {
            "requestId": "req-1",
            "runId": "x-intelligence:req-1",
            "triggerSha": "b" * 40,
            "triggerType": "push",
            "scheduledAt": None,
            "legacyRequestedAt": None,
            "githubRunId": 10,
            "githubRunAttempt": 1,
        }
        receipt = new_receipt("x-intelligence", context, "2026-09-21T05:30:00+00:00")
        set_collection(
            receipt,
            "empty_valid",
            source_checked_at="2026-09-21T05:30:10+00:00",
            source_updated_at=None,
            completed_at="2026-09-21T05:30:11+00:00",
        )
        set_validation(receipt, "success", completed_at="2026-09-21T05:30:11+00:00")
        validate_receipt(receipt)

        self.assertEqual(receipt["stages"]["collection"]["status"], "empty_valid")
        self.assertEqual(receipt["stages"]["publication"]["status"], "not_run")
        self.assertEqual(receipt["stages"]["notification"]["status"], "not_run")
        self.assertEqual(lineage_for_payload(receipt)["requestId"], "req-1")

    def test_manual_dispatch_does_not_reuse_stale_trigger_request(self):
        with tempfile.TemporaryDirectory() as directory:
            trigger = self.make_trigger(directory)
            with patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_NAME": "workflow_dispatch",
                    "GITHUB_RUN_ID": "456",
                    "GITHUB_SHA": "a" * 40,
                },
                clear=False,
            ):
                context = trigger_context(trigger, "x-intelligence")

        self.assertEqual(context["requestId"], "x-intelligence-gh-456")

    def test_schedule_run_does_not_depend_on_trigger_file(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_trigger = Path(directory) / "missing-trigger.json"
            with patch.dict(
                os.environ,
                {
                    "GITHUB_EVENT_NAME": "schedule",
                    "GITHUB_RUN_ID": "789",
                    "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_SHA": "b" * 40,
                },
                clear=False,
            ):
                context = trigger_context(missing_trigger, "x-intelligence")

        self.assertEqual(context["requestId"], "x-intelligence-gh-789")
        self.assertEqual(context["triggerType"], "schedule")
        self.assertEqual(context["triggerSha"], "b" * 40)
        self.assertIsNone(context["scheduledAt"])
        self.assertIsNone(context["legacyRequestedAt"])


    def test_404_is_fetch_failed_not_unchanged(self):
        context = {
            "requestId": "req-404",
            "runId": "web3-daily-triage:req-404",
            "triggerSha": "c" * 40,
            "triggerType": "push",
            "scheduledAt": None,
            "legacyRequestedAt": None,
            "githubRunId": 11,
            "githubRunAttempt": 1,
        }
        receipt = new_receipt("web3-daily-triage", context, "2026-09-21T05:30:00+00:00")
        set_collection(
            receipt,
            "fetch_failed",
            source_checked_at="2026-09-21T05:30:02+00:00",
            source_updated_at=None,
            completed_at="2026-09-21T05:30:02+00:00",
            details={"errorCode": "http_404", "httpStatus": 404},
        )
        validate_receipt(receipt)

        self.assertEqual(receipt["result"], "failed")
        self.assertEqual(receipt["stages"]["collection"]["status"], "fetch_failed")
        self.assertEqual(
            receipt["stages"]["collection"]["details"]["errorCode"], "http_404"
        )


if __name__ == "__main__":
    unittest.main()
