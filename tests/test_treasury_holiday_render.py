import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("xrender", Path(__file__).parents[1] / "scripts" / "publish_x_post.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)

class TreasuryHolidayRenderTests(unittest.TestCase):
    def test_closed_market_shows_dated_latest_official_value_without_daily_arrow(self):
        text = render.treasury_line("美债10Y", {"previous": 5.28, "anchor": 5.24, "status": "2026-10-12休市；最近官方2026-10-09"})
        self.assertIn("5.240%", text)
        self.assertIn("2026-10-09", text)
        self.assertIn("休市", text)
        self.assertNotIn("→", text)

    def test_open_market_retains_comparison(self):
        text = render.treasury_line("美债10Y", {"previous": 5.28, "anchor": 5.24, "status": "2026-10-08 → 2026-10-09"})
        self.assertIn("5.280% → 5.240%", text)
