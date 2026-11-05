import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import update_btc_etf_flow as etf


class BtcEtfFlowTests(unittest.TestCase):
    def test_partial_fund_values_preserve_day_and_long_streak(self):
        rows = [
            {"date": f"2026-11-{day:02d}", "total": -float(day),
             "funds": {"IBIT": None, "FBTC": None, "GBTC": None}}
            for day in range(1, 8)
        ]
        with patch.object(etf, "fetch_text", return_value=json.dumps({"rows": rows})) as fetch:
            payload = etf.build_payload()

        self.assertEqual(payload["latest"], {
            "date": "2026-11-07", "total": -7.0, "streak_days": 7
        })
        self.assertEqual(len(payload["rows"]), 5)
        self.assertEqual(payload["rows"][0], {"date": "2026-11-07", "total": -7.0})
        self.assertEqual(set(payload["rows"][0]), {"date", "total"})
        self.assertNotIn("funds", payload)
        self.assertNotIn("seven_day_total", payload["latest"])
        self.assertEqual(fetch.call_count, 1)  # No BTC price request.

    def test_missing_total_keeps_previous_output(self):
        rows = [
            {"date": f"2026-11-{day:02d}", "total": None if day == 7 else 3.0}
            for day in range(1, 8)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "btc-etf-flow.json"
            output.write_text("previous dataset\n")
            with patch.object(etf, "OUTPUT", output), patch.object(
                etf, "fetch_text", return_value=json.dumps({"rows": rows})
            ):
                etf.main()
            self.assertEqual(output.read_text(), "previous dataset\n")

    def test_direct_source_fallback_reads_total_without_fund_requirements(self):
        lines = ["Date", "IBIT", "FBTC", "Total"]
        for day in range(7, 0, -1):
            lines.extend([f"{day:02d} Nov 2026", "-", "-", f"({day}.0)"])
        html = "".join(f"<td>{value}</td>" for value in lines)

        def fetch(url):
            if url == etf.FARSIDE_BRIDGE_URL:
                raise RuntimeError("bridge unavailable")
            return html

        with patch.object(etf, "fetch_text", side_effect=fetch):
            payload = etf.build_payload()
        self.assertEqual(payload["latest"]["streak_days"], 7)
        self.assertEqual(payload["rows"][0]["total"], -7.0)


if __name__ == "__main__":
    unittest.main()
