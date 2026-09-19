from stage3a_technical import evaluate_technical
from stage3b_fundamental import evaluate_fundamental
from stage3c_cash import evaluate_cash
from stage3d_valuation import evaluate_valuation
from stage3e_sector import evaluate_sector
from stage3f_catalyst import evaluate_catalyst
from stage3g_risk import evaluate_risk

NOT_EVALUATED="NOT_EVALUATED"
ENGINES={
 "technical":evaluate_technical, "business":evaluate_fundamental, "cash_flow":evaluate_cash,
 "valuation":evaluate_valuation, "sector":evaluate_sector, "catalyst":evaluate_catalyst, "risk":evaluate_risk
}

def _safe(name, fn, stock, analysis_date):
    try:
        r=fn(stock,analysis_date)
        if not isinstance(r,dict): raise TypeError("engine returned non-dict")
        return r
    except Exception as exc:
        return {"domain":name.upper(),"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"ENGINE_FAILURE","error_type":type(exc).__name__,"components":{},
                "contradictions":[],"data_quality":{"freshness":"UNKNOWN","coverage":0},
                "recommendation":None,"ranking":None}

def _cross(dom):
    c=[]
    st={k:v.get("state",NOT_EVALUATED) for k,v in dom.items()}
    if st["business"] in {"STRONG","HEALTHY"} and st["cash_flow"] in {"WEAK","STRESSED"}:
        c.append("STRONG_BUSINESS_WEAK_CASH")
    if st["business"] in {"STRONG","HEALTHY"} and st["valuation"] in {"EXPENSIVE","EXTREME"}:
        c.append("STRONG_BUSINESS_EXPENSIVE_VALUATION")
    if st["technical"] in {"STRONG","BULLISH","BULL"} and st["catalyst"] in {"NEGATIVE","STRONGLY_NEGATIVE"}:
        c.append("STRONG_TECHNICAL_NEGATIVE_CATALYST")
    if st["sector"]=="HEADWIND" and st["technical"] in {"STRONG","BULLISH","BULL"}:
        c.append("STRONG_TECHNICAL_SECTOR_HEADWIND")
    if st["risk"] in {"HIGH","CRITICAL"}:
        favorable=any(st[k] in {"STRONG","BULLISH","CHEAP","TAILWIND","POSITIVE","STRONGLY_POSITIVE"} for k in dom if k!="risk")
        if favorable:c.append("FAVORABLE_EVIDENCE_COEXISTS_WITH_HIGH_RISK")
    return c

def build_dossier(stock,analysis_date="2026-09-17"):
    if not isinstance(stock,dict):
        return {"stage3_status":"BLOCKED","reason":"INVALID_STOCK_PAYLOAD","domains":{}}
    stage2=stock.get("stage2",{}) if isinstance(stock.get("stage2",{}),dict) else {}
    eligibility=stage2.get("eligibility",stage2.get("status","UNKNOWN"))
    upstream=stock.get("upstream_gate",stage2.get("upstream_gate","PASS"))
    if upstream=="BLOCKED":
        return {"symbol":stock.get("symbol"),"stage3_status":"BLOCKED","reason":"UPSTREAM_BLOCKED",
                "stage2_eligibility":eligibility,"domains":{},"recommendation":None,"ranking":None}
    dom={name:_safe(name,fn,stock,analysis_date) for name,fn in ENGINES.items()}
    freshness={k:v.get("data_quality",{}).get("freshness","UNKNOWN") for k,v in dom.items()}
    evaluated=[k for k,v in dom.items() if v.get("state")!=NOT_EVALUATED]
    failures=[k for k,v in dom.items() if v.get("reason")=="ENGINE_FAILURE"]
    stale=[k for k,x in freshness.items() if x in {"STALE","FUTURE_INVALID"}]
    confidence={k:v.get("confidence","UNKNOWN") for k,v in dom.items()}
    review_protected=eligibility=="REVIEW"
    status="REVIEW_PROTECTED" if review_protected else ("PARTIAL" if failures or len(evaluated)<len(dom) else "COMPLETE")
    return {
      "symbol":stock.get("symbol"),"stage3_status":status,"stage2_eligibility":eligibility,
      "review_protected":review_protected,"domains":dom,
      "cross_engine_contradictions":_cross(dom),
      "data_quality":{"evaluated_domains":evaluated,"failed_domains":failures,
                      "stale_or_future_domains":stale,"freshness_by_domain":freshness},
      "confidence_by_domain":confidence,
      "recommendation":None,"ranking":None,"horizon_score":None
    }
