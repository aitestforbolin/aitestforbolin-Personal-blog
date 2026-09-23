#!/usr/bin/env python3
import argparse, json, re, subprocess, sys
from pathlib import Path
SAFE_ID=re.compile(r"^[A-Za-z0-9._-]+$")
CONFIG={
 "x":{"request":Path("data/x-intelligence-publish-request.json"),"current":Path("data/x-intelligence.json"),"archive_dir":Path("data/x-intelligence/archive"),"receipt":Path("data/x-intelligence-refresh-status.json"),"receipt_dir":Path("data/x-intelligence/run-receipts"),"date_field":"reportDate"},
 "web3":{"request":Path("data/web3-daily-triage-publish-request.json"),"current":Path("data/web3-daily-triage.json"),"archive_dir":Path("data/web3-daily-triage/archive"),"receipt":Path("data/crypto-fundraising-refresh-status.json"),"receipt_dir":Path("data/web3-daily-triage/run-receipts"),"date_field":"runDate"}}
def fail(m): print(m,file=sys.stderr); raise SystemExit(2)
def load(p):
 try:return json.loads(p.read_text())
 except Exception as e:fail(f"cannot read {p}: {e}")
def set_payload_publication_status(payload,status):
 execution_status=payload.get("executionStatus")
 if not isinstance(execution_status,dict):return
 publication=execution_status.get("publication")
 if isinstance(publication,dict):publication["status"]=status
 else:execution_status["publication"]=status
def normalize_web3_status(payload,collection):
 counts=payload.get("counts") or {}
 if not isinstance(counts,dict) or type(counts.get("new")) is not int or counts["new"]<0:fail("invalid Web3 candidate count")
 payload["status"]="success" if counts["new"]>0 or collection=="success" else "unchanged"
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--kind",choices=CONFIG);a=ap.parse_args();c=CONFIG[a.kind]
 req=load(c["request"]);receipt=load(c["receipt"]);payload=req.get("payload")
 if not isinstance(payload,dict):fail("request payload missing")
 rid=req.get("requestId");tsha=req.get("triggerSha")
 if not rid or not SAFE_ID.fullmatch(rid):fail("invalid requestId")
 if receipt.get("requestId")!=rid:fail("receipt requestId mismatch")
 lineage=receipt.get("lineage") or {};stages=receipt.get("stages") or {}
 if lineage.get("triggerSha")!=tsha or not tsha:fail("receipt triggerSha mismatch")
 if (stages.get("validation") or {}).get("status")!="success":fail("validation is not success")
 collection=(stages.get("collection") or {}).get("status");allowed={"x":{"success","empty_valid"},"web3":{"success","unchanged"}}[a.kind]
 if collection not in allowed:fail(f"collection status not publishable: {collection}")
 pl=payload.get("executionLineage") or {}
 if pl.get("requestId")!=rid or pl.get("triggerSha")!=tsha:fail("payload lineage mismatch")
 date=payload.get(c["date_field"])
 if not isinstance(date,str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}",date):fail("invalid publication date")
 if req.get("publicationDate")!=date:fail("request publicationDate mismatch")
 archive=c["archive_dir"]/f"{date}.json"
 if archive.exists():fail(f"immutable archive already exists: {archive}")
 published=req.get("publishedAt")
 if not published:fail("publishedAt missing")
 payload["executionLineage"]["publishedAt"]=published
 if "publishedAt" in payload:payload["publishedAt"]=published
 set_payload_publication_status(payload,"success")
 if a.kind=="web3":normalize_web3_status(payload,collection)
 text=json.dumps(payload,ensure_ascii=False,indent=2)+"\n";c["current"].write_text(text);archive.parent.mkdir(parents=True,exist_ok=True);archive.write_text(text)
 subprocess.run(["git","add","--",str(c["current"]),str(archive)],check=True);subprocess.run(["git","commit","-m",f"Publish {a.kind} intelligence for {date}"],check=True)
 sha=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
 receipt.setdefault("timestamps",{})["publishedAt"]=published;receipt.setdefault("stages",{}).setdefault("publication",{}).update({"status":"success","commitSha":sha})
 ra=c["receipt_dir"]/f"{date}--{rid}.json";ra.parent.mkdir(parents=True,exist_ok=True);rt=json.dumps(receipt,ensure_ascii=False,indent=2)+"\n";c["receipt"].write_text(rt);ra.write_text(rt)
 subprocess.run(["git","add","--",str(c["receipt"]),str(ra)],check=True);subprocess.run(["git","commit","-m",f"Finalize {a.kind} publication receipt for {date}"],check=True)
 print(f"publication_commit={sha}");print(f"current={c['current']}");print(f"archive={archive}")
if __name__=="__main__":main()
