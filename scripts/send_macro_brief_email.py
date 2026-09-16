#!/usr/bin/env python3
"""Send a generated Macro Brief through the existing iCloud SMTP channel."""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BRIEF = ROOT / "data" / "macro-brief.json"
DEFAULT_PAGE = "https://aitestforbolin.github.io/aitestforbolin-Personal-blog/macro-brief/"


def build_message(payload: dict, sender: str, recipient: str, page_url: str, run_url: str) -> EmailMessage:
    event = payload.get("event") or {}
    scheduled_label = str(event.get("scheduledAtLabel") or "")
    scheduled_time = scheduled_label.split(" ", 1)[1][:5] if " " in scheduled_label else "待定"
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = f"📊 Macro Brief｜{event.get('title') or '美国宏观事件'}｜{scheduled_time}"
    message.set_content("\n".join([str(payload.get("copyText") or "Macro Brief暂不可用"), "", f"网页：{page_url}", f"Workflow：{run_url}"]))
    return message


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", type=Path, default=DEFAULT_BRIEF)
    parser.add_argument("--page-url", default=DEFAULT_PAGE)
    parser.add_argument("--run-url", required=True)
    args = parser.parse_args()
    payload = json.loads(args.brief.read_text(encoding="utf-8"))
    username = os.getenv("ICLOUD_SMTP_USER", "").strip()
    password = os.getenv("ICLOUD_APP_PASSWORD", "").strip()
    recipient = os.getenv("EMAIL_NOTIFY_TO", "").strip()
    if not username or not password or not recipient:
        print("ERROR: configure ICLOUD_SMTP_USER, ICLOUD_APP_PASSWORD and EMAIL_NOTIFY_TO")
        return 2
    message = build_message(payload, username, recipient, args.page_url, args.run_url)
    try:
        with smtplib.SMTP("smtp.mail.me.com", 587, timeout=30) as smtp:
            smtp.ehlo(); smtp.starttls(context=ssl.create_default_context()); smtp.ehlo()
            smtp.login(username, password); smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        print(f"ERROR: Macro Brief email failed ({type(exc).__name__})")
        return 3
    print("Macro Brief email sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
