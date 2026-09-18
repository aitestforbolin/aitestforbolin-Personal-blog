import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "fixtures" / "web3_triage_golden_cases.json"
SCRIPT = ROOT / "scripts" / "evaluate_web3_triage_regression.py"
SKILL = ROOT / ".agents" / "skills" / "daily-financing-triage" / "SKILL.md"


def load_evaluator():
    spec = importlib.util.spec_from_file_location("web3_triage_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_golden_case_contract():
    payload = json.loads(GOLDEN.read_text(encoding="utf-8"))
    cases = payload["cases"]
    assert len(cases) == 10
    assert {case["expected_decision"] for case in cases} == {"ACTION", "WATCH", "STOP"}
    assert len({case["id"] for case in cases}) == 10
    for case in cases:
        assert case["project_name"]
        assert case["input_snapshot"]["signals"]
        assert case["expected_basis"]
        if case["expected_decision"] == "WATCH":
            assert case.get("recheck_trigger")


def test_skill_contains_core_safety_and_decision_contract():
    text = SKILL.read_text(encoding="utf-8")
    for required in (
        "ACTION",
        "WATCH",
        "STOP",
        "feed_is_new",
        "official X",
        "recheck_trigger",
        "new_live_no_token",
        "existing_token",
        "renamed_existing",
        "confirmed live/tradable native token",
        "If `token_status` is `token_live`, the final decision must be `STOP`",
    ):
        assert required in text


def test_evaluator_scores_perfect_run():
    evaluator = load_evaluator()
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = {
        "results": [
            {"id": case["id"], "decision": case["expected_decision"]}
            for case in golden["cases"]
        ]
    }
    report = evaluator.score(golden, actual)
    assert report["accuracy"] == 1.0
    assert report["weighted_penalty"] == 0.0
    assert not report["missing"]
    assert not report["unexpected"]
    assert not report["invalid"]


def test_evaluator_penalizes_false_stop_more_than_action_to_watch():
    evaluator = load_evaluator()
    assert evaluator.PENALTY[("ACTION", "STOP")] > evaluator.PENALTY[("ACTION", "WATCH")]
    assert evaluator.PENALTY[("WATCH", "STOP")] > evaluator.PENALTY[("WATCH", "ACTION")]
