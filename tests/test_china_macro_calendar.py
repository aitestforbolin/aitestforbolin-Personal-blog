from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1] / "scripts" / "update_china_macro_calendar.py"
)
SPEC = importlib.util.spec_from_file_location("china_macro_calendar_updater", SCRIPT_PATH)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = updater
SPEC.loader.exec_module(updater)


class ChinaMacroCalendarTests(unittest.TestCase):
    def test_all_first_release_groups_have_multiple_official_metrics_where_expected(self):
        events = updater.build_static_calendar()
        groups = {event["group"] for event in events}
        self.assertEqual(groups, set(updater.GROUP_META))
        activity = next(event for event in events if event["group"] == "activity")
        prices = next(event for event in events if event["group"] == "prices")
        self.assertEqual(len(activity["metrics"]), 5)
        self.assertEqual(len(prices["metrics"]), 3)
        self.assertTrue(all(updater.is_official_url(event["sourceUrl"]) for event in events))

    def test_date_tbd_does_not_invent_a_timestamp(self):
        event = updater.make_event("credit", "2027-01")
        self.assertIsNone(event["scheduledAt"])
        self.assertEqual(event["dateStatus"], "date_tbd")
        self.assertNotIn("expectedWindow", event)

    def test_expected_window_remains_non_exact(self):
        event = updater.make_event(
            "fiscal",
            "2026-07",
            expected_window=("2026-08-15", "2026-08-25"),
        )
        self.assertIsNone(event["scheduledAt"])
        self.assertEqual(event["dateStatus"], "expected_window")
        self.assertEqual(event["expectedWindow"]["end"], "2026-08-25")

    def test_january_february_combined_periods_are_explicit(self):
        for series in ("activity", "profits", "trade", "fiscal"):
            self.assertEqual(
                updater.period_for_release(series, 2027, 3),
                "2027-01/02",
            )
        self.assertEqual(updater.period_for_release("prices", 2027, 3), "2027-02")

    def test_nbs_pmi_parser_reads_one_multi_indicator_release(self):
        release = updater.parse_nbs_pmi(
            """
            2026年7月中国采购经理指数运行情况 2026/07/31 09:30
            7月份，制造业采购经理指数（ PMI ）为 49.2% 。
            7月份，非制造业商务活动指数为49.0%。
            7月份，综合 PMI 产出指数为49.3%。
            """
        )
        self.assertEqual(release.period, "2026-07")
        self.assertEqual(release.metrics["manufacturing_pmi"], "49.2")
        self.assertEqual(len(release.metrics), 3)

    def test_official_source_parsers_extract_fact_values(self):
        prices = updater.parse_nbs_prices(
            """
            2026年6月份 2026/07/09 09:30
            全国居民消费价格同比上涨1.0%。6月份核心 CPI 同比上涨1.0%。
            工业生产者出厂价格同比上涨4.1%。
            """,
            updater.SAMPLE_URLS["prices"],
        )
        self.assertEqual(prices.metrics["cpi_yoy"], "1.0")
        self.assertEqual(prices.metrics["core_cpi_yoy"], "1.0")
        self.assertEqual(prices.metrics["ppi_yoy"], "4.1")

        credit = updater.parse_pbc_financial(
            """
            2026年上半年金融统计数据报告 2026-07-15 17:00
            6月末，广义货币（M2）余额356.71万亿元，同比增长8.0%。
            狭义货币（M1）余额118.48万亿元，同比增长4.0%。
            对实体经济发放的人民币贷款增加10.76万亿元。
            上半年人民币贷款增加10.72万亿元，上半年社会融资规模增量累计为20.84万亿元。
            """,
            updater.SAMPLE_URLS["credit"],
        )
        self.assertEqual(credit.period, "2026-06")
        self.assertEqual(credit.metrics["m1_yoy"], "4.0")
        self.assertEqual(credit.metrics["new_yuan_loans"], "10.72")
        self.assertEqual(credit.metrics["tsf_increment"], "20.84")

        housing = updater.parse_nbs_housing(
            """
            2026年6月份70个大中城市商品住宅销售价格变动情况 2026/07/15 09:30
            一线城市新建商品住宅销售价格环比上涨0.1%，二线城市新建商品住宅销售价格环比由上月下降0.1%转为持平，三线城市新建商品住宅销售价格环比下降0.3%。
            一线城市二手住宅销售价格环比上涨0.3%，二线城市二手住宅销售价格环比下降0.3%，三线城市二手住宅销售价格环比下降0.4%。
            """,
            updater.SAMPLE_URLS["housing"],
        )
        self.assertEqual(housing.metrics["tier2_new_home_mom"], "0.0")

        activity = updater.parse_nbs_activity(
            """
            上半年国民经济运行总体平稳 2026/07/15 10:00
            上半年规模以上工业增加值同比增长5.4%。6月份，规模以上工业增加值同比增长 5.3% 。
            上半年社会消费品零售总额同比增长1.3%。6月份，社会消费品零售总额同比增长 1.0% 。
            固定资产投资（不含农户）226370亿元，同比下降5.7%。房地产开发投资下降18.0%。
            6月份，全国城镇调查失业率为5.0%。
            """,
            updater.SAMPLE_URLS["activity"],
        )
        self.assertEqual(activity.period, "2026-06")
        self.assertEqual(activity.metrics["industrial_output_yoy"], "5.3")
        self.assertEqual(activity.metrics["retail_sales_yoy"], "1.0")
        self.assertEqual(activity.metrics["property_investment_ytd"], "-18.0")

        reserves = updater.parse_safe_reserves(
            "截至2026年6月末，我国外汇储备规模为34163亿美元。2026-07-07 10:00",
            updater.SAMPLE_URLS["reserves"],
        )
        self.assertEqual(reserves.metrics["fx_reserves"], "34163")

        fiscal = updater.parse_mof_fiscal(
            """
            2026年上半年财政收支情况 2026-07-22 10:00
            上半年，全国一般公共预算收入 121047 亿元 ，同比增长 4 .7 %。
            全国一般公共预算支出 143329 亿元，同比增长 1.5 %。
            """,
            updater.SAMPLE_URLS["fiscal"],
        )
        self.assertEqual(fiscal.period, "2026-01/06")
        self.assertEqual(fiscal.metrics["general_spending"], "143329")

    def test_revision_is_recorded_when_official_actual_changes(self):
        events = updater.build_static_calendar()
        release = updater.Release(
            group="pmi",
            period="2026-07",
            released_at="2026-08-01T09:30:00+08:00",
            source_url=updater.SAMPLE_URLS["pmi"],
            metrics={"manufacturing_pmi": "49.1"},
        )
        changed = updater.apply_releases(events, [release], "2026-08-02T12:00:00+08:00")
        event = next(
            item for item in events if item["group"] == "pmi" and item["period"] == "2026-07"
        )
        self.assertTrue(changed)
        self.assertEqual(event["revisionStatus"], "revised")
        metric = next(item for item in event["metrics"] if item["id"] == "manufacturing_pmi")
        self.assertEqual(metric["actual"], "49.1")
        self.assertEqual(metric["revisionStatus"], "revised")

    def test_new_official_period_is_added_without_erasing_future_events(self):
        events = updater.build_static_calendar()
        original_count = len(events)
        release = updater.Release(
            group="reserves",
            period="2026-06",
            released_at="2026-07-07T16:08:00+08:00",
            source_url=updater.SAMPLE_URLS["reserves"],
            metrics={"fx_reserves": "34163"},
        )
        changed = updater.apply_releases(
            events,
            [release],
            "2026-08-02T12:00:00+08:00",
        )
        released = next(
            event
            for event in events
            if event["group"] == "reserves" and event["period"] == "2026-06"
        )
        self.assertTrue(changed)
        self.assertEqual(len(events), original_count + 1)
        self.assertEqual(released["dateStatus"], "confirmed")
        self.assertEqual(released["metrics"][0]["actual"], "34163")

    def test_failed_sources_preserve_previous_valid_events(self):
        previous = updater.load_or_seed(Path("/path/that/does/not/exist.json"))
        before = json.dumps(previous["events"], ensure_ascii=False, sort_keys=True)
        payload, status = updater.refresh_payload(
            previous,
            offline=True,
            now=datetime(2026, 8, 2, tzinfo=timezone.utc),
        )
        after = json.dumps(payload["events"], ensure_ascii=False, sort_keys=True)
        self.assertEqual(before, after)
        self.assertEqual(status["status"], "stale")
        self.assertFalse(status["updated"])

    def test_atomic_writer_never_writes_empty_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "china.json"
            valid = updater.load_or_seed(Path(temporary) / "missing.json")
            updater.write_if_changed(output, valid, None)
            written = json.loads(output.read_text(encoding="utf-8"))
            self.assertGreater(len(written["events"]), 0)
            with self.assertRaises(ValueError):
                updater.validate_payload({"schemaVersion": 1, "events": []})

    def test_partial_run_updates_successful_provider_only(self):
        previous = updater.load_or_seed(Path("/path/that/does/not/exist.json"))
        revised = updater.Release(
            "pmi",
            "2026-07",
            "2026-07-31T09:30:00+08:00",
            updater.SAMPLE_URLS["pmi"],
            {"manufacturing_pmi": "49.1"},
        )

        def fake_collect(provider, fetcher=updater.fetch_text, max_pages=18):
            if provider == "nbs":
                return [revised]
            raise RuntimeError("blocked in runner")

        with patch.object(updater, "collect_provider", side_effect=fake_collect):
            payload, status = updater.refresh_payload(
                previous,
                now=datetime(2026, 8, 2, tzinfo=timezone.utc),
            )

        self.assertEqual(status["status"], "partial")
        self.assertEqual(status["successfulSources"], ["nbs"])
        self.assertEqual(len(payload["events"]), len(previous["events"]))

    def test_lpr_uses_china_money_only_when_pbc_listing_fails(self):
        def fake_fetch(url):
            if url == updater.PBC_LPR_INDEX:
                raise RuntimeError("PBC listing unavailable")
            if url == updater.CIBM_LPR_FALLBACK:
                return """
                2026年7月20日 09:00
                1年期LPR为3.0%，5年期以上LPR为3.5%。
                """
            raise AssertionError(f"Unexpected URL: {url}")

        releases = updater.collect_provider("pbc_lpr", fetcher=fake_fetch)
        self.assertEqual(len(releases), 1)
        self.assertEqual(releases[0].period, "2026-07")
        self.assertEqual(releases[0].source_url, updater.CIBM_LPR_FALLBACK)
        self.assertEqual(releases[0].metrics["lpr_5y"], "3.5")


if __name__ == "__main__":
    unittest.main()
