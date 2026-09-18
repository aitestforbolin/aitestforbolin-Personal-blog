#!/usr/bin/env python3
"""Run blind Web3 triage regression cases against the OpenAI Responses API."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SKILL = ROOT / ".agents" / "skills" / "daily-financing-triage" / "SKILL.md"
DEFAULT_GOLDEN = ROOT / "tests" / "fixtures" / "web3_triage_golden_cases.json"
API_URL = "https://api.openai.com/v1/responses"
VALID_DECISIONS = {"ACTION", "WATCH", "STOP"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def case_input(case: dict[str, Any]) -> dict[str, Any]:
    """Return only fields the model is allowed to see during regression."""
    return {
        "id": case["id"],
        "project_name": case["project_name"],
        "input_snapshot": case["input_snapshot"],
    }


def output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "id": {"type": "string"},
            "decision": {
                "type": "string",
                "enum": ["ACTION", "WATCH", "STOP"],
            },
            "rationale": {
                "type": "array",
                "items": {"type": "string"},
            },
            "recheck_trigger": {
                "type": ["string", "null"],
            },
        },
        "required": ["id", "decision", "rationale", "recheck_trigger"],
    }


def build_instructions(skill_text: str) -> str:
    return (
        skill_text.strip()
        + "\n\n"
        + "## Regression mode\n\n"
        + "You are evaluating a historical snapshot. Use only the supplied snapshot. "
        + "Do not browse the web, do not update the case with current knowledge, and do not infer "
        + "an expected label from test metadata. Decide independently using the skill's decision policy. "
        + "Return concise reasons. For WATCH, provide a concrete recheck_trigger. "
        + "For ACTION or STOP, recheck_trigger must be null."
    )


def build_request(
    *,
    model: str,
    reasoning_effort: str,
    instructions: str,
    case: dict[str, Any],
) -> dict[str, Any]:
    return {
        "model": model,
        "reasoning": {"effort": reasoning_effort},
        "instructions": instructions,
        "input": json.dumps(case_input(case), ensure_ascii=False),
        "text": {
            "format": {
                "type": "json_schema",
                "name": "web3_triage_regression_result",
                "description": "Blind Web3 financing triage result for one historical case.",
                "strict": True,
                "schema": output_schema(),
            }
        },
        "max_output_tokens": 1200,
        "store": False,
    }


def extract_output_text(response: dict[str, Any]) -> str:
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for part in item.get("content", []):
            if part.get("type") == "output_text" and isinstance(part.get("text"), str):
                return part["text"]
            if part.get("type") == "refusal":
                raise RuntimeError(f"Model refused the regression case: {part.get('refusal')}")
    raise RuntimeError("Responses API payload did not contain output_text")


def call_responses_api(api_key: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API returned HTTP {exc.code}: {body[:1500]}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"OpenAI API request failed: {type(exc).__name__}") from exc


def normalize_result(case_id: str, response: dict[str, Any]) -> dict[str, Any]:
    raw = extract_output_text(response)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model returned invalid JSON for {case_id}") from exc

    if result.get("id") != case_id:
        raise RuntimeError(
            f"Model result id mismatch: expected {case_id!r}, got {result.get('id')!r}"
        )
    if result.get("decision") not in VALID_DECISIONS:
        raise RuntimeError(f"Unsupported decision for {case_id}: {result.get('decision')!r}")
    if result["decision"] == "WATCH" and not str(result.get("recheck_trigger") or "").strip():
        raise RuntimeError(f"WATCH result for {case_id} is missing recheck_trigger")
    if result["decision"] != "WATCH" and result.get("recheck_trigger") is not None:
        raise RuntimeError(f"{result['decision']} result for {case_id} must not set recheck_trigger")
    return result


def add_usage(total: dict[str, int], response: dict[str, Any]) -> None:
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            total[key] = total.get(key, 0) + value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-5.6-sol"),
        help="OpenAI model ID",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=os.getenv("OPENAI_REASONING_EFFORT", "medium"),
        choices=("low", "medium", "high"),
    )
    parser.add_argument("--skill", type=Path, default=DEFAULT_SKILL)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY is required.", file=sys.stderr)
        return 2

    skill_text = args.skill.read_text(encoding="utf-8")
    golden = load_json(args.golden)
    cases = golden.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise RuntimeError("Golden fixture does not contain regression cases")

    instructions = build_instructions(skill_text)
    results: list[dict[str, Any]] = []
    usage: dict[str, int] = {}

    for index, case in enumerate(cases, start=1):
        case_id = str(case["id"])
        print(f"[{index}/{len(cases)}] Running {case_id}...", flush=True)
        payload = build_request(
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            instructions=instructions,
            case=case,
        )
        response = call_responses_api(api_key, payload)
        result = normalize_result(case_id, response)
        results.append(result)
        add_usage(usage, response)
        print(f"  -> {result['decision']}", flush=True)

    rendered = {
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "case_count": len(results),
        "usage": usage,
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(rendered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
