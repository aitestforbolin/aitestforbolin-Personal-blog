#!/usr/bin/env python3
import argparse, json, os, re, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")
CONFIG = {
    "x": {
        "request": Path("data/x-intelligence-publish-request.json"),
        "current": Path("data/x-intelligence.json"),
        "archive_dir": Path("data/x-intelligence/archive"),
        "receipt": Path("data/x-intelligence-refresh-status.json"),
        "receipt_dir": Path("data/x-intelligence/run-receipts"),
        "date_field": "reportDate",
        "input": Path("data/x-intelligence-input.json"),
    },
    "web3": {
        "request": Path("data/web3-daily-triage-publish-request.json"),
        "current": Path("data/web3-daily-triage.json"),
        "archive_dir": Path("data/web3-daily-triage/archive"),
        "receipt": Path("data/crypto-fundraising-refresh-status.json"),
        "receipt_dir": Path("data/web3-daily-triage/run-receipts"),
        "date_field": "runDate",
        "input": Path("data/crypto-fundraising-history.json"),
    },
}

def fail(msg):
    print(msg, file=sys.stderr); raise SystemExit(2)

def load(path):
    try: return json.loads(path.read_text())
    except Exception as e: fail(f"cannot read {path}: {e}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--kind", choices=CONFIG); args=ap.parse_args()
    c=CONFIG[args.kind]; req=load(c["request"]); receipt=load(c["receipt"]); payload=req.get("payload")
    if not isinstance(payload, dict): fail("request payload missing")
    request_id=req.get("requestId"); trigger_sha=req.get("triggerSha")
    if not request_id or not SAFE_ID.fullmatch(request_id): fail("invalid requestId")
    if receipt.get("requestId") != request_id: fail("receipt requestId mismatch")
    lineage=receipt.get("lineage") or {}; stages=receipt.get("stages") or {}
    if lineage.get("triggerSha") != trigger_sha or not trigger_sha: fail("receipt triggerSha mismatch")
    if (stages.get("validation") or {}).get("status") != "success": fail("validation is not success")
    collection=(stages.get("collection") or {}).get("status")
    allowed={"x":{"success","empty_valid"},"web3":{"success","unchanged"}}[args.kind]
    if collection not in allowed: fail(f"collection status not publishable: {collection}")
    p_lineage=payload.get("executionLineage") or {}
    if p_lineage.get("requestId") != request_id or p_lineage.get("triggerSha") != trigger_sha: fail("payload lineage mismatch")
    date=payload.get(c["date_field"])
    if not isinstance(date,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",date): fail("invalid publication date")
    if req.get("publicationDate") != date: fail("request publicationDate mismatch")
    archive=c["archive_dir"] / f"{date}.json"
    if archive.exists(): fail(f"immutable archive already exists: {archive}")
    published_at=req.get("publishedAt")
    if not published_at: fail("publishedAt missing")
    payload["executionLineage"]["publishedAt"]=published_at
    if "publishedAt" in payload: payload["publishedAt"]=published_at
    pub=(payload.get("executionStatus") or {}).get("publication")
    if isinstance(pub,dict): pub["status"]="success"
    text=json.dumps(payload,ensure_ascii=False,indent=2)+"\n"
    c["current"].write_text(text); archive.parent.mkdir(parents=True,exist_ok=True); archive.write_text(text)
    receipt.setdefault("timestamps",{})["publishedAt"]=published_at
    receipt.setdefault("stages",{}).setdefault("publication",{})["status"]="success"
    receipt["stages"]["publication"]["commitSha"]="PENDING_SELF_COMMIT"
    receipt_archive=c["receipt_dir"] / f"{date}--{request_id}.json"
    receipt_archive.parent.mkdir(parents=True,exist_ok=True)
    rtext=json.dumps(receipt,ensure_ascii=False,indent=2)+"\n"; c["receipt"].write_text(rtext); receipt_archive.write_text(rtext)
    paths=[str(c["current"]),str(archive),str(c["receipt"]),str(receipt_archive)]
    subprocess.run(["git","add","--",*paths],check=True)
    subprocess.run(["git","commit","-m",f"Publish {args.kind} intelligence for {date}"],check=True)
    sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    print(f"publication_commit={sha}")
    print(f"current={c['current']}")
    print(f"archive={archive}")
if __name__=="__main__": main()
