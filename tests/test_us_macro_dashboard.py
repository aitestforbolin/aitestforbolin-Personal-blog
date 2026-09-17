import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "update_us_macro_dashboard.py"

spec = importlib.util.spec_from_file_location("us_macro_dashboard_for_tests", SCRIPT)
updater = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(updater)

FF_URL = "https://www.forexfactory.com/calendar?day=sep16.2026"


def ff_metric(label, actual, forecast="0.0%", previous="0.0%"):
    return {
        "label": label, "actual": actual, "forecast": forecast, "previous": previous,
        "actual_source": "Forex Factory 网页日历", "actual_url": FF_URL,
        "consensus_source": "Forex Factory 市场日历", "consensus_url": "https://www.forexfactory.com/calendar",
    }


def ff_event(title, metrics, day="2026-09-16", period="August 2026", status="released"):
    return {
        "date": day, "title_cn": title, "period": period, "release_status": status,
        "source": "Forex Factory", "url": "https://www.forexfactory.com/calendar",
        "result_source": "Forex Factory 网页日历", "result_url": FF_URL,
        "metric_values": metrics,
    }


class USMacroDashboardTests(unittest.TestCase):
    def run_update(self, events, dashboard=None, history=None):
        directory = tempfile.TemporaryDirectory()
        base = Path(directory.name)
        calendar_path, dashboard_path, history_path = base / "calendar.json", base / "dashboard.json", base / "history.json"
        calendar_path.write_text(json.dumps(events, ensure_ascii=False), encoding="utf-8")
        dashboard_path.write_text(json.dumps(dashboard or updater.make_dashboard(), ensure_ascii=False), encoding="utf-8")
        history_path.write_text(json.dumps(history or {"schemaVersion": "1.0", "observations": []}, ensure_ascii=False), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--calendar", str(calendar_path), "--dashboard", str(dashboard_path), "--history", str(history_path)],
            check=True, capture_output=True, text=True,
        )
        return directory, json.loads(dashboard_path.read_text(encoding="utf-8")), json.loads(history_path.read_text(encoding="utf-8")), result

    @staticmethod
    def cards(payload):
        return {card["id"]: card for group in payload["groups"] for card in group["cards"]}

    def test_layout_contains_only_forex_factory_supported_rows(self):
        payload = updater.make_dashboard()
        cards = self.cards(payload)
        self.assertNotIn("retail-control", cards)
        self.assertNotIn("real-pce", cards)
        self.assertNotIn("PPI剔除食品能源贸易服务环比", str(payload))
        self.assertNotIn("YoY", [row["label"] for row in cards["industrial-production"]["rows"]])
        self.assertEqual(cards["core-retail-sales"]["rows"][0]["label"], "Core Retail Sales m/m")
        self.assertTrue(all(card["source"] == "Forex Factory" for card in cards.values()))

    def test_released_retail_values_update_dashboard_without_legacy_calendar(self):
        event = ff_event("美国零售销售", [
            ff_metric("零售环比", "1.2%", "0.8%", "-0.5%"),
            ff_metric("核心零售环比", "1.4%", "0.6%", "-0.2%"),
        ])
        directory, dashboard, history, result = self.run_update([event])
        try:
            cards = self.cards(dashboard)
            self.assertIn("updated 2 dashboard rows", result.stdout)
            self.assertEqual(cards["retail-sales"]["rows"][0], {"label": "Retail Sales m/m", "actual": "1.2%", "forecast": "0.8%", "previous": "-0.5%"})
            self.assertEqual(cards["core-retail-sales"]["rows"][0]["actual"], "1.4%")
            self.assertEqual(cards["retail-sales"]["source"], "Forex Factory")
            self.assertEqual(cards["retail-sales"]["sourceUrl"], FF_URL)
            self.assertEqual(cards["retail-sales"]["releaseDate"], "2026-09-16")
            self.assertEqual(len(history["observations"]), 2)
            self.assertEqual(dashboard["summary"][2]["state"], "消费回升")
        finally:
            directory.cleanup()

    def test_scheduled_or_empty_actual_never_updates_a_card(self):
        dashboard_before = updater.make_dashboard()
        scheduled = ff_event("美国零售销售", [ff_metric("零售环比", None, "0.8%", "-0.5%")], status="scheduled")
        released_without_actual = ff_event("美国零售销售", [ff_metric("核心零售环比", None, "0.6%", "-0.2%")])
        directory, dashboard, history, result = self.run_update([scheduled, released_without_actual], dashboard_before)
        try:
            self.assertIn("no new released Forex Factory", result.stdout)
            self.assertEqual(dashboard, dashboard_before)
            self.assertEqual(history["observations"], [])
        finally:
            directory.cleanup()

    def test_partial_ppi_release_updates_available_metrics_only(self):
        event = ff_event("美国PPI", [
            ff_metric("PPI环比", "0.3%", "0.2%", "0.1%"),
            ff_metric("核心PPI环比", None, "0.2%", "0.1%"),
        ])
        directory, dashboard, history, result = self.run_update([event])
        try:
            cards = self.cards(dashboard)
            self.assertIn("updated 1 dashboard rows", result.stdout)
            self.assertEqual(cards["ppi"]["rows"][0]["actual"], "0.3%")
            self.assertIsNone(cards["core-ppi"]["rows"][0]["actual"])
            self.assertEqual(len(history["observations"]), 1)
        finally:
            directory.cleanup()

    def test_same_release_revision_replaces_history_not_duplicate(self):
        first = ff_event("美国零售销售", [ff_metric("零售环比", "0.8%")])
        directory, dashboard, history, _ = self.run_update([first])
        try:
            revised = ff_event("美国零售销售", [ff_metric("零售环比", "1.2%")])
            second_dir, dashboard, history, _ = self.run_update([revised], dashboard, history)
            try:
                row = self.cards(dashboard)["retail-sales"]["rows"][0]
                self.assertEqual(row["actual"], "1.2%")
                observations = [item for item in history["observations"] if item["cardId"] == "retail-sales"]
                self.assertEqual(len(observations), 1)
                self.assertEqual(observations[0]["source"], "Forex Factory")
            finally:
                second_dir.cleanup()
        finally:
            directory.cleanup()

    def test_history_accumulates_distinct_releases_and_produces_trend(self):
        events = [
            ff_event("美国零售销售", [ff_metric("零售环比", "0.1%")], "2026-07-15", "June 2026"),
            ff_event("美国零售销售", [ff_metric("零售环比", "0.3%")], "2026-08-14", "July 2026"),
            ff_event("美国零售销售", [ff_metric("零售环比", "0.6%")], "2026-09-16", "August 2026"),
        ]
        directory, dashboard, history, _ = self.run_update(events)
        try:
            self.assertEqual(len([item for item in history["observations"] if item["cardId"] == "retail-sales"]), 3)
            self.assertIn("总体上行", self.cards(dashboard)["retail-sales"]["trend"])
            self.assertEqual(self.cards(dashboard)["retail-sales"]["period"], "August 2026")
        finally:
            directory.cleanup()

    def test_old_dashboard_is_migrated_to_forex_factory_only_schema(self):
        legacy = {"schemaVersion": "1.0", "groups": [], "summary": []}
        directory, dashboard, _, result = self.run_update([], dashboard=legacy)
        try:
            self.assertIn("updated 0 dashboard rows", result.stdout)
            self.assertEqual(dashboard["schemaVersion"], "2.0")
            self.assertEqual(dashboard["dataQuality"]["source"], "Forex Factory")
            self.assertNotIn("Reuters", json.dumps(dashboard))
            self.assertNotIn("Investing.com", json.dumps(dashboard))
        finally:
            directory.cleanup()


if __name__ == "__main__":
    unittest.main()
