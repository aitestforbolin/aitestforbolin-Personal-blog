#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

API_URL = "https://api.socialdata.tools/twitter/search"
ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "data" / "x-author-search.json"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class SocialDataError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(value: str) -> str:
    username = (value or "").strip().lstrip("@")
    if not USERNAME_RE.fullmatch(username):
        raise ValueError("Invalid X username: %r" % value)
    return username


def parse_keywords(values: list[str] | None, csv_value: str | None) -> list[str]:
    result: list[str] = []
    raw_values = list(values or [])
    if csv_value:
        raw_values.extend(csv_value.split(","))

    for raw in raw_values:
        keyword = str(raw).strip()
        if keyword and keyword not in result:
            result.append(keyword)
    return result


def quote_term(value: str) -> str:
    term = value.strip()
    if not term:
        raise ValueError("Keyword cannot be empty")
    if any(ch.isspace() for ch in term):
        return '"' + term.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return term


def build_query(
    username: str,
    keywords: list[str],
    *,
    match: str,
    since_time: int,
    include_replies: bool,
) -> str:
    username = normalize_username(username)
    if match not in {"any", "all"}:
        raise ValueError("match must be 'any' or 'all'")

    parts = [f"from:{username}"]

    if keywords:
        terms = [quote_term(item) for item in keywords]
        if match == "any" and len(terms) > 1:
            parts.append("(" + " OR ".join(terms) + ")")
        else:
            parts.extend(terms)

    if not include_replies:
        parts.append("-filter:replies")

    parts.append(f"since_time:{int(since_time)}")
    return " ".join(parts)


def parse_request_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Request JSON must be an object")

    username = normalize_username(str(payload.get("username") or ""))
    raw_keywords = payload.get("keywords") or []
    if isinstance(raw_keywords, str):
        keywords = parse_keywords([], raw_keywords)
    elif isinstance(raw_keywords, list):
        keywords = parse_keywords([str(item) for item in raw_keywords], "")
    else:
        raise ValueError("request keywords must be a string or array")

    days = int(payload.get("days", 30))
    match = str(payload.get("match") or "any")
    include_replies = bool(payload.get("includeReplies", False))
    max_results = int(payload.get("maxResults", 100))
    max_pages = int(payload.get("maxPages", 10))
    search_type = str(payload.get("searchType") or "Latest")
    request_id = str(payload.get("requestId") or "").strip() or None

    if match not in {"any", "all"}:
        raise ValueError("request match must be 'any' or 'all'")
    if search_type not in {"Latest", "Top"}:
        raise ValueError("request searchType must be 'Latest' or 'Top'")

    return {
        "username": username,
        "keywords": keywords,
        "days": days,
        "match": match,
        "include_replies": include_replies,
        "max_results": max_results,
        "max_pages": max_pages,
        "search_type": search_type,
        "request_id": request_id,
    }


def load_request(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return parse_request_payload(payload)


def request_json(api_key: str, query: str, *, search_type: str, cursor: str | None) -> dict:
    params = {"query": query, "type": search_type}
    if cursor:
        params["cursor"] = cursor

    url = API_URL + "?" + urlencode(params)
    headers = {
        "Authorization": "Bearer " + api_key,
        "Accept": "application/json",
        "User-Agent": "bolin-x-author-search/1.0",
    }

    last_error: Exception | None = None
    for attempt in range(3):
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise SocialDataError("SocialData returned a non-object response")
            return payload
        except HTTPError as exc:
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if exc.code == 402:
                raise SocialDataError("SocialData balance is insufficient (HTTP 402)") from exc
            if exc.code in {429, 500, 502, 503}:
                last_error = SocialDataError(f"HTTP {exc.code}: {body[:300]}")
                time.sleep(2 ** attempt)
                continue
            raise SocialDataError(f"HTTP {exc.code}: {body[:500]}") from exc
        except (URLError, TimeoutError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)

    raise SocialDataError(f"SocialData request failed after retries: {last_error}")


def tweet_url(tweet: dict) -> str:
    user = tweet.get("user") or {}
    username = user.get("screen_name") or ""
    tweet_id = str(tweet.get("id_str") or tweet.get("id") or "")
    if username and tweet_id:
        return f"https://x.com/{username}/status/{tweet_id}"
    return ""


def external_urls(tweet: dict) -> list[str]:
    result: list[str] = []
    for item in ((tweet.get("entities") or {}).get("urls") or []):
        if not isinstance(item, dict):
            continue
        value = item.get("expanded_url") or item.get("unwound_url") or item.get("url")
        if not value:
            continue
        host = urlparse(value).netloc.lower()
        if host.endswith("x.com") or host.endswith("twitter.com"):
            continue
        if value not in result:
            result.append(value)
    return result[:8]


def media(tweet: dict) -> dict:
    groups = []
    entities = tweet.get("entities") or {}
    extended = tweet.get("extended_entities") or {}
    if isinstance(entities.get("media"), list):
        groups.append(entities["media"])
    if isinstance(extended.get("media"), list):
        groups.append(extended["media"])

    seen: set[str] = set()
    types: list[str] = []
    urls: list[str] = []
    for group in groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id_str") or item.get("media_url_https") or item.get("media_url") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            media_type = str(item.get("type") or "unknown")
            if media_type not in types:
                types.append(media_type)
            image_url = item.get("media_url_https") or item.get("media_url")
            if image_url and image_url not in urls:
                urls.append(image_url)
    return {"types": types[:4], "urls": urls[:8]}


def tweet_context(tweet: dict | None) -> dict | None:
    if not isinstance(tweet, dict):
        return None
    user = tweet.get("user") or {}
    return {
        "tweet_id": str(tweet.get("id_str") or tweet.get("id") or ""),
        "created_at": tweet.get("tweet_created_at") or tweet.get("created_at") or "",
        "author": {
            "username": user.get("screen_name") or "",
            "name": user.get("name") or "",
        },
        "text": tweet.get("full_text") or tweet.get("text") or "",
        "url": tweet_url(tweet),
        "external_urls": external_urls(tweet),
        "media": media(tweet),
        "quote": tweet_context(quoted),
        "quote_context_missing": bool(
            (tweet.get("is_quote_status") or tweet.get("quoted_status_id_str") or tweet.get("quoted_status_id"))
            and not isinstance(quoted, dict)
        ),
    }


def normalize(tweet: dict) -> dict:
    user = tweet.get("user") or {}
    tweet_id = str(tweet.get("id_str") or tweet.get("id") or "")
    username = str(user.get("screen_name") or "")
    quoted = tweet.get("quoted_status")
    return {
        "tweet_id": tweet_id,
        "created_at": tweet.get("tweet_created_at") or tweet.get("created_at") or "",
        "author": {
            "username": username,
            "name": user.get("name") or "",
        },
        "text": tweet.get("full_text") or tweet.get("text") or "",
        "url": tweet_url(tweet),
        "is_reply": bool(tweet.get("in_reply_to_status_id_str") or tweet.get("in_reply_to_status_id")),
        "is_quote": bool(tweet.get("is_quote_status") or tweet.get("quoted_status_id_str") or tweet.get("quoted_status_id")),
        "engagement": {
            "views": tweet.get("views_count"),
            "likes": tweet.get("favorite_count"),
            "replies": tweet.get("reply_count"),
            "reposts": tweet.get("retweet_count"),
            "quotes": tweet.get("quote_count"),
        },
        "external_urls": external_urls(tweet),
        "media": media(tweet),
    }


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def collect(
    *,
    api_key: str,
    username: str,
    keywords: list[str],
    days: int,
    match: str,
    include_replies: bool,
    max_results: int,
    max_pages: int,
    search_type: str,
    request_id: str | None = None,
) -> dict:
    if days < 1:
        raise ValueError("days must be >= 1")
    if max_results < 1:
        raise ValueError("max_results must be >= 1")
    if max_pages < 1:
        raise ValueError("max_pages must be >= 1")

    now = utc_now()
    since = now - timedelta(days=days)
    query = build_query(
        username,
        keywords,
        match=match,
        since_time=int(since.timestamp()),
        include_replies=include_replies,
    )

    cursor: str | None = None
    raw_count = 0
    pages = 0
    unique: dict[str, dict] = {}

    for _ in range(max_pages):
        payload = request_json(api_key, query, search_type=search_type, cursor=cursor)
        tweets = payload.get("tweets") or []
        if not isinstance(tweets, list):
            raise SocialDataError("SocialData response field 'tweets' is not an array")

        pages += 1
        raw_count += len(tweets)

        for tweet in tweets:
            if not isinstance(tweet, dict):
                continue
            row = normalize(tweet)
            tweet_id = row.get("tweet_id")
            author = (row.get("author") or {}).get("username") or ""
            if not tweet_id:
                continue
            if author.lower() != username.lower():
                continue
            if tweet_id not in unique:
                unique[tweet_id] = row
            if len(unique) >= max_results:
                break

        if len(unique) >= max_results:
            break

        next_cursor = payload.get("next_cursor")
        if not tweets or not next_cursor:
            break
        cursor = str(next_cursor)

    posts = list(unique.values())[:max_results]

    return {
        "schemaVersion": 1,
        "source": "SocialData Twitter Search",
        "generatedAt": now.isoformat(),
        "requestId": request_id,
        "username": username,
        "keywords": keywords,
        "match": match,
        "days": days,
        "includeReplies": include_replies,
        "searchType": search_type,
        "query": query,
        "pagesFetched": pages,
        "rawTweetsFetched": raw_count,
        "resultCount": len(posts),
        "posts": posts,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search one X author's posts by keyword using the existing SocialData API key."
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--username", help="X username, with or without @")
    source.add_argument("--request-file", help="JSON request file used by the GitHub trigger workflow")
    parser.add_argument(
        "--keywords",
        nargs="*",
        default=[],
        help='Keywords or quoted phrases, e.g. --keywords airdrop points "agent trading"',
    )
    parser.add_argument(
        "--keywords-csv",
        default="",
        help="Comma-separated keywords; convenient for GitHub Actions manual input.",
    )
    parser.add_argument("--days", type=int, default=30, help="Look back this many days (default: 30)")
    parser.add_argument(
        "--match",
        choices=["any", "all"],
        default="any",
        help="Match any keyword (OR) or all keywords (AND). Default: any.",
    )
    parser.add_argument(
        "--include-replies",
        action="store_true",
        help="Include replies. By default only non-reply posts are searched.",
    )
    parser.add_argument("--max-results", type=int, default=100, help="Maximum unique posts to save")
    parser.add_argument("--max-pages", type=int, default=10, help="Maximum SocialData result pages")
    parser.add_argument(
        "--search-type",
        choices=["Latest", "Top"],
        default="Latest",
        help="SocialData search type. Default: Latest.",
    )
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Output JSON path (default: data/x-author-search.json)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    api_key = os.environ.get("SOCIALDATA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing SOCIALDATA_API_KEY")

    if args.request_file:
        config = load_request(Path(args.request_file))
    else:
        config = {
            "username": normalize_username(args.username),
            "keywords": parse_keywords(args.keywords, args.keywords_csv),
            "days": args.days,
            "match": args.match,
            "include_replies": args.include_replies,
            "max_results": args.max_results,
            "max_pages": args.max_pages,
            "search_type": args.search_type,
            "request_id": None,
        }

    payload = collect(api_key=api_key, **config)

    output = Path(args.output)
    write_json_atomic(output, payload)
    print(
        json.dumps(
            {
                "requestId": payload.get("requestId"),
                "username": payload["username"],
                "keywords": payload["keywords"],
                "resultCount": payload["resultCount"],
                "pagesFetched": payload["pagesFetched"],
                "output": str(output),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"::error::{exc}", file=sys.stderr)
        raise
