import math
import unittest

from stage2 import CompanyContext, EvidenceInterpreter, EvidenceState, Horizon


class TestStage2Core(unittest.TestCase):
    def base(self):
        return {
            "symbol": "TEST",
            "RSI14": 61.0,
            "Previous RSI14": 68.0,
            "PE TTM": 8.0,
            "PE -1SD 5Y": 9.0,
            "PE Mean 5Y": 12.0,
            "PE +1SD 5Y": 15.0,
            "B9 PE Semantic Validity": "VALID_CONTEXT",
            "PBV": 1.2,
            "B9 PBV Semantic Validity": "SPECIAL_TREATMENT",
            "Net Income TTM": 100.0,
            "Cash From Operations TTM": 60.0,
        }

    def test_missing_is_not_zero(self):
        r = self.base(); r["CAPEX TTM"] = None
        e = EvidenceInterpreter(r).evidence("CAPEX TTM")
        self.assertEqual(e.state, EvidenceState.MISSING)
        self.assertIsNone(e.value)

    def test_not_applicable_is_not_missing(self):
        e = EvidenceInterpreter(self.base()).evidence("NIM", applicable=False)
        self.assertEqual(e.state, EvidenceState.NOT_APPLICABLE)

    def test_directional_uses_current_and_previous(self):
        f = EvidenceInterpreter(self.base()).directional(
            current="RSI14", previous="Previous RSI14", horizon=Horizon.SWING,
            family="MOMENTUM", finding_id="S2.SW.MOM.001")
        self.assertIn("menurun", f.summary)
        self.assertEqual(len(f.evidence), 2)

    def test_historical_valid_context(self):
        f = EvidenceInterpreter(self.base()).historical_band(
            current="PE TTM", low="PE -1SD 5Y", mean="PE Mean 5Y", high="PE +1SD 5Y",
            semantic_field="B9 PE Semantic Validity", horizon=Horizon.LONG_TERM,
            family="VALUATION", finding_id="S2.LT.VAL.001")
        self.assertIn("-1SD", f.summary)

    def test_special_treatment_blocks_normal_historical_read(self):
        r = self.base(); r.update({"PBV -1SD 5Y": .8, "PBV Mean 5Y": 1.0, "PBV +1SD 5Y": 1.4})
        f = EvidenceInterpreter(r).historical_band(
            current="PBV", low="PBV -1SD 5Y", mean="PBV Mean 5Y", high="PBV +1SD 5Y",
            semantic_field="B9 PBV Semantic Validity", horizon=Horizon.LONG_TERM,
            family="VALUATION", finding_id="S2.LT.VAL.002")
        self.assertIn("perlakuan khusus", f.summary)

    def test_company_context_symbol_must_match(self):
        with self.assertRaises(ValueError):
            EvidenceInterpreter(self.base(), CompanyContext(symbol="OTHER", business_context="BANK"))

    def test_relation_does_not_score_or_mutate(self):
        r = self.base(); before = dict(r)
        f = EvidenceInterpreter(r).relation(
            left="Net Income TTM", right="Cash From Operations TTM", horizon=Horizon.LONG_TERM,
            family="CASH_QUALITY", finding_id="S2.LT.CASH.001", relation_name="Laba terhadap arus kas")
        self.assertEqual(r, before)
        self.assertNotIn("score", f.__dict__)


if __name__ == "__main__":
    unittest.main()
