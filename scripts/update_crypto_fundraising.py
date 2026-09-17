#!/usr/bin/env python3
"""Refresh the five displayed Crypto-Fundraising projects through the bridge API."""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SITE_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = SITE_ROOT / "data" / "crypto-fundraising.json"
BRIDGE_URL = "https://crypto-fundraising-bridge.laibocszd.chatgpt.site/api/crypto-fundraising"
FETCH_TIMEOUT = 30
FETCH_RETRIES = 2
PROJECT_LIMIT = 5
SOURCE_HOST = "crypto-fundraising.info"


class BridgeDataError(RuntimeError):
    """The bridge response is unavailable or violates the published five-item contract."""


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
        if amount_usd is not None and (isinstance(amount_usd, bool) or not isinstance(amount_usd, (int, float)) or amount_usd < 0):
            raise BridgeDataError(f"Invalid amount_usd at rank {rank}")
        if detail_url in urls:
            raise BridgeDataError("Bridge projects contain duplicate detail URLs")
        urls.add(detail_url)
        normalized.append({
            "id": stable_project_id(detail_url),
            "source_rank": rank,
            "name": name.strip(),
            "round": round_name.strip() if isinstance(round_name, str) else None,
            "announced_month": announced_month,
            "amount_usd": amount_usd,
            "detail_url": detail_url,
        })
    return normalized


def fetch_bridge_payload() -> dict[str, object]:
    request = Request(BRIDGE_URL, headers={"Accept": "application/json", "User-Agent": "personal-site-crypto-fundraising/2.0"})
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urlopen(request, timeout=FETCH_TIMEOUT) as response:
                if response.status != 200:
                    raise BridgeDataError(f"Bridge returned HTTP {response.status}")
                payload = json.loads(response.read().decode("utf-8"))
            validate_bridge_payload(payload)
            return payload
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError, BridgeDataError) as error:
            last_error = error
            if attempt < FETCH_RETRIES:
                time.sleep(attempt * 5)
    raise BridgeDataError(f"Could not fetch a valid bridge payload after {FETCH_RETRIES} attempts") from last_error


def load_previous_payload() -> dict[str, object] | None:
    try:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def build_payload(bridge_payload: object, previous_payload: dict[str, object] | None) -> dict[str, object]:
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


def project_data_changed(payload: dict[str, object], previous: dict[str, object] | None) -> bool:
    if previous is None:
        return True
    def comparable(item: dict[str, object]) -> object:
        return [{key: value for key, value in project.items() if key != "is_new"} for project in item.get("projects", [])]
    return any(previous.get(key) != payload.get(key) for key in ("source", "source_url", "selection")) or comparable(previous) != comparable(payload)


def write_payload(payload: dict[str, object]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=OUTPUT.parent, delete=False) as handle:
        handle.write(rendered)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, OUTPUT)


def main() -> None:
    previous = load_previous_payload()
    payload = build_payload(fetch_bridge_payload(), previous)
    if not project_data_changed(payload, previous):
        print("Crypto fundraising data is unchanged.")
        return
    write_payload(payload)
    print(f"Updated {OUTPUT} with {len(payload['projects'])} bridge projects.")


if __name__ == "__main__":
    main()
