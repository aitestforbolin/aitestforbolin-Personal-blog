#!/usr/bin/env python3
"""Direct fallback reader for the public Crypto-Fundraising homepage."""

from __future__ import annotations

import re
import time
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

SOURCE_URL = "https://crypto-fundraising.info/"
PROJECT_LIMIT = 5
MONTHS = {
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "may": "05", "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[dict[str, object]]] = []
        self._row: list[dict[str, object]] | None = None
        self._cell: dict[str, object] | None = None
        self._anchor: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self._row = []
            return
        if tag in {"td", "th"} and self._row is not None:
            self._cell = {"parts": [], "links": []}
            return
        if tag == "a" and self._cell is not None:
            href = dict(attrs).get("href") or ""
            self._anchor = {"href": href, "parts": []}

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            parts = self._cell["parts"]
            assert isinstance(parts, list)
            parts.append(data)
        if self._anchor is not None:
            parts = self._anchor["parts"]
            assert isinstance(parts, list)
            parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._anchor is not None and self._cell is not None:
            links = self._cell["links"]
            assert isinstance(links, list)
            links.append(
                {
                    "href": self._anchor["href"],
                    "text": _clean_text(" ".join(self._anchor["parts"])),
                }
            )
            self._anchor = None
            return
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._cell["text"] = _clean_text(" ".join(self._cell["parts"]))
            self._cell.pop("parts", None)
            self._row.append(self._cell)
            self._cell = None
            return
        if tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None
            self._anchor = None


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _project_name(value: str) -> str:
    value = _clean_text(value)
    tokens = value.split()
    if len(tokens) >= 2:
        if tokens[-1] == tokens[-2]:
            tokens = tokens[:-1]
        elif re.fullmatch(r"[A-Z0-9._-]{2,10}", tokens[-1]) and any(
            char.islower() for char in " ".join(tokens[:-1])
        ):
            tokens = tokens[:-1]
    return " ".join(tokens).strip()


def _announced_month(value: str) -> str:
    match = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d{2})\b",
        value,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError(f"Could not parse fundraising month: {value!r}")
    return f"{match.group(2)}-{MONTHS[match.group(1)[:3].lower()]}"


def _round_name(value: str) -> str | None:
    cleaned = _clean_text(value)
    if cleaned.lower() in {"", "-", "unknown", "n/a", "none"}:
        return None
    return cleaned


def _amount_usd(value: str) -> int | float | None:
    cleaned = _clean_text(value).lower().replace(",", "")
    if not cleaned or cleaned in {"-", "unknown", "n/a"}:
        return None
    match = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*([kmb])?\b", cleaned)
    if not match:
        return None
    number = float(match.group(1))
    multiplier = {None: 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[match.group(2)]
    amount = number * multiplier
    return int(amount) if amount.is_integer() else amount


def parse_homepage_payload(html: str) -> dict[str, object]:
    parser = _TableParser()
    parser.feed(html)

    projects: list[dict[str, object]] = []
    for row in parser.rows:
        project_cell_index = None
        project_link = None
        for index, cell in enumerate(row):
            links = cell.get("links")
            if not isinstance(links, list):
                continue
            for link in links:
                if not isinstance(link, dict):
                    continue
                href = str(link.get("href") or "")
                path = urlparse(urljoin(SOURCE_URL, href)).path
                if path.startswith("/projects/") and path.rstrip("/").count("/") == 2:
                    project_cell_index = index
                    project_link = link
                    break
            if project_link is not None:
                break

        if project_link is None or project_cell_index is None:
            continue
        if len(row) <= project_cell_index + 3:
            continue

        detail_url = urljoin(SOURCE_URL, str(project_link.get("href") or ""))
        if not detail_url.endswith("/"):
            detail_url += "/"
        name = _project_name(str(project_link.get("text") or ""))
        if not name:
            continue

        projects.append(
            {
                "id": f"direct-{len(projects) + 1}",
                "source_rank": len(projects) + 1,
                "name": name,
                "round": _round_name(str(row[project_cell_index + 1].get("text") or "")),
                "announced_month": _announced_month(
                    str(row[project_cell_index + 2].get("text") or "")
                ),
                "amount_usd": _amount_usd(
                    str(row[project_cell_index + 3].get("text") or "")
                ),
                "detail_url": detail_url,
            }
        )
        if len(projects) == PROJECT_LIMIT:
            break

    if len(projects) != PROJECT_LIMIT:
        raise ValueError(
            f"Direct homepage fallback found {len(projects)} project rows; expected {PROJECT_LIMIT}"
        )

    return {
        "source": "Crypto-Fundraising",
        "selection": "homepage_recent_fundraising_events",
        "projects": projects,
    }


def fetch_direct_source_payload(timeout: int = 30, retries: int = 2) -> dict[str, object]:
    request = Request(
        SOURCE_URL,
        headers={
            "Accept": "text/html,application/xhtml+xml",
            "User-Agent": "personal-site-crypto-fundraising/4.0",
        },
    )
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                if response.status != 200:
                    raise RuntimeError(f"Direct source returned HTTP {response.status}")
                html = response.read().decode("utf-8")
            return parse_homepage_payload(html)
        except (HTTPError, URLError, TimeoutError, UnicodeDecodeError, ValueError, RuntimeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(attempt * 5)
    raise RuntimeError(
        f"Could not fetch a valid direct Crypto-Fundraising homepage after {retries} attempts"
    ) from last_error
