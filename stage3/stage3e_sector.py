from datetime import date
import math
from stage3_common import result, NOT_EVALUATED, missing

DOMAIN="3E_SECTOR_INDUSTRY"
NUMERIC=("sector_return_1m","sector_return_3m","industry_return_1m","industry_return_3m",
         "stock_return_1m","stock_return_3m","sector_breadth_pct","industry_breadth_pct",
         "commodity_change_3m","macro_sensitivity")

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
    c="HIGH" if cov>=.80 else ("MODERATE" if cov>=.55 else ("LOW" if cov>=.30 else "INSUFFICIENT"))
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT","INSUFFICIENT":"INSUFFICIENT"}[c]
    return c

def _component_conf(state, domain_conf):
    return "INSUFFICIENT" if state==NOT_EVALUATED else domain_conf

def _momentum(r1,r3):
    if r1 is None and r3 is None:return NOT_EVALUATED
    vals=[x for x in (r1,r3) if x is not None]
    if all(x>0 for x in vals):return "POSITIVE"
    if all(x<0 for x in vals):return "NEGATIVE"
    return "MIXED"

def evaluate_sector(s,analysis_date="2026-09-17"):
    e=s.get("sector_enrichment",{})
    if not isinstance(e,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"INVALID_SECTOR_PAYLOAD","components":{},"contradictions":[]}

    meta=e.get("metadata",{}) if isinstance(e.get("metadata",{}),dict) else {}
    fresh,age=_fresh(meta,analysis_date)
    present={k:e.get(k) for k in NUMERIC if not missing(e.get(k))}
    invalid=[k for k,v in present.items() if not _num(v)]
    # Breadth is percentage evidence; finite values outside 0..100 are semantically invalid.
    invalid_domain=[k for k in ("sector_breadth_pct","industry_breadth_pct")
                    if _num(e.get(k)) and not (0 <= e.get(k) <= 100)]
    invalid_all=list(dict.fromkeys(invalid+invalid_domain))
    cov=sum(1 for k in NUMERIC if _num(e.get(k)))/len(NUMERIC)
    sector=e.get("sector"); industry=e.get("industry")
    classification_ok=isinstance(sector,str) and bool(sector.strip()) and isinstance(industry,str) and bool(industry.strip())
    dq={"source":meta.get("source",e.get("source","UNKNOWN")),"as_of_date":meta.get("as_of_date"),
        "freshness":fresh,"age_days":age,"coverage":round(cov,4),
        "classification_complete":classification_ok,"invalid_fields":invalid_all}
    if invalid_all:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"INVALID_SECTOR_FIELD","components":{},"contradictions":[],"data_quality":dq}

    g=lambda k:e.get(k) if _num(e.get(k)) else None
    sr1,sr3=g("sector_return_1m"),g("sector_return_3m")
    ir1,ir3=g("industry_return_1m"),g("industry_return_3m")
    rr1,rr3=g("stock_return_1m"),g("stock_return_3m")
    sb,ib=g("sector_breadth_pct"),g("industry_breadth_pct")
    cc,ms=g("commodity_change_3m"),g("macro_sensitivity")

    classification="DOCUMENTED" if classification_ok else NOT_EVALUATED
    sm=_momentum(sr1,sr3)
    if sm==NOT_EVALUATED and sb is None: sector_state=NOT_EVALUATED
    elif sm=="POSITIVE" and (sb is None or sb>=55): sector_state="HEALTHY"
    elif sm=="NEGATIVE" and (sb is None or sb<=45): sector_state="DETERIORATING"
    else: sector_state="MIXED"

    im=_momentum(ir1,ir3)
    if im==NOT_EVALUATED and ib is None: industry_state=NOT_EVALUATED
    elif im=="POSITIVE" and (ib is None or ib>=55): industry_state="HEALTHY"
    elif im=="NEGATIVE" and (ib is None or ib<=45): industry_state="DETERIORATING"
    else: industry_state="MIXED"

    spreads=[]
    if rr1 is not None and ir1 is not None: spreads.append(rr1-ir1)
    if rr3 is not None and ir3 is not None: spreads.append(rr3-ir3)
    if not spreads: leadership=NOT_EVALUATED
    elif all(x>=3 for x in spreads): leadership="LEADER"
    elif all(x<=-3 for x in spreads): leadership="LAGGARD"
    else: leadership="NEUTRAL"

    deltas=[]
    if sr1 is not None and sr3 is not None:deltas.append(sr1-sr3/3)
    if ir1 is not None and ir3 is not None:deltas.append(ir1-ir3/3)
    if not deltas: context_momentum=NOT_EVALUATED
    elif all(x>1 for x in deltas):context_momentum="ACCELERATING"
    elif all(x<-1 for x in deltas):context_momentum="DECELERATING"
    else:context_momentum="STABLE_OR_MIXED"

    commodity=e.get("commodity_exposure",{})
    if isinstance(commodity,dict) and commodity:
        direction=commodity.get("benefit_from_rising","UNKNOWN")
        if cc is None or direction=="UNKNOWN": commodity_state="DOCUMENTED_UNRESOLVED"
        elif direction is True: commodity_state="TAILWIND" if cc>0 else ("HEADWIND" if cc<0 else "NEUTRAL")
        elif direction is False: commodity_state="HEADWIND" if cc>0 else ("TAILWIND" if cc<0 else "NEUTRAL")
        else: commodity_state="DOCUMENTED_UNRESOLVED"
    else: commodity_state=NOT_EVALUATED

    macro=e.get("macro_exposure",{})
    if isinstance(macro,dict) and macro:
        macro_state="HIGH_SENSITIVITY" if ms is not None and abs(ms)>=.7 else ("MODERATE_SENSITIVITY" if ms is not None and abs(ms)>=.3 else ("LOW_SENSITIVITY" if ms is not None else "DOCUMENTED_UNRESOLVED"))
    else: macro_state=NOT_EVALUATED

    votes=[]
    for x in (sector_state,industry_state):
        if x=="HEALTHY":votes.append(1)
        elif x=="DETERIORATING":votes.append(-1)
    if commodity_state=="TAILWIND":votes.append(1)
    elif commodity_state=="HEADWIND":votes.append(-1)
    if not votes: context=NOT_EVALUATED
    elif sum(votes)>=2:context="TAILWIND"
    elif sum(votes)<=-2:context="HEADWIND"
    else:context="MIXED"

    conf=_conf(cov,fresh)
    comps={
      "classification":result(classification,[f"sector={sector}",f"industry={industry}"],"HIGH" if classification_ok else "INSUFFICIENT"),
      "sector_state":result(sector_state,[f"sector_return_1m={sr1}",f"sector_return_3m={sr3}",f"sector_breadth_pct={sb}"],_component_conf(sector_state,conf)),
      "industry_state":result(industry_state,[f"industry_return_1m={ir1}",f"industry_return_3m={ir3}",f"industry_breadth_pct={ib}"],_component_conf(industry_state,conf)),
      "relative_leadership":result(leadership,[f"stock_return_1m={rr1}",f"stock_return_3m={rr3}",f"relative_spreads={spreads}"],_component_conf(leadership,conf)),
      "context_momentum":result(context_momentum,[f"sector_momentum={sm}",f"industry_momentum={im}",f"deltas={deltas}"],_component_conf(context_momentum,conf)),
      "commodity_exposure":result(commodity_state,[f"commodity_change_3m={cc}",f"exposure={commodity}"],_component_conf(commodity_state,conf)),
      "macro_exposure":result(macro_state,[f"macro_sensitivity={ms}",f"exposure={macro}"],_component_conf(macro_state,conf)),
      "tailwind_headwind":result(context,[f"sector_state={sector_state}",f"industry_state={industry_state}",f"commodity_state={commodity_state}"],_component_conf(context,conf))
    }

    contradictions=[]
    if sector_state=="HEALTHY" and industry_state=="DETERIORATING": contradictions.append("HEALTHY_SECTOR_BUT_DETERIORATING_INDUSTRY")
    if sector_state=="DETERIORATING" and industry_state=="HEALTHY": contradictions.append("DETERIORATING_SECTOR_BUT_HEALTHY_INDUSTRY")
    if leadership=="LEADER" and context=="HEADWIND": contradictions.append("STOCK_LEADER_DESPITE_CONTEXT_HEADWIND")
    if leadership=="LAGGARD" and context=="TAILWIND": contradictions.append("STOCK_LAGGARD_DESPITE_CONTEXT_TAILWIND")
    severity="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")

    overall=context if context!=NOT_EVALUATED else ("MIXED" if any(x!=NOT_EVALUATED for x in (sector_state,industry_state,leadership)) else NOT_EVALUATED)
    return {"domain":DOMAIN,"state":overall,"confidence":conf,"components":comps,
            "contradictions":contradictions,"contradiction_severity":severity,
            "data_quality":dq,"recommendation":None,"ranking":None}
