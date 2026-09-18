import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURRENT = ROOT / "data" / "web3-daily-triage.json"
FUNDRAISING_PAGE = ROOT / "fundraising" / "index.html"
HOME = ROOT / "index.html"
HOME_FUNDRAISING = ROOT / "home-fundraising.js"
FUNDRAISING_RENDERER = ROOT / "fundraising" / "fundraising.js"
READER = ROOT / "fundraising" / "daily-triage" / "index.html"
RENDERER = ROOT / "fundraising" / "daily-triage" / "daily-triage.js"


def test_current_web3_triage_payload_contract():
    payload = json.loads(CURRENT.read_text(encoding="utf-8"))
    assert payload["schemaVersion"] == 1
    assert payload["status"] == "success"
    assert payload["runDate"]
    assert payload["publishedAt"]
    assert payload["windowStart"]
    assert payload["windowEnd"]
    assert isinstance(payload["reportedEventIds"], list)
    assert isinstance(payload["projects"], list)

    counts = payload["counts"]
    assert counts["new"] == len(payload["projects"])
    assert counts["new"] == counts["action"] + counts["watch"] + counts["stop"]

    for project in payload["projects"]:
        assert project["event_id"]
        assert project["project_name"]
        assert project["decision"] in {"ACTION", "WATCH", "STOP"}
        if project["project_status"]["token_status"] == "token_live":
            assert project["decision"] == "STOP"
        if project["decision"] == "WATCH":
            assert project["recheck_trigger"]
        if project["decision"] == "ACTION":
            assert project["next_step"]


def test_current_web3_triage_matches_immutable_archive():
    payload = json.loads(CURRENT.read_text(encoding="utf-8"))
    archive = ROOT / "data" / "web3-daily-triage" / "archive" / f'{payload["runDate"]}.json'
    assert archive.exists()
    assert CURRENT.read_text(encoding="utf-8") == archive.read_text(encoding="utf-8")


def test_web3_triage_reader_is_linked_from_site():
    fundraising = FUNDRAISING_PAGE.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    reader = READER.read_text(encoding="utf-8")
    renderer = RENDERER.read_text(encoding="utf-8")

    assert 'href="daily-triage/"' in fundraising
    assert 'href="fundraising/daily-triage/"' in home
    fundraising_section = home.split('id="fundraising"', 1)[1].split("</section>", 1)[0]
    copy_block = fundraising_section.split('class="briefing-home-copy"', 1)[1].split("</div>", 1)[0]
    assert "home-fundraising-triage" in copy_block
    assert "home-fundraising-triage" not in fundraising_section.split('class="fundraising-home-panel"', 1)[1]
    assert "每日融资项目初筛" in reader
    assert 'document.currentScript?.src' in renderer
    assert 'new URL("../../data/web3-daily-triage.json", SCRIPT_URL).href' in renderer
    assert "ACTION" in renderer
    assert "WATCH" in renderer
    assert "STOP" in renderer


def test_row_level_manual_research_buttons_stay_removed():
    home_renderer = HOME_FUNDRAISING.read_text(encoding="utf-8")
    fundraising_renderer = FUNDRAISING_RENDERER.read_text(encoding="utf-8")
    home = HOME.read_text(encoding="utf-8")
    fundraising = FUNDRAISING_PAGE.read_text(encoding="utf-8")

    assert "data-research-copy" not in home_renderer
    assert "data-prompt-type" not in home_renderer
    assert "BolinResearchPrompt" not in home_renderer
    assert "data-research-copy" not in fundraising_renderer
    assert "data-prompt-type" not in fundraising_renderer
    assert "BolinResearchPrompt" not in fundraising_renderer
    assert "research-prompt.js" not in home
    assert "research-prompt.js" not in fundraising
