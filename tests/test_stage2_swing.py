import copy
import unittest

from stage2 import EvidenceInterpreter, FindingKind
from stage2.swing import SwingResearch


def base():
    return {
        "symbol":"TEST", "Price":120, "Price MA20":115, "Price MA50":105, "Price MA100":100, "Price MA200":90,
        "RSI14":62, "Previous RSI14":58, "MACD":3, "Previous MACD":2, "ADX14":25, "DI+":30, "DI-":18,
        "Volume":150, "Volume MA20":100, "Value":1000, "ADTV30":900, "ADTV90":1000,
        "RS Line 1M":2, "RS Line 3M":5, "RS Line 6M":7, "RS Line 9M":9, "RS Line 1Y":10,
        "Foreign Flow":1, "Net Foreign Buy / Sell":1, "1 Month Net Foreign Flow":2, "3 Month Net Foreign Flow":3,
        "Bandar Accum/Dist":1, "Bandar Value":1,
        "ATR14":4, "ADR14":3, "Beta 3Y":1.1, "StdDev 3Y":20, "52W High":140, "52W Low":70,
    }

class TestSwingResearch(unittest.TestCase):
    def research(self, r=None): return SwingResearch(EvidenceInterpreter(r or base()))
    def test_positive_case(self):
        fs=self.research().research(); by={f.family:f for f in fs if f.family not in {"MOMENTUM"}}
        self.assertEqual(by["TREND"].kind, FindingKind.SUPPORT)
        self.assertEqual(by["PARTICIPATION"].kind, FindingKind.SUPPORT)
        self.assertEqual(by["RELATIVE_STRENGTH"].kind, FindingKind.SUPPORT)
        self.assertEqual(by["FLOW"].kind, FindingKind.SUPPORT)
    def test_trend_contradiction(self):
        r=base(); r.update({"Price":80,"Price MA20":90,"Price MA50":100,"Price MA100":110})
        f=self.research(r).trend(); self.assertEqual(f.kind, FindingKind.CONTRADICTION); self.assertEqual(f.materiality,"MATERIAL")
    def test_momentum_can_weaken_inside_positive_trend(self):
        r=base(); r.update({"RSI14":61,"Previous RSI14":68,"MACD":1,"Previous MACD":3})
        fs=self.research(r).momentum(); self.assertTrue(any(f.kind==FindingKind.CONTRADICTION for f in fs))
        self.assertEqual(self.research(r).trend().kind, FindingKind.SUPPORT)
    def test_missing_not_negative(self):
        r=base(); r["Volume"]=None
        self.assertEqual(self.research(r).participation().kind, FindingKind.UNKNOWN)
    def test_flow_mixed_is_context(self):
        r=base(); r.update({"Foreign Flow":1,"Net Foreign Buy / Sell":-1,"1 Month Net Foreign Flow":2,"3 Month Net Foreign Flow":-2,"Bandar Accum/Dist":0})
        self.assertEqual(self.research(r).flow().kind, FindingKind.CONTEXT)
    def test_volatility_is_risk_not_contradiction(self):
        r=base(); r.update({"ATR14":10,"ADR14":8,"Beta 3Y":2})
        self.assertEqual(self.research(r).volatility_risk().kind, FindingKind.RISK)
    def test_does_not_mutate_s1(self):
        r=base(); before=copy.deepcopy(r); self.research(r).research(); self.assertEqual(r,before)
    def test_no_score_or_recommendation(self):
        for f in self.research().research():
            self.assertNotIn("score", f.__dict__); self.assertNotIn("recommendation", f.__dict__)
    def test_unique_lineage_ids(self):
        ids=[f.finding_id for f in self.research().research()]; self.assertEqual(len(ids),len(set(ids)))

if __name__=='__main__': unittest.main()

class TestSwingMateriality(unittest.TestCase):
    def r(self,d=None): return SwingResearch(EvidenceInterpreter(d or base()))
    def test_actionable_materiality_matrix(self):
        r=self.r()
        self.assertEqual(r.trend().materiality,"MODERATE")
        moms=r.momentum(); self.assertEqual([x.materiality for x in moms],["MODERATE","MINOR","MODERATE"])
        self.assertEqual(r.participation().materiality,"MODERATE")
        self.assertEqual(r.relative_strength().materiality,"MODERATE")
        self.assertEqual(r.flow().materiality,"MODERATE")
    def test_unknown_branches_remain_unassessed(self):
        d=base(); d.update({"RSI14":None,"MACD":None,"ADX14":None})
        for x in self.r(d).momentum():
            self.assertEqual(x.kind,FindingKind.UNKNOWN); self.assertEqual(x.materiality,"UNASSESSED")
