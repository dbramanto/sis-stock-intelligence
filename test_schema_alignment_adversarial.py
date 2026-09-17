from pathlib import Path
import re
from sis_core import parse,norm,align_batches_with_evidence,conflict_details
from app_schema import EXPECTED

text=Path(__file__).with_name("stockbit_realdata_fixture_2026-09-16.txt").read_text(encoding="utf-8")
parts=re.split(r"(?m)^Batch [123]\s*$",text)
parsed=[parse(parts[i+1]) for i in range(3)]

def ck(name,cond,detail=""):
 assert cond, f"{name} FAILED: {detail}"
 print(f"PASS — {name}" + (f" — {detail}" if detail else ""))

# A. Known Stockbit anomaly: B1 displayed headers are permuted, values are canonical by position.
aligned,diag,gate=align_batches_with_evidence(parsed,EXPECTED)
nd=[norm(d) for d in aligned]
ck("REAL FIXTURE EVIDENCE ALIGNMENT",not gate["blocked"] and diag[0]["realigned"] and conflict_details(nd).empty,
   f"baseline_conflicts={gate.get('baseline_conflicts')}; best={gate.get('best_conflicts')}")

# B. True reordered export: values actually follow the reordered headers. Must NOT positional-rename.
# Build from canonical-correct B1, then physically reorder columns+values to the raw displayed B1 order.
canonical=aligned[0].copy()
raw_order=list(parsed[0].columns)
true_reordered=canonical[raw_order].copy()
case=[true_reordered,parsed[1].copy(),parsed[2].copy()]
a2,d2,g2=align_batches_with_evidence(case,EXPECTED)
n2=[norm(d) for d in a2]
ck("TRUE REORDER PRESERVES HEADER/VALUE PAIRING",not g2["blocked"] and not d2[0]["realigned"] and conflict_details(n2).empty)
slis=n2[0][n2[0].Symbol=="SLIS"].iloc[0]
ck("TRUE REORDER VALUE INTEGRITY",slis["Price"]==93 and slis["Volume"]==684854000 and slis["Price MA 20"]==91)

# C. Deliberately ambiguous: only one permuted batch and no cross-batch comparable evidence.
# Remove all common metric values from B2/B3 while preserving schemas. Engine must not guess positional.
amb=[parsed[0].copy(),parsed[1].copy(),parsed[2].copy()]
common=["Volume","Volume MA 20","Price MA 20","Price MA 50","RSI (14)","ADTV 30","Price"]
for j in (1,2):
 for c in common:
  if c in amb[j]: amb[j][c]="-"
a3,d3,g3=align_batches_with_evidence(amb,EXPECTED)
ck("AMBIGUOUS ALIGNMENT FAILS CLOSED",g3["blocked"] and g3["state"] in {"AMBIGUOUS_SCHEMA_ALIGNMENT","LOW_CONFIDENCE_ALIGNMENT"},g3["state"])

# D. Unknown/missing schema column must block, never guess.
bad=[x.copy() for x in parsed]
bad[0]=bad[0].rename(columns={bad[0].columns[-1]:"Unexpected Metric"})
a4,d4,g4=align_batches_with_evidence(bad,EXPECTED)
ck("SCHEMA MISMATCH FAILS CLOSED",g4["blocked"] and g4["state"]=="SCHEMA_MISMATCH")

print("PASS SCHEMA ALIGNMENT ADVERSARIAL — 5/5 checks")
