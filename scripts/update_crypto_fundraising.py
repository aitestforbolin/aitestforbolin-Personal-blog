#!/usr/bin/env python3
"""Build the static latest-crypto-fundraising JSON for the personal site."""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


SITE_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = SITE_ROOT / "data" / "crypto-fundraising.json"
SOURCE_URL = "https://crypto-fundraising.info/"
SOURCE_HOST = "crypto-fundraising.info"
FETCH_TIMEOUT = 45
FETCH_RETRIES = 4
PROJECT_LIMIT = 5
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class SourceStructureError(RuntimeError):
    """The public source no longer matches the validated recent-events structure."""


class SourceAccessBlocked(RuntimeError):
    """The public source returned its browser-verification page instead of data."""


def clean_text(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


class RecentEventsParser(HTMLParser):
    """Extract rows only from the homepage's Recent fundraising events section."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[dict[str, object]] = []
        self.current_row: dict[str, object] | None = None
        self.rows: list[dict[str, object]] = []

    def inside_recent_section(self) -> bool:
        return any(bool(entry.get("recent_section")) for entry in self.stack)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        classes = set(attr_map.get("class", "").split())
        parent = self.stack[-1] if self.stack else None
        entry: dict[str, object] = {"tag": tag, "classes": classes}

        if tag == "section" and {"recently-launched", "dealflow"} <= classes:
            entry["recent_section"] = True

        if (
            self.current_row is None
            and self.inside_recent_section()
            and tag == "div"
            and {"hp-table-row", "hpt-data"} <= classes
        ):
            self.current_row = {
                "source_event_id": digits_only(attr_map.get("data-eid", "")),
                "source_project_id": digits_only(attr_map.get("data-projectid", "")),
                "col3_seen": 0,
            }
            entry["row_root"] = True

        elif self.current_row is not None:
            if tag == "a" and "t-project-link" in classes:
                self.current_row["detail_url"] = attr_map.get("href", "")

            if tag == "h5" and "cointitle" in classes:
                entry["capture"] = "name"
                entry["capture_parts"] = []

            if tag == "span" and "abbrusd" in classes:
                entry["capture"] = "amount"
                entry["capture_parts"] = []

            if tag == "div" and parent and parent.get("row_root"):
                if "hpt-col3" in classes:
                    column_index = int(self.current_row["col3_seen"])
                    entry["row_column"] = "round" if column_index == 0 else "date"
                    entry["column_parts"] = []
                    self.current_row["col3_seen"] = column_index + 1

        if tag not in VOID_TAGS:
            self.stack.append(entry)

    def handle_data(self, data: str) -> None:
        if self.current_row is None or not data.strip():
            return

        for entry in reversed(self.stack):
            if entry.get("capture"):
                parts = entry.get("capture_parts")
                if isinstance(parts, list):
                    parts.append(data)
                break

        for entry in reversed(self.stack):
            if entry.get("row_column"):
                parts = entry.get("column_parts")
                if isinstance(parts, list):
                    parts.append(data)
                break

    def handle_endtag(self, tag: str) -> None:
        if tag in VOID_TAGS or not self.stack:
            return

        matched_index = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].get("tag") == tag:
                matched_index = index
                break
        if matched_index is None:
            return

        closing = self.stack[matched_index:]
        del self.stack[matched_index:]
        for entry in reversed(closing):
            self.finish_entry(entry)

    def finish_entry(self, entry: dict[str, object]) -> None:
        if self.current_row is None:
            return

        capture = entry.get("capture")
        capture_parts = entry.get("capture_parts")
        if capture and isinstance(capture_parts, list):
            self.current_row[str(capture)] = clean_text(capture_parts)

        column = entry.get("row_column")
        column_parts = entry.get("column_parts")
        if column and isinstance(column_parts, list):
            self.current_row[str(column)] = clean_text(column_parts)

        if entry.get("row_root"):
            self.current_row.pop("col3_seen", None)
            self.rows.append(self.current_row)
            self.current_row = None


def digits_only(value: str) -> str:
    match = re.search(r"\d+", value)
    return match.group(0) if match else ""


def parse_announced_month(value: str) -> str:
    try:
        return datetime.strptime(value.strip(), "%b %Y").strftime("%Y-%m")
    except ValueError as error:
        raise SourceStructureError(f"Unexpected fundraising date: {value!r}") from error


def parse_amount(value: str) -> int | float | None:
    normalized = value.replace("$", "").replace(",", "").strip()
    if not normalized or normalized.upper() in {"TBD", "N/A", "UNKNOWN", "-"}:
        return None
    try:
        amount = Decimal(normalized)
    except InvalidOperation as error:
        raise SourceStructureError(f"Unexpected fundraising amount: {value!r}") from error
    if amount < 0:
        raise SourceStructureError(f"Fundraising amount cannot be negative: {value!r}")
    return int(amount) if amount == amount.to_integral() else float(amount)


def normalize_detail_url(value: str) -> str:
    detail_url = urljoin(SOURCE_URL, value.strip())
    parsed = urlparse(detail_url)
    if parsed.scheme != "https" or parsed.hostname not in {SOURCE_HOST, f"www.{SOURCE_HOST}"}:
        raise SourceStructureError(f"Unexpected project detail host: {detail_url!r}")
    if not parsed.path.startswith("/projects/"):
        raise SourceStructureError(f"Unexpected project detail path: {detail_url!r}")
    return detail_url.rstrip("/") + "/"


def stable_project_id(detail_url: str) -> str:
    """Build a source-independent ID from the canonical project URL."""
    slug = urlparse(detail_url).path.rstrip("/").rsplit("/", 1)[-1]
    if not slug or not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
        raise SourceStructureError(f"Unexpected project slug: {slug!r}")
    return f"crypto-fundraising-{slug}"


def reject_browser_verification(html: str, url: str = SOURCE_URL) -> None:
    """Reject anti-bot interstitials before they look like parser breakage."""
    lowered = html.casefold()
    challenge_signals = (
        "<title>one moment, please...</title>",
        "window.location.reload()",
        "anubis",
    )
    if any(signal in lowered for signal in challenge_signals):
        raise SourceAccessBlocked(
            f"{url} returned a browser-verification page instead of fundraising data"
        )


def parse_recent_events(html: str, limit: int = PROJECT_LIMIT) -> list[dict[str, object]]:
    parser = RecentEventsParser()
    parser.feed(html)
    parser.close()

    if len(parser.rows) < limit:
        raise SourceStructureError(
            f"Recent fundraising section returned {len(parser.rows)} rows; expected at least {limit}"
        )

    projects: list[dict[str, object]] = []
    for rank, row in enumerate(parser.rows[:limit], start=1):
        name = str(row.get("name", "")).strip()
        event_id = str(row.get("source_event_id", "")).strip()
        project_id = str(row.get("source_project_id", "")).strip()
        round_name = str(row.get("round", "")).strip()
        if not name or not event_id or not project_id:
            raise SourceStructureError(f"Incomplete recent fundraising row: {row!r}")

        detail_url = normalize_detail_url(str(row.get("detail_url", "")))
        projects.append(
            {
                "id": stable_project_id(detail_url),
                "source_rank": rank,
                "name": name,
                "round": None if round_name.lower() == "unknown" else round_name,
                "announced_month": parse_announced_month(str(row.get("date", ""))),
                "amount_usd": parse_amount(str(row.get("amount", ""))),
                "detail_url": detail_url,
            }
        )

    validate_projects(projects, limit)
    return projects


def validate_projects(projects: list[dict[str, object]], limit: int = PROJECT_LIMIT) -> None:
    if len(projects) != limit:
        raise SourceStructureError(f"Expected exactly {limit} normalized projects")
    ids = [str(project["id"]) for project in projects]
    urls = [str(project["detail_url"]) for project in projects]
    if len(ids) != len(set(ids)) or len(urls) != len(set(urls)):
        raise SourceStructureError("Recent fundraising projects contain duplicate IDs or links")


def fetch_homepage() -> str:
    request = Request(
        SOURCE_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": (
                "Mozilla/5.0 (compatible; PersonalSiteFundraising/1.1; "
                "+https://github.com/aitestforbolin/aitestforbolin-Personal-blog)"
            ),
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, FETCH_RETRIES + 1):
        try:
            with urlopen(request, timeout=FETCH_TIMEOUT) as response:
                body = response.read()
                encoding = response.headers.get_content_charset() or "utf-8"
            html = body.decode(encoding, errors="replace")
            reject_browser_verification(html)
            return html
        except (TimeoutError, URLError) as error:
            last_error = error
            print(
                f"Fundraising source request {attempt}/{FETCH_RETRIES} failed: "
                f"{error.__class__.__name__}: {error}",
                flush=True,
            )
            if attempt < FETCH_RETRIES:
                time.sleep(attempt * 5)
    raise RuntimeError(
        f"Could not fetch {SOURCE_URL} after {FETCH_RETRIES} attempts"
    ) from last_error


def build_payload(
    html: str | None = None, previous_payload: dict[str, object] | None = None
) -> dict[str, object]:
    projects = parse_recent_events(html if html is not None else fetch_homepage())
    previous_projects = (
        previous_payload.get("projects")
        if isinstance(previous_payload, dict)
        and isinstance(previous_payload.get("projects"), list)
        else None
    )
    previous_urls = (
        {
            str(project.get("detail_url", "")).rstrip("/") + "/"
            for project in previous_projects
            if isinstance(project, dict) and project.get("detail_url")
        }
        if previous_projects is not None
        else None
    )
    for project in projects:
        project["is_new"] = (
            previous_urls is not None and str(project["detail_url"]) not in previous_urls
        )
    return {
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "Crypto-Fundraising",
        "source_url": SOURCE_URL,
        "selection": "homepage_recent_fundraising_events",
        "projects": projects,
    }


def load_previous_payload() -> dict[str, object] | None:
    if not OUTPUT.exists():
        return None
    try:
        payload = json.loads(OUTPUT.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def project_data_changed(
    payload: dict[str, object], previous: dict[str, object] | None = None
) -> bool:
    if previous is None:
        previous = load_previous_payload()
    if previous is None:
        return True

    for key in ("source", "source_url", "selection"):
        if previous.get(key) != payload.get(key):
            return True

    def source_projects(item: dict[str, object]) -> object:
        projects = item.get("projects")
        if not isinstance(projects, list):
            return projects
        return [
            {key: value for key, value in project.items() if key != "is_new"}
            if isinstance(project, dict)
            else project
            for project in projects
        ]

    return source_projects(previous) != source_projects(payload)


def write_payload(payload: dict[str, object]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=OUTPUT.parent,
        prefix=f".{OUTPUT.name}.",
        delete=False,
    ) as handle:
        handle.write(rendered)
        temporary_path = Path(handle.name)
    os.replace(temporary_path, OUTPUT)


def main() -> None:
    previous = load_previous_payload()
    payload = build_payload(previous_payload=previous)
    if not project_data_changed(payload, previous):
        print("Latest Crypto-Fundraising projects are unchanged.")
        return
    write_payload(payload)
    print(f"Updated {OUTPUT} with {len(payload['projects'])} projects.")


if __name__ == "__main__":
    main()
