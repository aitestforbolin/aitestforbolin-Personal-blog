from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import update_crypto_fundraising_resilient as resilient  # noqa: E402
from tests.test_crypto_fundraising import FIXTURE  # noqa: E402


class CryptoFundraisingResilienceTests(unittest.TestCase):
    def test_deal_flow_fallback_reuses_first_five_rows(self):
        deal_flow_html = FIXTURE.replace(
            '<section class="recently-launched dealflow nospacebottom">',
            '<section class="vc-deal-flow">',
            1,
        )
        previous = {
            "projects": [
                {"id": "crypto-fundraising-201"},
                {"id": "crypto-fundraising-202"},
                {"id": "crypto-fundraising-203"},
                {"id": "crypto-fundraising-204"},
                {"id": "crypto-fundraising-205"},
            ]
        }

        with patch.object(resilient, "fetch_text", return_value=deal_flow_html):
            payload = resilient.build_from_deal_flow(previous)

        self.assertEqual(
            [project["name"] for project in payload["projects"]],
            ["Alpha Protocol", "Beta", "Gamma", "Delta", "Epsilon"],
        )


if __name__ == "__main__":
    unittest.main()
