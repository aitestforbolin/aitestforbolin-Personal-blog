import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
MODULE_PATH = SCRIPTS / "watch_market_briefing_run.py"
SPEC = importlib.util.spec_from_file_location("watch_market_briefing_run", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class RunWatchdogTests(unittest.TestCase):
    def test_keeps_valid_status_for_today(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.json"
            snapshot = root / "snapshot.json"
            status.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "runDate": "2026-09-15",
                        "asOf": "2026-09-14",
                        "status": "no_new_session",
                        "stage": "done",
                        "briefingCommit": None,
                        "xPostId": None,
                        "xPostUrl": None,
                        "reasonCode": "already_current",
                        "updatedAt": "2026-09-15T07:00:00+08:00",
                    }
                ),
                encoding="utf-8",
            )
            snapshot.write_text('{"asOf":"2026-09-14"}', encoding="utf-8")
            argv = [
                "watch",
                "--status",
                str(status),
                "--snapshot",
                str(snapshot),
                "--now",
                "2026-09-15T00:00:00+00:00",
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(MODULE.main(), 0)
            self.assertEqual(json.loads(status.read_text())["status"], "no_new_session")

    def test_writes_failure_when_status_is_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.json"
            snapshot = root / "snapshot.json"
            status.write_text('{"runDate":"2026-09-14"}', encoding="utf-8")
            snapshot.write_text('{"asOf":"2026-09-14"}', encoding="utf-8")
            argv = [
                "watch",
                "--status",
                str(status),
                "--snapshot",
                str(snapshot),
                "--now",
                "2026-09-15T00:00:00+00:00",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(os.environ, {}, clear=False):
                self.assertEqual(MODULE.main(), 0)
            payload = json.loads(status.read_text())
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["reasonCode"], "status_missing_after_deadline")

    def test_requests_notification_for_existing_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            status = root / "status.json"
            snapshot = root / "snapshot.json"
            output = root / "github-output.txt"
            status.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "runDate": "2026-09-15",
                        "asOf": "2026-09-14",
                        "status": "failed",
                        "stage": "x",
                        "briefingCommit": None,
                        "xPostId": None,
                        "xPostUrl": None,
                        "reasonCode": "x_publish_failed",
                        "updatedAt": "2026-09-15T07:04:00+08:00",
                    }
                ),
                encoding="utf-8",
            )
            snapshot.write_text('{"asOf":"2026-09-14"}', encoding="utf-8")
            argv = [
                "watch",
                "--status",
                str(status),
                "--snapshot",
                str(snapshot),
                "--now",
                "2026-09-15T00:00:00+00:00",
            ]
            with mock.patch.object(sys, "argv", argv), mock.patch.dict(
                os.environ, {"GITHUB_OUTPUT": str(output)}, clear=False
            ):
                self.assertEqual(MODULE.main(), 0)
            self.assertIn("action=notify_existing_failure", output.read_text())


if __name__ == "__main__":
    unittest.main()
