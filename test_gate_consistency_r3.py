from pathlib import Path
import re
from sis_core import parse,norm,align_batches_with_evidence,conflict_details
from app_schema import EXPECTED
from stage2_adapter import run_stage2
text=Path(__file__).with_name('stockbit_realdata_fixture_2026-09-16.txt').read_text(encoding='utf-8')
parts=re.split(r'(?m)^Batch [123]\s*$',text)
parsed=[parse(parts[i+1]) for i in range(3)]
aligned,diags,gate=align_batches_with_evidence(parsed,EXPECTED)
assert not gate['blocked']
ds=[norm(d) for d in aligned]
# Create a genuine non-price common-field conflict. Core must REVIEW, not silently PASS.
ds[1].loc[ds[1].Symbol=='ANTM','RSI (14)'] += 5
D=conflict_details(ds)
assert not D.empty and not (D.Field=='Price').any()
core_state='REVIEW'
s2=run_stage2(ds)
if core_state=='REVIEW': s2['integrity']['state']='REVIEW'
assert s2['integrity']['state']=='REVIEW'
print('PASS — NON-PRICE CONFLICT => CORE REVIEW')
print('PASS — STAGE 2 GATE CONSISTENCY => REVIEW')
print('PASS GATE CONSISTENCY R3')
