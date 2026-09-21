from __future__ import annotations

import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")
    requests_stub.RequestException = Exception
    sys.modules["requests"] = requests_stub

from scripts import update_x_intelligence_input as updater


class XIntelligenceLineageTests(unittest.TestCase):
    def test_empty_valid_collection_preserves_request_and_trigger_sha(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trigger = root / "trigger.json"
            sources = root / "sources.json"
            output = root / "input.json"
            receipt = root / "receipt.json"
            trigger.write_text(
                json.dumps({"schemaVersion": 1, "requestId": "x-run-1"}),
                encoding="utf-8",
            )
            sources.write_text(
                json.dumps(
                    {
                        "lists": [
                            {"id": str(index), "name": f"List {index}"}
                            for index in range(1, 5)
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.object(updater, "TRIGGER_PATH", trigger),
                patch.object(updater, "SOURCES_PATH", sources),
                patch.object(updater, "OUTPUT_PATH", output),
                patch.object(updater, "RECEIPT_PATH", receipt),
                patch.object(updater, "get_page", return_value={"tweets": []}),
                patch.dict(
                    os.environ,
                    {
                        "SOCIALDATA_API_KEY": "test-key",
                        "GITHUB_EVENT_NAME": "push",
                        "GITHUB_RUN_ID": "100",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_SHA": "d" * 40,
                    },
                    clear=False,
                ),
            ):
                updater.main()

            payload = json.loads(output.read_text(encoding="utf-8"))
            run_receipt = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertEqual(payload["executionLineage"]["requestId"], "x-run-1")
        self.assertEqual(payload["executionLineage"]["triggerSha"], "d" * 40)
        self.assertEqual(run_receipt["stages"]["collection"]["status"], "empty_valid")
        self.assertEqual(run_receipt["stages"]["validation"]["status"], "success")

    def test_http_404_is_persisted_as_fetch_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            trigger = root / "trigger.json"
            sources = root / "sources.json"
            receipt = root / "receipt.json"
            trigger.write_text(
                json.dumps({"schemaVersion": 1, "requestId": "x-run-404"}),
                encoding="utf-8",
            )
            sources.write_text(
                json.dumps(
                    {
                        "lists": [
                            {"id": str(index), "name": f"List {index}"}
                            for index in range(1, 5)
                        ]
                    }
                ),
                encoding="utf-8",
            )
            error = updater.SourceFetchError("HTTP 404", http_status=404)
            with (
                patch.object(updater, "TRIGGER_PATH", trigger),
                patch.object(updater, "SOURCES_PATH", sources),
                patch.object(updater, "OUTPUT_PATH", root / "input.json"),
                patch.object(updater, "RECEIPT_PATH", receipt),
                patch.object(updater, "get_page", side_effect=error),
                patch.dict(
                    os.environ,
                    {
                        "SOCIALDATA_API_KEY": "test-key",
                        "GITHUB_EVENT_NAME": "push",
                        "GITHUB_RUN_ID": "101",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_SHA": "e" * 40,
                    },
                    clear=False,
                ),
            ):
                with self.assertRaises(updater.SourceFetchError):
                    updater.run_main()

            run_receipt = json.loads(receipt.read_text(encoding="utf-8"))

        self.assertEqual(run_receipt["result"], "failed")
        self.assertEqual(run_receipt["stages"]["collection"]["status"], "fetch_failed")
        self.assertEqual(
            run_receipt["stages"]["collection"]["details"]["errorCode"], "http_404"
        )


if __name__ == "__main__":
    unittest.main()
