import copy, unittest
from stage2 import CompanyContext, EvidenceInterpreter, FindingKind
from stage2.longterm import LongTermResearch

def base():
    return {"symbol":"TEST",
      "Revenue Quarterly YoY":12,"Revenue Annual YoY":10,"Revenue Growth 3Y":8,
      "Net Income Quarterly YoY":15,"Net Income Annual YoY":12,"EPS Quarter YoY":14,"EPS Annual YoY":11,"EPS 3Y CAGR":9,
      "Gross Margin TTM":30,"Operating Margin TTM":18,"Net Profit Margin TTM":12,"Avg Net Profit Margin 5Y":10,
      "ROIC TTM":15,"ROE TTM":18,"ROCE TTM":16,"ROA TTM":8,"Asset Turnover":1.1,"Avg ROE 3Y":17,
      "Cash":500,"Short Term Investments":100,"Current Assets":1000,"Current Liabilities":600,"Short Term Debt Quarter":100,
      "Long Term Debt Quarter":200,"Total Debt Quarter":300,"Total Equity Quarter":1500,"Interest Coverage TTM":6,"Finance Cost TTM":50,
      "Net Income TTM":400,"Cash From Operations TTM":500,"Operating Cash Flow Quarter":130,"CAPEX TTM":100,"Free Cash Flow TTM":400,
      "PE TTM":10,"PE -1SD 5Y":8,"PE Mean 5Y":12,"PE +1SD 5Y":16,"B9 PE Semantic Validity":"VALID_CONTEXT",
      "PBV":1.5,"PBV -1SD 5Y":1.2,"PBV Mean 5Y":1.8,"PBV +1SD 5Y":2.4,"B9 PBV Semantic Validity":"VALID_CONTEXT",
      "EV/EBITDA TTM":6,"Earnings Yield TTM":10,"Forward PE":9,"PEG":1.1}

class TestLongTerm(unittest.TestCase):
    def r(self,d=None,ctx=None): return LongTermResearch(EvidenceInterpreter(d or base(),ctx))
    def test_positive_core(self):
        fs=self.r().research(); by={f.family:f for f in fs if f.family not in {"VALUATION"}}
        for fam in ("GROWTH","PROFITABILITY","CAPITAL_EFFICIENCY","FINANCIAL_STRENGTH","CASH_QUALITY"):
            self.assertEqual(by[fam].kind,FindingKind.SUPPORT)
    def test_turnaround_is_context_not_full_support(self):
        d=base(); d.update({"Revenue Growth 3Y":-5,"EPS 3Y CAGR":-4,"Revenue Annual YoY":-2,"Net Income Annual YoY":-3,"EPS Annual YoY":-1})
        self.assertEqual(self.r(d).growth()[0].kind,FindingKind.CONTEXT)
    def test_profit_cash_contradiction_material(self):
        d=base(); d["Cash From Operations TTM"]=-50
        f=self.r(d).cash_quality(); self.assertEqual(f.kind,FindingKind.CONTRADICTION); self.assertEqual(f.materiality,"MATERIAL")
    def test_negative_fcf_is_risk_not_automatic_invalidation(self):
        d=base(); d["Free Cash Flow TTM"]=-100
        self.assertEqual(self.r(d).cash_quality().kind,FindingKind.RISK)
    def test_missing_is_unknown(self):
        d=base(); d["Net Income TTM"]=None
        self.assertEqual(self.r(d).cash_quality().kind,FindingKind.UNKNOWN)
    def test_special_pe_not_forced(self):
        d=base(); d["B9 PE Semantic Validity"]="SPECIAL_TREATMENT"
        self.assertEqual(self.r(d).valuation()[0].kind,FindingKind.UNKNOWN)
    def test_no_company_context_does_not_guess_sector(self):
        self.assertEqual(self.r().business_context().kind,FindingKind.UNKNOWN)
    def test_minimal_company_context(self):
        c=CompanyContext(symbol="TEST",business_context="BANKING",sector="Financials")
        self.assertEqual(self.r(base(),c).business_context().kind,FindingKind.CONTEXT)
    def test_does_not_mutate_s1(self):
        d=base(); before=copy.deepcopy(d); self.r(d).research(); self.assertEqual(d,before)
    def test_no_score_recommendation(self):
        for f in self.r().research():
            self.assertNotIn("score",f.__dict__); self.assertNotIn("recommendation",f.__dict__)
    def test_unique_ids(self):
        ids=[f.finding_id for f in self.r().research()]; self.assertEqual(len(ids),len(set(ids)))
if __name__=='__main__': unittest.main()

class TestLongTermMateriality(unittest.TestCase):
    def r(self,d=None,ctx=None): return LongTermResearch(EvidenceInterpreter(d or base(),ctx))
    def test_positive_core_materiality(self):
        fs={f.family:f for f in self.r().research()}
        for fam in ("GROWTH","PROFITABILITY","CAPITAL_EFFICIENCY","FINANCIAL_STRENGTH","CASH_QUALITY"):
            self.assertEqual(fs[fam].kind,FindingKind.SUPPORT); self.assertEqual(fs[fam].materiality,"MODERATE")
    def test_growth_persistent_negative_is_material(self):
        d=base();
        for k in ("Revenue Quarterly YoY","Net Income Quarterly YoY","EPS Quarter YoY","Revenue Annual YoY","Net Income Annual YoY","EPS Annual YoY","Revenue Growth 3Y","EPS 3Y CAGR"): d[k]=-5
        f=self.r(d).growth()[0]; self.assertEqual(f.kind,FindingKind.CONTRADICTION); self.assertEqual(f.materiality,"MATERIAL")
    def test_growth_recent_weakness_is_moderate(self):
        d=base(); d.update({"Revenue Quarterly YoY":-5,"Net Income Quarterly YoY":-5,"EPS Quarter YoY":-5})
        f=self.r(d).growth()[0]; self.assertEqual(f.kind,FindingKind.CONTRADICTION); self.assertEqual(f.materiality,"MODERATE")
    def test_profitability_and_efficiency_negative_are_material(self):
        d=base(); d.update({"Operating Margin TTM":-1,"Net Profit Margin TTM":-1,"ROIC TTM":-2,"ROE TTM":-2,"ROCE TTM":-2,"ROA TTM":-2})
        self.assertEqual(self.r(d).profitability().materiality,"MATERIAL")
        self.assertEqual(self.r(d).capital_efficiency().materiality,"MATERIAL")
    def test_sector_applicability_is_explicit(self):
        c=CompanyContext(symbol="TEST",business_context="BANKING",sector="Financials")
        f=self.r(base(),c).business_context(); states={e.field:e.state.value for e in f.evidence}
        self.assertEqual(states["NIM"],"MISSING"); self.assertEqual(states["Mining Properties"],"NOT_APPLICABLE")
