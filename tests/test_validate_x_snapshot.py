import copy
import unittest

from scripts.validate_x_snapshot import SnapshotQualityError, validate_snapshot


class XSnapshotQualityTests(unittest.TestCase):
    def complete_snapshot(self):
        return {
            "fallback": {
                "markets": [
                    {"id": "SPX", "changePercent": 0.1},
                    {"id": "IXIC", "changePercent": -0.2},
                    {"id": "DJI", "changePercent": 0.3},
                    {"id": "US02Y", "previousClose": 4.1, "price": 4.2},
                    {"id": "US10Y", "previousClose": 4.6, "price": 4.7},
                    {"id": "US30Y", "previousClose": 5.1, "price": 5.2},
                ],
                "breadth": [
                    {
                        "id": "SP500",
                        "advancers": 250,
                        "decliners": 250,
                        "unchanged": 3,
                        "advancePercent": 50.0,
                        "status": "ok",
                    },
                    {
                        "id": "NASDAQ",
                        "advancers": 2400,
                        "decliners": 2300,
                        "unchanged": 100,
                        "advancePercent": 51.1,
                        "status": "ok",
                    },
                ],
            },
            "macroAnchors": [
                {"id": "DXY", "previous": 98.9, "anchor": 99.1},
                {"id": "BRN1!", "previous": 86.0, "anchor": 86.5},
                {"id": "GOLD", "previous": 4667.1, "anchor": 4603.6},
                {"id": "BTCUSDT", "previous": 78789, "anchor": 78504},
            ],
            "fedProbability": {"previous": 40.1, "current": 39.0},
            "view": ["市场观点"],
        }

    def test_complete_snapshot_passes(self):
        validate_snapshot(self.complete_snapshot())

    def test_missing_sp500_breadth_is_blocked(self):
        snapshot = self.complete_snapshot()
        row = snapshot["fallback"]["breadth"][0]
        row.update(
            {
                "advancers": None,
                "decliners": None,
                "unchanged": None,
                "advancePercent": None,
                "status": "unavailable",
            }
        )
        with self.assertRaisesRegex(SnapshotQualityError, "SP500"):
            validate_snapshot(snapshot)

    def test_partial_nasdaq_flat_count_is_allowed(self):
        snapshot = self.complete_snapshot()
        snapshot["fallback"]["breadth"][1]["unchanged"] = None
        validate_snapshot(snapshot)

    def test_missing_gold_anchor_uses_latest_quote(self):
        snapshot = self.complete_snapshot()
        gold = next(row for row in snapshot["macroAnchors"] if row["id"] == "GOLD")
        gold["anchor"] = None
        gold["latest"] = 4603.56
        validate_snapshot(snapshot)

    def test_missing_gold_anchor_and_latest_quote_is_blocked(self):
        snapshot = self.complete_snapshot()
        gold = next(row for row in snapshot["macroAnchors"] if row["id"] == "GOLD")
        gold["anchor"] = None
        with self.assertRaisesRegex(SnapshotQualityError, "GOLD"):
            validate_snapshot(snapshot)


if __name__ == "__main__":
    unittest.main()
