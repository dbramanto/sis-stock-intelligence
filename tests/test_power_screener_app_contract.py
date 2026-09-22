import unittest
from pathlib import Path


class TestPowerScreenerAppContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = Path("app.py").read_text(encoding="utf-8")

    def test_funnel_is_integrated_in_production_app(self):
        self.assertIn("render_opportunity_funnel(st, stage3", self.src)

    def test_top_n_remains_three(self):
        self.assertIn("top_n=3", self.src)

    def test_market_closed_input_guidance_remains_visible(self):
        self.assertIn("wajib dilakukan setelah market tutup", self.src)

    def test_all_candidates_remain_available_for_swing_drilldown(self):
        self.assertIn("for candidate in candidates", self.src)
        self.assertIn("final_swing_symbol", self.src)

    def test_all_candidates_remain_available_for_longterm_drilldown(self):
        self.assertIn("lt_options", self.src)
        self.assertIn("final_lt_symbol", self.src)

    def test_no_new_composite_score_added_by_app(self):
        self.assertNotIn("funnel_score", self.src)
        self.assertNotIn("power_score", self.src)


if __name__ == "__main__":
    unittest.main()
