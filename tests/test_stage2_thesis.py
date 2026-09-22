import unittest
from stage2 import Finding, FindingKind, EvaluationMode, Horizon, ThesisBuilder


def f(i, h, fam, kind, mat="UNASSESSED", text=None):
    return Finding(i,h,fam,EvaluationMode.RELATIONAL,kind,text or f"{fam} {kind.value}",(),mat)

class TestThesisBuilder(unittest.TestCase):
    def test_confirmed_requires_breadth(self):
        fs=[f("1",Horizon.SWING,"TREND",FindingKind.SUPPORT),f("2",Horizon.SWING,"MOMENTUM",FindingKind.SUPPORT),f("3",Horizon.SWING,"PARTICIPATION",FindingKind.SUPPORT)]
        p=ThesisBuilder("X",Horizon.SWING,fs).build(); self.assertEqual(p.thesis_status,"CONFIRMED"); self.assertEqual(p.confidence,"HIGH")
    def test_material_contradiction_not_outvoted(self):
        fs=[f("1",Horizon.LONG_TERM,"GROWTH",FindingKind.SUPPORT),f("2",Horizon.LONG_TERM,"PROFITABILITY",FindingKind.SUPPORT),f("3",Horizon.LONG_TERM,"EFF",FindingKind.SUPPORT),f("4",Horizon.LONG_TERM,"CASH",FindingKind.CONTRADICTION,"MATERIAL")]
        self.assertEqual(ThesisBuilder("X",Horizon.LONG_TERM,fs).build().thesis_status,"WEAKENED")
    def test_two_material_contradictions_invalidate(self):
        fs=[f("1",Horizon.LONG_TERM,"GROWTH",FindingKind.SUPPORT),f("2",Horizon.LONG_TERM,"CASH",FindingKind.CONTRADICTION,"MATERIAL"),f("3",Horizon.LONG_TERM,"FIN",FindingKind.CONTRADICTION,"MATERIAL")]
        self.assertEqual(ThesisBuilder("X",Horizon.LONG_TERM,fs).build().thesis_status,"INVALIDATED")
    def test_moderate_risk_partial(self):
        fs=[f("1",Horizon.SWING,"TREND",FindingKind.SUPPORT),f("2",Horizon.SWING,"MOM",FindingKind.SUPPORT),f("3",Horizon.SWING,"RS",FindingKind.SUPPORT),f("4",Horizon.SWING,"RISK",FindingKind.RISK,"MODERATE")]
        self.assertEqual(ThesisBuilder("X",Horizon.SWING,fs).build().thesis_status,"PARTIALLY_CONFIRMED")
    def test_missing_lowers_confidence_not_strength_vote(self):
        fs=[f("1",Horizon.SWING,"TREND",FindingKind.SUPPORT),f("2",Horizon.SWING,"MOM",FindingKind.SUPPORT),f("3",Horizon.SWING,"RS",FindingKind.SUPPORT),f("4",Horizon.SWING,"FLOW",FindingKind.UNKNOWN),f("5",Horizon.SWING,"PART",FindingKind.UNKNOWN),f("6",Horizon.SWING,"RISK",FindingKind.UNKNOWN)]
        p=ThesisBuilder("X",Horizon.SWING,fs).build(); self.assertEqual(p.confidence,"LOW"); self.assertEqual(p.thesis_status,"CONFIRMED")
    def test_insufficient(self):
        fs=[f("1",Horizon.LONG_TERM,"G",FindingKind.UNKNOWN),f("2",Horizon.LONG_TERM,"P",FindingKind.UNKNOWN),f("3",Horizon.LONG_TERM,"C",FindingKind.SUPPORT)]
        self.assertEqual(ThesisBuilder("X",Horizon.LONG_TERM,fs).build().thesis_status,"INSUFFICIENT_EVIDENCE")
    def test_business_context_unknown_not_confidence_penalty(self):
        fs=[f("1",Horizon.LONG_TERM,"G",FindingKind.SUPPORT),f("2",Horizon.LONG_TERM,"P",FindingKind.SUPPORT),f("3",Horizon.LONG_TERM,"C",FindingKind.SUPPORT),f("4",Horizon.LONG_TERM,"BUSINESS_CONTEXT",FindingKind.UNKNOWN)]
        self.assertEqual(ThesisBuilder("X",Horizon.LONG_TERM,fs).build().confidence,"HIGH")
    def test_mixed_horizon_rejected(self):
        fs=[f("1",Horizon.SWING,"A",FindingKind.SUPPORT),f("2",Horizon.LONG_TERM,"B",FindingKind.SUPPORT)]
        with self.assertRaises(ValueError): ThesisBuilder("X",Horizon.SWING,fs)
    def test_no_recommendation_or_score(self):
        fs=[f("1",Horizon.SWING,"A",FindingKind.SUPPORT),f("2",Horizon.SWING,"B",FindingKind.SUPPORT),f("3",Horizon.SWING,"C",FindingKind.SUPPORT)]
        p=ThesisBuilder("X",Horizon.SWING,fs).build(); self.assertNotIn("recommendation",p.__dict__); self.assertNotIn("score",p.__dict__)

if __name__ == '__main__': unittest.main()

class TestSpecificInvalidation(unittest.TestCase):
    def test_confirmed_has_family_specific_invalidation(self):
        fs=[f("1",Horizon.SWING,"TREND",FindingKind.SUPPORT,"MODERATE"),f("2",Horizon.SWING,"MOMENTUM",FindingKind.SUPPORT,"MODERATE"),f("3",Horizon.SWING,"PARTICIPATION",FindingKind.SUPPORT,"MODERATE")]
        p=ThesisBuilder("X",Horizon.SWING,fs).build()
        self.assertTrue(p.invalidation_condition); self.assertTrue(any("tren" in x.lower() for x in p.invalidation_condition))
        self.assertFalse(any("evidence utama yang mendukung" in x.lower() for x in p.invalidation_condition))
    def test_weakened_has_nonempty_specific_invalidation(self):
        fs=[f("1",Horizon.LONG_TERM,"GROWTH",FindingKind.SUPPORT,"MODERATE"),f("2",Horizon.LONG_TERM,"PROFITABILITY",FindingKind.CONTRADICTION,"MODERATE"),f("3",Horizon.LONG_TERM,"CAPITAL_EFFICIENCY",FindingKind.CONTRADICTION,"MODERATE")]
        p=ThesisBuilder("X",Horizon.LONG_TERM,fs).build(); self.assertEqual(p.thesis_status,"WEAKENED")
        self.assertTrue(p.invalidation_condition); self.assertTrue(any("margin" in x.lower() or "roic" in x.lower() for x in p.invalidation_condition))
    def test_material_contradiction_drives_specific_invalidation(self):
        fs=[f("1",Horizon.LONG_TERM,"GROWTH",FindingKind.SUPPORT,"MODERATE"),f("2",Horizon.LONG_TERM,"CASH_QUALITY",FindingKind.CONTRADICTION,"MATERIAL")]
        p=ThesisBuilder("X",Horizon.LONG_TERM,fs).build(); self.assertTrue(any("arus kas" in x.lower() for x in p.invalidation_condition))
