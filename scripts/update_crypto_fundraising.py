#!/usr/bin/env python3
"""Refresh the five displayed Crypto-Fundraising projects and retain observed event history."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SITE_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = SITE_ROOT / "data" / "crypto-fundraising.json"
HISTORY_OUTPUT = SITE_ROOT / "data" / "crypto-fundraising-history.json"
BRIDGE_URL = "https://crypto-fundraising-bridge.laibocszd.chatgpt.site/api/crypto-fundraising"
FETCH_TIMEOUT = 30
FETCH_RETRIES = 2
PROJECT_LIMIT = 5
HISTORY_LIMIT = 1000
SOURCE_HOST = "crypto-fundraising.info"


class BridgeDataError(RuntimeError):
    """The bridge response or local persisted data violates the expected contract."""


def canonical_detail_url(value: object) -> str:
    if not isinstance(value, str):
        raise BridgeDataError("Project detail_url must be a string")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in {SOURCE_HOST, f"www.{SOURCE_HOST}"}:
        raise BridgeDataError(f"Unexpected project detail host: {value!r}")
    if not parsed.path.startswith("/projects/"):
        raise BridgeDataError(f"Unexpected project detail path: {value!r}")
    return f"https://{SOURCE_HOST}{parsed.path.rstrip('/')}/"


def stable_project_id(detail_url: str) -> str:
    slug = urlparse(detail_url).path.rstrip("/").rsplit("/", 1)[-1]
    if not slug or not all(char.islower() or char.isdigit() or char == "-" for char in slug):
        raise BridgeDataError(f"Unexpected project slug: {slug!r}")
    return f"crypto-fundraising-{slug}"


def normalized_round_slug(round_name: object) -> str:
    if not isinstance(round_name, str) or not round_name.strip():
        return "round-unknown"
    slug = re.sub(r"[^a-z0-9]+", "-", round_name.strip().lower()).strip("-")
    return slug or "round-unknown"


def stable_event_id(project: dict[str, object]) -> str:
    """Identify a financing event independently from feed freshness.

    Project detail URLs are stable across appearances in the homepage feed. The
    announced month + round allows a later financing round for the same project
    to become a new history event instead of overwriting the older one.
    """
    project_id = str(project.get("id") or "")
    announced_month = str(project.get("announced_month") or "")
    if not project_id or not announced_month:
        raise BridgeDataError("Cannot build funding event id without project id and announced_month")
    return f"{project_id}--{announced_month}--{normalized_round_slug(project.get('round'))}"


def validate_bridge_payload(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict):
        raise BridgeDataError("Bridge response must be a JSON object")
    if payload.get("source") != "Crypto-Fundraising":
        raise BridgeDataError("Bridge response has an unexpected source")
    if payload.get("selection") != "homepage_recent_fundraising_events":
        raise BridgeDataError("Bridge response has an unexpected selection")
    projects = payload.get("projects")
    if not isinstance(projects, list) or len(projects) != PROJECT_LIMIT:
        raise BridgeDataError("Bridge response must contain exactly five projects")

    normalized: list[dict[str, object]] = []
    urls: set[str] = set()
    for rank, item in enumerate(projects, start=1):
        if not isinstance(item, dict):
            raise BridgeDataError("Bridge project must be an object")
        name = item.get("name")
        round_name = item.get("round")
        announced_month = item.get("announced_month")
        amount_usd = item.get("amount_usd")
        detail_url = canonical_detail_url(item.get("detail_url"))
        if item.get("source_rank") != rank or not isinstance(name, str) or not name.strip():
            raise BridgeDataError(f"Invalid project at rank {rank}")
        if round_name is not None and (not isinstance(round_name, str) or not round_name.strip()):
            raise BridgeDataError(f"Invalid round at rank {rank}")
        if not isinstance(announced_month, str) or len(announced_month) != 7 or announced_month[4] != "-":
            raise BridgeDataError(f"Invalid announced_month at rank {rank}")
        if amount_usd is not None and (
            isinstance(amount_usd, bool)
            or not isinstance(amount_usd, (int, float))
            or amount_usd < 0
        ):
            raise BridgeDataError(f"Invalid amount_usd at rank {rank}")
        if detail_url in urls:
            raise BridgeDataError("Bridge projects contain duplicate detail URLs")
        urls.add(detail_url)
        normalized.append(
            {
                "id": stable_project_id(detail_url),
                "source_rank": rank,
                "name": name.strip(),
                "round": round_name.strip() if isinstance(round_name, str) else None,
                "announced_month": announced_month,
                "amount_usd": amount_usd,
                "detail_url": detail_url,
            }
        )
    return normalized


def fetch_bridge_payload() -> dict[str, object]:
    request = Request(
        BRIDGE_URL,
        headers={"Accept": "application/json", "User-Agent": "personal-site-crypto-fundraising/3.0"},
    )
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urlopen(request, timeout=FETCH_TIMEOUT) as response:
                if response.status != 200:
                    raise BridgeDataError(f"Bridge returned HTTP {response.status}")
                payload = json.loads(response.read().decode("utf-8"))
            validate_bridge_payload(payload)
            return payload
        except (
            HTTPError,
            URLError,
            TimeoutError,
            UnicodeDecodeError,
            json.JSONDecodeError,
            BridgeDataError,
        ) as error:
            last_error = error
            if attempt < FETCH_RETRIES:
                time.sleep(attempt * 5)
    raise BridgeDataError(
        f"Could not fetch a valid bridge payload after {FETCH_RETRIES} attempts"
    ) from last_error


def load_json_object(path: Path, *, allow_missing: bool = True) -> dict[str, object] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        if allow_missing:
            return None
        raise
    except json.JSONDecodeError as exc:
        raise BridgeDataError(f"Persisted JSON is invalid: {path}") from exc
    except OSError as exc:
        raise BridgeDataError(f"Could not read persisted JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise BridgeDataError(f"Persisted payload must be an object: {path}")
    return payload


def load_previous_payload() -> dict[str, object] | None:
    return load_json_object(OUTPUT)


def load_history_payload() -> dict[str, object] | None:
    payload = load_json_object(HISTORY_OUTPUT)
    if payload is None:
        return None
    events = payload.get("events")
    if not isinstance(events, list) or any(not isinstance(event, dict) for event in events):
        raise BridgeDataError("Persisted fundraising history has an invalid events list")
    return payload


def build_payload(
    bridge_payload: object, previous_payload: dict[str, object] | None
) -> dict[str, object]:
    projects = validate_bridge_payload(bridge_payload)
    previous_urls = {
        str(project.get("detail_url", ""))
        for project in (previous_payload or {}).get("projects", [])
        if isinstance(project, dict)
    }
    for project in projects:
        project["is_new"] = project["detail_url"] not in previous_urls
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Crypto-Fundraising",
        "source_url": "https://crypto-fundraising.info/",
        "selection": "homepage_recent_fundraising_events",
        "projects": projects,
    }


def feed_projects(payload: dict[str, object] | None) -> list[dict[str, object]]:
    if payload is None:
        return []
    projects = payload.get("projects")
    if not isinstance(projects, list):
        return []
    return [project for project in projects if isinstance(project, dict)]


def history_event_from_project(project: dict[str, object], first_seen_at: str) -> dict[str, object]:
    return {
        "event_id": stable_event_id(project),
        "project_id": project.get("id"),
        "name": project.get("name"),
        "round": project.get("round"),
        "announced_month": project.get("announced_month"),
        "amount_usd": project.get("amount_usd"),
        "detail_url": project.get("detail_url"),
        "first_seen_at": first_seen_at,
        "first_seen_source_rank": project.get("source_rank"),
    }


def build_history_payload(
    current_payload: dict[str, object],
    previous_history: dict[str, object] | None,
    previous_feed: dict[str, object] | None = None,
) -> dict[str, object]:
    events_by_id: dict[str, dict[str, object]] = {}

    for event in (previous_history or {}).get("events", []):
        if not isinstance(event, dict):
            continue
        event_id = event.get("event_id")
        if isinstance(event_id, str) and event_id:
            events_by_id[event_id] = dict(event)

    def ingest(payload: dict[str, object] | None, fallback_seen_at: str) -> None:
        if payload is None:
            return
        seen_at = payload.get("updated_at")
        if not isinstance(seen_at, str) or not seen_at:
            seen_at = fallback_seen_at
        for project in feed_projects(payload):
            clean_project = {key: value for key, value in project.items() if key != "is_new"}
            event_id = stable_event_id(clean_project)
            if event_id in events_by_id:
                # Keep the original first-seen timestamp while refreshing corrected
                # source metadata for the same financing event.
                original = events_by_id[event_id]
                refreshed = history_event_from_project(
                    clean_project, str(original.get("first_seen_at") or seen_at)
                )
                refreshed["first_seen_source_rank"] = original.get(
                    "first_seen_source_rank", refreshed["first_seen_source_rank"]
                )
                events_by_id[event_id] = refreshed
            else:
                events_by_id[event_id] = history_event_from_project(clean_project, seen_at)

    current_seen_at = str(current_payload.get("updated_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"))
    ingest(previous_feed, current_seen_at)
    ingest(current_payload, current_seen_at)

    events = sorted(
        events_by_id.values(),
        key=lambda event: (str(event.get("first_seen_at") or ""), str(event.get("event_id") or "")),
        reverse=True,
    )[:HISTORY_LIMIT]

    candidate = {
        "updated_at": current_seen_at,
        "source": "Crypto-Fundraising",
        "source_url": "https://crypto-fundraising.info/",
        "selection": "observed_homepage_fundraising_events_history",
        "coverage": "observed snapshots of the five-item homepage feed; not a complete source-wide archive",
        "events": events,
    }

    if previous_history is not None and history_events_equal(candidate, previous_history):
        return previous_history
    return candidate


def project_data_changed(
    payload: dict[str, object], previous: dict[str, object] | None
) -> bool:
    if previous is None:
        return True

    def comparable(item: dict[str, object]) -> object:
        return [
            {key: value for key, value in project.items() if key != "is_new"}
            for project in item.get("projects", [])
            if isinstance(project, dict)
        ]

    return any(
        previous.get(key) != payload.get(key)
        for key in ("source", "source_url", "selection")
    ) or comparable(previous) != comparable(payload)


def history_events_equal(
    payload: dict[str, object], previous: dict[str, object] | None
) -> bool:
    if previous is None:
        return False
    return (
        previous.get("source") == payload.get("source")
        and previous.get("source_url") == payload.get("source_url")
        and previous.get("selection") == payload.get("selection")
        and previous.get("coverage") == payload.get("coverage")
        and previous.get("events") == payload.get("events")
    )


def write_json(path: Path, payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(rendered)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, path)


def main() -> None:
    previous_feed = load_previous_payload()
    previous_history = load_history_payload()

    current_feed = build_payload(fetch_bridge_payload(), previous_feed)
    current_history = build_history_payload(
        current_feed,
        previous_history,
        previous_feed=previous_feed,
    )

    feed_changed = project_data_changed(current_feed, previous_feed)
    history_changed = not history_events_equal(current_history, previous_history)

    if not feed_changed and not history_changed:
        print("Crypto fundraising data and observed history are unchanged.")
        return

    if feed_changed:
        write_json(OUTPUT, current_feed)
        print(f"Updated {OUTPUT} with {len(current_feed['projects'])} bridge projects.")

    if history_changed:
        write_json(HISTORY_OUTPUT, current_history)
        print(
            f"Updated {HISTORY_OUTPUT} with "
            f"{len(current_history['events'])} observed financing events."
        )


if __name__ == "__main__":
    main()
