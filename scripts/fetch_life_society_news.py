#!/usr/bin/env python3
"""Fetch the first-phase RSS candidate set; no site data is changed."""
from __future__ import annotations

import datetime as dt
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "life-society-news-sources.json"
OUTPUT = ROOT / "data" / "life-society-news.json"
LIMIT_PER_SOURCE = 20


def text(node: ET.Element | None, *names: str) -> str:
    if node is None:
        return ""
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return re.sub(r"<[^>]+>", "", html.unescape(child.text)).strip()
    return ""


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; personal-site-rss-test/1.0)", "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    # One unavailable publisher must not hold up the complete daily list.
    with urlopen(request, timeout=8) as response:
        return response.read()


def entries(payload: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(payload)
    found: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        found.append({"originalTitle": text(item, "title"), "url": text(item, "link"), "publishedAt": text(item, "pubDate", "{http://purl.org/dc/elements/1.1/}date"), "description": text(item, "description")})
    atom = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{atom}entry"):
        link = item.find(f"{atom}link")
        found.append({"originalTitle": text(item, f"{atom}title"), "url": (link.get("href", "") if link is not None else ""), "publishedAt": text(item, f"{atom}updated", f"{atom}published"), "description": text(item, f"{atom}summary", f"{atom}content")})
    return [row for row in found if row["originalTitle"] and row["url"]][:LIMIT_PER_SOURCE]


def main() -> int:
    registry = json.loads(SOURCES.read_text(encoding="utf-8"))
    enabled_sources = [source for source in registry["sources"] if source.get("enabled")]
    audit, candidates = [], []
    def collect(source: dict) -> tuple[dict, list[dict]]:
        try:
            rows = entries(fetch(source["rssUrl"]))
            status = "ok" if rows else "empty"
            return ({"country": source["country"], "outlet": source["outlet"], "rssUrl": source["rssUrl"], "status": status, "count": len(rows)}, [{**row, "country": source["country"], "outlet": source["outlet"], "sectionUrl": source["sectionUrl"]} for row in rows])
        except Exception as exc:
            return ({"country": source["country"], "outlet": source["outlet"], "rssUrl": source["rssUrl"], "status": "error", "error": type(exc).__name__}, [])
    with ThreadPoolExecutor(max_workers=len(enabled_sources)) as pool:
        futures = [pool.submit(collect, source) for source in enabled_sources]
        for future in as_completed(futures):
            source_audit, source_rows = future.result()
            audit.append(source_audit)
            candidates.extend(source_rows)
    candidates.sort(key=lambda row: row.get("publishedAt", ""), reverse=True)
    output = {
        "schemaVersion": 1,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "translationStatus": "not_enabled",
        "sourceAudit": audit,
        "items": [
            {**row, "chineseTitle": None, "displayTitle": row["originalTitle"]}
            for row in candidates
        ],
    }
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    return 0 if candidates else 1


if __name__ == "__main__":
    sys.exit(main())
