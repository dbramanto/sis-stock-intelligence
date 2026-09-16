from pathlib import Path
import pandas as pd
from sis_stage2 import parse_fixture
from stage2_adapter import run_stage2, MAPS

b=parse_fixture(Path("stage2_fixture_v1.txt").read_text(encoding="utf-8"))
ds=[]
for i in (1,2,3):
 rev={v:k for k,v in MAPS[i].items()}
 rows=[]
 for sym,data in b[i].items():
  row={"Symbol":sym}
  for k,v in data.items():
   if k in rev:row[rev[k]]=v
  rows.append(row)
 ds.append(pd.DataFrame(rows))
o=run_stage2(ds)
assert o["integrity"]["state"]=="PASS" and len(o["results"])==24
by={r["symbol"]:r for r in o["results"]}
assert by["SLIS"]["eligibility"]=="REVIEW"
assert by["ANTM"]["eligibility"]=="ELIGIBLE"
assert by["KJEN"]["eligibility"]=="ELIGIBLE"
assert by["AYAM"]["eligibility"]=="CONDITIONAL"
print("PASS INTEGRATION — 24/24 — Stage 2 connected")
