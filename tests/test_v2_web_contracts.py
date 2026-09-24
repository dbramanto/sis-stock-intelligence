import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "app.py").read_text(encoding="utf-8")
UI = (ROOT / "stage3" / "opportunity_funnel_ui.py").read_text(encoding="utf-8")


class TestV2WebContracts(unittest.TestCase):
    def test_canonical_app_delegates_to_v2_result_ui(self):
        self.assertIn("render_opportunity_funnel", APP)
        self.assertIn("render_stock_detail", APP)
        self.assertNotIn("run_stage3_from_current_analysis(", APP)

    def test_stage_order_is_preserved(self):
        self.assertIn('s2 = run_stage2(s1["canonical"])', APP)
        self.assertIn("s3 = _run_stage3(", APP)
        self.assertLess(APP.index('s2 = run_stage2(s1["canonical"])'), APP.index("s3 = _run_stage3("))

    def test_new_run_clears_v2_result_state(self):
        self.assertIn('"v2_stage3"', APP)
        self.assertIn('st.session_state.pop(key, None)', APP)

    def test_top3_and_full_universe_access_are_preserved(self):
        self.assertIn("build_opportunity_funnel(stage3, top_n=3)", UI)
        self.assertIn("Semua saham", UI)
        self.assertIn('stage3.get("candidates")', UI)

    def test_user_horizons_and_price_terms_are_consistent(self):
        self.assertIn('st.tabs(["Swing", "Jangka Panjang"])', UI)
        self.assertIn("Area beli", UI)
        self.assertNotIn("Area entry:", UI)
        self.assertNotIn("Analisis Long-Term", UI)

    def test_decision_language_is_v2_and_no_composite_score_added(self):
        for token in ("TUNGGU HARGA", "TUNGGU KONFIRMASI", "LAYAK DIBELI", "BELUM LAYAK"):
            self.assertIn(token, UI)
        for token in ("funnel_score", "power_score", "Final S3 Score"):
            self.assertNotIn(token, APP + UI)

    def test_longterm_detail_uses_business_domain_output(self):
        self.assertIn("_longterm_row", UI)
        self.assertIn("Kualitas bisnis", UI)
        self.assertIn("Prospek jangka panjang", UI)

    def test_user_facing_result_hides_internal_stage_explanations(self):
        self.assertNotIn("S2 adalah research & thesis engine.", UI)
        self.assertNotIn("Hasil Akhir SIS — Stage 3", UI)
        self.assertIn("Peluang Utama SIS", UI)

    def test_input_guidance_for_market_close_remains_visible(self):
        self.assertIn("Input setelah market tutup", APP)
        self.assertIn("Market Tutup", APP)

    def test_snapshot_download_is_available(self):
        self.assertIn("Unduh Snapshot", APP)
        self.assertIn("Unduh Snapshot Valid", APP)

    def test_top3_uses_single_detail_action(self):
        self.assertIn('st.button("Buka rincian"', UI)
        self.assertNotIn('key=f"funnel_swing_', UI)
        self.assertNotIn('key=f"funnel_long_', UI)

    def test_detail_explains_decision_without_internal_stage_copy(self):
        self.assertIn("**Saran SIS**", UI)
        self.assertIn("**Mengapa?**", UI)
        self.assertNotIn("Rincian ini hanya menjelaskan hasil Stage 3", UI)

    def test_snapshot_history_shows_user_relevant_status(self):
        self.assertIn("Status analisis", APP)
        self.assertIn("Jumlah saham", APP)
        self.assertIn("Hasil analisis tersimpan dan dapat dimuat bersama snapshot ini.", APP)
        self.assertIn("Snapshot input valid tersedia. Hasil analisis belum tersimpan untuk snapshot ini.", APP)

    def test_streamlit_browser_config_exists(self):
        config = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
        self.assertIn("headless = true", config)
        self.assertIn("enableXsrfProtection = true", config)
        self.assertIn("gatherUsageStats = false", config)


if __name__ == "__main__":
    unittest.main()
