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
                if any(row["consensus"] not in (None, "") for row in card["rows"]):
                    self.assertTrue(card.get("consensusSources"), card["id"])
                    for source in card["consensusSources"]:
                        self.assertTrue(
                            source["name"] == "Reuters"
                            or source["name"].startswith("Investing.com"),
                            source["name"],
                        )
                        self.assertTrue(source["url"].startswith("https://"))

    def test_reference_consensus_values_are_filled(self):
        payload = json.loads(DATA.read_text(encoding="utf-8"))
        cards = {
            card["id"]: card
            for group in payload["groups"]
            for card in group["cards"]
        }
        expected = {
            ("pce", "MoM"): "-0.1%",
            ("core-pce", "MoM"): "+0.2%",
            ("nfp", "当月新增"): "+80k",
            ("unemployment", "失业率"): "4.2%",
            ("earnings", "MoM"): "+0.3%",
            ("ism-manufacturing", "PMI"): "54.0",
            ("ism-services", "PMI"): "54.5",
            ("industrial-production", "MoM"): "+0.3%",
            ("real-gdp", "QoQ年化"): "+2.1%",
        }
        for (card_id, label), value in expected.items():
            row = next(item for item in cards[card_id]["rows"] if item["label"] == label)
            self.assertEqual(row["consensus"], value)

        unemployment = next(
            item for item in cards["unemployment"]["rows"] if item["label"] == "失业率"
        )
        self.assertEqual(unemployment["previous"], "4.2%")

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
            "consensus_source": "Investing.com",
            "consensus_url": "https://www.investing.com/economic-calendar/cpi-733",
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
            self.assertEqual(cards["cpi"]["consensusSources"][0]["name"], "Investing.com")
            self.assertEqual(updated["sourceEvents"]["美国CPI / 核心CPI"], "2026-09-11")
            self.assertTrue(updated["sourceEventFingerprints"]["美国CPI / 核心CPI"])
            inflation = next(item for item in updated["summary"] if item["id"] == "inflation")
            self.assertEqual(inflation["state"], "仍偏高，边际降温")
            self.assertIn("2.4%", inflation["detail"])


if __name__ == "__main__":
    unittest.main()
