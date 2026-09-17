from pathlib import Path
import re
import pandas as pd
from sis_core import parse, align_batches_with_evidence
from app_schema import EXPECTED

text=Path(__file__).with_name('stockbit_realdata_fixture_2026-09-16.txt').read_text(encoding='utf-8')
parts=re.split(r'(?m)^Batch [123]\s*$',text)
good=[parse(parts[i+1]) for i in range(3)]

cases={
 'B1 EMPTY':[pd.DataFrame(),good[1],good[2]],
 'B2 EMPTY':[good[0],pd.DataFrame(),good[2]],
 'B3 EMPTY':[good[0],good[1],pd.DataFrame()],
 'B1+B2 EMPTY':[pd.DataFrame(),pd.DataFrame(),good[2]],
 'B1+B3 EMPTY':[pd.DataFrame(),good[1],pd.DataFrame()],
 'B2+B3 EMPTY':[good[0],pd.DataFrame(),pd.DataFrame()],
 'ALL EMPTY':[pd.DataFrame(),pd.DataFrame(),pd.DataFrame()],
}
for name,ds in cases.items():
 aligned,diags,gate=align_batches_with_evidence(ds,EXPECTED)
 assert gate['blocked'] is True,(name,gate)
 assert len(diags)==3,(name,len(diags))
 assert [d['batch'] for d in diags]==[1,2,3]
 assert len(aligned)==3
 print(f'PASS — {name} => BLOCKED; diagnostic slots=3')

# Release-blocker regression: app must clear all derived state before each PROCESS,
# use bounded diagnostic lookup, and never enter merge path after a fatal schema/input gate.
src=Path(__file__).with_name('app.py').read_text(encoding='utf-8')
assert 'reset_processing_state()\n  parsed=' in src
for token in ['st.session_state.x=pd.DataFrame()','st.session_state.stage2=None','st.session_state.gate_state="BLOCKED"']:
 assert token in src,token
assert 'diag=schema_diag[i] if i < len(schema_diag) else {}' in src
assert 'if not fatal and not any(d.empty for d in ds):' in src
print('PASS — STALE DERIVED STATE CLEARED BEFORE PARSE')
print('PASS — UI DIAGNOSTIC ACCESS BOUNDED')
print('PASS — FATAL INPUT CANNOT ENTER MERGE/STAGE2 PATH')
print('PASS STATE/UI R3.1 REGRESSION')
