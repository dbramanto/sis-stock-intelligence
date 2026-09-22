from __future__ import annotations
import sys
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parent
for p in (ROOT/"integration_pipeline", ROOT/"stage3"):
    s=str(p)
    if s not in sys.path: sys.path.insert(0,s)

from stage1.clipboard import parse_clipboard_text
from stage1.pipeline import run_stage1
from stage1.history import load_snapshot, get_snapshot_batch
from stage2.runner import run_stage2
from pipeline_p10_orchestrator import run_pipeline
from stage3_e2e_runner import run_stage3_universe


def _canonical_map(df):
    out={}
    for _,row in df.iterrows():
        d=row.to_dict(); sym=str(d.get("symbol","")).strip().upper()
        if sym: out[sym]=d
    return out


def run_snapshot_stage3(snapshot_id: str, *, analysis_as_of: str, top_n: int=3) -> dict[str,Any]:
    snap=load_snapshot(snapshot_id)
    parsed={}
    for i in range(1,12):
        raw=get_snapshot_batch(snap,i)
        df,issues=parse_clipboard_text(raw)
        if issues: return {"status":"BLOCKED","stage":"INPUT","issues":[f"B{i}:{x}" for x in issues]}
        parsed[i]=df
    expected_total=len(parsed[1])
    s1=run_stage1(parsed,expected_total=expected_total)
    if s1["status"]!="PASS": return {"status":"BLOCKED","stage":"S1","issues":s1.get("issues",[])}
    s2=run_stage2(s1["canonical"])
    if s2.status!="PASS": return {"status":"BLOCKED","stage":"S2","issues":s2.issues}
    cmap=_canonical_map(s1["canonical"])
    p10=run_pipeline(stage2_records=s2.packages,analysis_as_of=analysis_as_of,canonical_by_symbol=cmap)
    if p10.state=="BLOCKED": return {"status":"BLOCKED","stage":"P10","diagnostics":list(p10.diagnostics)}
    s3=run_stage3_universe(list(p10.payloads),analysis_date=analysis_as_of,top_n=top_n)
    return {"status":s3.get("status"),"snapshot_id":snapshot_id,"counts":{"s1":len(s1["canonical"]),"s2":len(s2.packages),"p10":len(p10.payloads)},"p10_state":p10.state,"p10_diagnostics":list(p10.diagnostics),"stage3":s3}
