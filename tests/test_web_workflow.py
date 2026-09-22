import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app.py"


class TestWebWorkflowContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = APP.read_text(encoding="utf-8")

    def test_run_analysis_replaces_stage1_button(self):
        self.assertIn('"Run Analysis"', self.source)
        self.assertNotIn('"Run Stage 1"', self.source)

    def test_stage1_pass_flows_into_stage2(self):
        self.assertIn('s1 = run_stage1(', self.source)
        self.assertIn('if s1["status"] != "PASS":', self.source)
        self.assertIn('s2 = run_stage2(s1["canonical"])', self.source)

    def test_technical_stage1_tables_not_rendered(self):
        forbidden = [
            'st.subheader("Universe / Capture Summary")',
            'st.subheader("Normalization Events")',
            'st.subheader("Canonical Evidence Dataset")',
            'st.subheader("Technical Control Reconciliation")',
            'Download canonical CSV',
        ]
        for token in forbidden:
            self.assertNotIn(token, self.source)

    def test_s2_user_output_contract(self):
        for token in ["Status tesis", "Keyakinan evidence", "Alasan utama", "Hal yang melemahkan tesis", "Risiko utama", "Kapan tesis perlu dievaluasi ulang"]:
            self.assertIn(token, self.source)

    def test_no_s2_decision_fields(self):
        # UI may explain that these are absent, but must not index/render them as fields.
        for token in ['data["score"]', 'data["rank"]', 'data["recommendation"]', 'data["entry"]', 'data["tp"]', 'data["sl"]']:
            self.assertNotIn(token, self.source)


if __name__ == "__main__":
    unittest.main()
