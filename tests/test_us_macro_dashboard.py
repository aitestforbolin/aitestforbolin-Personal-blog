import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "us-macro-dashboard.json"
SCRIPT = ROOT / "scripts" / "update_us_macro_dashboard.py"

spec = importlib.util.spec_from_file_location("us_macro_calendar_for_dashboard_tests", ROOT / "scripts" / "update_us_macro_calendar.py")
calendar_updater = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(calendar_updater)
dashboard_spec = importlib.util.spec_from_file_location("us_macro_dashboard_for_tests", SCRIPT)
dashboard_updater = importlib.util.module_from_spec(dashboard_spec)
assert dashboard_spec and dashboard_spec.loader
dashboard_spec.loader.exec_module(dashboard_updater)


def metric(label, actual, forecast, previous):
    return {
        "label": label,
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "actual_source": "BLS",
        "actual_url": "https://www.bls.gov/news.release/cpi.nr0.htm",
        "consensus_source": "Investing.com",
        "consensus_url": "https://www.investing.com/economic-calendar/cpi-733",
    }


def cpi_event(day="2026-09-11", period="August 2026", value="+0.2%"):
    return {
        "date": day,
        "period": period,
        "title_cn": "美国CPI / 核心CPI",
        "release_status": "released",
        "actual_source": "BLS",
        "actual_url": "https://www.bls.gov/news.release/cpi.nr0.htm",
        "consensus_source": "Investing.com",
        "consensus_url": "https://www.investing.com/economic-calendar/cpi-733",
        "metric_values": [
            metric("CPI环比", value, "+0.2%", "+0.1%"),
            metric("CPI同比", value, "+3.2%", "+3.4%"),
            metric("核心CPI环比", "+0.2%", "+0.2%", "+0.2%"),
            metric("核心CPI同比", "+2.4%", "+2.5%", "+2.5%"),
        ],
    }


class USMacroDashboardTests(unittest.TestCase):
    def setUp(self):
        self.payload = json.loads(DATA.read_text(encoding="utf-8"))

    def run_update(self, events, payload=None):
        directory = tempfile.TemporaryDirectory()
        base = Path(directory.name)
        dashboard, calendar, history = base / "dashboard.json", base / "calendar.json", base / "history.json"
        dashboard.write_text(json.dumps(payload or self.payload, ensure_ascii=False), encoding="utf-8")
        calendar.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        history.write_text('{"schemaVersion":"1.0","observations":[]}', encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--calendar", str(calendar), "--dashboard", str(dashboard), "--history", str(history)],
            check=True, capture_output=True, text=True,
        )
        return directory, dashboard, history, result

    def cards(self, payload):
        return {card["id"]: card for group in payload["groups"] for card in group["cards"]}

    def test_dashboard_has_four_states_fifteen_cards_and_twenty_five_rows(self):
        self.assertEqual(self.payload["schemaVersion"], "1.0")
        self.assertEqual(len(self.payload["summary"]), 4)
        cards = self.cards(self.payload)
        self.assertEqual(len(cards), 15)
        self.assertEqual(sum(len(card["rows"]) for card in cards.values()), 25)

    def test_calendar_uses_fourteen_day_recovery_window(self):
        self.assertEqual(calendar_updater.DEFAULT_LOOKBACK_DAYS, 14)

    def test_release_bundles_cover_all_twenty_five_dashboard_rows(self):
        mapped = {
            target for bundle in dashboard_updater.RELEASE_BUNDLES.values()
            for target in bundle["targets"].values()
        }
        displayed = {
            (card["id"], row["label"])
            for card in self.cards(self.payload).values() for row in card["rows"]
        }
        self.assertEqual(mapped, displayed)

    def test_investing_enrichment_standardizes_complete_cpi_bundle(self):
        event = calendar_updater.make_event(
            day=calendar_updater.date(2026, 9, 11), eastern_time="08:30",
            title="Consumer Price Index", title_cn="美国CPI / 核心CPI", period="August 2026",
            category="inflation", source="BLS", url="https://www.bls.gov/news.release/cpi.nr0.htm", stars=5,
        )
        results = {"美国CPI / 核心CPI": [
            {"date": "2026-09-11", "label": label, "actual": actual, "forecast": forecast,
             "previous": previous, "consensus_source": "Investing.com", "consensus_url": url,
             "actual_source": "Investing.com（官方发布值转录）", "actual_url": url}
            for label, actual, forecast, previous, url in [
                ("CPI环比", "+0.2%", "+0.2%", "+0.1%", "https://www.investing.com/economic-calendar/cpi-69"),
                ("CPI同比", "+3.2%", "+3.2%", "+3.4%", "https://www.investing.com/economic-calendar/cpi-733"),
                ("核心CPI环比", "+0.2%", "+0.2%", "+0.2%", "https://www.investing.com/economic-calendar/core-cpi-56"),
                ("核心CPI同比", "+2.4%", "+2.5%", "+2.5%", "https://www.investing.com/economic-calendar/core-cpi-736"),
            ]
        ]}
        calendar_updater.enrich_events_with_investing_core_values(
            [event], results, calendar_updater.date(2026, 9, 1), calendar_updater.date(2026, 9, 20)
        )
        self.assertEqual(len(event["metric_values"]), 4)
        self.assertEqual(event["release_status"], "released")
        self.assertEqual(event["actual_source"], "BLS")
        self.assertEqual(event["consensus_source"], "Investing.com")

    def test_industrial_production_can_be_backfilled_without_static_schedule(self):
        results = {"美国工业产出": [
            {"date": "2026-08-18", "label": "工业产出环比", "actual": "+0.3%", "forecast": "+0.2%", "previous": "+0.1%",
             "consensus_source": "Investing.com", "consensus_url": "https://www.investing.com/economic-calendar/industrial-production-161"},
            {"date": "2026-08-18", "label": "工业产出同比", "actual": "+2.1%", "forecast": None, "previous": "+1.8%",
             "consensus_source": "Investing.com", "consensus_url": "https://www.investing.com/economic-calendar/industrial-production-1755"},
        ]}
        events = []
        calendar_updater.enrich_events_with_investing_core_values(
            events, results, calendar_updater.date(2026, 8, 5), calendar_updater.date(2026, 8, 19)
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["title_cn"], "美国工业产出")
        self.assertEqual(events[0]["period"], "July 2026")
        self.assertEqual(len(events[0]["metric_values"]), 2)

    def test_exact_ppi_parser_accepts_bls_yearly_sentence_order(self):
        html = """
        <p>Prices for final demand less foods, energy, and trade services rose 0.4 percent in July.</p>
        <p>The index for final demand less foods, energy, and trade services increased 4.7 percent for the 12 months ended in July.</p>
        """
        with patch.object(calendar_updater, "fetch_text", return_value=html):
            values = calendar_updater.fetch_bls_ppi_exclusion_values()
        self.assertEqual(values["PPI剔除食品能源贸易服务环比"], "+0.4%")
        self.assertEqual(values["PPI剔除食品能源贸易服务同比"], "+4.7%")

    def test_every_card_has_rows_trend_and_source(self):
        for card in self.cards(self.payload).values():
            self.assertTrue(card["rows"], card["id"])
            self.assertTrue(card["trend"], card["id"])
            self.assertTrue(card["source"]["url"].startswith("https://"), card["id"])
            for row in card["rows"]:
                self.assertTrue({"actual", "consensus", "previous"}.issubset(row))
            for source in card.get("consensusSources", []):
                self.assertTrue(source["name"] == "Reuters" or source["name"].startswith("Investing.com"))

    def test_incomplete_release_is_rejected_without_any_write(self):
        event = cpi_event()
        event["metric_values"] = event["metric_values"][:2]
        directory, dashboard, history, result = self.run_update([event])
        try:
            self.assertIn("no complete publishable bundle", result.stdout)
            self.assertEqual(json.loads(dashboard.read_text(encoding="utf-8")), self.payload)
            self.assertEqual(json.loads(history.read_text(encoding="utf-8"))["observations"], [])
        finally:
            directory.cleanup()

    def test_complete_cpi_release_updates_all_four_rows_atomically(self):
        directory, dashboard, history, result = self.run_update([cpi_event()])
        try:
            updated = json.loads(dashboard.read_text(encoding="utf-8"))
            cards = self.cards(updated)
            self.assertIn("updated 4 dashboard rows", result.stdout)
            self.assertEqual(cards["cpi"]["period"], "August 2026")
            self.assertEqual(cards["core-cpi"]["releaseDate"], "2026-09-11")
            self.assertEqual(cards["core-cpi"]["rows"][1]["actual"], "+2.4%")
            self.assertEqual(cards["cpi"]["source"]["name"], "BLS")
            self.assertEqual(cards["cpi"]["consensusSources"][0]["name"], "Investing.com")
            observations = json.loads(history.read_text(encoding="utf-8"))["observations"]
            self.assertEqual(len([item for item in observations if item["releaseDate"] == "2026-09-11"]), 4)
        finally:
            directory.cleanup()

    def test_same_value_new_release_still_advances_period_and_date(self):
        cards = self.cards(self.payload)
        old_value = cards["real-gdp"]["rows"][0]["actual"]
        event = {
            "date": "2026-08-26", "period": "2nd Quarter 2026 (Second Estimate)",
            "title_cn": "美国GDP", "release_status": "released",
            "actual_source": "BEA", "actual_url": "https://www.bea.gov/news/current-releases",
            "consensus_source": "Investing.com", "consensus_url": "https://www.investing.com/economic-calendar/gdp-375",
            "metric_values": [{"label": "GDP年化环比", "actual": old_value, "forecast": "+2.1%", "previous": old_value}],
        }
        directory, dashboard, _, _ = self.run_update([event])
        try:
            updated = self.cards(json.loads(dashboard.read_text(encoding="utf-8")))["real-gdp"]
            self.assertEqual(updated["period"], "2nd Quarter 2026 (Second Estimate)")
            self.assertEqual(updated["releaseDate"], "2026-08-26")
        finally:
            directory.cleanup()

    def test_complete_ppi_release_maps_exact_exclusion_rows(self):
        event = {
            "date": "2026-09-10", "period": "August 2026", "title_cn": "美国PPI", "release_status": "released",
            "actual_source": "BLS", "actual_url": "https://www.bls.gov/news.release/ppi.nr0.htm",
            "consensus_source": "Investing.com", "consensus_url": "https://www.investing.com/economic-calendar/ppi-734",
            "metric_values": [
                {"label": "PPI环比", "actual": "+0.1%", "forecast": "+0.2%", "previous": "0.0%"},
                {"label": "PPI同比", "actual": "+4.5%", "forecast": "+4.6%", "previous": "+4.7%"},
                {"label": "PPI剔除食品能源贸易服务环比", "actual": "+0.2%", "forecast": None, "previous": "+0.4%"},
                {"label": "PPI剔除食品能源贸易服务同比", "actual": "+4.4%", "forecast": None, "previous": "+4.7%"},
            ],
        }
        directory, dashboard, _, _ = self.run_update([event])
        try:
            rows = self.cards(json.loads(dashboard.read_text(encoding="utf-8")))["ppi"]["rows"]
            self.assertEqual([row["actual"] for row in rows], ["+0.1%", "+4.5%", "+0.2%", "+4.4%"])
        finally:
            directory.cleanup()

    def test_three_releases_create_history_based_trend(self):
        events = [
            cpi_event("2026-09-11", "August 2026", "+0.3%"),
            cpi_event("2026-10-13", "September 2026", "+0.2%"),
            cpi_event("2026-11-12", "October 2026", "+0.1%"),
        ]
        directory, dashboard, history, _ = self.run_update(events)
        try:
            card = self.cards(json.loads(dashboard.read_text(encoding="utf-8")))["cpi"]
            self.assertIn("最近", card["trend"])
            self.assertIn("总体下行", card["trend"])
            observations = json.loads(history.read_text(encoding="utf-8"))["observations"]
            self.assertEqual(len([item for item in observations if item["releaseDate"] >= "2026-09-11"]), 12)
        finally:
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
