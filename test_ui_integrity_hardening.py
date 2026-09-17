from pathlib import Path
from copy import deepcopy
import pandas as pd

from sis_stage2 import parse_fixture, integrity_gate, evaluate_symbol
from stage2_adapter import run_stage2, frames_to_stage2

FIXTURE = Path(__file__).with_name("stage2_fixture_v1.txt")
text = FIXTURE.read_text(encoding="utf-8")
base = parse_fixture(text)

def ok(name, cond, detail=""):
    if not cond:
        raise AssertionError(f"{name} FAILED: {detail}")
    print(f"PASS — {name}" + (f" — {detail}" if detail else ""))

# Price tolerance must match Core policy (~0.1%).
b=deepcopy(base)
b[2]["ANTM"]["price"]=b[1]["ANTM"]["price"]*1.0005
ok("PRICE TOLERANCE CONSISTENCY", integrity_gate(b)["state"]=="PASS")

b=deepcopy(base)
b[2]["ANTM"]["price"]=b[1]["ANTM"]["price"]*1.01
ok("REAL PRICE CONFLICT BLOCKS", integrity_gate(b)["state"]=="BLOCKED")

# Missing technical values must not crash and must lower confidence / evaluation state.
for field in ("price_ma20","price_ma50","di_plus14","di_minus14","macd","prev_macd","volume"):
    b=deepcopy(base)
    b[1]["ANTM"][field]=None
    r=evaluate_symbol("ANTM",b)
    ok(f"MISSING {field}", r.get("stage2_state") in {"EVALUATED","NOT_EVALUATED"})

# Adapter must return zero results when integrity is BLOCKED.
def to_frames(batches):
    rev = {}
    from stage2_adapter import MAPS
    for i,m in MAPS.items():
        rev[i]={dst:src for src,dst in m.items()}
    ds=[]
    for i in (1,2,3):
        rows=[]
        for sym,vals in batches[i].items():
            row={"Symbol":sym}
            for k,v in vals.items():
                if k in rev[i]: row[rev[i][k]]=v
            rows.append(row)
        ds.append(pd.DataFrame(rows))
    return ds

b=deepcopy(base)
b[2]["ANTM"]["price"]=b[1]["ANTM"]["price"]*1.01
r=run_stage2(to_frames(b))
ok("BLOCKED ADAPTER ZERO RESULTS", r["integrity"]["state"]=="BLOCKED" and r["results"]==[])

# Partial universe remains REVIEW and partial symbol is not evaluated.
b=deepcopy(base)
b[3].pop("ITMG")
r=run_stage2(to_frames(b))
itmg=next(x for x in r["results"] if x["symbol"]=="ITMG")
ok("PARTIAL UNIVERSE REVIEW", r["integrity"]["state"]=="REVIEW" and itmg["stage2_state"]=="NOT_EVALUATED")

print()
print("PASS UI/INTEGRITY HARDENING REGRESSION")
