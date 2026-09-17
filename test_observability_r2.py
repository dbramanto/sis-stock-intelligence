from pathlib import Path
import re
from sis_core import parse,norm,align_to_expected,missing_value_details
from app_schema import EXPECTED
text=Path(__file__).with_name('stockbit_realdata_fixture_2026-09-16.txt').read_text(encoding='utf-8')
parts=re.split(r'(?m)^Batch [123]\s*$',text)
raw=[]; ds=[]
for i in range(3):
 d=parse(parts[i+1]);a,_=align_to_expected(d,EXPECTED[i],i+1);raw.append(a);ds.append(norm(a))
md=missing_value_details(raw,ds)
assert len(md)==19, len(md)
assert (md['Source Batch']==1).sum()==15
assert (md['Source Batch']==2).sum()==4
assert (md['Source Batch']==3).sum()==0
assert set(md[md['Source Batch']==1]['Field'])=={'Rank (RS 9m)'}
assert set(md[md['Source Batch']==2]['Field'])=={'Debt to Equity Ratio (Quarter)'}
assert set(md['Source Value'])=={'-'}
assert set(md['Status'])=={'SOURCE MISSING'}
print('PASS NULL TRANSPARENCY — 19/19 traced to source')
print('PASS BATCH 1 — 15 missing Rank (RS 9m)')
print('PASS BATCH 2 — 4 missing Debt to Equity Ratio (Quarter)')
print('PASS BATCH 3 — 0 missing')
print('PASS OBSERVABILITY R2')
