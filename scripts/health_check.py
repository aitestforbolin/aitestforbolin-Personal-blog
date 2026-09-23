#!/usr/bin/env python3
"""Read-only business outcome check for the briefing, X and Web3 runs."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

SH = ZoneInfo("Asia/Shanghai")
REPO = "aitestforbolin/aitestforbolin-Personal-blog"


def read(root: Path, name: str):
    try:
        return json.loads((root / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def date_of(value):
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(SH).date()
    except (TypeError, ValueError):
        return None


def check(root: Path, now: dt.datetime):
    day = now.astimezone(SH).date()
    stamp = day.isoformat()
    issues = []
    checked = []
    # Tuesday–Saturday, after the 07:00 scheduled briefing and 07:30 watchdog.
    if day.weekday() in (1, 2, 3, 4, 5) and now.astimezone(SH).hour >= 8:
        checked.append("market briefing")
        status = read(root, "data/run-status.json") or {}
        snapshot = read(root, "data/daily-market-status.json") or {}
        if status.get("runDate") != stamp:
            issues.append(("briefing.missing", "No terminal briefing status for today; check the 07:00 task and 07:30 watchdog."))
        elif status.get("status") == "failed":
            issues.append(("briefing.failed", f"{status.get('stage')}: {status.get('reasonCode')}"))
        elif status.get("status") == "success":
            as_of = status.get("asOf")
            archive = read(root, f"data/daily-market-status/archive/{as_of}.json") if as_of else None
            if not as_of or snapshot.get("asOf") != as_of or archive != snapshot:
                issues.append(("briefing.content_mismatch", "Success status, current snapshot and immutable archive disagree."))
            if not status.get("briefingCommit") or not status.get("xPostId"):
                issues.append(("briefing.publication_unconfirmed", "Success status lacks confirmed publication details."))
        elif status.get("status") != "no_new_session":
            issues.append(("briefing.unknown", "Briefing status is invalid or unfinished."))

    for kind, trigger, receipt, current, archive_dir, day_field in (
        ("x", "data/x-intelligence-trigger.json", "data/x-intelligence-refresh-status.json", "data/x-intelligence.json", "data/x-intelligence/archive", "reportDate"),
        ("web3", "data/crypto-fundraising-trigger.json", "data/crypto-fundraising-refresh-status.json", "data/web3-daily-triage.json", "data/web3-daily-triage/archive", "runDate"),
    ):
        t = read(root, trigger) or {}
        request = t.get("requestId")
        trigger_time = t.get("requestedAt") or t.get("createdAt") or t.get("scheduledAt")
        requested_at = date_of(trigger_time)
        # The trigger itself, not an inferred 13:00 schedule, starts the obligation.
        # A unique request ID with no date-bearing timestamp is checked via its ID.
        today = requested_at == day or (requested_at is None and isinstance(request, str) and stamp.replace("-", "") in request)
        if not today:
            continue
        try:
            trigger_dt = dt.datetime.fromisoformat(str(trigger_time).replace("Z", "+00:00"))
            if now - trigger_dt < dt.timedelta(minutes=75):
                continue
        except (TypeError, ValueError):
            pass
        checked.append(kind)
        r = read(root, receipt) or {}
        c = read(root, current) or {}
        archived = read(root, f"{archive_dir}/{stamp}.json")
        if r.get("requestId") != request:
            issues.append((f"{kind}.receipt_missing", "Today's trigger has no matching collector receipt."))
            continue
        stages = r.get("stages") or {}
        collection = (stages.get("collection") or {}).get("status")
        validation = (stages.get("validation") or {}).get("status")
        publication = (stages.get("publication") or {}).get("status")
        if collection not in ("success", "unchanged", "empty_valid") or validation != "success":
            issues.append((f"{kind}.collection", f"collection={collection}; validation={validation}"))
            continue
        if publication not in ("success", "unchanged"):
            issues.append((f"{kind}.publication_missing", f"Collector completed but publication={publication}."))
            continue
        if c.get(day_field) != stamp or archived is None or archived != c:
            issues.append((f"{kind}.archive_mismatch", "Published date/current/immutable archive disagree."))
            continue
        lineage = c.get("executionLineage") or {}
        if lineage.get("requestId") != request or lineage.get("triggerSha") != (r.get("lineage") or {}).get("triggerSha"):
            issues.append((f"{kind}.lineage", "Published content does not match collector requestId and trigger SHA."))
        payload_pub = (c.get("executionStatus") or {}).get("publication")
        payload_pub = payload_pub.get("status") if isinstance(payload_pub, dict) else payload_pub
        if payload_pub not in ("success", "unchanged"):
            issues.append((f"{kind}.display_status", f"Receipt publication={publication}, but displayed payload says {payload_pub}."))
        notification = (stages.get("notification") or {}).get("status")
        if notification == "failed":
            issues.append((f"{kind}.notification", "Publication succeeded but its notification failed."))
    return checked, issues


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument("--now", default=None)
    p.add_argument("--notify", action="store_true")
    args = p.parse_args()
    now = dt.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else dt.datetime.now(dt.timezone.utc)
    checked, issues = check(args.root, now)
    lines = [f"## Business outcome check · {now.astimezone(SH):%Y-%m-%d %H:%M} CST", "", f"Checked: {', '.join(checked) or 'no due runs'}", ""]
    if issues:
        lines += ["### Requires attention", ""]
        for code, detail in issues:
            lines.append(f"- **{code}**: {detail}")
        lines += ["", f"Evidence: [Actions runs](https://github.com/{REPO}/actions), `data/*-refresh-status.json`, `data/run-status.json`, current files and daily archives.", "Review the matching request and workflow logs before changing any publication or archive."]
    else:
        lines.append("No contract mismatch found. This does not verify the editorial accuracy of the published content.")
    summary = "\n".join(lines) + "\n"
    print(summary)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as out:
            out.write(summary)
    if issues and args.notify:
        sender = os.getenv("ICLOUD_SMTP_USER")
        password = os.getenv("ICLOUD_APP_PASSWORD")
        recipient = os.getenv("EMAIL_NOTIFY_TO")
        if sender and password and recipient:
            mail = EmailMessage()
            mail["From"] = sender
            mail["To"] = recipient
            mail["Subject"] = f"网站工作流异常｜{now.astimezone(SH):%Y-%m-%d}"
            mail.set_content(summary + "\n" + os.getenv("GITHUB_RUN_URL", ""))
            try:
                with smtplib.SMTP("smtp.mail.me.com", 587, timeout=30) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    smtp.login(sender, password)
                    smtp.send_message(mail)
                print("Failure notification sent.")
            except (OSError, smtplib.SMTPException) as exc:
                print(f"Failure notification unavailable: {type(exc).__name__}")
        else:
            print("Failure notification unavailable: mail secrets are not configured.")
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
