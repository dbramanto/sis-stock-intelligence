import unittest,sys,os,tempfile
from datetime import datetime,timezone
import pandas as pd
sys.path.insert(0,os.path.dirname(os.path.dirname(__file__)))
from stage1.schema import BATCHES,B10_SPECIAL_FIELDS
from stage1.pipeline import run_stage1,parse_number,validate_batch
from stage1.clipboard import parse_clipboard_text
from stage1.history import save_snapshot,load_snapshot,get_snapshot_batch

def batches(n=1):
 d={}
 for b,cols in BATCHES.items():
  rows=[]
  for j in range(n):
   row={'Symbol':f'A{j:02d}'}
   for c in cols: row[c]=10
   rows.append(row)
  d[b]=pd.DataFrame(rows)
 d[5]['Short Term Debt Quarter']=3; d[5]['Long Term Debt Quarter']=7
 d[6]['Cash From Operations TTM']=20; d[6]['CAPEX TTM']=-5
 d[7]['PE TTM']=5; d[7]['Market Cap']=100; d[5]['Common Equity']=50
 d[4]['Revenue TTM']=25; d[7]['Enterprise Value']=80; d[4]['EBITDA TTM']=20
 return d

class FinalContract(unittest.TestCase):
 def test_pass(self): self.assertEqual(run_stage1(batches(),expected_total=1)['status'],'PASS')
 def test_all10_required(self):
  x=batches(); del x[10]; self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')
 def test_expected_total_blocks(self): self.assertEqual(run_stage1(batches(),expected_total=2)['status'],'BLOCKED')
 def test_no_expected_is_review(self): self.assertEqual(run_stage1(batches())['status'],'REVIEW')
 def test_symbol_set_mismatch_blocks(self):
  x=batches(); x[10].loc[0,'Symbol']='ZZZ'; self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')
 def test_row_order_irrelevant(self):
  x=batches(2); x[5]=x[5].iloc[::-1].reset_index(drop=True); self.assertEqual(run_stage1(x,expected_total=2)['status'],'PASS')
 def test_duplicate_blocks(self):
  x=batches(); x[1]=pd.concat([x[1],x[1]],ignore_index=True); self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')
 def test_price_conflict_blocks(self):
  x=batches(); x[10].loc[0,'Price']=-11; self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')
 def test_nonprice_control_review(self):
  x=batches(); x[10].loc[0,'Volume']=-11; self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')
 def test_b9_negative_band_special(self):
  x=batches(); x[9].loc[0,'PE -1SD 5Y']=-1; x[9].loc[0,'PE Mean 5Y']=5; x[9].loc[0,'PE +1SD 5Y']=10
  self.assertEqual(run_stage1(x,expected_total=1)['canonical'].iloc[0]['B9 PE Semantic Validity'],'SPECIAL_TREATMENT')
 def test_b10_null_not_zero(self):
  x=batches()
  for c in B10_SPECIAL_FIELDS: x[10][c]=None
  a=run_stage1(x,expected_total=1)['canonical'].iloc[0]
  self.assertEqual(a['B10 Specialized Available Count'],0); self.assertEqual(a['B10 Applicability State'],'NOT_EVALUATED')
 def test_derived(self):
  a=run_stage1(batches(),expected_total=1)['canonical'].iloc[0]
  self.assertEqual(a['Derived Total Debt'],10); self.assertEqual(a['Derived Free Cash Flow TTM'],15); self.assertEqual(a['Derived Earnings Yield TTM'],20)

class ParserRegression(unittest.TestCase):
 def test_parentheses(self): self.assertEqual(parse_number('(1,200)')[0],-1200)
 def test_suffix(self): self.assertEqual(parse_number('2.50 B')[0],2.5e9)
 def test_missing(self): self.assertIsNone(parse_number('-')[0])
 def test_narrow_eps_repair(self): self.assertEqual(parse_number('-,961.72',field='EPS Annual YoY')[0],-961.72)
 def test_ambiguous_elsewhere(self): self.assertEqual(parse_number('-,961.72',field='Other')[1],'AMBIGUOUS_NUMERIC_FORMAT')
 def test_tsv(self):
  df,issues=parse_clipboard_text('Symbol\tPrice\tVolume\nAAA\t1,200\t2.5M'); self.assertFalse(issues); self.assertEqual(df.shape,(1,3))
 def test_vertical_b1_fixture(self):
  from pathlib import Path
  raw=(Path(__file__).resolve().parents[1]/'fixtures'/'B1_RAW_STOCKBIT_GOLDEN.txt').read_text(encoding='utf-8')
  df,issues=parse_clipboard_text(raw); self.assertFalse(issues); self.assertEqual(validate_batch(df,1),[])

class HistoryV3(unittest.TestCase):
 def test_roundtrip_b1_b11(self):
  raw={i:f'raw-{i}' for i in range(1,12)}
  with tempfile.TemporaryDirectory() as td:
   s=save_snapshot(raw,base_dir=td,now=datetime(2026,9,20,tzinfo=timezone.utc),metadata={'expected_total':32})
   x=load_snapshot(s['snapshot_id'],base_dir=td); self.assertEqual(get_snapshot_batch(x,11),'raw-11')
 def test_incomplete_rejected(self):
  with tempfile.TemporaryDirectory() as td:
   with self.assertRaises(ValueError): save_snapshot({i:'x' for i in range(1,11)},base_dir=td)
 def test_old_snapshot_future_batch_empty(self): self.assertEqual(get_snapshot_batch({'raw_batches':{'1':'x'}},10),'')


class B11CoreContract(unittest.TestCase):
 def test_b11_required(self):
  x=batches(); del x[11]; self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')
 def test_b11_universe_mismatch_blocks(self):
  x=batches(); x[11].loc[0,'Symbol']='ZZZ'; self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')
 def test_b11_forward_null_allowed(self):
  x=batches()
  for c in BATCHES[11]:
   if c not in {'Price','Volume','Volume MA20','Price MA20','Price MA50','RSI14','ADTV30'}: x[11][c]=None
  r=run_stage1(x,expected_total=1); self.assertEqual(r['status'],'PASS'); self.assertEqual(len(r['canonical']),1)
 def test_b11_control_conflict_detected(self):
  x=batches(); x[11].loc[0,'Price']=-11; self.assertEqual(run_stage1(x,expected_total=1)['status'],'BLOCKED')


class B11RealDataContract(unittest.TestCase):
 def test_b11_vendor_headers(self):
  expected=[
   "Expected Revenue (Growth: 2Y CAGR)",
   "Expected Revenue (Growth: YoY)",
   "Expected Op. Profit (Growth: YoY)",
   "Expected Op. Profit (Growth: 2Y CAGR)",
   "Expected Net Income (Growth: YoY)",
   "Expected Net Income (Growth: 2Y CAGR)",
   "Expected EPS (Growth: YoY)",
   "Expected EPS (Growth: 2Y CAGR)",
   "EPS (Forward)",
   "PEG (Forward)",
  ]
  for c in expected: self.assertIn(c,BATCHES[11])

 def test_b11_dash_is_valid_missing(self):
  x=batches()
  for c in BATCHES[11]:
   if c not in {"Price","Volume","Volume MA20","Price MA20","Price MA50","RSI14","ADTV30"}:
    x[11][c]="-"
  r=run_stage1(x,expected_total=1)
  self.assertEqual(r["status"],"PASS")
  row=r["canonical"].iloc[0]
  self.assertIsNone(row["EPS (Forward)"])
  self.assertIsNone(row["PEG (Forward)"])


class ReconciliationV2Contract(unittest.TestCase):
 def test_dynamic_control_drift_does_not_block(self):
  x=batches()
  x[1]['Price']=100.0
  x[11]['Price']=102.0
  r=run_stage1(x,expected_total=1)
  self.assertNotEqual(r['status'],'BLOCKED')
  self.assertFalse(any('PRICE_CONFLICT' in str(i) for i in r.get('issues',[])))

 def test_latest_valid_control_becomes_canonical(self):
  x=batches()
  x[1]['Price']=100.0
  x[10]['Price']=101.0
  x[11]['Price']=102.0
  r=run_stage1(x,expected_total=1)
  self.assertEqual(float(r['canonical'].iloc[0]['Price']),102.0)

 def test_universe_mismatch_remains_fail_closed_v2(self):
  x=batches()
  z=x[11].copy()
  z['Symbol']='ZZZZ'
  x[11]=pd.concat([x[11],z],ignore_index=True)
  r=run_stage1(x,expected_total=1)
  self.assertEqual(r['status'],'BLOCKED')


class ControlSanityFinalContract(unittest.TestCase):
 def test_rsi_out_of_range_blocks(self):
  x=batches(); x[11].loc[0,'RSI14']=101
  r=run_stage1(x,expected_total=1)
  self.assertEqual(r['status'],'BLOCKED')
  self.assertTrue(any('CONTROL_SANITY:RSI_OUT_OF_RANGE' in str(i) for i in r.get('issues',[])))

 def test_normal_sequential_drift_uses_latest(self):
  x=batches()
  x[1].loc[0,'Price']=100
  x[10].loc[0,'Price']=101
  x[11].loc[0,'Price']=102
  x[1].loc[0,'RSI14']=55
  x[11].loc[0,'RSI14']=57
  r=run_stage1(x,expected_total=1)
  self.assertEqual(r['status'],'PASS')
  self.assertEqual(float(r['canonical'].iloc[0]['Price']),102.0)
  self.assertEqual(float(r['canonical'].iloc[0]['RSI14']),57.0)


if __name__=='__main__': unittest.main()
