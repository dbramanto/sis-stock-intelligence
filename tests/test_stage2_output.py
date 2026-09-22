import unittest
from stage2 import Finding, FindingKind, EvaluationMode, Horizon, ThesisPackage
from stage2.output import build_research_package, build_symbol_research_package, serialize_thesis


def pkg(symbol,horizon,status="CONFIRMED",conf="HIGH"):
    f=Finding("f1",horizon,"TREND" if horizon==Horizon.SWING else "GROWTH",EvaluationMode.RELATIONAL,FindingKind.SUPPORT,"reason",(),"MODERATE")
    return ThesisPackage(symbol,horizon,status,conf,["reason"],[],["risk"],["invalidate"],[f])

class TestStage2Output(unittest.TestCase):
    def test_contract_fields(self):
        d=serialize_thesis(pkg("AAA",Horizon.SWING))
        self.assertEqual(set(d),{"ticker","horizon","thesis_status","confidence","main_reasons","key_contradictions","key_risks","invalidation_condition","evidence_lineage"})
    def test_no_decision_fields(self):
        d=serialize_thesis(pkg("AAA",Horizon.SWING))
        for k in ("recommendation","action","buy","sell","score","rank","entry","tp","sl"):
            self.assertNotIn(k,d)
    def test_independent_horizons(self):
        d=build_symbol_research_package("AAA",pkg("AAA",Horizon.SWING,"CONFIRMED"),pkg("AAA",Horizon.LONG_TERM,"WEAKENED"))
        self.assertEqual(d["swing"]["thesis_status"],"CONFIRMED")
        self.assertEqual(d["long_term"]["thesis_status"],"WEAKENED")
    def test_symbol_mismatch_rejected(self):
        with self.assertRaises(ValueError): build_symbol_research_package("AAA",pkg("AAA",Horizon.SWING),pkg("BBB",Horizon.LONG_TERM))
    def test_horizon_mismatch_rejected(self):
        with self.assertRaises(ValueError): build_symbol_research_package("AAA",pkg("AAA",Horizon.LONG_TERM),pkg("AAA",Horizon.SWING))
    def test_duplicate_rejected(self):
        p=pkg("AAA",Horizon.SWING)
        with self.assertRaises(ValueError): build_research_package([p,p])
    def test_deterministic_not_ranked(self):
        out=build_research_package([pkg("BBB",Horizon.SWING),pkg("AAA",Horizon.SWING)])
        self.assertEqual([x["ticker"] for x in out],["AAA","BBB"])
        self.assertFalse(any("rank" in x for x in out))
    def test_invalid_status_rejected(self):
        with self.assertRaises(ValueError): serialize_thesis(pkg("AAA",Horizon.SWING,"BUY"))
    def test_invalid_confidence_rejected(self):
        with self.assertRaises(ValueError): serialize_thesis(pkg("AAA",Horizon.SWING,"CONFIRMED","99"))
    def test_lineage_keeps_ids_without_raw_dump(self):
        d=serialize_thesis(pkg("AAA",Horizon.SWING))
        self.assertEqual(d["evidence_lineage"][0]["finding_id"],"f1")
        self.assertNotIn("value",d["evidence_lineage"][0]["evidence"][0] if d["evidence_lineage"][0]["evidence"] else {})

if __name__=='__main__': unittest.main()
