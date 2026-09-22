
import sys, copy, math
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline_p9_payload import MetricEvidence, build_stage3_payload
from pipeline_p10_orchestrator import run_pipeline

def s2(sym="ANTM",elig="ELIGIBLE"):
    return {"symbol":sym,"eligibility":elig,"technical":{"score":80},"source_features":{"rsi_delta":1}}

def bars(n=60):
    from datetime import date,timedelta
    d=date(2026,7,1)
    return [{"date":str(d+timedelta(days=i)),"open":100+i*.1,"high":102+i*.1,
             "low":99+i*.1,"close":101+i*.1,"volume":100000+i} for i in range(n)]

def run():
    checks=[]
    # 1 normal complete shape
    p=build_stage3_payload("ANTM",s2(),[MetricEvidence("npm",12,"VALID","IDX","2026-06-30")],
                           ohlcv=bars(),analysis_as_of="2026-09-18")
    checks.append(("S3P01",p["symbol"]=="ANTM" and p["fundamental_enrichment"]["npm"]==12))
    # 2 conditional preserved
    checks.append(("S3P02",build_stage3_payload("A",s2("A","CONDITIONAL"),[],analysis_as_of="2026-09-18")["stage2"]["eligibility"]=="CONDITIONAL"))
    # 3 review preserved
    checks.append(("S3P03",build_stage3_payload("A",s2("A","REVIEW"),[],analysis_as_of="2026-09-18")["stage2"]["eligibility"]=="REVIEW"))
    # 4 missing never zero
    q=build_stage3_payload("A",s2("A"),[],analysis_as_of="2026-09-18")
    checks.append(("S3P04","npm" not in q["fundamental_enrichment"]))
    # 5 explicit zero preserved
    q=build_stage3_payload("A",s2("A"),[MetricEvidence("npm",0,"VALID","IDX","2026-06-30")],analysis_as_of="2026-09-18")
    checks.append(("S3P05",q["fundamental_enrichment"]["npm"]==0))
    # 6 stale can pass but retains conservative date
    q=build_stage3_payload("A",s2("A"),[MetricEvidence("npm",1,"STALE","IDX","2026-01-01")],analysis_as_of="2026-09-18")
    checks.append(("S3P06",q["fundamental_enrichment"]["metadata"]["as_of_date"]=="2026-01-01"))
    # 7 mixed dates oldest controls freshness
    q=build_stage3_payload("A",s2("A"),[MetricEvidence("npm",1,"VALID","IDX","2026-01-01"),MetricEvidence("roic",2,"VALID","IDX","2026-06-30")],analysis_as_of="2026-09-18")
    checks.append(("S3P07",q["fundamental_enrichment"]["metadata"]["as_of_date"]=="2026-01-01"))
    # 8 conflict never flattened
    q=build_stage3_payload("A",s2("A"),[MetricEvidence("npm",99,"CONFLICT","IDX","2026-06-30")],analysis_as_of="2026-09-18")
    checks.append(("S3P08","npm" not in q["fundamental_enrichment"]))
    # 9 partial never flattened
    q=build_stage3_payload("A",s2("A"),[MetricEvidence("npm",99,"PARTIAL","IDX","2026-06-30")],analysis_as_of="2026-09-18")
    checks.append(("S3P09","npm" not in q["fundamental_enrichment"]))
    # 10 nonfinite omitted
    q=build_stage3_payload("A",s2("A"),[MetricEvidence("npm",float("nan"),"VALID","IDX","2026-06-30")],analysis_as_of="2026-09-18")
    checks.append(("S3P10","npm" not in q["fundamental_enrichment"]))
    # 11 stage2 deep-copy
    original=s2("A","REVIEW"); q=build_stage3_payload("A",original,[],analysis_as_of="2026-09-18")
    q["stage2"]["source_features"]["rsi_delta"]=999
    checks.append(("S3P11",original["source_features"]["rsi_delta"]==1))
    # 12 future OHLCV metadata blocked
    meta=MetricEvidence("OHLCV_META",{"source":"X","as_of_date":"2026-10-01"},"VALID","X","2026-10-01")
    q=build_stage3_payload("A",s2("A"),[meta],ohlcv=bars(),analysis_as_of="2026-09-18")
    checks.append(("S3P12",q["technical_enrichment"]["metadata"]["as_of_date"] is None))
    # 13 valid upcoming event
    ev={"type":"DIVIDEND","direction":"POSITIVE","materiality":"MODERATE","status":"UPCOMING",
        "probability":0.8,"priced_in":"UNKNOWN","event_date":"2026-10-01","published_at":"2026-09-15"}
    q=build_stage3_payload("A",s2("A"),[],catalyst_events=[ev],analysis_as_of="2026-09-18")
    checks.append(("S3P13",len(q["catalyst_enrichment"]["events"])==1 and q["catalyst_enrichment"]["metadata"]["as_of_date"]=="2026-09-15"))
    # 14 future-published event blocked
    bad=dict(ev); bad["published_at"]="2026-09-20"
    q=build_stage3_payload("A",s2("A"),[],catalyst_events=[bad],analysis_as_of="2026-09-18")
    checks.append(("S3P14",q["catalyst_enrichment"]["events"]==[]))
    # 15 completed future event blocked
    bad=dict(ev); bad.update(status="COMPLETED",event_date="2026-10-01")
    q=build_stage3_payload("A",s2("A"),[],catalyst_events=[bad],analysis_as_of="2026-09-18")
    checks.append(("S3P15",q["catalyst_enrichment"]["events"]==[]))
    # 16 provider/enrichment absence preserves requested symbols
    r=run_pipeline(stage2_records=[s2("A"),s2("B","REVIEW")],analysis_as_of="2026-09-18")
    checks.append(("S3P16",r.scope_symbols==("A","B") and len(r.payloads)==2))
    # 17 no decision leak
    checks.append(("S3P17",all(k not in q for k in ("decision","buy","sell","ranking","recommendation"))))
    # 18 deterministic
    a=run_pipeline(stage2_records=[s2("A")],analysis_as_of="2026-09-18")
    b=run_pipeline(stage2_records=[s2("A")],analysis_as_of="2026-09-18")
    checks.append(("S3P18",a==b))
    failed=[x for x in checks if not x[1]]
    for k,ok in checks: print(("PASS " if ok else "FAIL ")+k)
    assert not failed,failed
    print("PASS 18/18 INTEGRATION PIPELINE FINAL ACCEPTANCE")
if __name__=="__main__": run()
