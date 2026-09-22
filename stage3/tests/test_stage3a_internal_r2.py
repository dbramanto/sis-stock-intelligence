import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from stage3a_technical import evaluate_technical

def stock(**over):
 m={'price':100.0,'previous_price':98.0,'open':99.0,'high':102.0,'low':98.0,'vwap':100.0,
    'ma20':98.0,'ma50':95.0,'ma100':90.0,'ma200':85.0,'rsi14':60.0,'previous_rsi14':55.0,
    'macd':2.0,'previous_macd':1.0,'adx14':25.0,'di_plus':30.0,'di_minus':15.0,
    'atr14':3.0,'adr14':4.0,'volume':2000.0,'previous_volume':1500.0,'volume_ma20':1500.0,
    'adtv30':1e10,'adtv90':9e9,'rs_3m':90.0,'rs_6m':80.0,'rs_9m':70.0}
 m.update(over)
 return {'technical_enrichment':{'ohlcv':[],'internal_market':m,'metadata':{'source':'S1_CANONICAL_INTERNAL','as_of_date':'2026-09-21'}}}

class TestInternalR2(unittest.TestCase):
 def test_no_ohlcv_uses_internal(self):
  r=evaluate_technical(stock(),'2026-09-21'); self.assertEqual(r['state'],'BULL'); self.assertNotEqual(r['confidence'],'INSUFFICIENT'); self.assertEqual(r['data_quality']['mode'],'INTERNAL_MARKET_EVIDENCE')
 def test_structure_unknown_not_fake_support_resistance(self):
  r=evaluate_technical(stock(),'2026-09-21'); self.assertEqual(r['components']['price_structure']['state'],'UNKNOWN'); self.assertIn('historical_structure=UNAVAILABLE_OPTIONAL',r['components']['price_structure']['evidence'])
 def test_missing_core_trend_fails_closed(self):
  r=evaluate_technical(stock(ma20=None),'2026-09-21'); self.assertEqual(r['state'],'NOT_EVALUATED')
 def test_optional_bad_ohlcv_does_not_block_valid_internal(self):
  s=stock(); s['technical_enrichment']['ohlcv']=[{'bad':1}]; r=evaluate_technical(s,'2026-09-21'); self.assertEqual(r['state'],'BULL')
 def test_bear_internal(self):
  r=evaluate_technical(stock(price=80.0,ma20=85.0,ma50=90.0,ma100=95.0,ma200=100.0),'2026-09-21'); self.assertEqual(r['state'],'BEAR')

if __name__=='__main__':unittest.main()
