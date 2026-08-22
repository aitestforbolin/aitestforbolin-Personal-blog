from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "update_crypto_fundraising.py"
)
ROOT = SCRIPT_PATH.parents[1]
SPEC = importlib.util.spec_from_file_location("crypto_fundraising_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = updater
SPEC.loader.exec_module(updater)


FIXTURE = """
<html><body>
  <section class="recently-launched dealflow nospacebottom">
    <h1>Recent fundraising events</h1>
    <div class="hp-table-row hpt-data" data-projectid="101;" data-eid="201">
      <div class="hpt-col1">01</div>
      <div class="hpt-col2">
        <a class="t-project-link" href="/projects/alpha">
          <h5 class="cointitle">Alpha Protocol</h5>
        </a>
      </div>
      <div class="hpt-col3">Series A</div>
      <div class="hpt-col3">Aug 2026</div>
      <div class="hpt-col4"><div class="mob-only">Raised</div><span class="abbrusd">40000000</span></div>
    </div>
    <div class="hp-table-row hpt-data" data-projectid="102;" data-eid="202">
      <div class="hpt-col2"><a class="t-project-link" href="/projects/beta"><h5 class="cointitle">Beta</h5></a></div>
      <div class="hpt-col3">Unknown</div><div class="hpt-col3">Aug 2026</div>
      <div class="hpt-col4"><span class="abbrusd"></span></div>
    </div>
    <div class="hp-table-row hpt-data" data-projectid="103;" data-eid="203">
      <div class="hpt-col2"><a class="t-project-link" href="https://crypto-fundraising.info/projects/gamma"><h5 class="cointitle">Gamma</h5></a></div>
      <div class="hpt-col3">Seed</div><div class="hpt-col3">Jul 2026</div>
      <div class="hpt-col4"><span class="abbrusd">1,500,000</span></div>
    </div>
    <div class="hp-table-row hpt-data" data-projectid="104;" data-eid="204">
      <div class="hpt-col2"><a class="t-project-link" href="/projects/delta"><h5 class="cointitle">Delta</h5></a></div>
      <div class="hpt-col3">Strategic</div><div class="hpt-col3">Jul 2026</div>
      <div class="hpt-col4"><span class="abbrusd">2000000</span></div>
    </div>
    <div class="hp-table-row hpt-data" data-projectid="105;" data-eid="205">
      <div class="hpt-col2"><a class="t-project-link" href="/projects/epsilon"><h5 class="cointitle">Epsilon</h5></a></div>
      <div class="hpt-col3">Pre-Seed</div><div class="hpt-col3">Jun 2026</div>
      <div class="hpt-col4"><span class="abbrusd">500000</span></div>
    </div>
  </section>
  <section class="largest-rounds">
    <h2>Last 30 days biggest fundraising rounds</h2>
    <div class="hp-table-row hpt-data" data-projectid="999;" data-eid="999">
      <div class="hpt-col2"><a class="t-project-link" href="/projects/wrong"><h5 class="cointitle">Wrong List</h5></a></div>
      <div class="hpt-col3">Series Z</div><div class="hpt-col3">Aug 2026</div>
      <div class="hpt-col4"><span class="abbrusd">999999999</span></div>
    </div>
  </section>
</body></html>
"""


class CryptoFundraisingTests(unittest.TestCase):
    def test_extracts_only_first_five_recent_events(self):
        projects = updater.parse_recent_events(FIXTURE)
        self.assertEqual(
            [item["name"] for item in projects],
            ["Alpha Protocol", "Beta", "Gamma", "Delta", "Epsilon"],
        )
        self.assertEqual(projects[0]["round"], "Series A")
        self.assertEqual(projects[0]["announced_month"], "2026-08")
        self.assertEqual(projects[0]["amount_usd"], 40_000_000)
        self.assertIsNone(projects[1]["round"])
        self.assertIsNone(projects[1]["amount_usd"])
        self.assertEqual(projects[2]["amount_usd"], 1_500_000)
        self.assertNotIn("Wrong List", [item["name"] for item in projects])

    def test_normalizes_project_detail_links(self):
        projects = updater.parse_recent_events(FIXTURE)
        self.assertEqual(
            projects[0]["detail_url"],
            "https://crypto-fundraising.info/projects/alpha/",
        )
        self.assertEqual(
            projects[2]["detail_url"],
            "https://crypto-fundraising.info/projects/gamma/",
        )

    def test_rejects_incomplete_recent_section(self):
        html = FIXTURE.replace(
            '<div class="hp-table-row hpt-data" data-projectid="103;" data-eid="203">',
            '<div class="not-a-row" data-projectid="103;" data-eid="203">',
        )
        with self.assertRaises(updater.SourceStructureError):
            updater.parse_recent_events(html)

    def test_rejects_offsite_project_link(self):
        html = FIXTURE.replace("/projects/alpha", "https://example.com/projects/alpha")
        with self.assertRaises(updater.SourceStructureError):
            updater.parse_recent_events(html)

    def test_published_data_and_frontend_keep_five_item_contract(self):
        payload = json.loads(
            (ROOT / "data" / "crypto-fundraising.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(payload["projects"]), 5)
        self.assertEqual(
            [project["source_rank"] for project in payload["projects"]],
            [1, 2, 3, 4, 5],
        )
        page = (ROOT / "fundraising" / "index.html").read_text(encoding="utf-8")
        frontend = (ROOT / "fundraising" / "fundraising.js").read_text(
            encoding="utf-8"
        )
        homepage = (ROOT / "index.html").read_text(encoding="utf-8")
        self.assertIn("data-fundraising-list", page)
        self.assertIn('../data/crypto-fundraising.json', frontend)
        self.assertIn('href="fundraising/">融资追踪</a>', homepage)

    def test_marks_only_new_project_ids(self):
        previous_payload = {
            "projects": [
                {"id": "crypto-fundraising-201"},
                {"id": "crypto-fundraising-202"},
                {"id": "crypto-fundraising-203"},
                {"id": "crypto-fundraising-204"},
                {"id": "crypto-fundraising-205"},
            ]
        }
        payload = updater.build_payload(FIXTURE, previous_payload)
        self.assertEqual(
            [project["is_new"] for project in payload["projects"]],
            [False, False, False, False, False],
        )

        newer_fixture = FIXTURE.replace('data-eid="201"', 'data-eid="999"')
        payload = updater.build_payload(newer_fixture, previous_payload)
        self.assertEqual(
            [project["is_new"] for project in payload["projects"]],
            [True, False, False, False, False],
        )

    def test_unchanged_source_projects_do_not_rewrite_new_badges(self):
        previous = updater.build_payload(FIXTURE)
        previous["projects"][0]["is_new"] = True
        refreshed = updater.build_payload(FIXTURE, previous)

        self.assertFalse(updater.project_data_changed(refreshed, previous))

    def test_new_source_project_still_requires_update(self):
        previous = updater.build_payload(FIXTURE)
        newer_fixture = FIXTURE.replace('data-eid="201"', 'data-eid="999"')
        refreshed = updater.build_payload(newer_fixture, previous)

        self.assertTrue(updater.project_data_changed(refreshed, previous))

    def test_fetch_retries_temporary_network_errors(self):
        class Response:
            headers = type("Headers", (), {"get_content_charset": lambda self: "utf-8"})()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def read(self):
                return FIXTURE.encode("utf-8")

        with patch.object(
            updater, "urlopen", side_effect=[URLError("temporary failure"), Response()]
        ) as mocked_urlopen, patch.object(updater.time, "sleep") as mocked_sleep:
            self.assertEqual(updater.fetch_homepage(), FIXTURE)

        self.assertEqual(mocked_urlopen.call_count, 2)
        mocked_sleep.assert_called_once_with(5)

    def test_fetch_failure_reports_retry_count(self):
        with patch.object(
            updater, "urlopen", side_effect=URLError("source unavailable")
        ) as mocked_urlopen, patch.object(updater.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "after 4 attempts"):
                updater.fetch_homepage()

        self.assertEqual(mocked_urlopen.call_count, updater.FETCH_RETRIES)

if __name__ == "__main__":
    unittest.main()
