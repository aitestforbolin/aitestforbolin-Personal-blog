#!/usr/bin/env python3
"""Refresh China's official macro calendar without ever replacing valid data with empties.

The updater intentionally uses only public pages operated by the National Bureau of
Statistics, People's Bank of China, General Administration of Customs, State
Administration of Foreign Exchange and Ministry of Finance.  The National Data
internal JSON service is not used as a primary source.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen


SITE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = SITE_ROOT / "data" / "china-macro-calendar.json"
SCHEMA_VERSION = 1
SHANGHAI_SUFFIX = "+08:00"
SAMPLE_RETRIEVED_AT = "2026-08-02T10:00:00+08:00"

NBS_SCHEDULE_URL = (
    "https://www.stats.gov.cn/xxgk/sjfb/fbrcb/202512/"
    "t20251224_1962137.html"
)
NBS_RELEASE_INDEX = "https://www.stats.gov.cn/sj/zxfb/"
NBS_INTERPRETATION_INDEX = "https://www.stats.gov.cn/sj/sjjd/"
PBC_NEWS_INDEX = "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/index.html"
PBC_LPR_INDEX = (
    "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/"
    "3876551/index.html"
)
GACC_RELEASE_INDEX = (
    "https://www.customs.gov.cn/customs/302249/zfxxgk/fdzdgknr/"
    "302274/302275/index.html"
)
SAFE_RELEASE_INDEX = "https://www.safe.gov.cn/safe/index.html"
MOF_RELEASE_INDEX = (
    "https://www.mof.gov.cn/zhengwuxinxi/redianzhuanti/"
    "quanguocaizhengshouzhiqingkuang/"
)
CIBM_LPR_FALLBACK = "https://www.chinamoney.com.cn/chinese/bklpr/"

OFFICIAL_HOST_SUFFIXES = (
    "stats.gov.cn",
    "pbc.gov.cn",
    "customs.gov.cn",
    "safe.gov.cn",
    "mof.gov.cn",
    "chinamoney.com.cn",
)

SOURCE_LABELS = {
    "nbs": "国家统计局",
    "pbc": "中国人民银行",
    "gacc": "海关总署",
    "safe": "国家外汇管理局",
    "mof": "财政部",
}

GROUP_META = {
    "pmi": ("中国官方PMI", "manufacturing", "high", "nbs"),
    "prices": ("中国CPI / 核心CPI / PPI", "prices", "high", "nbs"),
    "trade": ("中国进出口与贸易差额", "external", "high", "gacc"),
    "credit": ("中国货币与融资数据", "credit", "high", "pbc"),
    "activity": (
        "中国工业 / 社零 / 投资 / 房地产 / 失业率",
        "activity",
        "critical",
        "nbs",
    ),
    "housing": ("中国70城房价", "housing", "medium", "nbs"),
    "lpr": ("中国贷款市场报价利率（LPR）", "monetary_policy", "high", "pbc"),
    "reserves": ("中国外汇储备", "reserves", "medium", "safe"),
    "fiscal": ("中国财政收支", "fiscal", "medium", "mof"),
    "profits": ("中国规模以上工业企业利润", "profits", "medium", "nbs"),
}

NBS_EXACT_RELEASES = {
    "pmi": [
        ("2026-07", "2026-07-31T09:30:00+08:00"),
        ("2026-08", "2026-08-31T09:30:00+08:00"),
        ("2026-09", "2026-09-30T09:30:00+08:00"),
        ("2026-10", "2026-10-31T09:30:00+08:00"),
        ("2026-11", "2026-11-30T09:30:00+08:00"),
        ("2026-12", "2026-12-31T09:30:00+08:00"),
    ],
    "prices": [
        ("2026-07", "2026-08-09T09:30:00+08:00"),
        ("2026-08", "2026-09-09T09:30:00+08:00"),
        ("2026-09", "2026-10-14T09:30:00+08:00"),
        ("2026-10", "2026-11-09T09:30:00+08:00"),
        ("2026-11", "2026-12-09T09:30:00+08:00"),
    ],
    "activity": [
        ("2026-07", "2026-08-17T10:00:00+08:00"),
        ("2026-08", "2026-09-15T10:00:00+08:00"),
        ("2026-09", "2026-10-19T10:00:00+08:00"),
        ("2026-10", "2026-11-16T10:00:00+08:00"),
        ("2026-11", "2026-12-15T10:00:00+08:00"),
    ],
    "housing": [
        ("2026-07", "2026-08-17T09:30:00+08:00"),
        ("2026-08", "2026-09-15T09:30:00+08:00"),
        ("2026-09", "2026-10-19T09:30:00+08:00"),
        ("2026-10", "2026-11-16T09:30:00+08:00"),
        ("2026-11", "2026-12-15T09:30:00+08:00"),
    ],
    "profits": [
        ("2026-01/07", "2026-08-27T09:30:00+08:00"),
        ("2026-01/08", "2026-09-28T09:30:00+08:00"),
        ("2026-01/09", "2026-10-27T09:30:00+08:00"),
        ("2026-01/10", "2026-11-27T09:30:00+08:00"),
        ("2026-01/11", "2026-12-27T09:30:00+08:00"),
    ],
}

SAMPLE_URLS = {
    "pmi": "https://www.stats.gov.cn/sj/zxfb/202607/t20260731_1964253.html",
    "prices": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964121.html",
    "trade": (
        "https://www.customs.gov.cn/customs/2026-07/14/"
        "article_2026071409283860670.html"
    ),
    "credit": (
        "https://www.pbc.gov.cn/goutongjiaoliu/113456/113469/"
        "2026071512340454869/index.html"
    ),
    "activity": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964121.html",
    "housing": "https://www.stats.gov.cn/sj/sjjd/202607/t20260715_1964114.html",
    "lpr": (
        "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/"
        "3876551/2026072008093186869/index.html"
    ),
    "reserves": "https://www.safe.gov.cn/safe/2026/0706/27661.html",
    "fiscal": "https://m.mof.gov.cn/czsj/202607/t20260722_3993943.htm",
    "profits": "https://www.stats.gov.cn/sj/zxfb/202607/t20260727_1964194.html",
}

SAMPLE_PREVIOUS = {
    "pmi": {
        "manufacturing_pmi": (None, "49.2"),
        "non_manufacturing_pmi": (None, "49.0"),
        "composite_pmi": (None, "49.3"),
    },
    "prices": {
        "cpi_yoy": (None, "1.0"),
        "core_cpi_yoy": (None, "1.0"),
        "ppi_yoy": (None, "4.1"),
    },
    "trade": {
        "exports": (None, "4123.9"),
        "imports": (None, "2867.6"),
        "trade_balance": (None, "1256.3"),
    },
    "credit": {
        "m1_yoy": (None, "4.0"),
        "m2_yoy": (None, "8.0"),
        "new_yuan_loans": (None, "10.72"),
        "tsf_increment": (None, "20.84"),
    },
    "activity": {
        "industrial_output_yoy": (None, "5.3"),
        "retail_sales_yoy": (None, "1.0"),
        "fixed_asset_investment_ytd": (None, "-5.7"),
        "property_investment_ytd": (None, "-18.0"),
        "surveyed_unemployment": (None, "5.0"),
    },
    "housing": {
        "tier1_new_home_mom": (None, "0.1"),
        "tier2_new_home_mom": (None, "0.0"),
        "tier3_new_home_mom": (None, "-0.3"),
        "tier1_resale_mom": (None, "0.3"),
        "tier2_resale_mom": (None, "-0.3"),
        "tier3_resale_mom": (None, "-0.4"),
    },
    "lpr": {
        "lpr_1y": (None, "3.0"),
        "lpr_5y": (None, "3.5"),
    },
    "reserves": {"fx_reserves": (None, "34163")},
    "fiscal": {
        "general_revenue": (None, "121047"),
        "general_revenue_yoy": (None, "4.7"),
        "general_spending": (None, "143329"),
        "general_spending_yoy": (None, "1.5"),
    },
    "profits": {
        "industrial_profits_ytd": (None, "18.7"),
        "industrial_profits_monthly": (None, "15.1"),
    },
}

SAMPLE_RELEASED_PMI = {
    "manufacturing_pmi": ("49.2", "50.3"),
    "non_manufacturing_pmi": ("49.0", "50.2"),
    "composite_pmi": ("49.3", "50.6"),
}

METRIC_SOURCE_URLS = {
    "cpi_yoy": "https://www.stats.gov.cn/sj/zxfb/202607/t20260709_1964084.html",
    "core_cpi_yoy": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964121.html",
    "ppi_yoy": "https://www.stats.gov.cn/sj/zxfb/202607/t20260709_1964083.html",
    "industrial_output_yoy": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964123.html",
    "retail_sales_yoy": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964127.html",
    "fixed_asset_investment_ytd": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964124.html",
    "property_investment_ytd": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964126.html",
    "surveyed_unemployment": "https://www.stats.gov.cn/sj/zxfb/202607/t20260715_1964121.html",
}

SOURCE_INDEX_URLS = {
    "nbs": NBS_SCHEDULE_URL,
    "pbc": PBC_NEWS_INDEX,
    "gacc": GACC_RELEASE_INDEX,
    "safe": SAFE_RELEASE_INDEX,
    "mof": MOF_RELEASE_INDEX,
}

METRIC_META = {
    "manufacturing_pmi": ("制造业PMI", "指数"),
    "non_manufacturing_pmi": ("非制造业商务活动指数", "指数"),
    "composite_pmi": ("综合PMI产出指数", "指数"),
    "cpi_yoy": ("CPI同比", "%"),
    "core_cpi_yoy": ("核心CPI同比", "%"),
    "ppi_yoy": ("PPI同比", "%"),
    "exports": ("出口", "亿美元"),
    "imports": ("进口", "亿美元"),
    "trade_balance": ("贸易差额", "亿美元"),
    "m1_yoy": ("M1同比", "%"),
    "m2_yoy": ("M2同比", "%"),
    "new_yuan_loans": ("人民币贷款累计新增", "万亿元"),
    "tsf_increment": ("社融增量累计", "万亿元"),
    "industrial_output_yoy": ("规模以上工业增加值同比", "%"),
    "retail_sales_yoy": ("社会消费品零售总额同比", "%"),
    "fixed_asset_investment_ytd": ("固定资产投资累计同比", "%"),
    "property_investment_ytd": ("房地产开发投资累计同比", "%"),
    "surveyed_unemployment": ("全国城镇调查失业率", "%"),
    "tier1_new_home_mom": ("一线新房环比", "%"),
    "tier2_new_home_mom": ("二线新房环比", "%"),
    "tier3_new_home_mom": ("三线新房环比", "%"),
    "tier1_resale_mom": ("一线二手房环比", "%"),
    "tier2_resale_mom": ("二线二手房环比", "%"),
    "tier3_resale_mom": ("三线二手房环比", "%"),
    "lpr_1y": ("1年期LPR", "%"),
    "lpr_5y": ("5年期以上LPR", "%"),
    "fx_reserves": ("外汇储备规模", "亿美元"),
    "general_revenue": ("一般公共预算收入", "亿元"),
    "general_revenue_yoy": ("一般公共预算收入同比", "%"),
    "general_spending": ("一般公共预算支出", "亿元"),
    "general_spending_yoy": ("一般公共预算支出同比", "%"),
    "industrial_profits_ytd": ("规模以上工业企业利润累计同比", "%"),
    "industrial_profits_monthly": ("规模以上工业企业利润当月同比", "%"),
}


@dataclass(frozen=True)
class Release:
    group: str
    period: str
    released_at: str | None
    source_url: str
    metrics: dict[str, str]


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)


class LinkExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.current_href = urljoin(self.base_url, href)
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current_href:
            text = " ".join("".join(self.current_text).split())
            if text:
                self.links.append((text, self.current_href))
            self.current_href = None
            self.current_text = []


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(parser.parts)


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    parser = LinkExtractor(base_url)
    parser.feed(html)
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    for title, url in parser.links:
        if url not in seen and is_official_url(url):
            result.append((title, url))
            seen.add(url)
    return result


def is_official_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    return any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in OFFICIAL_HOST_SUFFIXES)


def fetch_text(url: str, timeout: int = 20) -> str:
    if not is_official_url(url):
        raise ValueError(f"Refusing non-official URL: {url}")
    request = Request(
        url,
        headers={
            "User-Agent": "bolin-brief-official-macro-calendar/1.0 (+https://github.com/)"
        },
    )
    with urlopen(request, timeout=timeout) as response:
        final_url = response.geturl()
        if not is_official_url(final_url):
            raise ValueError(f"Official URL redirected outside the allowlist: {final_url}")
        body = response.read()
        declared_encoding = response.headers.get_content_charset()
    encodings = [declared_encoding] if declared_encoding else []
    encodings.extend(["utf-8", "gb18030"])
    for encoding in dict.fromkeys(encodings):
        try:
            return body.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return body.decode("utf-8", errors="replace")


def normalize_stat_text(text: str) -> str:
    text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", text)
    return re.sub(r"(?<=\d)\s*(?=%)", "", text)


def signed_value(direction: str | None, number: str) -> str:
    normalized = number.replace(",", "")
    if direction in {"下降", "减少", "下跌"} and not normalized.startswith("-"):
        return f"-{normalized}"
    return normalized


def first_match(text: str, pattern: str, flags: int = 0) -> str | None:
    match = re.search(pattern, text, flags)
    return match.group(1) if match else None


def directional_match(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text)
    if not match:
        return None
    return signed_value(match.group(1), match.group(2))


def month_period(text: str) -> str | None:
    match = re.search(r"(20\d{2})年(?:上半年|1[—-]6月)", text)
    if match:
        return f"{match.group(1)}-01/06"
    match = re.search(r"(20\d{2})年1[—-](\d{1,2})月", text)
    if match:
        return f"{match.group(1)}-01/{int(match.group(2)):02d}"
    match = re.search(r"(20\d{2})年一季度", text)
    if match:
        return f"{match.group(1)}-01/03"
    match = re.search(r"(20\d{2})年前三季度", text)
    if match:
        return f"{match.group(1)}-01/09"
    match = re.search(r"(20\d{2})年(\d{1,2})月(?:份|末)?", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return None


def period_from_release_date(text: str, series: str, *, same_month: bool = False) -> str | None:
    stated_period = month_period(text[:1200])
    if stated_period:
        return stated_period
    match = re.search(
        r"(?:发布日期\s*[:：]\s*)?(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})日?",
        text[:4000],
    )
    if match:
        release_year, release_month = map(int, match.groups()[:2])
        if same_month:
            return f"{release_year}-{release_month:02d}"
        return period_for_release(series, release_year, release_month)
    return month_period(text)


def release_timestamp(text: str) -> str | None:
    match = re.search(
        r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})日?\s+(\d{1,2}):(\d{2})",
        text,
    )
    if not match:
        return None
    year, month, day, hour, minute = map(int, match.groups())
    return f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:00{SHANGHAI_SUFFIX}"


def period_for_release(series: str, release_year: int, release_month: int) -> str:
    """Return the reporting period, including China's January-February convention."""
    combined = {"activity", "trade"}
    if series in combined and release_month == 3:
        return f"{release_year}-01/02"
    reporting_month = 12 if release_month == 1 else release_month - 1
    reporting_year = release_year - 1 if release_month == 1 else release_year
    if series in {"profits", "fiscal"} and reporting_month >= 2:
        return f"{reporting_year}-01/{reporting_month:02d}"
    return f"{reporting_year}-{reporting_month:02d}"


def parse_nbs_pmi(text: str, source_url: str = SAMPLE_URLS["pmi"]) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "pmi", same_month=True)
    values = {
        "manufacturing_pmi": first_match(
            text,
            r"制造业采购经理指数(?:[（(]\s*PMI\s*[）)])?为\s*([\d.]+)%",
        ),
        "non_manufacturing_pmi": first_match(text, r"非制造业商务活动指数为\s*([\d.]+)%"),
        "composite_pmi": first_match(text, r"综合\s*PMI\s*产出指数为\s*([\d.]+)%"),
    }
    metrics = {key: value for key, value in values.items() if value is not None}
    if not period or not metrics:
        raise ValueError("NBS PMI page did not contain a period and headline values")
    return Release("pmi", period, release_timestamp(text), source_url, metrics)


def parse_nbs_prices(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "prices")
    values = {
        "cpi_yoy": directional_match(
            text,
            r"全国居民消费价格(?:（\s*CPI\s*）)?同比(上涨|下降|持平)\s*([\d.]+)%",
        ),
        "core_cpi_yoy": directional_match(
            text,
            r"\d{1,2}\s*月份?核心\s*CPI\s*同比(上涨|下降|持平)\s*([\d.]+)%",
        ),
        "ppi_yoy": directional_match(
            text,
            r"工业生产者出厂价格(?:（\s*PPI\s*）)?同比(上涨|下降|持平)\s*([\d.]+)%",
        ),
    }
    metrics = {key: value for key, value in values.items() if value is not None}
    if not period or not metrics:
        raise ValueError("NBS price page did not contain a period and CPI/PPI values")
    return Release("prices", period, release_timestamp(text), source_url, metrics)


def parse_nbs_activity(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "activity")
    values = {
        "industrial_output_yoy": directional_match(
            text,
            r"\d{1,2}\s*月份?[，,]?\s*规模以上工业增加值同比(?:实际)?(增长|下降)\s*([\d.]+)%",
        ),
        "retail_sales_yoy": directional_match(
            text,
            r"\d{1,2}\s*月份?[，,]?\s*社会消费品零售总额[^。]{0,80}?同比(增长|下降)\s*([\d.]+)%",
        ),
        "fixed_asset_investment_ytd": directional_match(
            text,
            r"固定资产投资（不含农户）[^。]{0,80}?同比(增长|下降)\s*([\d.]+)%",
        ),
        "property_investment_ytd": directional_match(
            text, r"房地产开发投资[^。]{0,80}?(?:同比)?(增长|下降)\s*([\d.]+)%"
        ),
        "surveyed_unemployment": first_match(
            text, r"全国城镇调查失业率为\s*([\d.]+)%"
        ),
    }
    metrics = {key: value for key, value in values.items() if value is not None}
    if not period or not metrics:
        raise ValueError("NBS activity page did not contain a period and activity values")
    if "/" in period:
        year, end_month = period.split("-01/")
        period = f"{year}-{end_month}"
    return Release("activity", period, release_timestamp(text), source_url, metrics)


def parse_nbs_housing(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "housing")
    patterns = {
        "tier1_new_home_mom": r"一线城市新建商品住宅销售价格环比(上涨|下降|持平)\s*([\d.]+)%",
        "tier2_new_home_mom": r"二线城市新建商品住宅销售价格环比(?:由上月[^。]{0,20})?(上涨|下降|持平)?\s*([\d.]+)%?",
        "tier3_new_home_mom": r"三线城市新建商品住宅销售价格环比(上涨|下降|持平)\s*([\d.]+)%",
        "tier1_resale_mom": r"一线城市二手住宅销售价格环比(上涨|下降|持平)\s*([\d.]+)%",
        "tier2_resale_mom": r"二线城市二手住宅销售价格环比(上涨|下降|持平)\s*([\d.]+)%",
        "tier3_resale_mom": r"三线城市二手住宅销售价格环比(上涨|下降|持平)\s*([\d.]+)%",
    }
    metrics: dict[str, str] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            direction = match.group(1) or "持平"
            value = "0.0" if direction == "持平" else match.group(2)
            metrics[key] = signed_value(direction, value)
    if re.search(r"二线城市新建商品住宅销售价格环比[^。]{0,40}?转为持平", text):
        metrics["tier2_new_home_mom"] = "0.0"
    if not period or not metrics:
        raise ValueError("NBS housing page did not contain a period and city-tier values")
    return Release("housing", period, release_timestamp(text), source_url, metrics)


def parse_nbs_profits(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "profits")
    values = {
        "industrial_profits_ytd": directional_match(
            text,
            r"规模以上工业企业(?:实现)?利润(?:总额)?[^。]{0,80}?同比(增长|下降)\s*([\d.]+)%",
        ),
        "industrial_profits_monthly": directional_match(
            text,
            r"\d{1,2}\s*月份[^。]{0,30}?规模以上工业企业利润同比(增长|下降)\s*([\d.]+)%",
        ),
    }
    metrics = {key: value for key, value in values.items() if value is not None}
    if not period or not metrics:
        raise ValueError("NBS profit page did not contain a period and profit values")
    if "/" not in period:
        year, month = period.split("-")
        period = f"{year}-01/{month}"
    return Release("profits", period, release_timestamp(text), source_url, metrics)


def parse_pbc_financial(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "credit")
    values = {
        "m1_yoy": first_match(
            text,
            r"狭义货币(?:供应量)?\s*[(（]?M1[)）]?[^。]{0,50}?同比增长\s*([\d.]+)%",
        ),
        "m2_yoy": first_match(
            text,
            r"广义货币(?:供应量)?\s*[(（]?M2[)）]?[^。]{0,50}?同比增长\s*([\d.]+)%",
        ),
        "new_yuan_loans": first_match(
            text,
            r"(?:上半年|前\d+个月|1[—-]\d{1,2}月|当月|\d{1,2}月份)[，,]?\s*人民币贷款(?:增加|新增)\s*([\d.]+)万亿元",
        ),
        "tsf_increment": first_match(
            text,
            r"(?:当月|\d{1,2}月份)?社会融资规模增量(?:累计)?(?:为|约为)\s*([\d.]+)万亿元",
        ),
    }
    metrics = {key: value for key, value in values.items() if value is not None}
    if not period or not metrics:
        raise ValueError("PBC financial report did not contain a period and headline values")
    if "/" in period:
        year, end_month = period.split("-01/")
        period = f"{year}-{end_month}"
    return Release("credit", period, release_timestamp(text), source_url, metrics)


def parse_pbc_lpr(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "lpr", same_month=True)
    values = {
        "lpr_1y": first_match(text, r"1年期LPR为\s*([\d.]+)%"),
        "lpr_5y": first_match(text, r"5年期以上LPR为\s*([\d.]+)%"),
    }
    metrics = {key: value for key, value in values.items() if value is not None}
    if not period or len(metrics) != 2:
        raise ValueError("PBC LPR announcement did not contain both tenors")
    return Release("lpr", period, release_timestamp(text), source_url, metrics)


def parse_gacc_trade(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "trade")
    values = {
        "exports": first_match(text, r"出口总值\s*([\d,.]+)"),
        "imports": first_match(text, r"进口总值\s*([\d,.]+)"),
        "trade_balance": first_match(text, r"进出口差额\s*([\d,.-]+)"),
    }
    metrics = {
        key: value.replace(",", "") for key, value in values.items() if value is not None
    }
    if not period or not metrics:
        raise ValueError("Customs table did not contain a period and trade values")
    return Release("trade", period, release_timestamp(text), source_url, metrics)


def parse_safe_reserves(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "reserves")
    value = first_match(text, r"外汇储备规模为\s*([\d,.]+)\s*亿美元")
    if not period or not value:
        raise ValueError("SAFE page did not contain a period and reserve value")
    return Release(
        "reserves",
        period,
        release_timestamp(text),
        source_url,
        {"fx_reserves": value.replace(",", "")},
    )


def parse_mof_fiscal(text: str, source_url: str) -> Release:
    text = normalize_stat_text(text)
    period = period_from_release_date(text, "fiscal")
    revenue = re.search(
        r"全国一般公共预算收入\s*([\d,]+)\s*亿元\s*[，,]\s*同比(增长|下降)\s*([\d.]+)%",
        text,
    )
    spending = re.search(
        r"全国一般公共预算支出\s*([\d,]+)\s*亿元\s*[，,]\s*同比(增长|下降)\s*([\d.]+)%",
        text,
    )
    metrics: dict[str, str] = {}
    if revenue:
        metrics["general_revenue"] = revenue.group(1).replace(",", "")
        metrics["general_revenue_yoy"] = signed_value(revenue.group(2), revenue.group(3))
    if spending:
        metrics["general_spending"] = spending.group(1).replace(",", "")
        metrics["general_spending_yoy"] = signed_value(spending.group(2), spending.group(3))
    if not period or not metrics:
        raise ValueError("MOF page did not contain a period and fiscal values")
    return Release("fiscal", period, release_timestamp(text), source_url, metrics)


def metric_list(group: str, actual_previous: dict[str, tuple[str | None, str | None]]) -> list[dict]:
    metrics: list[dict] = []
    for metric_id, (actual, previous) in actual_previous.items():
        label, unit = METRIC_META[metric_id]
        metrics.append(
            {
                "id": metric_id,
                "label": label,
                "actual": actual,
                "previous": previous,
                "unit": unit,
                "sourceUrl": METRIC_SOURCE_URLS.get(metric_id, SAMPLE_URLS[group]),
            }
        )
    return metrics


def make_event(
    group: str,
    period: str,
    *,
    scheduled_at: str | None = None,
    expected_window: tuple[str, str] | None = None,
    actual_previous: dict[str, tuple[str | None, str | None]] | None = None,
    released_at: str | None = None,
) -> dict:
    title, category, importance, provider = GROUP_META[group]
    if scheduled_at:
        date_status = "confirmed"
    elif expected_window:
        date_status = "expected_window"
    else:
        date_status = "date_tbd"
    upcoming_source_url = PBC_LPR_INDEX if group == "lpr" else SOURCE_INDEX_URLS[provider]
    event = {
        "id": f"cn-{group}-{period.replace('/', '-')}",
        "country": "CN",
        "period": period,
        "scheduledAt": scheduled_at,
        "dateStatus": date_status,
        "title": title,
        "category": category,
        "importance": importance,
        "source": SOURCE_LABELS[provider],
        "sourceUrl": SAMPLE_URLS[group] if released_at else upcoming_source_url,
        "metrics": metric_list(group, actual_previous or SAMPLE_PREVIOUS[group]),
        "releasedAt": released_at,
        "retrievedAt": SAMPLE_RETRIEVED_AT,
        "revisionStatus": "not_revised",
        "releaseStatus": "released" if released_at else "scheduled",
        "sourceStatus": "static_official_sample",
        "group": group,
    }
    if expected_window:
        event["expectedWindow"] = {
            "start": expected_window[0],
            "end": expected_window[1],
            "timezone": "Asia/Shanghai",
        }
    if group in {"pmi", "prices", "activity", "housing", "profits"}:
        event["scheduleSourceUrl"] = NBS_SCHEDULE_URL
    if group == "lpr":
        event["fallbackSourceUrl"] = CIBM_LPR_FALLBACK
    return event


def monthly_windows(
    group: str,
    periods: Iterable[str],
    release_months: Iterable[int],
    start_day: int,
    end_day: int,
) -> list[dict]:
    events: list[dict] = []
    for period, release_month in zip(periods, release_months):
        year = 2026
        events.append(
            make_event(
                group,
                period,
                expected_window=(
                    f"{year}-{release_month:02d}-{start_day:02d}",
                    f"{year}-{release_month:02d}-{end_day:02d}",
                ),
            )
        )
    return events


def build_static_calendar() -> list[dict]:
    events: list[dict] = []
    for group, releases in NBS_EXACT_RELEASES.items():
        for period, scheduled_at in releases:
            if group == "pmi" and period == "2026-07":
                events.append(
                    make_event(
                        group,
                        period,
                        scheduled_at=scheduled_at,
                        actual_previous=SAMPLE_RELEASED_PMI,
                        released_at=scheduled_at,
                    )
                )
            else:
                events.append(make_event(group, period, scheduled_at=scheduled_at))

    report_periods = ["2026-07", "2026-08", "2026-09", "2026-10", "2026-11"]
    release_months = [8, 9, 10, 11, 12]
    events.extend(monthly_windows("trade", report_periods, release_months, 7, 14))
    events.extend(monthly_windows("credit", report_periods, release_months, 9, 15))
    events.extend(monthly_windows("reserves", report_periods, release_months, 6, 8))
    events.extend(
        monthly_windows(
            "fiscal",
            ["2026-01/07", "2026-01/08", "2026-01/09", "2026-01/10", "2026-01/11"],
            release_months,
            15,
            25,
        )
    )
    events.extend(
        monthly_windows(
            "lpr",
            ["2026-08", "2026-09", "2026-10", "2026-11", "2026-12"],
            release_months,
            20,
            22,
        )
    )
    return sorted(events, key=event_sort_key)


def event_sort_key(event: dict) -> tuple[str, str]:
    scheduled = event.get("scheduledAt")
    if scheduled:
        return scheduled, event["id"]
    window = event.get("expectedWindow") or {}
    return f"{window.get('start', '9999-12-31')}T23:59:59+08:00", event["id"]


def route_release(provider: str, title: str, html: str, url: str) -> list[Release]:
    text = html_to_text(html)
    combined = f"{title} {text}"
    releases: list[Release] = []
    if provider == "nbs":
        if "采购经理指数" in title:
            releases.append(parse_nbs_pmi(combined, url))
        elif "居民消费价格" in title or "工业生产者出厂价格" in title:
            releases.append(parse_nbs_prices(combined, url))
        elif "70个大中城市" in title or "商品住宅销售价格变动情况" in title:
            releases.append(parse_nbs_housing(combined, url))
        elif "工业企业利润" in title:
            releases.append(parse_nbs_profits(combined, url))
        elif any(
            needle in title
            for needle in (
                "国民经济运行",
                "规模以上工业增加值",
                "固定资产投资",
                "房地产市场基本情况",
                "社会消费品零售总额",
            )
        ):
            activity_release = parse_nbs_activity(combined, url)
            releases.append(activity_release)
            if "国民经济运行" in title:
                try:
                    price_release = parse_nbs_prices(combined, url)
                    core_value = price_release.metrics.get("core_cpi_yoy")
                    if core_value is not None:
                        releases.append(
                            Release(
                                "prices",
                                activity_release.period,
                                price_release.released_at,
                                price_release.source_url,
                                {"core_cpi_yoy": core_value},
                            )
                        )
                except ValueError:
                    # Some headline releases include core CPI, while others do not.
                    pass
    elif provider == "pbc":
        if "金融统计数据报告" in title or "金融统计数据情况" in title:
            releases.append(parse_pbc_financial(combined, url))
        elif "贷款市场报价利率" in title or "LPR" in title:
            releases.append(parse_pbc_lpr(combined, url))
    elif provider == "gacc" and "全国进出口总值表" in title and "美元值" in title:
        releases.append(parse_gacc_trade(combined, url))
    elif provider == "safe" and "外汇储备规模数据" in title:
        releases.append(parse_safe_reserves(combined, url))
    elif provider == "mof" and "财政收支情况" in title:
        releases.append(parse_mof_fiscal(combined, url))
    return releases


PROVIDER_LISTINGS = {
    "nbs": [NBS_INTERPRETATION_INDEX, NBS_RELEASE_INDEX],
    "pbc_credit": [PBC_NEWS_INDEX],
    "pbc_lpr": [PBC_LPR_INDEX],
    "gacc": [GACC_RELEASE_INDEX],
    "safe": [SAFE_RELEASE_INDEX],
    "mof": [MOF_RELEASE_INDEX],
}

PROVIDER_TITLE_NEEDLES = {
    "nbs": (
        "采购经理指数",
        "居民消费价格",
        "工业生产者出厂价格",
        "规模以上工业增加值",
        "固定资产投资",
        "房地产市场基本情况",
        "社会消费品零售总额",
        "70个大中城市",
        "商品住宅销售价格变动情况",
        "工业企业利润",
        "国民经济运行",
    ),
    "pbc_credit": ("金融统计数据报告", "金融统计数据情况"),
    "pbc_lpr": ("贷款市场报价利率", "LPR"),
    "gacc": ("全国进出口总值表（美元值）",),
    "safe": ("外汇储备规模数据",),
    "mof": ("财政收支情况",),
}

PROVIDER_BASE = {
    "pbc_credit": "pbc",
    "pbc_lpr": "pbc",
}

EXPECTED_PROVIDER_GROUPS = {
    "nbs": {"pmi", "prices", "activity", "housing", "profits"},
    "pbc_credit": {"credit"},
    "pbc_lpr": {"lpr"},
    "gacc": {"trade"},
    "safe": {"reserves"},
    "mof": {"fiscal"},
}

EXPECTED_PROVIDER_METRICS = {
    provider: {
        metric_id
        for group in groups
        for metric_id in SAMPLE_PREVIOUS[group]
    }
    for provider, groups in EXPECTED_PROVIDER_GROUPS.items()
}

PROVIDER_DIRECT_PAGES = {
    "nbs": [
        ("2026年7月中国采购经理指数运行情况", SAMPLE_URLS["pmi"]),
        ("2026年6月份居民消费价格同比上涨1.0%", METRIC_SOURCE_URLS["cpi_yoy"]),
        (
            "2026年6月份工业生产者出厂价格同比上涨4.1%",
            METRIC_SOURCE_URLS["ppi_yoy"],
        ),
        ("2026年上半年国民经济运行总体平稳", SAMPLE_URLS["activity"]),
        ("2026年6月份商品住宅销售价格变动情况", SAMPLE_URLS["housing"]),
        ("2026年1—6月份工业企业利润", SAMPLE_URLS["profits"]),
    ],
    "pbc_credit": [("2026年6月金融统计数据报告", SAMPLE_URLS["credit"])],
}

PROVIDER_PAGE_LIMITS = {
    "nbs": 6,
    "pbc_credit": 3,
    "pbc_lpr": 2,
    "gacc": 2,
    "safe": 2,
    "mof": 2,
}


def select_candidate_pages(
    provider: str,
    candidates: list[tuple[str, str]],
    max_pages: int,
) -> list[tuple[str, str]]:
    if provider != "nbs":
        return candidates[:max_pages]

    selected: list[tuple[str, str]] = []

    def page_rank(item: tuple[str, str]) -> str:
        dates = re.findall(r"20\d{6}", item[1])
        return max(dates, default="")

    def pick(title_needle: str, preferred_path: str) -> None:
        matches = [item for item in candidates if title_needle in item[0]]
        preferred = [item for item in matches if preferred_path in item[1]]
        ordered = sorted(preferred, key=page_rank, reverse=True) + sorted(
            matches, key=page_rank, reverse=True
        )
        for item in ordered:
            if item not in selected:
                selected.append(item)
                return

    pick("采购经理指数", "/sj/zxfb/")
    pick("居民消费价格", "/sj/zxfb/")
    pick("工业生产者出厂价格", "/sj/zxfb/")
    pick("国民经济运行", "/sj/zxfb/")
    pick("商品住宅销售价格变动情况", "/sj/sjjd/")
    pick("工业企业利润", "/sj/zxfb/")
    return (selected or candidates)[:max_pages]


def collect_provider(
    provider: str,
    fetcher: Callable[[str], str] = fetch_text,
    max_pages: int | None = None,
) -> list[Release]:
    max_pages = max_pages or PROVIDER_PAGE_LIMITS[provider]
    candidates: list[tuple[str, str]] = list(PROVIDER_DIRECT_PAGES.get(provider, []))
    listing_errors: list[str] = []
    for listing_url in PROVIDER_LISTINGS[provider]:
        try:
            listing_html = fetcher(listing_url)
            candidates.extend(
                item
                for item in extract_links(listing_html, listing_url)
                if item[1].rstrip("/") != listing_url.rstrip("/")
            )
        except Exception as exc:  # noqa: BLE001 - provider errors are reported and isolated.
            listing_errors.append(f"{listing_url}: {exc}")

    needles = PROVIDER_TITLE_NEEDLES[provider]
    selected: list[tuple[str, str]] = []
    seen_urls: set[str] = set()
    for item in candidates:
        if item[1] in seen_urls or not any(needle in item[0] for needle in needles):
            continue
        selected.append(item)
        seen_urls.add(item[1])
    if not selected and provider != "pbc_lpr":
        detail = "; ".join(listing_errors) or "no matching official links"
        raise RuntimeError(f"{provider}: {detail}")

    releases: list[Release] = []
    parse_errors: list[str] = []
    pages = select_candidate_pages(provider, selected, max_pages)
    fetched_pages: dict[int, str] = {}
    if pages:
        with ThreadPoolExecutor(max_workers=min(4, len(pages))) as pool:
            pending = {
                pool.submit(fetcher, url): (index, title, url)
                for index, (title, url) in enumerate(pages)
            }
            for future in as_completed(pending):
                index, title, url = pending[future]
                try:
                    fetched_pages[index] = future.result()
                except Exception as exc:  # noqa: BLE001 - one page failure is isolated.
                    parse_errors.append(f"{title}: {exc}")

    for index, (title, url) in enumerate(pages):
        if index not in fetched_pages:
            continue
        try:
            releases.extend(
                route_release(
                    PROVIDER_BASE.get(provider, provider),
                    title,
                    fetched_pages[index],
                    url,
                )
            )
        except Exception as exc:  # noqa: BLE001 - one malformed page must not erase a source.
            parse_errors.append(f"{title}: {exc}")
    if provider == "pbc_lpr" and not releases:
        try:
            fallback_html = fetcher(CIBM_LPR_FALLBACK)
            fallback_links = extract_links(fallback_html, CIBM_LPR_FALLBACK)
            for title, url in fallback_links[:max_pages]:
                if "LPR" in title or "贷款市场报价利率" in title:
                    releases.extend(route_release("pbc", title, fetcher(url), url))
            if not releases:
                releases.extend(
                    route_release("pbc", "LPR", fallback_html, CIBM_LPR_FALLBACK)
                )
        except Exception as exc:  # noqa: BLE001 - fallback failure is surfaced below.
            parse_errors.append(f"中国货币网LPR备用源: {exc}")
    if not releases:
        raise RuntimeError(f"{provider}: no pages parsed; {'; '.join(parse_errors[:3])}")
    missing_groups = EXPECTED_PROVIDER_GROUPS[provider] - {
        release.group for release in releases
    }
    if missing_groups:
        raise RuntimeError(f"{provider}: missing release groups {sorted(missing_groups)}")
    found_metrics = {
        metric_id for release in releases for metric_id in release.metrics
    }
    missing_metrics = EXPECTED_PROVIDER_METRICS[provider] - found_metrics
    if missing_metrics:
        raise RuntimeError(f"{provider}: missing metrics {sorted(missing_metrics)}")
    return releases


def merge_metric_values(event: dict, release: Release, retrieved_at: str) -> bool:
    changed = False
    by_id = {metric["id"]: metric for metric in event.get("metrics", [])}
    for metric_id, value in release.metrics.items():
        if metric_id not in by_id:
            label, unit = METRIC_META[metric_id]
            metric = {
                "id": metric_id,
                "label": label,
                "actual": None,
                "previous": None,
                "unit": unit,
                "sourceUrl": release.source_url,
            }
            event.setdefault("metrics", []).append(metric)
            by_id[metric_id] = metric
        metric = by_id[metric_id]
        old_actual = metric.get("actual")
        if old_actual not in (None, "") and old_actual != value:
            event["revisionStatus"] = "revised"
            metric["revisionStatus"] = "revised"
        if old_actual != value or metric.get("sourceUrl") != release.source_url:
            metric["actual"] = value
            metric["sourceUrl"] = release.source_url
            changed = True

    if changed:
        event["sourceUrl"] = release.source_url
        if urlparse(release.source_url).hostname == "www.chinamoney.com.cn":
            event["source"] = "中国货币网（LPR备用）"
        event["releasedAt"] = release.released_at or event.get("scheduledAt")
        event["releaseStatus"] = "released"
        event["sourceStatus"] = "fresh"
        event["retrievedAt"] = retrieved_at
        if release.released_at:
            event["scheduledAt"] = release.released_at
            event["dateStatus"] = "confirmed"
            event.pop("expectedWindow", None)
    return changed


def carry_release_to_next_event(events: list[dict], release: Release) -> bool:
    same_group = sorted(
        [event for event in events if event.get("group") == release.group],
        key=lambda event: event.get("period", ""),
    )
    future = [event for event in same_group if event.get("period", "") > release.period]
    if not future:
        return False
    changed = False
    by_id = {metric["id"]: metric for metric in future[0].get("metrics", [])}
    for metric_id, value in release.metrics.items():
        metric = by_id.get(metric_id)
        if metric and metric.get("previous") != value:
            metric["previous"] = value
            metric["previousPeriod"] = release.period
            metric["sourceUrl"] = release.source_url
            changed = True
    return changed


def add_released_event(events: list[dict], release: Release) -> dict:
    prior_events = sorted(
        [
            event
            for event in events
            if event.get("group") == release.group
            and event.get("period", "") < release.period
        ],
        key=lambda event: event.get("period", ""),
        reverse=True,
    )
    previous_by_metric: dict[str, str | None] = {}
    for metric_id in SAMPLE_PREVIOUS[release.group]:
        previous_by_metric[metric_id] = None
        for event in prior_events:
            metric = next(
                (item for item in event.get("metrics", []) if item.get("id") == metric_id),
                None,
            )
            if not metric:
                continue
            value = metric.get("actual") or metric.get("previous")
            if value not in (None, ""):
                previous_by_metric[metric_id] = value
                break

    event = make_event(
        release.group,
        release.period,
        scheduled_at=release.released_at,
        actual_previous={
            metric_id: (None, previous_by_metric[metric_id])
            for metric_id in SAMPLE_PREVIOUS[release.group]
        },
    )
    events.append(event)
    return event


def apply_releases(events: list[dict], releases: Iterable[Release], retrieved_at: str) -> bool:
    changed = False
    by_key = {(event.get("group"), event.get("period")): event for event in events}
    for release in sorted(releases, key=lambda item: (item.period, item.group)):
        event = by_key.get((release.group, release.period))
        if not event:
            event = add_released_event(events, release)
            by_key[(release.group, release.period)] = event
            changed = True
        changed = merge_metric_values(event, release, retrieved_at) or changed
        changed = carry_release_to_next_event(events, release) or changed
    return changed


REQUIRED_EVENT_FIELDS = {
    "id",
    "country",
    "period",
    "scheduledAt",
    "dateStatus",
    "title",
    "category",
    "importance",
    "source",
    "sourceUrl",
    "metrics",
    "releasedAt",
    "retrievedAt",
    "revisionStatus",
}


def validate_payload(payload: dict) -> None:
    if payload.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("Unsupported or missing schemaVersion")
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("China calendar must contain at least one event")
    ids: set[str] = set()
    groups: set[str] = set()
    for event in events:
        missing = REQUIRED_EVENT_FIELDS - set(event)
        if missing:
            raise ValueError(f"{event.get('id', '<unknown>')} missing fields: {sorted(missing)}")
        if event["id"] in ids:
            raise ValueError(f"Duplicate event id: {event['id']}")
        ids.add(event["id"])
        groups.add(event.get("group", ""))
        if event["country"] != "CN":
            raise ValueError(f"China event has wrong country: {event['id']}")
        if event["dateStatus"] == "expected_window" and not event.get("expectedWindow"):
            raise ValueError(f"Expected-window event lacks a window: {event['id']}")
        if not isinstance(event["metrics"], list) or not event["metrics"]:
            raise ValueError(f"Event lacks metrics: {event['id']}")
        if not is_official_url(event["sourceUrl"]):
            raise ValueError(f"Non-official source URL: {event['sourceUrl']}")
    missing_groups = set(GROUP_META) - groups
    if missing_groups:
        raise ValueError(f"China calendar missing groups: {sorted(missing_groups)}")


def semantic_payload(payload: dict) -> dict:
    comparable = copy.deepcopy(payload)
    comparable.pop("generatedAt", None)
    return comparable


def load_or_seed(path: Path) -> dict:
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_payload(payload)
        return payload
    return {
        "schemaVersion": SCHEMA_VERSION,
        "status": "static_sample",
        "generatedAt": SAMPLE_RETRIEVED_AT,
        "timezone": "Asia/Shanghai",
        "sourcePolicy": "official_only",
        "failedSources": [],
        "events": build_static_calendar(),
    }


def refresh_payload(
    previous: dict,
    *,
    offline: bool = False,
    fetcher: Callable[[str], str] = fetch_text,
    now: datetime | None = None,
) -> tuple[dict, dict]:
    now = now or datetime.now(timezone.utc).astimezone()
    retrieved_at = now.isoformat(timespec="seconds")
    payload = copy.deepcopy(previous)
    existing = {event["id"]: event for event in payload.get("events", [])}
    for event in build_static_calendar():
        existing.setdefault(event["id"], event)
    payload["events"] = sorted(existing.values(), key=event_sort_key)

    failures: dict[str, str] = {}
    successes: list[str] = []
    changed = False
    if offline:
        failures = {provider: "offline mode" for provider in PROVIDER_LISTINGS}
    else:
        for provider in PROVIDER_LISTINGS:
            try:
                releases = collect_provider(provider, fetcher=fetcher)
                changed = apply_releases(payload["events"], releases, retrieved_at) or changed
                successes.append(provider)
            except Exception as exc:  # noqa: BLE001 - preserve each failed provider independently.
                failures[provider] = str(exc)

    if not successes:
        run_status = "stale"
    elif failures:
        run_status = "partial"
    else:
        run_status = "healthy"

    # Status metadata changes only when data is being written for a semantic reason.
    # Repeated failures therefore do not create timestamp-only commits.
    if changed:
        payload["status"] = run_status
        payload["failedSources"] = sorted(failures)
        payload["generatedAt"] = retrieved_at
    payload["events"] = sorted(payload["events"], key=event_sort_key)
    validate_payload(payload)
    status = {
        "status": run_status,
        "updated": changed,
        "successfulSources": successes,
        "failedSources": failures,
    }
    return payload, status


def write_if_changed(path: Path, payload: dict, previous: dict | None) -> bool:
    if previous is not None and semantic_payload(previous) == semantic_payload(payload):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--status-file", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validate_only:
        validate_payload(json.loads(args.output.read_text(encoding="utf-8")))
        print(f"Validated {args.output}")
        return 0

    previous = load_or_seed(args.output)
    payload, status = refresh_payload(previous, offline=args.offline)
    wrote = write_if_changed(args.output, payload, previous if args.output.exists() else None)
    status["written"] = wrote
    if args.status_file:
        args.status_file.parent.mkdir(parents=True, exist_ok=True)
        args.status_file.write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
