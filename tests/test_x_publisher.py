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
        self.snapshot_path = ROOT / "tests" / "fixtures" / "x-publisher-approved-snapshot.json"
        self.snapshot = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
        self.now = dt.datetime.fromisoformat("2026-08-20T03:30:00+00:00")

    def test_credentials_trim_surrounding_whitespace(self):
        values = {
            "X_API_KEY": " api-key ",
            "X_API_SECRET": "api-secret\n",
            "X_ACCESS_TOKEN": "\taccess-token\r\n",
            "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        }
        with mock.patch.dict(MODULE.os.environ, values):
            credentials = MODULE.credentials_from_environment()
        self.assertEqual(
            credentials,
            {
                "X_API_KEY": "api-key",
                "X_API_SECRET": "api-secret",
                "X_ACCESS_TOKEN": "access-token",
                "X_ACCESS_TOKEN_SECRET": "access-token-secret",
            },
        )

    def test_credentials_reject_embedded_whitespace(self):
        values = {
            "X_API_KEY": "api-key",
            "X_API_SECRET": "api secret",
            "X_ACCESS_TOKEN": "access-token",
            "X_ACCESS_TOKEN_SECRET": "access-token-secret",
        }
        with mock.patch.dict(MODULE.os.environ, values):
            with self.assertRaisesRegex(MODULE.PublishError, "X_API_SECRET"):
                MODULE.credentials_from_environment()

    def test_renderer_is_frozen_to_approved_web_output(self):
        text = MODULE.build_x_post(self.snapshot, now=self.now)
        self.assertEqual(len(text), 2330)
        self.assertEqual(
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "5d84f9d64395c1334f7e46651424c3a076f2eeb65c98282ed9010f3a8185372b",
        )
        self.assertIn("（今晚）8月20日｜周四", text)
        self.assertNotIn("跨资产大体确认", text)
        self.assertNotIn("昨日属于：", text)
        self.assertNotIn("──────────", text)

    def test_missing_sp500_breadth_values_block_publication(self):
        snapshot = json.loads(json.dumps(self.snapshot))
        sp500 = next(row for row in snapshot["fallback"]["breadth"] if row["id"] == "SP500")
        sp500["advancePercent"] = None
        with self.assertRaisesRegex(MODULE.PublishError, "SP500"):
            MODULE.build_x_post(snapshot, now=self.now)

    def test_gold_latest_quote_is_rendered_when_fixed_anchor_is_missing(self):
        snapshot = json.loads(json.dumps(self.snapshot))
        gold = next(row for row in snapshot["macroAnchors"] if row["id"] == "GOLD")
        gold["anchor"] = None
        gold["latest"] = 4603.56
        text = MODULE.build_x_post(snapshot, now=self.now)
        self.assertIn("黄金（XAU/USD）：最新 4,603.56", text)
        self.assertIn("固定锚点缺失，未计算日内变动", text)

    def test_missing_nasdaq_flat_count_is_omitted(self):
        snapshot = json.loads(json.dumps(self.snapshot))
        nasdaq = next(row for row in snapshot["fallback"]["breadth"] if row["id"] == "NASDAQ")
        nasdaq["unchanged"] = None
        text = MODULE.build_x_post(snapshot, now=self.now)
        nasdaq_line = next(line for line in text.splitlines() if line.startswith("· Nasdaq交易所"))
        self.assertNotIn("平—", nasdaq_line)

    def test_workflow_only_automates_completed_snapshot_updates(self):
        workflow = (ROOT / ".github" / "workflows" / "publish-x-manual.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("  push:\n    branches:\n      - main\n    paths:", workflow)
        self.assertIn("      - data/daily-market-status.json", workflow)
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertIn("          ref: main", workflow)
        self.assertIn("github.event_name == 'push' && 'automatic' || 'manual'", workflow)

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
            ), mock.patch.object(
                MODULE, "create_x_post", return_value="987654321"
            ) as create:
                result = MODULE.publish(
                    self.snapshot_path, state, None, False, "manual", now=self.now
                )
            created_text = create.call_args.args[0]
            saved = json.loads(state.read_text(encoding="utf-8"))
            record = saved["publishedByAsOf"]["2026-08-19"]
            self.assertEqual(result["status"], "published")
            self.assertEqual(record["postId"], "987654321")
            self.assertEqual(
                record["contentSha256"],
                "5d84f9d64395c1334f7e46651424c3a076f2eeb65c98282ed9010f3a8185372b",
            )
            self.assertEqual(record["mode"], "manual")
            self.assertNotIn(MODULE.AUTOMATIC_DISCLOSURE, created_text)

    def test_automatic_success_records_publish_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            with mock.patch.object(
                MODULE, "credentials_from_environment", return_value={}
            ), mock.patch.object(
                MODULE, "verify_target_account", return_value="whybolin"
            ), mock.patch.object(
                MODULE, "create_x_post", return_value="987654321"
            ) as create:
                result = MODULE.publish(
                    self.snapshot_path, state, None, False, "automatic", now=self.now
                )
            created_text = create.call_args.args[0]
            saved = json.loads(state.read_text(encoding="utf-8"))
            record = saved["publishedByAsOf"]["2026-08-19"]
            self.assertEqual(result["status"], "published")
            self.assertEqual(record["mode"], "automatic")
            self.assertTrue(created_text.endswith("\n\n（本推文自动定时发布）"))
            self.assertEqual(
                created_text.removesuffix("\n\n（本推文自动定时发布）"),
                MODULE.build_x_post(self.snapshot, now=self.now),
            )
            self.assertEqual(
                record["contentSha256"],
                hashlib.sha256(created_text.encode("utf-8")).hexdigest(),
            )

    def test_automatic_disclosure_cannot_exceed_post_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            with mock.patch.object(
                MODULE, "build_x_post", return_value="a" * MODULE.MAX_LONGFORM_CHARACTERS
            ), mock.patch.object(MODULE, "create_x_post") as create:
                with self.assertRaisesRegex(MODULE.PublishError, "disclosure"):
                    MODULE.publish(
                        self.snapshot_path, state, None, False, "automatic", now=self.now
                    )
                create.assert_not_called()
            self.assertFalse(state.exists())

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
