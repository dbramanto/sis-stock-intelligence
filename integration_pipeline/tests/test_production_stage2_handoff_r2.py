import sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from upstream_mapper import map_stage2_output
from pipeline_p10_orchestrator import run_pipeline


def pkg(sym='AAA', sw='CONFIRMED', lt='PARTIALLY_CONFIRMED'):
    def h(name,status,conf):
        return {'ticker':sym,'horizon':name,'thesis_status':status,'confidence':conf,
                'main_reasons':['x'],'key_contradictions':[],'key_risks':[],
                'invalidation_condition':['y'],'evidence_lineage':[]}
    return {'ticker':sym,'swing':h('SWING',sw,'HIGH'),'long_term':h('LONG_TERM',lt,'MEDIUM')}

class ProductionStage2HandoffR2(unittest.TestCase):
    def test_production_package_kept_in_scope_without_eligibility(self):
        r=map_stage2_output([pkg()], '2026-09-21')
        self.assertEqual(r.scope.symbols,('AAA',))
        self.assertFalse(r.diagnostics)
        mids={x.metric_id:x.normalized_value for x in r.evidence}
        self.assertEqual(mids['stage2_swing_thesis_status'],'CONFIRMED')
        self.assertEqual(mids['stage2_long_term_thesis_status'],'PARTIALLY_CONFIRMED')
        self.assertNotIn('stage2_eligibility',mids)
        self.assertFalse(any('score' in k for k in mids))

    def test_invalidated_thesis_is_prior_not_scope_exclusion(self):
        r=map_stage2_output([pkg(sw='INVALIDATED',lt='INVALIDATED')], '2026-09-21')
        self.assertEqual(r.scope.symbols,('AAA',))
        self.assertFalse(r.excluded)

    def test_duplicate_symbol_fails_closed_from_second_record(self):
        r=map_stage2_output([pkg(),pkg()], '2026-09-21')
        self.assertEqual(r.scope.symbols,('AAA',))
        self.assertIn('AAA:DUPLICATE_STAGE2_SYMBOL',r.diagnostics)

    def test_p10_passes_exact_production_stage2_object_to_p9(self):
        p=pkg()
        r=run_pipeline(stage2_records=[p],analysis_as_of='2026-09-21')
        self.assertEqual(r.state,'PASS')
        self.assertEqual(r.scope_symbols,('AAA',))
        self.assertEqual(r.payloads[0]['stage2'],p)
        self.assertEqual(r.payloads[0]['technical_enrichment']['ohlcv'],[])

if __name__=='__main__': unittest.main()
