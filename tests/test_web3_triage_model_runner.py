import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_web3_triage_regression.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("web3_triage_runner", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def sample_case():
    return {
        "id": "example",
        "project_name": "Example",
        "expected_decision": "STOP",
        "expected_basis": ["must stay hidden"],
        "anti_patterns": ["must also stay hidden"],
        "input_snapshot": {
            "signals": ["A real signal"],
            "participation": "Nothing useful now",
        },
    }


def test_case_input_hides_expected_fields():
    runner = load_runner()
    visible = runner.case_input(sample_case())
    assert visible["id"] == "example"
    assert visible["project_name"] == "Example"
    assert visible["input_snapshot"]["signals"] == ["A real signal"]
    assert "expected_decision" not in visible
    assert "expected_basis" not in visible
    assert "anti_patterns" not in visible


def test_request_is_blind_and_structured():
    runner = load_runner()
    payload = runner.build_request(
        model="gpt-5.6-sol",
        reasoning_effort="medium",
        instructions="skill instructions",
        case=sample_case(),
    )
    assert payload["model"] == "gpt-5.6-sol"
    assert payload["reasoning"] == {"effort": "medium"}
    assert payload["store"] is False
    assert "tools" not in payload
    assert payload["text"]["format"]["type"] == "json_schema"
    assert payload["text"]["format"]["strict"] is True
    assert "expected_decision" not in payload["input"]


def test_extract_output_text_and_normalize():
    runner = load_runner()
    response = {
        "output": [
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": (
                            '{"id":"example","decision":"WATCH",'
                            '"rationale":["worth retaining"],'
                            '"recheck_trigger":"mainnet launch"}'
                        ),
                    }
                ],
            }
        ]
    }
    assert runner.extract_output_text(response).startswith('{"id":"example"')
    result = runner.normalize_result("example", response)
    assert result["decision"] == "WATCH"
    assert result["recheck_trigger"] == "mainnet launch"
