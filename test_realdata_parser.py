from pathlib import Path
import re
from sis_core import parse,norm,align_batches_with_evidence,conflict_details,systematic_conflict_diagnosis
from app_schema import EXPECTED

text=Path(__file__).with_name("stockbit_realdata_fixture_2026-09-16.txt").read_text(encoding="utf-8")
parts=re.split(r"(?m)^Batch [123]\s*$",text)
assert len(parts)>=4
parsed=[parse(parts[i+1]) for i in range(3)]
aligned,diags,alignment_gate=align_batches_with_evidence(parsed,EXPECTED)
assert alignment_gate["blocked"] is False
batches=[norm(a) for a in aligned]

assert [len(d) for d in batches]==[24,24,24]
assert diags[0]["realigned"] is True
assert diags[1]["realigned"] is False
assert diags[2]["realigned"] is False

# Ground-truth spot checks from the user's real Stockbit paste.
for d in batches:
    slis=d[d.Symbol=="SLIS"].iloc[0]
    assert slis["Price"]==93
    assert slis["Volume"]==684854000
    assert slis["Volume MA 20"]==92666835

for d in batches:
    antm=d[d.Symbol=="ANTM"].iloc[0]
    assert antm["Price"]==3220
    assert antm["Volume"]==142697700
    assert antm["Price MA 20"]==3154

detail=conflict_details(batches)
assert detail.empty, detail.head(20).to_string()
diag=systematic_conflict_diagnosis(detail,24)
assert diag["state"]=="PASS"

print("PASS REAL STOCKBIT FIXTURE — 24/24/24")
print("PASS BATCH 1 HEADER-ORDER REALIGNMENT")
print("PASS COMMON-FIELD CONSISTENCY — 0 false conflicts")
print("PASS REAL-DATA PARSER REGRESSION")
