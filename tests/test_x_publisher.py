import datetime as dt
import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "publish_x_post.py"
SPEC = importlib.util.spec_from_file_location("publish_x_post", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class XPublisherTests(unittest.TestCase):
    def setUp(self):
        self.snapshot_path = ROOT / "data" / "daily-market-status.json"
        self.snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        self.now = dt.datetime.fromisoformat("2026-08-20T03:30:00+00:00")

    def test_renderer_is_frozen_to_approved_web_output(self):
        text = MODULE.build_x_post(self.snapshot, now=self.now)
        self.assertEqual(len(text), 2326)
        self.assertEqual(
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "0797cc7f32159188d840591ae15c910437a7724a93d7bc50a1bf41680d65e039",
        )
        self.assertIn("（今晚）8月20日｜周四", text)
        self.assertNotIn("跨资产大体确认", text)
        self.assertNotIn("昨日属于：", text)
        self.assertNotIn("──────────", text)

    def test_as_of_mismatch_stops_before_api(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            with mock.patch.object(MODULE, "create_x_post") as create:
                with self.assertRaises(MODULE.PublishError):
                    MODULE.publish(
                        self.snapshot_path,
                        state,
                        "2026-08-18",
                        False,
                        "manual",
                        now=self.now,
                    )
                create.assert_not_called()

    def test_existing_as_of_is_a_no_op(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            state.write_text(
                json.dumps(
                    {
                        "schemaVersion": 1,
                        "publishedByAsOf": {
                            "2026-08-19": {"postId": "123456789"}
                        },
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.object(MODULE, "create_x_post") as create:
                result = MODULE.publish(
                    self.snapshot_path, state, None, False, "manual", now=self.now
                )
                create.assert_not_called()
            self.assertEqual(result["status"], "skipped_duplicate")

    def test_api_failure_does_not_write_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            with mock.patch.object(
                MODULE, "credentials_from_environment", return_value={}
            ), mock.patch.object(
                MODULE, "verify_target_account", return_value="whybolin"
            ), mock.patch.object(
                MODULE, "create_x_post", side_effect=MODULE.PublishError("rejected")
            ):
                with self.assertRaises(MODULE.PublishError):
                    MODULE.publish(
                        self.snapshot_path, state, None, False, "manual", now=self.now
                    )
            self.assertFalse(state.exists())

    def test_success_records_post_id_and_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            with mock.patch.object(
                MODULE, "credentials_from_environment", return_value={}
            ), mock.patch.object(
                MODULE, "verify_target_account", return_value="whybolin"
            ), mock.patch.object(MODULE, "create_x_post", return_value="987654321"):
                result = MODULE.publish(
                    self.snapshot_path, state, None, False, "manual", now=self.now
                )
            saved = json.loads(state.read_text(encoding="utf-8"))
            record = saved["publishedByAsOf"]["2026-08-19"]
            self.assertEqual(result["status"], "published")
            self.assertEqual(record["postId"], "987654321")
            self.assertEqual(
                record["contentSha256"],
                "0797cc7f32159188d840591ae15c910437a7724a93d7bc50a1bf41680d65e039",
            )

    def test_wrong_x_account_stops_before_create(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            with mock.patch.dict(
                MODULE.os.environ, {"X_EXPECTED_USERNAME": "whybolin"}
            ), mock.patch.object(
                MODULE, "credentials_from_environment", return_value={}
            ), mock.patch.object(
                MODULE, "authenticated_username", return_value="BitalkNews"
            ), mock.patch.object(MODULE, "create_x_post") as create:
                with self.assertRaisesRegex(MODULE.PublishError, "expected @whybolin"):
                    MODULE.publish(
                        self.snapshot_path, state, None, False, "manual", now=self.now
                    )
                create.assert_not_called()
            self.assertFalse(state.exists())


if __name__ == "__main__":
    unittest.main()
