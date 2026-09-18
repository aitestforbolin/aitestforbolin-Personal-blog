#!/usr/bin/env python3
"""Score model triage labels against the Web3 golden-case fixture.

Expected actual-results shape:
{
  "results": [
    {"id": "brix", "decision": "ACTION"},
    ...
  ]
}
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

VALID = {"ACTION", "WATCH", "STOP"}

# Missing worthwhile projects is deliberately more expensive than an adjacent
# over-inclusion, while STOP->ACTION remains a severe mistake because ACTION
# can lead to real user effort/capital.
PENALTY = {
    ("ACTION", "ACTION"): 0.0,
    ("ACTION", "WATCH"): 0.5,
    ("ACTION", "STOP"): 2.0,
    ("WATCH", "ACTION"): 0.75,
    ("WATCH", "WATCH"): 0.0,
    ("WATCH", "STOP"): 1.5,
    ("STOP", "ACTION"): 1.5,
    ("STOP", "WATCH"): 0.5,
    ("STOP", "STOP"): 0.0,
}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def score(golden: dict, actual: dict) -> dict:
    expected = {case["id"]: case["expected_decision"] for case in golden["cases"]}
    observed = {item["id"]: item["decision"] for item in actual["results"]}

    missing = sorted(set(expected) - set(observed))
    unexpected = sorted(set(observed) - set(expected))
    invalid = sorted(
        {case_id: decision for case_id, decision in observed.items() if decision not in VALID}.items()
    )

    rows = []
    exact = 0
    total_penalty = 0.0
    for case_id, expected_decision in expected.items():
        actual_decision = observed.get(case_id)
        if actual_decision not in VALID:
            rows.append(
                {
                    "id": case_id,
                    "expected": expected_decision,
                    "actual": actual_decision,
                    "penalty": None,
                }
            )
            continue
        penalty = PENALTY[(expected_decision, actual_decision)]
        total_penalty += penalty
        exact += int(expected_decision == actual_decision)
        rows.append(
            {
                "id": case_id,
                "expected": expected_decision,
                "actual": actual_decision,
                "penalty": penalty,
            }
        )

    count = len(expected)
    return {
        "case_count": count,
        "exact_matches": exact,
        "accuracy": round(exact / count, 4) if count else 0.0,
        "weighted_penalty": round(total_penalty, 2),
        "missing": missing,
        "unexpected": unexpected,
        "invalid": invalid,
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("actual", type=Path, help="JSON file containing model decisions")
    parser.add_argument(
        "--golden",
        type=Path,
        default=Path("tests/fixtures/web3_triage_golden_cases.json"),
    )
    args = parser.parse_args()

    report = score(load_json(args.golden), load_json(args.actual))
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if report["missing"] or report["unexpected"] or report["invalid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
