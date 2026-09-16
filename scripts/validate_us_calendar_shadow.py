#!/usr/bin/env python3
"""Compare the temporary legacy calendar against the FF production calendar.

This emits warnings only. It intentionally cannot fail the public calendar
because the purpose of the shadow period is to measure the old pipeline rather
than keep it in the critical path.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path

CORE = {"美国CPI / 核心CPI", "美国PPI", "美国非农 / 失业率 / 平均时薪", "美国PCE / 核心PCE", "美国GDP", "美国零售销售", "美国ISM制造业PMI", "美国ISM服务业PMI", "美国JOLTS职位空缺"}

def read(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8")); return value if isinstance(value, list) else []
    except (OSError, ValueError): return []

def key(event): return event.get("title_cn"), event.get("date_et") or event.get("date")

def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--production", required=True); parser.add_argument("--legacy", required=True); args = parser.parse_args()
    production = {key(event): event for event in read(args.production) if event.get("title_cn") in CORE}
    legacy = {key(event): event for event in read(args.legacy) if event.get("title_cn") in CORE}
    missing = sorted(title for (title, day) in production if (title, day) not in legacy)
    disagreement = sorted(title for item, event in production.items() if item in legacy and event.get("time_et") != legacy[item].get("time_et") for title, _ in [item])
    if missing: print("::warning::legacy shadow missing FF core events: " + ", ".join(missing))
    if disagreement: print("::warning::legacy shadow time disagreement: " + ", ".join(disagreement))
    if not missing and not disagreement: print("legacy shadow agrees with current FF core events")

if __name__ == "__main__": main()
