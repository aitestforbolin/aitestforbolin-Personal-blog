from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("macro_brief", ROOT / "scripts" / "build_macro_brief.py")
assert spec and spec.loader
brief = importlib.util.module_from_spec(spec); sys.modules[spec.name] = brief; spec.loader.exec_module(brief)
mail_spec = importlib.util.spec_from_file_location("macro_brief_mail", ROOT / "scripts" / "send_macro_brief_email.py")
assert mail_spec and mail_spec.loader
mail = importlib.util.module_from_spec(mail_spec); sys.modules[mail_spec.name] = mail; mail_spec.loader.exec_module(mail)


class MacroBriefTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 16, 20, 5, tzinfo=ZoneInfo("Asia/Shanghai"))
        self.retail = {
            "id": "retail",
            "title": "美国零售销售",
            "scheduledAt": "2026-09-16T20:30:00+08:00",
            "source": "Forex Factory",
            "metrics": [{"label": "零售环比", "forecast": "0.8%", "previous": "-0.6%"}],
            "legacy": {"title": "Retail"},
        }

    def test_selects_whitelisted_event_inside_window(self):
        selected = brief.select_event([self.retail], self.now, 10, 30)
        self.assertEqual(selected[1]["id"], "retail")
        self.assertEqual(selected[2], "Retail")

    def test_rejects_non_whitelisted_event(self):
        event = {**self.retail, "id": "claims", "legacy": {"title": "Jobless Claims"}}
        self.assertIsNone(brief.select_event([event], self.now, 10, 30))

    def test_rejects_event_outside_window(self):
        event = {**self.retail, "scheduledAt": "2026-09-16T21:30:00+08:00"}
        self.assertIsNone(brief.select_event([event], self.now, 10, 30))

    def test_payload_uses_daily_treasuries_and_marks_them_non_intraday(self):
        daily = {"macroAnchors": [{"id": "US02Y", "latest": 4.67, "previous": 4.65, "provider": "U.S. Treasury"}], "fedProbability": {"label": "加息概率", "current": 94.5, "unit": "%"}}
        markets = {"symbols": [{"symbol": "DXY", "close": 99.6, "open": 99.5, "date": "2026-09-16", "time": "12:05 UTC"}]}
        scheduled = datetime.fromisoformat(self.retail["scheduledAt"])
        payload = brief.build_payload(self.retail, "Retail", scheduled, self.now, markets, daily)
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["market"]["treasuries"][0]["value"], 4.67)
        self.assertIn("非盘中", payload["market"]["treasuries"][0]["note"])
        self.assertIn("预期 0.8%", payload["copyText"])

    def test_email_contains_full_brief_and_release_time(self):
        payload = {"event": {"title": "美国零售销售", "scheduledAtLabel": "2026年09月16日 20:30（北京时间）"}, "copyText": "完整Brief正文"}
        message = mail.build_message(payload, "sender@icloud.com", "reader@example.com", "https://example.com/brief", "https://example.com/run")
        self.assertIn("20:30", str(message["Subject"]))
        self.assertIn("完整Brief正文", message.get_content())


if __name__ == "__main__":
    unittest.main()
