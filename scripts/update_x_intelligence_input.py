#!/usr/bin/env python3
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

API_BASE = "https://api.socialdata.tools/twitter/list/{list_id}/tweets"
PRICE_PER_TWEET = 0.0002
ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "data" / "x-intelligence-sources.json"
OUTPUT_PATH = ROOT / "data" / "x-intelligence-input.json"


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def get_page(api_key, list_id, cursor=None):
    headers = {"Authorization": "Bearer " + api_key, "Accept": "application/json"}
    params = {"cursor": cursor} if cursor else {}
    last_error = None
    for attempt in range(3):
        try:
            response = requests.get(
                API_BASE.format(list_id=list_id),
                headers=headers,
                params=params,
                timeout=30,
            )
            if response.status_code == 200:
                return response.json()
            if response.status_code == 402:
                raise RuntimeError("SocialData balance is insufficient (HTTP 402)")
            if response.status_code in (429, 500, 502, 503):
                last_error = RuntimeError("HTTP %s: %s" % (response.status_code, response.text[:300]))
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError("HTTP %s: %s" % (response.status_code, response.text[:500]))
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError("SocialData request failed after retries: %s" % last_error)


def tweet_url(tweet):
    if not isinstance(tweet, dict):
        return ""
    user = tweet.get("user") or {}
    username = user.get("screen_name") or ""
    tweet_id = str(tweet.get("id_str") or tweet.get("id") or "")
    return "https://x.com/%s/status/%s" % (username, tweet_id) if username and tweet_id else ""


def quote_flag(tweet):
    if not isinstance(tweet, dict):
        return False
    return bool(tweet.get("is_quote_status") or tweet.get("quoted_status_id_str") or tweet.get("quoted_status_id"))


def external_urls(tweet):
    if not isinstance(tweet, dict):
        return []
    result = []
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
    return result[:6]


def media(tweet):
    if not isinstance(tweet, dict):
        return {"types": [], "urls": []}
    groups = []
    entities = tweet.get("entities") or {}
    extended = tweet.get("extended_entities") or {}
    if isinstance(entities.get("media"), list):
        groups.append(entities["media"])
    if isinstance(extended.get("media"), list):
        groups.append(extended["media"])

    seen = set()
    types = []
    urls = []
    for group in groups:
        for item in group:
            if not isinstance(item, dict):
                continue
            key = str(item.get("id_str") or item.get("media_url_https") or item.get("media_url") or "")
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            mtype = item.get("type") or "unknown"
            if mtype not in types:
                types.append(mtype)
            image_url = item.get("media_url_https") or item.get("media_url")
            if image_url and image_url not in urls:
                urls.append(image_url)
            for variant in ((item.get("video_info") or {}).get("variants") or []):
                if not isinstance(variant, dict):
                    continue
                url = variant.get("url")
                content_type = variant.get("content_type") or ""
                if url and ("video" in content_type or url.endswith(".m3u8")) and url not in urls:
                    urls.append(url)
    return {"types": types[:4], "urls": urls[:8]}


def context(tweet):
    if not isinstance(tweet, dict):
        return None
    user = tweet.get("user") or {}
    return {
        "tweet_id": str(tweet.get("id_str") or tweet.get("id") or ""),
        "username": user.get("screen_name") or "",
        "name": user.get("name") or "",
        "text": tweet.get("full_text") or tweet.get("text") or "",
        "created_at": tweet.get("tweet_created_at") or tweet.get("created_at") or "",
        "url": tweet_url(tweet),
        "external_urls": external_urls(tweet),
        "media": media(tweet),
    }


def normalize(tweet, list_name, list_id):
    user = tweet.get("user") or {}
    tweet_id = str(tweet.get("id_str") or tweet.get("id") or "")
    username = user.get("screen_name") or ""
    retweeted = tweet.get("retweeted_status")
    is_retweet = isinstance(retweeted, dict)
    is_reply = bool(tweet.get("in_reply_to_status_id_str"))
    is_quote = bool((not is_retweet) and quote_flag(tweet))
    retweet_is_quote = bool(is_retweet and quote_flag(retweeted))

    if is_retweet:
        kind = "retweet"
    elif is_quote:
        kind = "quote"
    elif is_reply:
        kind = "reply"
    else:
        kind = "original"

    retweet_quote = None
    if retweet_is_quote and isinstance(retweeted, dict):
        retweet_quote = context(retweeted.get("quoted_status"))

    return {
        "list_name": list_name,
        "list_id": list_id,
        "tweet_id": tweet_id,
        "created_at": tweet.get("tweet_created_at") or tweet.get("created_at") or "",
        "kind": kind,
        "author": {"username": username, "name": user.get("name") or ""},
        "text": tweet.get("full_text") or tweet.get("text") or "",
        "url": "https://x.com/%s/status/%s" % (username, tweet_id) if username and tweet_id else "",
        "engagement": {
            "views": tweet.get("views_count"),
            "likes": tweet.get("favorite_count"),
            "replies": tweet.get("reply_count"),
            "reposts": tweet.get("retweet_count"),
            "quotes": tweet.get("quote_count"),
        },
        "external_urls": external_urls(tweet),
        "media": media(tweet),
        "quote": context(tweet.get("quoted_status")) if is_quote else None,
        "quote_context_missing": bool(is_quote and not isinstance(tweet.get("quoted_status"), dict)),
        "retweet": context(retweeted) if is_retweet else None,
        "retweet_is_quote": retweet_is_quote,
        "retweet_quote": retweet_quote,
        "retweet_quote_context_missing": bool(retweet_is_quote and retweet_quote is None),
    }


def main():
    api_key = os.environ.get("SOCIALDATA_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing SOCIALDATA_API_KEY")

    max_cost = float(os.environ.get("X_INTELLIGENCE_MAX_COST_USD", "0.10"))
    max_pages = int(os.environ.get("X_INTELLIGENCE_MAX_PAGES", "10"))
    window_hours = int(os.environ.get("X_INTELLIGENCE_WINDOW_HOURS", "24"))

    config = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    lists = config.get("lists") or []
    if len(lists) != 4:
        raise RuntimeError("Expected exactly 4 X Lists")

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    billed = 0
    all_rows = []
    per_list = []
    stopped = False

    for source in lists:
        if stopped:
            break
        list_id = str(source["id"])
        list_name = str(source.get("name") or list_id)
        cursor = None
        returned = 0
        pages = 0
        list_rows = []
        crossed_cutoff = False

        for _ in range(max_pages):
            payload = get_page(api_key, list_id, cursor)
            tweets = payload.get("tweets") or []
            next_cursor = payload.get("next_cursor")
            billed += len(tweets)
            returned += len(tweets)
            pages += 1

            rows = [normalize(tweet, list_name, list_id) for tweet in tweets]
            list_rows.extend(rows)
            all_rows.extend(rows)

            dates = [parse_dt(row.get("created_at")) for row in rows]
            dates = [value for value in dates if value is not None]
            if dates and min(dates) < cutoff:
                crossed_cutoff = True

            if billed * PRICE_PER_TWEET >= max_cost:
                stopped = True
                break
            if not tweets or not next_cursor or crossed_cutoff:
                break
            cursor = str(next_cursor)

        within = []
        for row in list_rows:
            dt = parse_dt(row.get("created_at"))
            if dt is not None and dt >= cutoff:
                within.append(row)

        per_list.append({
            "name": list_name,
            "id": list_id,
            "pages": pages,
            "returned": returned,
            "within_window": len(within),
            "discarded_old": max(0, returned - len(within)),
            "crossed_cutoff": crossed_cutoff,
        })

    if stopped or len(per_list) != len(lists):
        raise RuntimeError(
            "Collection stopped before all lists completed: completed=%s/%s, estimated_cost_usd=%.4f"
            % (len(per_list), len(lists), billed * PRICE_PER_TWEET)
        )

    unique = {}
    for row in all_rows:
        tweet_id = row.get("tweet_id")
        if tweet_id and tweet_id not in unique:
            unique[tweet_id] = row

    posts = []
    for row in unique.values():
        dt = parse_dt(row.get("created_at"))
        if dt is not None and dt >= cutoff:
            posts.append(row)
    posts.sort(key=lambda item: item.get("created_at") or "", reverse=True)

    output = {
        "schemaVersion": 1,
        "source": "SocialData X List Tweets",
        "generatedAt": now.isoformat(),
        "windowHours": window_hours,
        "cutoffUtc": cutoff.isoformat(),
        "listsRequested": len(lists),
        "listsCompleted": len(per_list),
        "stoppedForBudget": False,
        "estimatedCostUsd": round(billed * PRICE_PER_TWEET, 6),
        "stats": {
            "billedTweets": billed,
            "uniqueTweetsInWindow": len(posts),
            "usefulRatio": round(len(posts) / billed, 4) if billed else 0.0,
            "contentMix": {
                "originals": sum(1 for item in posts if item["kind"] == "original"),
                "replies": sum(1 for item in posts if item["kind"] == "reply"),
                "direct_quotes": sum(1 for item in posts if item["kind"] == "quote"),
                "retweets": sum(1 for item in posts if item["kind"] == "retweet"),
                "posts_with_media": sum(1 for item in posts if (item.get("media") or {}).get("urls")),
            },
        },
        "perList": per_list,
        "posts": posts,
    }

    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "listsCompleted": len(per_list),
        "posts": len(posts),
        "billedTweets": billed,
        "estimatedCostUsd": output["estimatedCostUsd"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("::error::%s" % exc, file=sys.stderr)
        raise
