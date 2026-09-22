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


    def test_detail_view_is_decision_first(self):
        self.assertIn('st.markdown("**Saran SIS**")', self.src)
        self.assertIn('st.markdown("**Rencana harga**")', self.src)
        self.assertIn('with st.expander("Lihat detail analisis", expanded=False):', self.src)
        self.assertIn('Kualitas analisis', self.src)
        self.assertIn('Tingkat keyakinan', self.src)


    def test_detail_swing_wait_labels_match_funnel(self):
        self.assertIn('action = "TUNGGU HARGA"', self.src)
        self.assertIn('action = "TUNGGU KONFIRMASI"', self.src)
        self.assertNotIn('"WAIT": "TUNGGU"', self.src)

    def test_user_facing_terms_are_consistent(self):
        self.assertIn('Kualitas analisis menunjukkan kekuatan kandidat', self.src)
        self.assertIn('Tingkat keyakinan menunjukkan seberapa yakin SIS', self.src)
        self.assertNotIn('Quality menunjukkan kekuatan kandidat', self.src)
        self.assertNotIn('Confidence menunjukkan tingkat keyakinan SIS', self.src)


    def test_longterm_detail_matches_funnel_decision_language(self):
        self.assertIn('return "LAYAK DIBELI"', self.src)
        self.assertIn('return "BAGUS, TUNGGU HARGA"', self.src)
        self.assertIn('return "PERTIMBANGKAN / TUNGGU"', self.src)
        self.assertIn('return "BELUM LAYAK"', self.src)
        self.assertIn('st.markdown("**Penilaian harga**")', self.src)
        self.assertNotIn('st.write(f"**Konteks DCA:', self.src)


    def test_price_format_is_numeric_only(self):
        self.assertIn('return f"{number:,.0f}".replace(",", ".")', self.src)
        self.assertNotIn('return f"Rp', self.src)


if __name__ == "__main__":
    unittest.main()
