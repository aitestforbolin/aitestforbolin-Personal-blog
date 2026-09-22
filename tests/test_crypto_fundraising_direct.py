from __future__ import annotations

import unittest

from scripts.crypto_fundraising_direct import parse_homepage_payload


class CryptoFundraisingDirectTests(unittest.TestCase):
    def test_parses_first_five_homepage_project_rows(self):
        html = """
        <table>
          <thead><tr><th>#</th><th>Project</th><th>Round</th><th>Date</th><th>Raised</th></tr></thead>
          <tbody>
            <tr><td>01</td><td><a href="/projects/dtcpay/">dtcpay</a></td><td>Series A</td><td>Sep 2026</td><td>15000000</td></tr>
            <tr><td>02</td><td><a href="/projects/openzeppelin/">OpenZeppelin</a></td><td>M&A</td><td>Sep 2026</td><td>-</td></tr>
            <tr><td>03</td><td><a href="/projects/ponygo/">PonyGo POG</a></td><td>Unknown</td><td>Sep 2026</td><td>-</td></tr>
            <tr><td>04</td><td><a href="/projects/rep/">Rep REP</a></td><td>Angel</td><td>Sep 2026</td><td>-</td></tr>
            <tr><td>05</td><td><a href="/projects/tenka/">Tenka</a></td><td>Pre-seed</td><td>Sep 2026</td><td>$2M</td></tr>
          </tbody>
        </table>
        """
        payload = parse_homepage_payload(html)
        self.assertEqual(len(payload["projects"]), 5)
        self.assertEqual(payload["projects"][0]["name"], "dtcpay")
        self.assertEqual(payload["projects"][0]["amount_usd"], 15_000_000)
        self.assertIsNone(payload["projects"][2]["round"])
        self.assertEqual(payload["projects"][2]["name"], "PonyGo")
        self.assertEqual(payload["projects"][3]["name"], "Rep")
        self.assertEqual(payload["projects"][4]["amount_usd"], 2_000_000)
        self.assertEqual(
            payload["projects"][4]["detail_url"],
            "https://crypto-fundraising.info/projects/tenka/",
        )


if __name__ == "__main__":
    unittest.main()
