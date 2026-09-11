#!/usr/bin/env python3
"""Send a best-effort Gmail status notification for the daily market briefing."""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT = ROOT / "data" / "daily-market-status.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", choices=("success", "failure"), required=True)
    parser.add_argument("--as-of", default="")
    parser.add_argument("--post-url", default="")
    parser.add_argument("--post-id", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    return parser.parse_args()


def snapshot_as_of(path: Path) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "unknown"
    value = str(payload.get("asOf") or "").strip() if isinstance(payload, dict) else ""
    return value or "unknown"


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

    as_of = args.as_of.strip() or snapshot_as_of(args.snapshot)
    post_url = args.post_url.strip()
    if not post_url and args.post_id.strip():
        post_url = f"https://x.com/i/web/status/{args.post_id.strip()}"

    message = EmailMessage()
    message["From"] = username
    message["To"] = recipient

    if args.status == "success":
        message["Subject"] = f"✅ 每日市场早报全部成功｜{as_of}"
        lines = [
            f"{as_of} 的每日市场早报工作流已全部完成。",
            "",
            "状态：早报制作成功；数据校验通过；X 发布成功。",
            "现在可以阅读今日早报。",
        ]
        if post_url:
            lines.extend(["", f"查看 X：{post_url}"])
    else:
        message["Subject"] = f"⚠️ 每日市场早报异常｜{as_of}"
        lines = [
            f"{as_of} 的每日市场早报工作流出现失败或异常。",
            "",
            f"异常信息：{args.reason.strip() or '请查看 Workflow 运行详情。'}",
            "",
            "请检查后再将今日早报视为完成。",
        ]
        if post_url:
            lines.extend(["", f"已存在的 X Post：{post_url}"])

    lines.extend(
        [
            "",
            f"查看本次 Workflow：{args.run_url}",
            "",
            "这是一封由每日市场早报 Workflow 自动发送的状态通知。",
        ]
    )
    message.set_content("\n".join(lines))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
        smtp.login(username, app_password)
        smtp.send_message(message)

    print(f"Gmail {args.status} notification sent to {recipient}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
