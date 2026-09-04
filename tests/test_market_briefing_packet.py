import datetime as dt
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).parents[1] / "scripts" / "build_market_briefing_packet.py"
SPEC = importlib.util.spec_from_file_location("market_packet", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def asset(source="Yahoo Finance"):
    return {
        "id": "DXY",
        "source": source,
        "comparison": {
            "kind": "16:00_ET",
            "previous": None,
            "current": {"date": "2026-08-25", "value": 98.8},
        },
    }


class MarketBriefingPacketTests(unittest.TestCase):
    def test_rows_from_supported_shapes(self):
        rows = [{"id": "SPX"}]
        self.assertEqual(MODULE.rows_from(rows, ("markets",)), rows)
        self.assertEqual(MODULE.rows_from({"markets": rows}, ("markets",)), rows)
        self.assertEqual(MODULE.rows_from({"data": rows}, ("markets", "data")), rows)

    def test_market_date_accepts_iso_and_milliseconds(self):
        self.assertEqual(MODULE.market_date({"tradingDate": "2026-08-10"}), "2026-08-10")
        self.assertEqual(MODULE.market_date({"updatedAt": 1786320000000}), "2026-08-10")

    def test_source_metadata_preserves_revision_and_fetch_time(self):
        self.assertEqual(
            MODULE.source_metadata({
                "sourceRevision": "rev-1", "fetchedAt": 123, "data": [],
            }),
            {"sourceRevision": "rev-1", "fetchedAt": 123},
        )

    def test_required_sector_contract_is_complete(self):
        sectors = {"XLK", "XLY", "XLC", "XLV", "XLU", "XLP", "XLE", "XLI", "XLB", "XLRE", "XLF"}
        self.assertTrue(sectors <= MODULE.REQUIRED_MARKETS)
        self.assertIn("SOX", MODULE.REQUIRED_MARKETS)

    def test_breadth_requires_numeric_counts_and_consistent_percentage(self):
        rows = [
            {
                "id": "SP500", "advancers": 283, "decliners": 218,
                "advancePercent": 56.4870259481, "status": "ok",
            },
            {
                "id": "NASDAQ", "advancers": 1991, "decliners": 2766,
                "advancePercent": 99.0, "status": "ok",
            },
        ]
        missing, invalid = MODULE.breadth_quality_issues(rows)
        self.assertEqual(missing, [])
        self.assertEqual(invalid, ["NASDAQ:percent_mismatch"])

        rows[0]["advancePercent"] = None
        _, invalid = MODULE.breadth_quality_issues(rows)
        self.assertIn("SP500:missing_numeric", invalid)

    def test_breadth_cache_requires_same_date_and_complete_values(self):
        rows = [
            {"id": "SP500", "advancers": 283, "decliners": 218, "advancePercent": 56.487},
            {"id": "NASDAQ", "advancers": 1991, "decliners": 2766, "advancePercent": 41.854},
        ]
        packet = {"tradingDate": "2026-08-26", "breadth": rows}
        self.assertEqual(
            MODULE.same_date_cached_breadth(packet, "2026-08-26"), rows
        )
        self.assertEqual(MODULE.same_date_cached_breadth(packet, "2026-08-25"), [])
        packet["breadth"][0]["advancePercent"] = None
        self.assertEqual(MODULE.same_date_cached_breadth(packet, "2026-08-26"), [])

    def test_fresh_swissquote_gold_quote_is_noncritical_when_anchor_is_missing(self):
        assets = [{
            "id": "GOLD",
            "source": "Swissquote",
            "price": 4603.56,
            "updatedAt": 1787775540000,
            "comparison": {"previous": {"value": 4667.095}, "current": None},
        }]
        critical, warnings = MODULE.classify_comparison_gaps(
            assets, "2026-08-26", ["GOLD"]
        )
        self.assertEqual(critical, [])
        self.assertEqual(warnings, ["GOLD:latest_only_no_16:00_ET_anchor"])

    def test_yahoo_gold_proxy_replaces_missing_spot_anchors(self):
        previous = int(dt.datetime(2026, 8, 31, 19, 55, tzinfo=dt.timezone.utc).timestamp())
        current = int(dt.datetime(2026, 9, 1, 19, 55, tzinfo=dt.timezone.utc).timestamp())
        payload = {
            "chart": {"result": [{
                "timestamp": [previous, current],
                "indicators": {"quote": [{"close": [4470.0, 4430.0]}]},
            }]}
        }
        assets = [{
            "id": "GOLD",
            "source": "Swissquote",
            "price": 4429.8,
            "comparison": {"previous": None, "current": None},
        }]
        with mock.patch.object(MODULE, "fetch_json", return_value=payload):
            changed = MODULE.replace_missing_gold_anchor_with_yahoo_proxy(
                assets, "2026-09-01"
            )
        self.assertTrue(changed)
        self.assertEqual(assets[0]["source"], "Yahoo Finance")
        self.assertEqual(assets[0]["sourceSymbol"], "GC=F")
        self.assertEqual(assets[0]["instrumentType"], "futures_proxy")
        self.assertEqual(assets[0]["proxyFor"], "XAU/USD")
        self.assertEqual(assets[0]["comparison"]["previous"]["value"], 4470.0)
        self.assertEqual(assets[0]["comparison"]["current"]["value"], 4430.0)
        self.assertFalse(
            any(issue.startswith("GOLD:") for issue in MODULE.macro_provider_issues(assets))
        )

    def test_unlabelled_yahoo_gold_is_rejected(self):
        assets = [{
            "id": "GOLD", "source": "Yahoo Finance", "sourceSymbol": "GC=F",
        }]
        self.assertIn("GOLD:Yahoo Finance", MODULE.macro_provider_issues(assets))

    def test_stale_gold_quote_remains_critical(self):
        assets = [{
            "id": "GOLD", "source": "Swissquote", "price": 4603.56,
            "updatedAt": 1787688000000,
        }]
        critical, warnings = MODULE.classify_comparison_gaps(
            assets, "2026-08-26", ["GOLD"]
        )
        self.assertEqual(critical, ["GOLD"])
        self.assertEqual(warnings, [])

    def test_compact_market_drops_history_points(self):
        row = {"id": "SPX", "price": 10, "changePercent": 1, "points": [{"time": 1, "value": 9}]}
        self.assertEqual(
            MODULE.compact_market(row),
            {"id": "SPX", "price": 10, "changePercent": 1},
        )

    def test_future_events_reads_curated_event_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            (data / "us-macro-calendar.json").write_text("[]", encoding="utf-8")
            curated = [
                {"event_id": "nvda-earnings", "date_bjt": "2026-08-27", "title": "NVIDIA earnings"},
                {"event_id": "expired", "date_bjt": "2026-08-10", "title": "Expired"},
            ]
            (data / "tech-company-events-curated.json").write_text(json.dumps(curated), encoding="utf-8")
            events = MODULE.future_events(dt.date(2026, 8, 26), root=root)
            self.assertEqual([event["event_id"] for event in events], ["nvda-earnings"])

    def test_local_calendar_date_uses_shanghai_not_utc(self):
        moment = dt.datetime(2026, 8, 25, 22, 10, tzinfo=dt.timezone.utc)
        self.assertEqual(MODULE.local_calendar_date(moment), dt.date(2026, 8, 26))

    def test_previous_packet_inherits_only_older_same_provider_anchor(self):
        assets = [asset()]
        previous = {
            "tradingDate": "2026-08-22",
            "macroAssets": [{
                "id": "DXY",
                "source": "Yahoo Finance",
                "comparison": {"current": {"date": "2026-08-22", "value": 99.1}},
            }],
        }
        inherited, gaps = MODULE.inherit_macro_comparisons(assets, "2026-08-25", previous, {})
        self.assertEqual(assets[0]["comparison"]["previous"]["value"], 99.1)
        self.assertEqual(inherited, ["DXY:previous_packet"])
        self.assertEqual(set(gaps), {"BRN1!", "BTCUSDT", "GOLD"})

    def test_provider_mismatch_is_rejected(self):
        assets = [asset("Yahoo Finance")]
        previous = {
            "tradingDate": "2026-08-22",
            "macroAssets": [{
                "id": "DXY",
                "source": "Another Provider",
                "comparison": {"current": {"date": "2026-08-22", "value": 99.1}},
            }],
        }
        inherited, gaps = MODULE.inherit_macro_comparisons(assets, "2026-08-25", previous, {})
        self.assertIsNone(assets[0]["comparison"]["previous"])
        self.assertEqual(inherited, [])
        self.assertIn("DXY", gaps)

    def test_daily_status_is_secondary_anchor_source(self):
        assets = [asset()]
        status = {
            "asOf": "2026-08-22",
            "macroAnchors": [{
                "id": "DXY", "provider": "Yahoo Finance", "anchor": 99.2,
                "anchorObservedAt": 123456,
            }],
        }
        inherited, _ = MODULE.inherit_macro_comparisons(assets, "2026-08-25", {}, status)
        self.assertEqual(
            assets[0]["comparison"]["previous"],
            {
                "date": "2026-08-22", "value": 99.2, "observedAt": 123456,
                "inheritedFrom": "daily_market_status",
            },
        )
        self.assertEqual(inherited, ["DXY:daily_market_status"])

    def test_same_date_daily_status_recovers_missing_previous_anchor(self):
        assets = [{
            "id": "BTCUSDT",
            "source": "Yahoo Finance",
            "comparison": {
                "kind": "16:00_ET",
                "previous": None,
                "current": {"date": "2026-08-31", "value": 78570},
            },
        }]
        status = {
            "asOf": "2026-08-31",
            "macroAnchors": [{
                "id": "BTCUSDT",
                "provider": "Yahoo Finance",
                "previous": 77744,
                "previousAnchorTime": 1787947200000,
                "previousObservedAt": 1787947200000,
                "anchor": 78570,
                "anchorTime": 1788206400000,
                "anchorObservedAt": 1788206400000,
            }],
        }
        inherited, gaps = MODULE.inherit_macro_comparisons(
            assets, "2026-08-31", {}, status
        )
        self.assertEqual(
            assets[0]["comparison"]["previous"],
            {
                "date": "2026-08-28",
                "value": 77744.0,
                "observedAt": 1787947200000,
                "inheritedFrom": "daily_market_status_same_date",
            },
        )
        self.assertIn("BTCUSDT:daily_market_status_same_date_previous", inherited)
        self.assertNotIn("BTCUSDT", gaps)

    def test_same_date_daily_status_does_not_mix_providers(self):
        assets = [{
            "id": "BTCUSDT",
            "source": "Yahoo Finance",
            "comparison": {"previous": None, "current": {"date": "2026-08-31", "value": 78570}},
        }]
        status = {
            "asOf": "2026-08-31",
            "macroAnchors": [{
                "id": "BTCUSDT",
                "provider": "Another Provider",
                "previous": 77744,
                "previousAnchorTime": 1787947200000,
                "anchor": 78570,
                "anchorTime": 1788206400000,
            }],
        }
        inherited, gaps = MODULE.inherit_macro_comparisons(
            assets, "2026-08-31", {}, status
        )
        self.assertIsNone(assets[0]["comparison"]["previous"])
        self.assertNotIn("BTCUSDT:daily_market_status_same_date_previous", inherited)
        self.assertIn("BTCUSDT", gaps)

    def test_yahoo_intraday_recovery_extracts_btc_close_anchors(self):
        previous = int(dt.datetime(2026, 8, 31, 19, 55, tzinfo=dt.timezone.utc).timestamp())
        current = int(dt.datetime(2026, 9, 1, 19, 55, tzinfo=dt.timezone.utc).timestamp())
        payload = {
            "chart": {"result": [{
                "timestamp": [previous, current],
                "indicators": {"quote": [{"close": [78570, 77225]}]},
            }]}
        }
        comparison = MODULE.yahoo_intraday_comparison(payload, "2026-09-01")
        self.assertEqual(comparison["previous"]["date"], "2026-08-31")
        self.assertEqual(comparison["previous"]["value"], 78570.0)
        self.assertEqual(comparison["current"]["date"], "2026-09-01")
        self.assertEqual(comparison["current"]["value"], 77225.0)
        self.assertEqual(comparison["current"]["minutesBeforeClose"], 5)

    def test_recover_yahoo_anchor_preserves_provider_and_fills_only_missing_values(self):
        previous = int(dt.datetime(2026, 8, 31, 19, 55, tzinfo=dt.timezone.utc).timestamp())
        current = int(dt.datetime(2026, 9, 1, 19, 55, tzinfo=dt.timezone.utc).timestamp())
        payload = {
            "chart": {"result": [{
                "timestamp": [previous, current],
                "indicators": {"quote": [{"close": [78570, 77225]}]},
            }]}
        }
        item = {
            "id": "BTCUSDT", "source": "Yahoo Finance",
            "comparison": {"kind": "16:00_ET", "previous": None, "current": None},
        }
        with mock.patch.object(MODULE, "fetch_json", return_value=payload):
            changed = MODULE.recover_yahoo_anchor(item, "2026-09-01")
        self.assertTrue(changed)
        self.assertEqual(item["comparison"]["previous"]["value"], 78570.0)
        self.assertEqual(item["comparison"]["current"]["value"], 77225.0)
        self.assertEqual(item["comparison"]["current"]["inheritedFrom"], "yahoo_intraday_recovery")

        mismatched = {
            "id": "BTCUSDT", "source": "Another Provider",
            "comparison": {"previous": None, "current": None},
        }
        with mock.patch.object(MODULE, "fetch_json") as fetch:
            self.assertFalse(MODULE.recover_yahoo_anchor(mismatched, "2026-09-01"))
            fetch.assert_not_called()

    def test_delayed_rebuild_reuses_only_same_date_swissquote_latest(self):
        current = [{
            "id": "GOLD", "source": "Swissquote", "price": 101,
            "updatedAt": int(dt.datetime(2026, 9, 3, 15, tzinfo=dt.timezone.utc).timestamp() * 1000),
        }]
        previous = {
            "tradingDate": "2026-09-02",
            "macroAssets": [{
                "id": "GOLD", "source": "Swissquote", "price": 99,
                "updatedAt": int(dt.datetime(2026, 9, 2, 19, 50, tzinfo=dt.timezone.utc).timestamp() * 1000),
            }],
        }
        self.assertTrue(
            MODULE.inherit_same_date_gold_latest(current, "2026-09-02", previous)
        )
        self.assertEqual(current[0]["price"], 99)
        self.assertEqual(current[0]["latestInheritedFrom"], "same_date_previous_packet")

        current[0]["price"] = 101
        self.assertFalse(
            MODULE.inherit_same_date_gold_latest(current, "2026-09-01", previous)
        )
        self.assertEqual(current[0]["price"], 101)

    def test_treasury_comparison_preserves_flat_consecutive_days(self):
        sep1 = int(dt.datetime(2026, 9, 1, 19, 30, tzinfo=dt.timezone.utc).timestamp() * 1000)
        sep2 = int(dt.datetime(2026, 9, 2, 19, 30, tzinfo=dt.timezone.utc).timestamp() * 1000)
        row = {
            "id": "US10Y",
            "source": "U.S. Treasury",
            "points": [
                {"time": sep1, "value": 4.79},
                {"time": sep2, "value": 4.79},
            ],
        }
        item = MODULE.macro_asset(row, "2026-09-02")
        self.assertEqual(item["comparison"]["previous"]["date"], "2026-09-01")
        self.assertEqual(item["comparison"]["previous"]["value"], 4.79)
        self.assertEqual(item["comparison"]["current"]["date"], "2026-09-02")
        self.assertEqual(item["comparison"]["current"]["value"], 4.79)
        self.assertEqual(MODULE.treasury_comparison_issues([item], "2026-09-02"), ["US02Y", "US30Y"])

    def test_treasury_missing_previous_is_a_validation_issue(self):
        assets = [
            {
                "id": asset_id,
                "comparison": {
                    "kind": "official_daily",
                    "previous": None if asset_id == "US10Y" else {
                        "date": "2026-09-01", "value": 4.0
                    },
                    "current": {"date": "2026-09-02", "value": 4.1},
                },
            }
            for asset_id in MODULE.TREASURY_IDS
        ]
        self.assertEqual(
            MODULE.treasury_comparison_issues(assets, "2026-09-02"),
            ["US10Y"],
        )

    def test_fixed_comparison_rejects_stale_non_null_current_anchor(self):
        assets = [
            {
                "id": asset_id,
                "comparison": {
                    "previous": {"date": "2026-08-31", "value": 99},
                    "current": {
                        "date": "2026-09-01" if asset_id == "DXY" else "2026-09-02",
                        "value": 100,
                    },
                },
            }
            for asset_id in MODULE.FIXED_ANCHOR_IDS - {"GOLD"}
        ]
        self.assertEqual(
            MODULE.fixed_comparison_issues(assets, "2026-09-02"),
            ["DXY"],
        )

    def test_session_market_dates_must_match_target(self):
        rows = [
            {
                "id": item,
                "tradingDate": "2026-09-01" if item == "XLK" else "2026-09-02",
                "price": 100,
                "changePercent": 1,
                "status": "ok",
            }
            for item in MODULE.SESSION_MARKET_IDS
        ]
        self.assertEqual(
            MODULE.session_market_date_issues(rows, "2026-09-02"),
            ["XLK:2026-09-01"],
        )

    def test_generated_after_new_york_close(self):
        before = dt.datetime(2026, 8, 25, 19, 59, tzinfo=dt.timezone.utc)
        after = dt.datetime(2026, 8, 25, 20, 1, tzinfo=dt.timezone.utc)
        self.assertFalse(MODULE.generated_after_close(before, "2026-08-25"))
        self.assertTrue(MODULE.generated_after_close(after, "2026-08-25"))

    def test_candidate_failure_is_warning_not_packet_failure(self):
        anchor_time = dt.datetime(2026, 8, 25, 19, 55, tzinfo=dt.timezone.utc).timestamp()
        treasury_previous = dt.datetime(2026, 8, 24, 19, 30, tzinfo=dt.timezone.utc).timestamp()
        treasury_current = dt.datetime(2026, 8, 25, 19, 30, tzinfo=dt.timezone.utc).timestamp()
        markets = []
        for market_id in MODULE.REQUIRED_MARKETS:
            row = {
                "id": market_id,
                "tradingDate": "2026-08-25",
                "source": MODULE.EXPECTED_MACRO_SOURCES.get(market_id, "Yahoo Finance"),
                "price": 100.0,
                "changePercent": 1.0,
                "status": "ok",
            }
            if market_id in MODULE.FIXED_ANCHOR_IDS:
                row["points"] = [{"time": anchor_time, "value": 100.0}]
            elif market_id in {"US02Y", "US10Y", "US30Y"}:
                row["points"] = [
                    {"time": treasury_previous, "value": 4.0},
                    {"time": treasury_current, "value": 4.1},
                ]
            markets.append(row)
        breadth = [
            {"id": item, "advancers": 60, "decliners": 40, "advancePercent": 60}
            for item in MODULE.REQUIRED_BREADTH
        ]
        previous = {
            "tradingDate": "2026-08-22",
            "macroAssets": [
                {
                    "id": market_id,
                    "source": MODULE.EXPECTED_MACRO_SOURCES[market_id],
                    "comparison": {"current": {"date": "2026-08-22", "value": 99.0}},
                }
                for market_id in MODULE.FIXED_ANCHOR_IDS
            ],
        }

        def fake_fetch(url):
            return markets if url == MODULE.MARKETS_URL else breadth

        def fake_candidate(ticker):
            return {"ticker": ticker, "status": "incomplete" if ticker == "NVDA" else "ok"}

        def fake_load(path, default):
            path = str(path)
            if path == "/tmp/test-previous-packet.json":
                return previous
            if path.endswith("btc-etf-flow.json"):
                return {"latest": {"date": "2026-08-25"}, "source": "Farside"}
            return default

        with (
            mock.patch.object(MODULE, "fetch_json", side_effect=fake_fetch),
            mock.patch.object(MODULE, "fetch_candidate", side_effect=fake_candidate),
            mock.patch.object(MODULE, "load_json", side_effect=fake_load),
            mock.patch.dict("os.environ", {"PREVIOUS_PACKET_PATH": "/tmp/test-previous-packet.json"}),
        ):
            packet = MODULE.build_packet(
                now=dt.datetime(2026, 8, 25, 22, 10, tzinfo=dt.timezone.utc)
            )
        self.assertTrue(packet["validation"]["complete"], packet["validation"]["criticalErrors"])
        self.assertNotIn("candidate_quote_failures:NVDA", packet["validation"]["criticalErrors"])
        self.assertIn("candidate_quote_failures:NVDA", packet["validation"]["warnings"])
        self.assertEqual(packet["validation"]["candidateQuoteFailures"], ["NVDA"])

    def test_fewer_than_five_candidate_quotes_is_critical(self):
        self.assertEqual(
            MODULE.candidate_quote_issues([{}] * 4),
            ["insufficient_candidate_quotes:4"],
        )
        self.assertEqual(MODULE.candidate_quote_issues([{}] * 5), [])


if __name__ == "__main__":
    unittest.main()
