import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from pipeline_p10_orchestrator import run_pipeline

def pkg():
 return {'ticker':'AAA','swing':{'ticker':'AAA','horizon':'SWING','thesis_status':'CONFIRMED','confidence':'HIGH'},
         'long_term':{'ticker':'AAA','horizon':'LONG_TERM','thesis_status':'CONFIRMED','confidence':'HIGH'}}

class InternalCanonicalP9R1(unittest.TestCase):
 def test_internal_market_without_ohlcv_is_valid_payload(self):
  c={'symbol':'AAA','Price':100.0,'Previous Price':99.0,'Open':99.5,'High':102.0,'Low':98.5,'VWAP':100.2,
     'Price MA20':97.0,'Price MA50':94.0,'Price MA100':90.0,'Price MA200':85.0,'RSI14':60.0,'Previous RSI14':58.0,
     'MACD':2.0,'Previous MACD':1.5,'ADX14':25.0,'DI+':30.0,'DI-':15.0,'ATR14':3.0,'ADR14':4.0,
     'Volume':2000.0,'Previous Volume':1500.0,'Volume MA20':1600.0,'ADTV30':1e10,'ADTV90':9e9,
     'RS Line 3M':80.0,'RS Line 6M':75.0,'RS Line 9M':70.0,
     'Net Profit Margin TTM':15.0,'ROIC TTM':18.0,'Piotroski Score':7.0,'Cash From Operations TTM':1000.0,
     'Derived Free Cash Flow TTM':700.0,'Net Income TTM':800.0,'Revenue TTM':5000.0,'PE TTM':12.0,
     'Expected EPS (Growth: YoY)':10.0,'EPS (Forward)':11.0}
  r=run_pipeline(stage2_records=[pkg()],analysis_as_of='2026-09-21',canonical_by_symbol={'AAA':c})
  self.assertEqual(r.state,'PASS'); p=r.payloads[0]
  self.assertEqual(p['technical_enrichment']['ohlcv'],[])
  self.assertEqual(p['technical_enrichment']['internal_market']['price'],100.0)
  self.assertEqual(p['fundamental_enrichment']['npm'],15.0)
  self.assertEqual(p['cash_enrichment']['ocf_ttm'],1000.0)
  self.assertEqual(p['valuation_enrichment']['pe'],12.0)
  self.assertEqual(p['forward_enrichment']['expected_eps_growth_yoy'],10.0)
  self.assertEqual(p['technical_enrichment']['metadata']['source'],'S1_CANONICAL_INTERNAL')

 def test_external_ohlcv_slot_remains_available(self):
  bars=[{'open':1,'high':2,'low':1,'close':2,'volume':3}]
  r=run_pipeline(stage2_records=[pkg()],analysis_as_of='2026-09-21',canonical_by_symbol={'AAA':{'Price':2.0}},ohlcv_by_symbol={'AAA':bars})
  self.assertEqual(r.payloads[0]['technical_enrichment']['ohlcv'],bars)
  self.assertEqual(r.payloads[0]['technical_enrichment']['internal_market']['price'],2.0)

if __name__=='__main__':unittest.main()
