
import sys, copy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
S3=ROOT.parent/"stage3"
if not S3.exists():
    raise SystemExit("BLOCKED: packaged stage3 not found")
sys.path.insert(0,str(ROOT)); sys.path.insert(0,str(S3))
from pipeline_p9_payload import MetricEvidence, build_stage3_payload
from stage3_dossier import ENGINES

def bars():
    from datetime import date,timedelta
    d=date(2026,7,1); out=[]
    for i in range(70):
        c=100+i*.2
        out.append({"date":str(d+timedelta(days=i)),"open":c,"high":c+2,"low":c-1,"close":c+1,"volume":100000+i*100})
    return out

stage2={"symbol":"ANTM","eligibility":"REVIEW","source_features":{"rsi_delta":1,"macd_delta":1,"rs_trajectory":"MIXED"}}
ev=[
 MetricEvidence("npm",12,"VALID","IDX","2026-06-30"),
 MetricEvidence("roic",15,"VALID","IDX","2026-06-30"),
 MetricEvidence("ocf_ttm",100,"VALID","IDX","2026-06-30"),
 MetricEvidence("fcf_ttm",70,"VALID","IDX","2026-06-30"),
 MetricEvidence("net_income_ttm",80,"VALID","IDX","2026-06-30"),
 MetricEvidence("pe",12,"VALID","IDX","2026-09-17"),
 MetricEvidence("pb",1.5,"VALID","IDX","2026-09-17"),
 MetricEvidence("beta",1.1,"VALID","MKT","2026-09-17"),
 MetricEvidence("atr_pct",3.0,"VALID","MKT","2026-09-17"),
]
payload=build_stage3_payload("ANTM",stage2,ev,ohlcv=bars(),analysis_as_of="2026-09-18")
assert payload["stage2"]["eligibility"]=="REVIEW"
for name,fn in ENGINES.items():
    r=fn(copy.deepcopy(payload),"2026-09-18")
    assert isinstance(r,dict),name
    assert r.get("recommendation") is None,name
    assert r.get("ranking") is None,name
    print("PASS",name,r.get("state"))
print("PASS STAGE3 FINAL FREEZE COMPATIBILITY — 7/7 ENGINES")
