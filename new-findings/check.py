"""Validate public editions and preserve previously published entries."""
import argparse
import json
import re
import unicodedata
from datetime import date
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
EDITION = re.compile(r"\d{4}-\d{2}-\d{2}-\d{2}")
EVIDENCE = {"官方确认", "多人独立实测", "单一报告"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def nonempty(text):
    return isinstance(text, str) and bool(text.strip())


def source_key(url):
    parsed = urlsplit(url)
    require(parsed.scheme in {"http", "https"} and parsed.hostname, "原文链接须为 HTTP(S)")
    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith("utm_") and k.lower() not in {"gclid", "fbclid"}]
    return parsed.hostname.removeprefix("www."), parsed.path.rstrip("/"), urlencode(sorted(query))


def title_key(title):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", title).casefold())


def validate(editions):
    ids = [edition["id"] for edition in editions]
    require(ids == sorted(set(ids), reverse=True), "期号必须唯一，并按新到旧排列")
    last_topic, by_title, by_source = {}, {}, {}
    for edition in reversed(editions):
        id_ = edition["id"]
        require(EDITION.fullmatch(id_), f"{id_}：期号格式应为 YYYY-MM-DD-NN")
        require(edition["date"] == str(date.fromisoformat(id_[:10])), f"{id_}：日期与期号须一致")
        require(1 <= len(edition["items"]) <= 5, f"{id_}：每期须有 1–5 条")
        current = set()
        for item in edition["items"]:
            topic = item["id"]
            require(SLUG.fullmatch(topic) and topic not in current, f"{id_}：条目键无效或本期重复：{topic}")
            current.add(topic)
            require(all(nonempty(item.get(k)) for k in ("title", "summary", "category")), f"{topic}：缺标题、摘要或分类")
            require(item.get("evidence") in EVIDENCE, f"{topic}：缺少有效证据标签")
            require(isinstance(item.get("details", []), list) and all(map(nonempty, item.get("details", []))), f"{topic}：详情须为文本列表")
            require(isinstance(item["sources"], list) and item["sources"], f"{topic}：至少提供一个原文")
            sources = set()
            for source in item["sources"]:
                require(nonempty(source.get("title")), f"{topic}：缺来源名称")
                sources.add(source_key(source["url"]))

            if topic in last_topic:
                require(last_topic[topic] != id_ and item.get("update_of") == last_topic[topic]
                        and nonempty(item.get("what_changed")), f"{topic}：已刊。续报须指向最近一期并说明实质变化")
            else:
                require(not item.get("update_of") and not item.get("what_changed"), f"{topic}：续报找不到原条目")
            title = title_key(item["title"])
            require(title and by_title.get(title, topic) == topic, f"{topic}：换用条目键后仍与已刊标题重复")
            shared = set().union(*(by_source.get(s, set()) for s in sources)) - {topic}
            require(not shared or nonempty(item.get("why_distinct")), f"{topic}：与其他条目共用来源，须注明用途有何不同")
            for source in sources:
                by_source.setdefault(source, set()).add(topic)
            last_topic[topic] = id_
            by_title[title] = topic


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))["editions"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--previous", type=Path, help="发布前从 main 读取的当前文件")
    args = parser.parse_args()
    try:
        editions = read(args.candidate)
        if args.previous:
            previous = read(args.previous)
            require(len(editions) == len(previous) + 1 and editions[1:] == previous,
                    "每次只在文件开头新增一期。过去各期必须原样保留")
        validate(editions)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        parser.exit(1, f"检查未通过：{error}\n")
    print(f"检查通过，共 {len(editions)} 期")


if __name__ == "__main__":
    main()
