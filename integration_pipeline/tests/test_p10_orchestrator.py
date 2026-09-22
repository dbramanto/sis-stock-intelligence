
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from pipeline_contracts import *
from pipeline_p10_orchestrator import *

def raw(sym,mid,val,unit,ptype=PeriodType.TTM,end="2026-06-30",pub="2026-07-30",eid=None):
    return Evidence(eid or f"RAW:{sym}:{mid}",sym,mid,val,val,unit,"IDR" if unit=="currency" else None,
        EvidenceOrigin.ENRICH_RAW,PeriodRef(ptype,period_end=end,published_at=pub),
        Provenance("IDX","OFFICIAL","idx://fixture","2026-09-18T10:00:00+07:00"),
        QualityState.VALID,FreshnessState.FRESH)

def run():
    s2=[
      {"symbol":"ANTM","eligibility":"ELIGIBLE","technical":{"score":80},"fundamental":{"score":70}},
      {"symbol":"SLIS","eligibility":"REVIEW","technical":{"score":95},"fundamental":{"score":16}},
    ]
    raws=[
      raw("ANTM","gross_profit_ttm",200.0,"currency"),
      raw("ANTM","revenue_ttm",1000.0,"currency"),
      raw("ANTM","cash_balance",300.0,"currency",PeriodType.QUARTER),
      raw("ANTM","short_term_debt",100.0,"currency",PeriodType.QUARTER),
      raw("SLIS","gross_profit_ttm",50.0,"currency"),
      raw("SLIS","revenue_ttm",500.0,"currency"),
    ]
    deriv=[
      DerivationRequest("ANTM","gross_margin_ttm",("gross_profit_ttm","revenue_ttm")),
      DerivationRequest("SLIS","gross_margin_ttm",("gross_profit_ttm","revenue_ttm")),
      DerivationRequest("ANTM","cash_short_debt_coverage",("cash_balance","short_term_debt")),
    ]
    r=run_pipeline(stage2_records=s2,analysis_as_of="2026-09-18",raw_evidence=raws,derivations=deriv)
    c=[]
    c += [r.scope_symbols==("ANTM","SLIS"),len(r.payloads)==2]
    by={p["symbol"]:p for p in r.payloads}
    c += [by["ANTM"]["stage2"]["eligibility"]=="ELIGIBLE",
          by["SLIS"]["stage2"]["eligibility"]=="REVIEW"]
    c += [abs(by["ANTM"]["fundamental_enrichment"]["gross_margin"]-20.0)<1e-12,
          abs(by["SLIS"]["fundamental_enrichment"]["gross_margin"]-10.0)<1e-12,
          "gross_margin_ttm" not in by["ANTM"]["fundamental_enrichment"]]
    c += [abs(by["ANTM"]["risk_enrichment"]["cash_short_debt_coverage"]-3.0)<1e-12]
    # REVIEW remains in deep-analysis scope and is not upgraded.
    c += [by["SLIS"]["stage2"]["eligibility"]=="REVIEW"]
    # provider/enrichment absence does not delete a symbol.
    r2=run_pipeline(stage2_records=s2,analysis_as_of="2026-09-18",raw_evidence=[])
    c += [len(r2.payloads)==2,r2.scope_symbols==("ANTM","SLIS")]
    # future-published evidence is rejected and never reaches payload.
    fut=raw("ANTM","revenue_ttm",1000.0,"currency",pub="2026-10-01",eid="FUT")
    r3=run_pipeline(stage2_records=s2,analysis_as_of="2026-09-18",raw_evidence=[fut])
    a={p["symbol"]:p for p in r3.payloads}["ANTM"]
    c += ["revenue_ttm" not in a["cash_enrichment"],"FUT" in r3.rejected_evidence_ids]
    # out-of-scope raw evidence rejected by P3; universe preserved.
    outsider=raw("BBCA","revenue_ttm",1.0,"currency",eid="OUT")
    r4=run_pipeline(stage2_records=s2,analysis_as_of="2026-09-18",raw_evidence=[outsider])
    c += [r4.scope_symbols==("ANTM","SLIS"),len(r4.payloads)==2,
          any("OUT_OF_SCOPE_EVIDENCE" in x for x in r4.diagnostics)]
    # duplicate Stage2 does not silently create duplicate scope.
    r5=run_pipeline(stage2_records=[s2[0],s2[0]],analysis_as_of="2026-09-18")
    c += [r5.scope_symbols==("ANTM",),any("DUPLICATE_STAGE2_SYMBOL" in x for x in r5.diagnostics)]
    # no decision leak at orchestrator level
    c += [all(all(k not in p for k in ("recommendation","ranking","decision","buy","sell")) for p in r.payloads)]
    assert all(c),[i for i,x in enumerate(c,1) if not x]
    print(f"PASS {len(c)}/{len(c)} P10 end-to-end/adversarial checks")
if __name__=="__main__": run()
