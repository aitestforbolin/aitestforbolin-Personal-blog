#!/usr/bin/env python3
"""Send a best-effort Gmail notification derived only from run-status.json."""

from __future__ import annotations

import argparse
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "data" / "run-status.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--status-file", type=Path, default=DEFAULT_STATUS)
    return parser.parse_args()


def load_status(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read run status from {path}") from exc
    if not isinstance(payload, dict) or payload.get("status") not in {
        "success", "no_new_session", "failed"
    }:
        raise RuntimeError("run-status.json has an unsupported status")
    return payload


def build_message(payload: dict, run_url: str, sender: str, recipient: str) -> EmailMessage:
    status = payload["status"]
    as_of = str(payload.get("asOf") or "unknown")
    run_date = str(payload.get("runDate") or "unknown")
    post_url = str(payload.get("xPostUrl") or "").strip()
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient

    if status == "success":
        message["Subject"] = f"✅ 每日市场早报全部成功｜{as_of}"
        lines = [
            f"{as_of} 的每日市场早报已完成。",
            "",
            "状态：早报提交成功；X 发布成功。",
        ]
        if post_url:
            lines.extend(["", f"查看 X：{post_url}"])
    elif status == "no_new_session":
        message["Subject"] = f"ℹ️ 每日市场早报无需更新｜{run_date}"
        lines = [
            f"{run_date} 没有需要发布的新交易日早报。",
            "",
            f"原因：{payload.get('reasonCode') or 'no_new_session'}",
            f"当前最新交易日：{as_of}",
        ]
    else:
        message["Subject"] = f"⚠️ 每日市场早报异常｜{run_date}"
        lines = [
            f"{run_date} 的每日市场早报自动化未完成。",
            "",
            f"失败阶段：{payload.get('stage') or 'unknown'}",
            f"原因代码：{payload.get('reasonCode') or 'unknown'}",
        ]
        if post_url:
            lines.extend(["", f"已确认的 X Post：{post_url}"])

    lines.extend(
        [
            "",
            f"查看本次 Workflow：{run_url}",
            "",
            "本邮件内容仅依据 data/run-status.json 生成。",
        ]
    )
    message.set_content("\n".join(lines))
    return message


def main() -> int:
    args = parse_args()
    username = os.getenv("GMAIL_SMTP_USER", "").strip()
    app_password = os.getenv("GMAIL_APP_PASSWORD", "").strip().replace(" ", "")
    recipient = os.getenv("GMAIL_NOTIFY_TO", "").strip() or username

    if not username or not app_password:
        print(
            "ERROR: Gmail notification unavailable; configure GMAIL_SMTP_USER and "
            "GMAIL_APP_PASSWORD repository secrets."
        )
        return 2

    payload = load_status(args.status_file)
    message = build_message(payload, args.run_url, username, recipient)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context, timeout=30) as smtp:
        smtp.login(username, app_password)
        smtp.send_message(message)

    print(f"Gmail {payload['status']} notification sent to {recipient}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
