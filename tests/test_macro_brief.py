from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import datetime, timedelta
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
        self.fomc = {
            "id": "fomc",
            "title": "FOMC 利率决议 / 经济预测",
            "scheduledAt": "2026-09-17T02:00:00+08:00",
            "source": "Federal Reserve",
            "metrics": [],
            "legacy": {"title": "FOMC"},
        }

    def plan_minutes_before(self, event, minutes, state=None):
        scheduled = datetime.fromisoformat(event["scheduledAt"])
        now = scheduled - timedelta(minutes=minutes)
        return brief.plan_next_event([event], now, state or {}, 0, 30)

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

    def test_stale_fedwatch_is_not_reused_in_macro_brief(self):
        daily = {"fedProbability": {
            "status": "available", "meetingEndDate": "2026-09-16T14:00:00-04:00",
            "probabilities": {"hike25": {"current": 100}},
        }}
        self.assertEqual(brief.fed_snapshot(daily)["status"], "unavailable")

    def test_capture_at_55_minutes_waits_without_generating(self):
        plan = self.plan_minutes_before(self.fomc, 55)
        self.assertEqual(plan["action"], "wait")
        self.assertEqual(plan["event"]["id"], "fomc")
        self.assertEqual(plan["waitSeconds"], 30 * 60)
        self.assertEqual(self.plan_minutes_before(self.fomc, 60)["waitSeconds"], 35 * 60)

    def test_capture_at_38_minutes_calculates_wait_to_25_minute_target(self):
        plan = self.plan_minutes_before(self.fomc, 38)
        self.assertEqual(plan["action"], "wait")
        self.assertEqual(plan["waitSeconds"], 13 * 60)
        self.assertEqual(plan["targetAt"].strftime("%H:%M"), "01:35")

    def test_generation_window_and_emergency_fallback(self):
        for minutes in (25, 10, 2):
            with self.subTest(minutes=minutes):
                self.assertEqual(self.plan_minutes_before(self.fomc, minutes)["action"], "generate")

    def test_does_not_wait_outside_capture_window_or_after_release(self):
        self.assertEqual(self.plan_minutes_before(self.fomc, 61)["action"], "too_early")
        self.assertEqual(self.plan_minutes_before(self.fomc, -1)["action"], "expired")

    def test_state_deduplicates_same_event_but_not_the_next_event(self):
        state = {"lastEventId": "retail"}
        self.assertEqual(self.plan_minutes_before(self.retail, 25, state)["action"], "already_sent")
        self.assertEqual(self.plan_minutes_before(self.fomc, 25, state)["action"], "generate")

    def test_fomc_dry_run_start_times(self):
        expected = {
            "01:05": ("wait", 30 * 60),
            "01:22": ("wait", 13 * 60),
            "01:35": ("generate", 0),
            "01:48": ("generate", 0),
            "01:59": ("generate", 0),
        }
        scheduled = datetime.fromisoformat(self.fomc["scheduledAt"])
        for clock, result in expected.items():
            hour, minute = map(int, clock.split(":"))
            now = scheduled.replace(hour=hour, minute=minute)
            plan = brief.plan_next_event([self.fomc], now, {}, 0, 30)
            with self.subTest(clock=clock):
                self.assertEqual((plan["action"], plan["waitSeconds"]), result)

    def test_email_contains_full_brief_and_release_time(self):
        payload = {"event": {"title": "美国零售销售", "scheduledAtLabel": "2026年09月16日 20:30（北京时间）"}, "copyText": "完整Brief正文"}
        message = mail.build_message(payload, "sender@icloud.com", "reader@example.com", "https://example.com/brief", "https://example.com/run")
        self.assertIn("20:30", str(message["Subject"]))
        self.assertIn("完整Brief正文", message.get_content())


if __name__ == "__main__":
    unittest.main()
