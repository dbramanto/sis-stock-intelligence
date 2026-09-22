import unittest
from pathlib import Path

APP=Path(__file__).resolve().parents[1]/'app.py'
SRC=APP.read_text(encoding='utf-8')

class TestFinalWebDeploy(unittest.TestCase):
    def test_internal_pipeline_order_preserved(self):
        self.assertIn('s2 = run_stage2(s1["canonical"])', SRC)
        self.assertIn('run_stage3_from_current_analysis(', SRC)
        self.assertLess(SRC.index('s2 = run_stage2(s1["canonical"])'), SRC.index('s3_result = run_stage3_from_current_analysis('))
    def test_no_hardcoded_realdata_winners(self):
        for sym in ('DSNG','LSIP','PGEO'):
            self.assertNotIn(sym, SRC)
    def test_no_new_final_score(self):
        self.assertNotIn('Final S3 Score', SRC)
        self.assertNotIn('final_score', SRC.lower())
    def test_wait_not_forced_into_top(self):
        self.assertIn('Belum ada kandidat Swing yang memenuhi seluruh kriteria untuk siap dipertimbangkan', SRC)
        self.assertIn('Pilih saham untuk melihat analisis Swing', SRC)
    def test_internal_stage_labels_hidden_from_user_result(self):
        self.assertNotIn('Hasil Research & Thesis', SRC)
        self.assertNotIn('Hasil Akhir SIS — Stage 3', SRC)
        self.assertNotIn('S2 adalah research & thesis engine.', SRC)
        self.assertIn('Hasil Analisis SIS', SRC)
    def test_drilldown_available(self):
        self.assertIn('Pilih saham untuk melihat analisis Swing', SRC)
        self.assertIn('Pilih saham untuk melihat analisis Jangka Panjang', SRC)
        self.assertIn('_render_thesis_block', SRC)
        self.assertIn('_candidate_for', SRC)
    def test_stage3_result_cleared_on_new_run(self):
        self.assertIn('st.session_state.pop("stage3_result", None)', SRC)

if __name__=='__main__': unittest.main()
