import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "us-macro-dashboard.json"
SCRIPT = ROOT / "scripts" / "update_us_macro_dashboard.py"


class USMacroDashboardTests(unittest.TestCase):
    def test_dashboard_has_four_states_and_fifteen_cards(self):
        payload = json.loads(DATA.read_text(encoding="utf-8"))
        self.assertEqual(payload["schemaVersion"], "1.0")
        self.assertEqual(len(payload["summary"]), 4)
        cards = [card for group in payload["groups"] for card in group["cards"]]
        self.assertEqual(len(cards), 15)
        self.assertEqual(len({card["id"] for card in cards}), 15)

    def test_every_card_has_rows_trend_and_source(self):
        payload = json.loads(DATA.read_text(encoding="utf-8"))
        for group in payload["groups"]:
            for card in group["cards"]:
                self.assertTrue(card["rows"], card["id"])
                self.assertTrue(card["trend"], card["id"])
                self.assertTrue(card["source"]["url"].startswith("https://"), card["id"])
                for row in card["rows"]:
                    self.assertIn("actual", row)
                    self.assertIn("consensus", row)
                    self.assertIn("previous", row)

    def test_no_new_release_makes_no_write(self):
        payload = json.loads(DATA.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            dashboard = base / "dashboard.json"
            calendar = base / "calendar.json"
            dashboard.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            calendar.write_text("[]", encoding="utf-8")
            before = dashboard.read_bytes()
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--calendar",
                    str(calendar),
                    "--dashboard",
                    str(dashboard),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("dashboard unchanged", result.stdout)
            self.assertEqual(before, dashboard.read_bytes())

    def test_new_cpi_release_updates_only_target_rows(self):
        payload = json.loads(DATA.read_text(encoding="utf-8"))
        event = {
            "date": "2026-09-11",
            "period": "August 2026",
            "title_cn": "美国CPI / 核心CPI",
            "release_status": "released",
            "metric_values": [
                {"label": "CPI环比", "actual": "0.2%", "forecast": "0.2%", "previous": "0.1%"},
                {"label": "核心CPI同比", "actual": "2.4%", "forecast": "2.5%", "previous": "2.5%"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            dashboard = base / "dashboard.json"
            calendar = base / "calendar.json"
            dashboard.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            calendar.write_text(json.dumps([event], ensure_ascii=False), encoding="utf-8")
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--calendar",
                    str(calendar),
                    "--dashboard",
                    str(dashboard),
                ],
                check=True,
            )
            updated = json.loads(dashboard.read_text(encoding="utf-8"))
            cards = {
                card["id"]: card
                for group in updated["groups"]
                for card in group["cards"]
            }
            cpi_mom = next(row for row in cards["cpi"]["rows"] if row["label"] == "MoM")
            core_yoy = next(row for row in cards["core-cpi"]["rows"] if row["label"] == "YoY")
            self.assertEqual(cpi_mom["actual"], "0.2%")
            self.assertEqual(core_yoy["actual"], "2.4%")
            self.assertEqual(updated["sourceEvents"]["美国CPI / 核心CPI"], "2026-09-11")
            self.assertTrue(updated["sourceEventFingerprints"]["美国CPI / 核心CPI"])
            inflation = next(item for item in updated["summary"] if item["id"] == "inflation")
            self.assertEqual(inflation["state"], "仍偏高，边际降温")
            self.assertIn("2.4%", inflation["detail"])


if __name__ == "__main__":
    unittest.main()
