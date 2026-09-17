import math
import numpy as np
from sis_stage2 import integrity_gate, evaluate_symbol

MAPS={1:{
"Volume":"volume","Volume MA 20":"volume_ma20","Price MA 20":"price_ma20","Price MA 50":"price_ma50","RSI (14)":"rsi14","ADTV 30":"adtv30","Price":"price","Price MA 200":"price_ma200","Average Directional Index 14":"adx14","Average Directional Index DI+ 14":"di_plus14","Average Directional Index DI- 14":"di_minus14","MACD (12,26)":"macd","Previous MACD (12,26)":"prev_macd","Previous RSI (14)":"prev_rsi14","Average True Range 14":"atr14","Average Daily Range 14":"adr14","Value":"value","Rank (RS 3m)":"rs3m","Rank (RS 6m)":"rs6m","Rank (RS 9m)":"rs9m"},
2:{"Volume":"volume","Volume MA 20":"volume_ma20","Price MA 20":"price_ma20","Price MA 50":"price_ma50","RSI (14)":"rsi14","ADTV 30":"adtv30","Price":"price","Net Profit Margin (TTM)(%)":"npm_ttm","Return On Invested Capital (TTM)":"roic_ttm","Piotroski F-Score":"piotroski","Earnings Yield (TTM)":"earnings_yield_ttm","Debt to Equity Ratio (Quarter)":"de_quarter","EPS (TTM YoY Growth)":"eps_yoy"},
3:{"Volume":"volume","Volume MA 20":"volume_ma20","Price MA 20":"price_ma20","Price MA 50":"price_ma50","RSI (14)":"rsi14","ADTV 30":"adtv30","Price":"price","Operating Cash Flow (Quarter)":"ocf_q","Free cash flow (TTM)":"fcf_ttm","Free cash flow (Quarter)":"fcf_q","Net Income (Quarter)":"ni_q","Net Income (Annual)":"ni_annual","Net Income (TTM)":"ni_ttm","Net Income (YTD)":"ni_ytd"}}

def _v(x):
 try:
  if x is None or bool(np.isnan(x)): return None
 except Exception: pass
 try:return float(x)
 except Exception:return None

def frames_to_stage2(ds):
 batches={}
 for i,d in enumerate(ds,1):
  rows={}
  if d is not None and not d.empty and "Symbol" in d.columns:
   for _,r in d.iterrows():
    sym=str(r["Symbol"]).strip().upper()
    rows[sym]={dst:_v(r.get(src)) for src,dst in MAPS[i].items()}
  batches[i]=rows
 return batches

def run_stage2(ds):
 b=frames_to_stage2(ds)
 gate=integrity_gate(b)
 universe=sorted(set().union(*(set(b[i]) for i in (1,2,3))))
 if gate["state"] == "BLOCKED":
  return {"integrity":gate,"results":[]}
 return {"integrity":gate,"results":[evaluate_symbol(sym,b) for sym in universe]}
