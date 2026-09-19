from datetime import date
import math
from stage3_common import result, NOT_EVALUATED, missing

DOMAIN="3G_RISK"
NUMERIC=("beta","max_drawdown_pct","sector_volatility_pct","revenue_concentration_pct",
         "debt_equity","interest_coverage","cash_short_debt_coverage","adtv",
         "bid_ask_spread_pct","pe_premium_pct","distance_ma200_pct","atr_pct",
         "negative_event_probability","data_coverage_pct")

def _num(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _fresh(meta,analysis_date):
    raw=meta.get("as_of_date") if isinstance(meta,dict) else None
    if not raw:return "UNKNOWN",None
    try:
        d=date.fromisoformat(str(raw)); a=date.fromisoformat(str(analysis_date)); age=(a-d).days
        if age<0:return "FUTURE_INVALID",age
        return ("FRESH" if age<=14 else "STALE"),age
    except Exception:return "UNKNOWN",None

def _conf(cov,fresh):
    c="HIGH" if cov>=.8 else ("MODERATE" if cov>=.55 else ("LOW" if cov>=.3 else "INSUFFICIENT"))
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT","INSUFFICIENT":"INSUFFICIENT"}[c]
    return c

def _severity(votes):
    if not votes:return NOT_EVALUATED
    score=sum(votes)
    return "HIGH" if score>=2 else ("LOW" if score<=-1 else "MODERATE")

def _semantic_invalid(k,v):
    # Integrity domains only; analytical thresholds remain unchanged.
    if k=="negative_event_probability": return not (0 <= v <= 1)
    if k in {"data_coverage_pct","revenue_concentration_pct"}: return not (0 <= v <= 100)
    if k in {"sector_volatility_pct","bid_ask_spread_pct","atr_pct"}: return v < 0
    if k in {"adtv","debt_equity","cash_short_debt_coverage"}: return v < 0
    return False

def evaluate_risk(s,analysis_date="2026-09-17"):
    e=s.get("risk_enrichment",{})
    if not isinstance(e,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"INVALID_RISK_PAYLOAD","components":{},"contradictions":[]}
    meta=e.get("metadata",{}) if isinstance(e.get("metadata",{}),dict) else {}
    fresh,age=_fresh(meta,analysis_date)
    present={k:e.get(k) for k in NUMERIC if not missing(e.get(k))}
    invalid_type=[k for k,v in present.items() if not _num(v)]
    invalid_domain=[k for k,v in present.items() if _num(v) and _semantic_invalid(k,v)]
    invalid=invalid_type+invalid_domain
    cov=sum(1 for k in NUMERIC if _num(e.get(k)) and not _semantic_invalid(k,e.get(k)))/len(NUMERIC)
    dq={"source":meta.get("source",e.get("source","UNKNOWN")),"as_of_date":meta.get("as_of_date"),
        "freshness":fresh,"age_days":age,"coverage":round(cov,4),"invalid_fields":invalid}
    if invalid:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"INVALID_RISK_FIELD","components":{},"contradictions":[],"data_quality":dq}

    contextual=any(e.get(k) not in (None,"","UNKNOWN") for k in
                   ("sector_context","cyclicality","valuation_context","opportunity_context"))
    if not present and not contextual:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"NO_RISK_EVIDENCE","components":{},"contradictions":[],
                "data_quality":dq,"recommendation":None,"ranking":None}
    g=lambda k:e.get(k) if _num(e.get(k)) else None

    beta,dd=g("beta"),g("max_drawdown_pct"); svol=g("sector_volatility_pct")
    conc=g("revenue_concentration_pct")
    de,ic,covcash=g("debt_equity"),g("interest_coverage"),g("cash_short_debt_coverage")
    adtv,spread=g("adtv"),g("bid_ask_spread_pct"); prem=g("pe_premium_pct")
    dma,atr=g("distance_ma200_pct"),g("atr_pct"); nep=g("negative_event_probability"); dcp=g("data_coverage_pct")

    v=[]
    if beta is not None:v.append(1 if beta>=1.5 else (-1 if beta<=.8 else 0))
    if dd is not None:v.append(1 if abs(dd)>=35 else (-1 if abs(dd)<=15 else 0))
    market=_severity(v)

    v=[]
    if svol is not None:v.append(1 if svol>=30 else (-1 if svol<=15 else 0))
    sector_context=e.get("sector_context","UNKNOWN")
    if sector_context=="HEADWIND":v.append(1)
    elif sector_context=="TAILWIND":v.append(-1)
    sector_risk=_severity(v)

    v=[]
    if conc is not None:v.append(1 if conc>=60 else (-1 if conc<=25 else 0))
    cyclicality=e.get("cyclicality","UNKNOWN")
    if cyclicality=="HIGH":v.append(1)
    elif cyclicality=="LOW":v.append(-1)
    business=_severity(v)

    v=[]
    if de is not None:v.append(1 if de>2 else (-1 if de<=.8 else 0))
    if ic is not None:v.append(1 if ic<2 else (-1 if ic>=5 else 0))
    if covcash is not None:v.append(1 if covcash<1 else (-1 if covcash>=2 else 0))
    financial=_severity(v)

    v=[]
    if adtv is not None:v.append(1 if adtv<1_000_000_000 else (-1 if adtv>=10_000_000_000 else 0))
    if spread is not None:v.append(1 if spread>=1 else (-1 if spread<=.25 else 0))
    liquidity=_severity(v)

    v=[]
    if prem is not None:v.append(1 if prem>=50 else (-1 if prem<=0 else 0))
    valuation_context=e.get("valuation_context","UNKNOWN")
    if valuation_context=="EXPENSIVE":v.append(1)
    elif valuation_context=="CHEAP":v.append(-1)
    valuation=_severity(v)

    v=[]
    if dma is not None:v.append(1 if dma<=-15 else (-1 if dma>=0 else 0))
    if atr is not None:v.append(1 if atr>=6 else (-1 if atr<=3 else 0))
    technical=_severity(v)

    v=[]
    if nep is not None:v.append(1 if nep>=.6 else (-1 if nep<=.2 else 0))
    if dcp is not None:v.append(1 if dcp<60 else (-1 if dcp>=90 else 0))
    if fresh in {"STALE","FUTURE_INVALID","UNKNOWN"}:v.append(1)
    event_data=_severity(v)

    conf=_conf(cov,fresh)
    def comp(state,evidence):
        return result(state,evidence,"INSUFFICIENT" if state==NOT_EVALUATED else conf)
    comps={
      "market_risk":comp(market,[f"beta={beta}",f"max_drawdown_pct={dd}"]),
      "sector_industry_risk":comp(sector_risk,[f"sector_volatility_pct={svol}",f"sector_context={sector_context}"]),
      "business_risk":comp(business,[f"revenue_concentration_pct={conc}",f"cyclicality={cyclicality}"]),
      "financial_cash_risk":comp(financial,[f"debt_equity={de}",f"interest_coverage={ic}",f"cash_short_debt_coverage={covcash}"]),
      "liquidity_execution_risk":comp(liquidity,[f"adtv={adtv}",f"bid_ask_spread_pct={spread}"]),
      "valuation_risk":comp(valuation,[f"pe_premium_pct={prem}",f"valuation_context={valuation_context}"]),
      "technical_risk":comp(technical,[f"distance_ma200_pct={dma}",f"atr_pct={atr}"]),
      "event_data_risk":comp(event_data,[f"negative_event_probability={nep}",f"data_coverage_pct={dcp}",f"freshness={fresh}"])
    }

    states=[x["state"] for x in comps.values() if x["state"]!=NOT_EVALUATED]
    high=states.count("HIGH"); low=states.count("LOW")
    overall="HIGH" if high>=2 else ("LOW" if states and low>=5 and high==0 else ("MODERATE" if states else NOT_EVALUATED))

    contradictions=[]
    opportunity=e.get("opportunity_context","UNKNOWN")
    if opportunity=="HIGH" and overall=="HIGH": contradictions.append("HIGH_OPPORTUNITY_COEXISTS_WITH_HIGH_RISK")
    if valuation_context=="CHEAP" and ((prem is not None and prem>=50) or valuation=="HIGH"):
        contradictions.append("CHEAP_VALUATION_WITH_HIGH_VALUATION_RISK")
    if sector_context=="TAILWIND" and ((svol is not None and svol>=30) or sector_risk=="HIGH"):
        contradictions.append("SECTOR_TAILWIND_WITH_HIGH_SECTOR_RISK")
    if dcp is not None and dcp>=90 and fresh in {"STALE","FUTURE_INVALID"}:
        contradictions.append("HIGH_COVERAGE_BUT_UNRELIABLE_FRESHNESS")
    severity="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")

    return {"domain":DOMAIN,"state":overall,"confidence":conf,"components":comps,
            "contradictions":contradictions,"contradiction_severity":severity,
            "data_quality":dq,"recommendation":None,"ranking":None}
