import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from stage3i_swing import evaluate_swing

def inputs(status='PASS',price=100,ma20=98,ma50=95,atr=3,adr=4,**kw):
 m={'price':price,'previous_price':99,'high':102,'low':98,'vwap':100,'ma20':ma20,'ma50':ma50,'atr14':atr,'adr14':adr};m.update(kw)
 syn={'symbol':'AAA','swing':{'quality':82,'confidence':90,'analytical_status':status}}
 tech={'state':'BULL','confidence':'HIGH','components':{'trend':{'state':'BULL'},'momentum':{'state':'ACCELERATING'},'participation':{'state':'CONFIRMED'},'relative_strength':{'state':'IMPROVING'},'setup_entry':{'state':'PULLBACK'}},'data_quality':{'freshness':'FRESH'},'contradiction_severity':'NONE'}
 dos={'symbol':'AAA','domains':{'technical':tech}}
 stock={'symbol':'AAA','technical_enrichment':{'ohlcv':[],'internal_market':m}}
 return syn,dos,stock
class SwingR2(unittest.TestCase):
 def test_no_ohlcv_can_produce_complete_plan(self):
  r=evaluate_swing(*inputs()); self.assertEqual(r['status'],'COMPLETE'); self.assertEqual(r['execution_method'],'INTERNAL_VOLATILITY'); self.assertIsNotNone(r['entry_area']); self.assertIsNotNone(r['target_1']); self.assertIsNotNone(r['risk_boundary'])
 def test_s3h_not_pass_cannot_be_ready(self):
  r=evaluate_swing(*inputs(status='REVIEW')); self.assertNotEqual(r['execution_status'],'READY')
 def test_poor_rr_not_manipulated(self):
  syn,dos,stock=inputs(low=99.5,vwap=99.8,previous_price=99.9,atr=1,adr=1.2); r=evaluate_swing(syn,dos,stock); self.assertIn(r['execution_status'],{'NOT_ATTRACTIVE','WAIT'}); self.assertIsNotNone(r['reward_risk']['target_1'])
 def test_missing_atr_fails_closed(self):
  r=evaluate_swing(*inputs(atr=None)); self.assertEqual(r['execution_status'],'INSUFFICIENT_DATA')
 def test_external_slot_does_not_override_internal_default(self):
  syn,dos,stock=inputs(); stock['technical_enrichment']['ohlcv']=[{'open':1,'high':2,'low':1,'close':2,'volume':1}]*60; r=evaluate_swing(syn,dos,stock); self.assertEqual(r['execution_method'],'INTERNAL_VOLATILITY')
if __name__=='__main__':unittest.main()
