#!/usr/bin/env python3
"""Collect a resilient EU and Germany Europe Watch feed and daily snapshot."""
from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "data" / "europe-watch-sources.json"
DEFAULT_STORE = ROOT / "data" / "europe-watch-store.json"
DEFAULT_SNAPSHOT = ROOT / "data" / "europe-watch.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")
STORE_HOURS = 48
SNAPSHOT_HOUR, SNAPSHOT_MINUTE = 7, 30
MIN_HEALTHY_ITEMS = 2
MAX_PER_REGION = 30

CATEGORY_KEYWORDS = {
    "economy": ["econom", "gdp", "inflation", "recession", "growth", "euro area", "eurozone", "interest rate", "monetary", "statistics", "consumer price", "business climate", "wirtschaft", "konjunktur", "bruttoinlands", "inflation"],
    "work_income": ["employment", "unemployment", "labour", "labor", "wage", "salary", "worker", "job", "workplace", "working time", "arbeitsmarkt", "arbeitslos", "lohn", "gehalt", "beschäftig"],
    "housing": ["housing", "house price", "rent", "rental", "tenant", "homebuilding", "wohnung", "miete", "wohnungs", "immobilien"],
    "immigration": ["migration", "migrant", "asylum", "refugee", "visa", "border", "immigration", "residence permit", "einwander", "asyl", "visum", "aufenthalt"],
    "education": ["education", "school", "university", "student", "training", "bildung", "schule", "hochschule", "stud"],
    "welfare_healthcare": ["pension", "health", "healthcare", "hospital", "care", "social security", "welfare", "retirement", "rente", "gesund", "pflege", "kranken", "sozial"],
    "industry": ["industry", "manufactur", "car", "auto", "automotive", "factory", "steel", "supply chain", "industrial", "industrie", "produktion", "auto", "werk"],
    "energy": ["energy", "electricity", "gas", "power grid", "renewable", "climate", "emission", "nuclear", "energie", "strom", "klima", "gas"],
    "technology": ["artificial intelligence", " ai ", "digital", "tech", "data act", "platform", "semiconductor", "cyber", "digitalisierung", "ki", "daten"],
    "trade": ["trade", "tariff", "customs", "export", "import", "china", "united states", "transatlantic", "handel", "zoll", "export", "import"],
    "politics_society": ["election", "government", "parliament", "law", "regulation", "policy", "coalition", "minister", "bundestag", "regierung", "gesetz", "wahl", "politik"],
    "defense_security": ["defence", "defense", "security", "military", "ukraine", "nato", "armed forces", "verteidigung", "sicherheit", "bundeswehr"],
    "population": ["population", "demograph", "birth", "ageing", "aging", "census", "bevölkerung", "demografi", "geburt", "alterung"],
}
EXCLUDED = ["sport", "football", "soccer", "celebrity", "entertainment", "movie", "music", "weather", "accident", "murder", "police appeal", "lottery"]
CRITICAL = ["emergency", "war", "invasion", "crisis", "historic", "landmark", "suspends", "bans", "tariff", "election result", "coalition agreement"]
IMPORTANT = ["adopts", "approved", "agreement", "decision", "rate decision", "forecast", "law", "bill", "reform", "plan", "package", "rises", "falls", "increase", "cut"]


def clean(value: object) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html.unescape(str(value or "")))).strip()


def node_text(node: ET.Element | None, *names: str) -> str:
    if node is None:
        return ""
    for name in names:
        child = node.find(name)
        if child is not None and child.text:
            return clean(child.text)
    return ""


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; BolinEuropeWatch/2.0)", "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=15) as response:
                return response.read()
        except (URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(attempt + 1)
    raise last_error or RuntimeError("feed request failed")


def parse_entries(payload: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(payload)
    entries: list[dict[str, str]] = []
    for item in root.findall(".//item"):
        entries.append({"title": node_text(item, "title"), "url": node_text(item, "link"), "publishedAt": node_text(item, "pubDate", "{http://purl.org/dc/elements/1.1/}date"), "summary": node_text(item, "description", "{http://purl.org/rss/1.0/modules/content/}encoded")})
    atom = "{http://www.w3.org/2005/Atom}"
    for item in root.findall(f".//{atom}entry"):
        link = next((x.get("href", "") for x in item.findall(f"{atom}link") if x.get("rel") in (None, "alternate")), "")
        entries.append({"title": node_text(item, f"{atom}title"), "url": link, "publishedAt": node_text(item, f"{atom}published", f"{atom}updated"), "summary": node_text(item, f"{atom}summary", f"{atom}content")})
    return [entry for entry in entries if entry["title"] and entry["url"]]


def parse_datetime(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip(): return None
    try: parsed = email.utils.parsedate_to_datetime(value.strip())
    except (TypeError, ValueError): parsed = None
    if parsed is None:
        try: parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError: return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)).astimezone(dt.timezone.utc)


def iso(value: dt.datetime) -> str: return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds")
def load_json(path: Path, default: object) -> object:
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return default
def effective_time(row: dict) -> dt.datetime | None: return parse_datetime(row.get("published_at")) or parse_datetime(row.get("first_seen_at"))
def normalized(value: str) -> set[str]: return set(re.findall(r"[a-z0-9]{3,}", unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()))


def classify(title: str, summary: str) -> str | None:
    text = f" {title} {summary} ".lower()
    if any(word in text for word in EXCLUDED): return None
    scores = {category: sum(word in text for word in words) for category, words in CATEGORY_KEYWORDS.items()}
    category, score = max(scores.items(), key=lambda pair: pair[1])
    return category if score else None


def importance(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    if any(word in text for word in CRITICAL): return "critical"
    if any(word in text for word in IMPORTANT): return "important"
    return "normal"


def title_cn(title: str) -> str:
    """Translate only through a public machine endpoint; original text remains if unavailable."""
    try:
        query = urllib.parse.urlencode({"client": "gtx", "sl": "auto", "tl": "zh-CN", "dt": "t", "q": title})
        payload = fetch(f"https://translate.googleapis.com/translate_a/single?{query}")
        translated = "".join(part[0] for part in json.loads(payload.decode("utf-8"))[0] if part and part[0])
        return clean(translated) or title
    except Exception:
        return title


def to_item(entry: dict, source: dict, now: dt.datetime) -> dict | None:
    category = classify(entry["title"], entry["summary"])
    if not category: return None
    published = parse_datetime(entry["publishedAt"])
    return {"id": hashlib.sha256(entry["url"].encode()).hexdigest()[:16], "region": source["region"], "title": entry["title"], "title_cn": "", "summary": entry["summary"][:700], "source": source["name"], "source_url": entry["url"], "published_at": iso(published) if published else None, "fetched_at": iso(now), "category": category, "importance": importance(entry["title"], entry["summary"]), "official_source": bool(source.get("official_source")), "first_seen_at": iso(now), "last_seen_at": iso(now)}


def stronger(a: dict, b: dict) -> dict:
    # Policy/statistical primary sources outrank coverage; otherwise readable media wins.
    policy_categories = {"economy", "politics_society", "technology", "trade", "energy", "work_income"}
    if a["official_source"] != b["official_source"] and a["category"] in policy_categories:
        return a if a["official_source"] else b
    return a if not a["official_source"] else b


def dedupe(items: list[dict]) -> list[dict]:
    selected: list[dict] = []
    for item in sorted(items, key=lambda row: (row.get("importance") == "critical", row.get("importance") == "important", effective_time(row) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)), reverse=True):
        tokens = normalized(item["title"])
        match = next((old for old in selected if old["region"] == item["region"] and len(tokens & normalized(old["title"])) / max(1, len(tokens | normalized(old["title"]))) >= .62), None)
        if match:
            winner = stronger(match, item)
            if winner is item: selected[selected.index(match)] = item
        else: selected.append(item)
    return selected


def merge_store(existing: object, candidates: list[dict], now: dt.datetime) -> list[dict]:
    previous = existing.get("items", []) if isinstance(existing, dict) else []
    by_url = {row.get("source_url"): dict(row) for row in previous if isinstance(row, dict) and row.get("source_url")}
    for item in candidates:
        old = by_url.get(item["source_url"], {})
        by_url[item["source_url"]] = {**old, **item, "title_cn": old.get("title_cn") or item.get("title_cn") or "", "first_seen_at": old.get("first_seen_at") or item["first_seen_at"], "last_seen_at": iso(now)}
    cutoff = now - dt.timedelta(hours=STORE_HOURS)
    retained = [row for row in by_url.values() if (effective_time(row) or now) >= cutoff]
    selected = dedupe(retained)
    selected.sort(key=lambda row: (row.get("importance") == "critical", row.get("importance") == "important", effective_time(row) or now), reverse=True)
    capped: list[dict] = []
    counts = {"eu": 0, "germany": 0}
    for row in selected:
        if counts.get(row["region"], 0) < MAX_PER_REGION:
            capped.append(row); counts[row["region"]] = counts.get(row["region"], 0) + 1
    missing = [row for row in capped if not row.get("title_cn")]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for row, translated in zip(missing, pool.map(lambda value: title_cn(value["title"]), missing)):
            row["title_cn"] = translated
    return capped


def snapshot_window(now: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    local = now.astimezone(SHANGHAI); end = local.replace(hour=SNAPSHOT_HOUR, minute=SNAPSHOT_MINUTE, second=0, microsecond=0)
    if local < end: end -= dt.timedelta(days=1)
    return (end - dt.timedelta(hours=24)).astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)


def snapshot_is_due(existing: object, now: dt.datetime) -> bool:
    _, expected_end = snapshot_window(now)
    return not isinstance(existing, dict) or (parse_datetime(existing.get("as_of") or existing.get("window_end")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)) < expected_end


def build_snapshot(store: dict, now: dt.datetime) -> dict:
    start, end = snapshot_window(now)
    items = [row for row in store.get("items", []) if effective_time(row) and start <= effective_time(row) < end]
    items = sorted(items, key=lambda row: (row["importance"] == "critical", row["importance"] == "important", effective_time(row)), reverse=True)
    return {"schema_version": 3, "generated_at": iso(now), "as_of": end.astimezone(SHANGHAI).isoformat(timespec="seconds"), "window_start": start.astimezone(SHANGHAI).isoformat(timespec="seconds"), "window_end": end.astimezone(SHANGHAI).isoformat(timespec="seconds"), "source_health": store.get("source_health", []), "items": items}


def collect_sources(now: dt.datetime) -> tuple[list[dict], list[dict]]:
    sources = [item for item in json.loads(SOURCES.read_text(encoding="utf-8"))["sources"] if item.get("enabled")]
    def collect(source: dict) -> tuple[dict, list[dict]]:
        try:
            rows = [to_item(entry, source, now) for entry in parse_entries(fetch(source["rss_url"]))]
            kept = [row for row in rows if row]
            return {"source": source["name"], "region": source["region"], "status": "ok" if kept else "empty", "count": len(kept), "checked_at": iso(now)}, kept
        except Exception as exc:
            return {"source": source["name"], "region": source["region"], "status": "error", "error": type(exc).__name__, "count": 0, "checked_at": iso(now)}, []
    audits, candidates = [], []
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        for future in as_completed([pool.submit(collect, source) for source in sources]):
            audit, rows = future.result(); audits.append(audit); candidates.extend(rows)
    return sorted(audits, key=lambda row: (row["region"], row["source"])), candidates


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--store-file", type=Path, default=DEFAULT_STORE); parser.add_argument("--snapshot-file", type=Path, default=DEFAULT_SNAPSHOT); parser.add_argument("--snapshot", action="store_true"); parser.add_argument("--snapshot-if-due", action="store_true"); parser.add_argument("--now")
    args = parser.parse_args(); now = parse_datetime(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    if now is None: raise SystemExit("--now must be a valid ISO timestamp")
    previous = load_json(args.store_file, {}); current_snapshot = load_json(args.snapshot_file, {})
    audit, candidates = collect_sources(now); store_items = merge_store(previous, candidates, now)
    healthy = len(candidates) >= MIN_HEALTHY_ITEMS or bool(store_items)
    store = {"schema_version": 3, "generated_at": iso(now), "retention_hours": STORE_HOURS, "source_health": audit, "items": store_items}
    if healthy:
        args.store_file.parent.mkdir(parents=True, exist_ok=True); args.store_file.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    publish = (args.snapshot or (args.snapshot_if_due and snapshot_is_due(current_snapshot, now))) and healthy
    if publish:
        snapshot = build_snapshot(store, now)
        if snapshot["items"]:
            args.snapshot_file.parent.mkdir(parents=True, exist_ok=True); args.snapshot_file.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else: publish = False
    print(json.dumps({"source_health": audit, "stored": len(store_items), "snapshot": publish, "healthy": healthy}, ensure_ascii=False))
    return 0 if healthy else 1


if __name__ == "__main__": sys.exit(main())
