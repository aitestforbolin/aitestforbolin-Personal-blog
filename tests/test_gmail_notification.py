import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "send_gmail_notification.py"
SPEC = importlib.util.spec_from_file_location("send_gmail_notification", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class GmailNotificationTests(unittest.TestCase):
    def test_missing_credentials_is_a_failure_not_a_silent_skip(self):
        args = type("Args", (), {"run_url": "https://example.com", "status_file": Path("missing")})()
        with (
            mock.patch.object(MODULE, "parse_args", return_value=args),
            mock.patch.dict(MODULE.os.environ, {}, clear=True),
        ):
            self.assertEqual(MODULE.main(), 2)

    def test_success_message_reads_status_fields(self):
        message = MODULE.build_message(
            {
                "status": "success",
                "runDate": "2026-09-15",
                "asOf": "2026-09-14",
                "xPostUrl": "https://x.com/i/web/status/123",
            },
            "https://github.com/example/actions/runs/1",
            "from@example.com",
            "to@example.com",
        )
        self.assertIn("全部成功", str(message["Subject"]))
        self.assertIn("https://x.com/i/web/status/123", message.get_content())

    def test_no_new_session_and_failure_have_distinct_messages(self):
        no_new = MODULE.build_message(
            {
                "status": "no_new_session",
                "runDate": "2026-09-15",
                "asOf": "2026-09-14",
                "reasonCode": "already_current",
            },
            "https://github.com/example/actions/runs/1",
            "from@example.com",
            "to@example.com",
        )
        failed = MODULE.build_message(
            {
                "status": "failed",
                "runDate": "2026-09-15",
                "asOf": "2026-09-14",
                "stage": "packet",
                "reasonCode": "packet_invalid",
            },
            "https://github.com/example/actions/runs/2",
            "from@example.com",
            "to@example.com",
        )
        self.assertIn("无需更新", str(no_new["Subject"]))
        self.assertIn("packet_invalid", failed.get_content())


if __name__ == "__main__":
    unittest.main()
