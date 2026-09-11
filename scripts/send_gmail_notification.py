#!/usr/bin/env python3
"""Send a best-effort Gmail notification after the daily briefing is published."""

from __future__ import annotations

import argparse
import os
import smtplib
import ssl
from email.message import EmailMessage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--post-url", required=True)
    parser.add_argument("--run-url", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    username = os.getenv("GMAIL_SMTP_USER", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    recipient = os.getenv("GMAIL_NOTIFY_TO", "").strip() or username

    if not username or not app_password:
        print(
            "Gmail notification skipped: configure GMAIL_SMTP_USER and "
            "GMAIL_APP_PASSWORD repository secrets."
        )
        return 0

    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient
    message["Subject"] = f"每日市场早报已发布｜{args.as_of}"
    message.set_content(
        "\n".join(
            [
                f"{args.as_of} 的每日市场早报已完成制作，并已成功发布到 X。",
                "",
                f"查看 X：{args.post_url}",
                f"查看本次 Workflow：{args.run_url}",
                "",
                "这是一封由每日市场早报 Workflow 自动发送的通知。",
            ]
        )
    )

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
        smtp.login(username, app_password)
        smtp.send_message(message)

    print(f"Gmail notification sent to {recipient}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
