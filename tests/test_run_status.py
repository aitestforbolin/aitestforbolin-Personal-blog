import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "finalize_run_status.py"
SPEC = importlib.util.spec_from_file_location("finalize_run_status", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class RunStatusTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime.fromisoformat("2026-09-14T23:04:10+00:00")
        self.commit = "e334e9deffa319b96225888d5c7dd7dbeb3d8c61"

    def test_success_contract(self):
        payload = MODULE.build_status(
            status="success",
            stage="done",
            run_date="2026-09-15",
            as_of="2026-09-14",
            briefing_commit=self.commit,
            x_post_id="2099635300519530627",
            x_post_url="https://x.com/i/web/status/2099635300519530627",
            reason_code=None,
            now=self.now,
        )
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["updatedAt"], "2026-09-15T07:04:10+08:00")

    def test_success_requires_full_commit_and_x_identity(self):
        with self.assertRaises(MODULE.RunStatusError):
            MODULE.build_status(
                status="success",
                stage="done",
                run_date="2026-09-15",
                as_of="2026-09-14",
                briefing_commit="e334e9de",
                x_post_id=None,
                x_post_url=None,
                reason_code=None,
                now=self.now,
            )

    def test_no_new_session_is_a_terminal_result(self):
        payload = MODULE.build_status(
            status="no_new_session",
            stage="done",
            run_date="2026-09-15",
            as_of="2026-09-14",
            briefing_commit=None,
            x_post_id=None,
            x_post_url=None,
            reason_code="already_current",
            now=self.now,
        )
        MODULE.validate_status(payload)

    def test_from_x_uses_confirmed_log_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot.json"
            x_log = root / "x.json"
            snapshot.write_text('{"asOf":"2026-09-14"}', encoding="utf-8")
            x_log.write_text(
                json.dumps(
                    {
                        "publishedByAsOf": {
                            "2026-09-14": {
                                "postId": "2099635300519530627",
                                "url": "https://x.com/i/web/status/2099635300519530627",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            args = type(
                "Args",
                (),
                {
                    "snapshot": snapshot,
                    "x_log": x_log,
                    "briefing_commit": self.commit,
                    "validate_outcome": "success",
                    "publish_outcome": "success",
                    "publish_status": "published",
                },
            )()
            payload = MODULE.from_x(args, self.now)
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["runDate"], "2026-09-15")

    def test_from_x_records_validation_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            snapshot = root / "snapshot.json"
            snapshot.write_text('{"asOf":"2026-09-14"}', encoding="utf-8")
            args = type(
                "Args",
                (),
                {
                    "snapshot": snapshot,
                    "x_log": root / "missing.json",
                    "briefing_commit": self.commit,
                    "validate_outcome": "failure",
                    "publish_outcome": "skipped",
                    "publish_status": "",
                },
            )()
            payload = MODULE.from_x(args, self.now)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["reasonCode"], "x_validation_failed")


if __name__ == "__main__":
    unittest.main()
