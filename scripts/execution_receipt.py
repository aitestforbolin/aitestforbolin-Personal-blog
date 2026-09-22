#!/usr/bin/env python3
"""Shared execution-lineage and run-receipt helpers for intelligence jobs."""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOP_LEVEL_RESULTS = {
    "in_progress",
    "success",
    "degraded",
    "unchanged",
    "failed",
    "not_run",
}
STAGE_RESULTS = {
    "success",
    "degraded",
    "unchanged",
    "empty_valid",
    "stale_source",
    "fetch_failed",
    "failed",
    "not_run",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_trigger(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"Could not read trigger JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Trigger JSON must be an object: {path}")
    return payload


def trigger_context(trigger_path: Path, automation: str) -> dict[str, Any]:
    trigger = load_trigger(trigger_path)
    event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
    run_id = os.environ.get("GITHUB_RUN_ID")
    request_id = str(trigger.get("requestId") or "").strip()
    if event_name != "push":
        request_id = f"manual-{run_id}" if run_id else f"local-{automation}-{utc_now()}"
    if not request_id:
        raise RuntimeError(f"Missing requestId in {trigger_path}")

    scheduled_at = trigger.get("scheduledAt")
    if not isinstance(scheduled_at, str) or not scheduled_at.strip():
        scheduled_at = None

    legacy_requested_at = trigger.get("requestedAt")
    if not isinstance(legacy_requested_at, str) or not legacy_requested_at.strip():
        legacy_requested_at = None

    return {
        "requestId": request_id,
        "runId": f"{automation}:{request_id}",
        "triggerSha": os.environ.get("GITHUB_SHA") or None,
        "triggerType": event_name,
        "scheduledAt": scheduled_at,
        "legacyRequestedAt": legacy_requested_at,
        "githubRunId": int(run_id) if run_id and run_id.isdigit() else None,
        "githubRunAttempt": int(os.environ.get("GITHUB_RUN_ATTEMPT", "0")) or None,
    }


def new_receipt(automation: str, context: dict[str, Any], started_at: str) -> dict[str, Any]:
    return {
        "schemaVersion": 2,
        "automation": automation,
        "runId": context["runId"],
        "requestId": context["requestId"],
        "result": "in_progress",
        "lineage": {
            "triggerType": context.get("triggerType"),
            "triggerSha": context.get("triggerSha"),
            "githubRunId": context.get("githubRunId"),
            "githubRunAttempt": context.get("githubRunAttempt"),
        },
        "timestamps": {
            "scheduledAt": context.get("scheduledAt"),
            "startedAt": started_at,
            "sourceCheckedAt": None,
            "sourceUpdatedAt": None,
            "completedAt": None,
            "publishedAt": None,
        },
        # Retained only to explain old trigger files. It is never used as the
        # authoritative freshness boundary.
        "legacyRequestedAt": context.get("legacyRequestedAt"),
        "stages": {
            "collection": {"status": "not_run"},
            "validation": {"status": "not_run"},
            "publication": {"status": "not_run"},
            "notification": {"status": "not_run"},
        },
    }


def set_collection(
    receipt: dict[str, Any],
    status: str,
    *,
    source_checked_at: str | None,
    source_updated_at: str | None,
    completed_at: str,
    details: dict[str, Any] | None = None,
) -> None:
    if status not in STAGE_RESULTS:
        raise ValueError(f"Unsupported collection status: {status}")
    receipt["timestamps"].update(
        {
            "sourceCheckedAt": source_checked_at,
            "sourceUpdatedAt": source_updated_at,
            "completedAt": completed_at,
        }
    )
    stage: dict[str, Any] = {"status": status, "completedAt": completed_at}
    if details:
        stage["details"] = details
    receipt["stages"]["collection"] = stage
    if status in {"fetch_failed", "failed"}:
        receipt["result"] = "failed"
    elif status == "stale_source":
        receipt["result"] = "degraded"
    elif status == "unchanged":
        receipt["result"] = "unchanged"
    else:
        receipt["result"] = "in_progress"


def set_validation(
    receipt: dict[str, Any], status: str, *, completed_at: str, reason: str | None = None
) -> None:
    if status not in STAGE_RESULTS:
        raise ValueError(f"Unsupported validation status: {status}")
    stage: dict[str, Any] = {"status": status, "completedAt": completed_at}
    if reason:
        stage["reason"] = reason
    receipt["stages"]["validation"] = stage
    if status in {"failed", "fetch_failed"}:
        receipt["result"] = "failed"


def lineage_for_payload(receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": receipt["schemaVersion"],
        "runId": receipt["runId"],
        "requestId": receipt["requestId"],
        "triggerSha": receipt["lineage"].get("triggerSha"),
        "githubRunId": receipt["lineage"].get("githubRunId"),
        **receipt["timestamps"],
    }


def validate_receipt(receipt: dict[str, Any]) -> None:
    if receipt.get("schemaVersion") != 2:
        raise ValueError("receipt.schemaVersion must be 2")
    if not receipt.get("runId") or not receipt.get("requestId"):
        raise ValueError("receipt must contain runId and requestId")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", str(receipt["requestId"])):
        raise ValueError("receipt.requestId contains unsupported characters")
    if receipt.get("result") not in TOP_LEVEL_RESULTS:
        raise ValueError("receipt has an unsupported top-level result")
    timestamps = receipt.get("timestamps")
    if not isinstance(timestamps, dict):
        raise ValueError("receipt.timestamps must be an object")
    for field in (
        "scheduledAt",
        "startedAt",
        "sourceCheckedAt",
        "sourceUpdatedAt",
        "completedAt",
        "publishedAt",
    ):
        if field not in timestamps:
            raise ValueError(f"receipt.timestamps.{field} is missing")
        value = timestamps[field]
        if value is not None:
            if not isinstance(value, str):
                raise ValueError(f"receipt.timestamps.{field} must be an ISO string or null")
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError(f"receipt.timestamps.{field} is not a valid ISO timestamp") from exc
    for required_timestamp in ("startedAt", "completedAt"):
        if not timestamps.get(required_timestamp):
            raise ValueError(f"receipt.timestamps.{required_timestamp} is required")
    lineage = receipt.get("lineage")
    if not isinstance(lineage, dict):
        raise ValueError("receipt.lineage must be an object")
    if lineage.get("triggerType") in {"push", "workflow_dispatch"}:
        trigger_sha = lineage.get("triggerSha")
        if not isinstance(trigger_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", trigger_sha):
            raise ValueError("receipt.lineage.triggerSha must be a 40-character commit SHA")
    stages = receipt.get("stages")
    if not isinstance(stages, dict):
        raise ValueError("receipt.stages must be an object")
    for stage_name in ("collection", "validation", "publication", "notification"):
        stage = stages.get(stage_name)
        if not isinstance(stage, dict) or stage.get("status") not in STAGE_RESULTS:
            raise ValueError(f"receipt.stages.{stage_name} is invalid")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(rendered)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)
