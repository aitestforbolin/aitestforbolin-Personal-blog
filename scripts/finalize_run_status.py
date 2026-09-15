#!/usr/bin/env python3
"""Create and validate the canonical daily market briefing run status."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STATUS = ROOT / "data" / "run-status.json"
DEFAULT_SNAPSHOT = ROOT / "data" / "daily-market-status.json"
DEFAULT_X_LOG = ROOT / "data" / "x-publish-log.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")
TERMINAL_STATUSES = {"success", "no_new_session", "failed"}
STAGES = {"packet", "briefing", "commit", "x", "done"}
SHA_PATTERN = re.compile(r"[0-9a-f]{40}")
POST_ID_PATTERN = re.compile(r"\d{1,25}")


class RunStatusError(RuntimeError):
    """The requested run status violates the public status contract."""


def load_json(path: Path, default: object | None = None) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        if default is not None:
            return default
        raise RunStatusError(f"Could not read valid JSON from {path}")


def iso_date(value: object, label: str, *, optional: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text and optional:
        return None
    try:
        return dt.date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise RunStatusError(f"{label} must be YYYY-MM-DD") from exc


def parse_datetime(value: str | None) -> dt.datetime:
    if not value:
        return dt.datetime.now(dt.timezone.utc)
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RunStatusError("--now must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise RunStatusError("--now must include a timezone")
    return parsed


def today_shanghai(now: dt.datetime) -> str:
    return now.astimezone(SHANGHAI).date().isoformat()


def snapshot_as_of(path: Path) -> str | None:
    payload = load_json(path, {})
    value = payload.get("asOf") if isinstance(payload, dict) else None
    return iso_date(value, "snapshot asOf", optional=True)


def x_record(path: Path, as_of: str) -> dict[str, Any] | None:
    payload = load_json(path, {})
    if not isinstance(payload, dict):
        return None
    records = payload.get("publishedByAsOf")
    if not isinstance(records, dict):
        return None
    record = records.get(as_of)
    return record if isinstance(record, dict) else None


def build_status(
    *,
    status: str,
    stage: str,
    run_date: str,
    as_of: str | None,
    briefing_commit: str | None,
    x_post_id: str | None,
    x_post_url: str | None,
    reason_code: str | None,
    now: dt.datetime,
) -> dict[str, Any]:
    payload = {
        "schemaVersion": 1,
        "runDate": run_date,
        "asOf": as_of,
        "status": status,
        "stage": stage,
        "briefingCommit": briefing_commit or None,
        "xPostId": x_post_id or None,
        "xPostUrl": x_post_url or None,
        "reasonCode": reason_code or None,
        "updatedAt": now.astimezone(SHANGHAI).isoformat(timespec="seconds"),
    }
    validate_status(payload)
    return payload


def validate_status(payload: object) -> None:
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        raise RunStatusError("run status schemaVersion must be 1")
    iso_date(payload.get("runDate"), "runDate")
    iso_date(payload.get("asOf"), "asOf", optional=True)
    status = payload.get("status")
    stage = payload.get("stage")
    reason = payload.get("reasonCode")
    if status not in TERMINAL_STATUSES:
        raise RunStatusError(f"unsupported status: {status}")
    if stage not in STAGES:
        raise RunStatusError(f"unsupported stage: {stage}")
    if status == "success":
        if stage != "done" or reason is not None:
            raise RunStatusError("success requires stage=done and reasonCode=null")
        if not payload.get("asOf"):
            raise RunStatusError("success requires asOf")
        commit = str(payload.get("briefingCommit") or "")
        post_id = str(payload.get("xPostId") or "")
        post_url = str(payload.get("xPostUrl") or "")
        if not SHA_PATTERN.fullmatch(commit):
            raise RunStatusError("success requires a full 40-character briefingCommit")
        if not POST_ID_PATTERN.fullmatch(post_id) or not post_url.startswith("https://x.com/"):
            raise RunStatusError("success requires a confirmed X Post ID and URL")
    elif status == "no_new_session":
        if stage != "done" or not reason:
            raise RunStatusError("no_new_session requires stage=done and a reasonCode")
        if payload.get("xPostId") or payload.get("xPostUrl"):
            raise RunStatusError("no_new_session cannot contain an X Post")
    elif not reason:
        raise RunStatusError("failed requires a reasonCode")


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def github_output(**values: object) -> None:
    target = os.getenv("GITHUB_OUTPUT")
    if not target:
        return
    with Path(target).open("a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={'' if value is None else value}\n")


def from_x(args: argparse.Namespace, now: dt.datetime) -> dict[str, Any]:
    as_of = snapshot_as_of(args.snapshot)
    commit = str(args.briefing_commit or "").strip() or None
    publish_status = str(args.publish_status or "").strip()
    record = x_record(args.x_log, as_of) if as_of else None

    if args.validate_outcome != "success":
        values = ("failed", "x", "x_validation_failed", None, None)
    elif args.publish_outcome != "success":
        values = ("failed", "x", "x_publish_failed", None, None)
    elif publish_status not in {"published", "skipped_duplicate"}:
        values = ("failed", "x", "x_publish_not_confirmed", None, None)
    elif not record:
        values = ("failed", "x", "x_publish_log_missing", None, None)
    else:
        post_id = str(record.get("postId") or "")
        post_url = str(record.get("url") or "")
        values = ("success", "done", None, post_id, post_url)

    status, stage, reason, post_id, post_url = values
    return build_status(
        status=status,
        stage=stage,
        run_date=today_shanghai(now),
        as_of=as_of,
        briefing_commit=commit,
        x_post_id=post_id,
        x_post_url=post_url,
        reason_code=reason,
        now=now,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--x-log", type=Path, default=DEFAULT_X_LOG)
    parser.add_argument("--now")
    parser.add_argument("--from-x", action="store_true")
    parser.add_argument("--validate-outcome", default="")
    parser.add_argument("--publish-outcome", default="")
    parser.add_argument("--publish-status", default="")
    parser.add_argument("--briefing-commit", default="")
    parser.add_argument("--status", choices=sorted(TERMINAL_STATUSES))
    parser.add_argument("--stage", choices=sorted(STAGES))
    parser.add_argument("--run-date")
    parser.add_argument("--as-of")
    parser.add_argument("--x-post-id")
    parser.add_argument("--x-post-url")
    parser.add_argument("--reason-code")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        now = parse_datetime(args.now)
        if args.from_x:
            payload = from_x(args, now)
        else:
            if not args.status or not args.stage:
                raise RunStatusError("direct mode requires --status and --stage")
            payload = build_status(
                status=args.status,
                stage=args.stage,
                run_date=iso_date(args.run_date, "runDate", optional=True)
                or today_shanghai(now),
                as_of=iso_date(args.as_of, "asOf", optional=True),
                briefing_commit=str(args.briefing_commit or "").strip() or None,
                x_post_id=str(args.x_post_id or "").strip() or None,
                x_post_url=str(args.x_post_url or "").strip() or None,
                reason_code=str(args.reason_code or "").strip() or None,
                now=now,
            )
        atomic_write(args.output, payload)
        github_output(
            status=payload["status"],
            stage=payload["stage"],
            as_of=payload.get("asOf"),
            reason_code=payload.get("reasonCode"),
        )
        print(
            f"Run status finalized: {payload['status']} "
            f"({payload['stage']}, {payload.get('asOf') or 'no asOf'})."
        )
        return 0
    except RunStatusError as exc:
        print(f"ERROR: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
