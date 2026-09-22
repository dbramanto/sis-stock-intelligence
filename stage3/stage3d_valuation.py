from datetime import date
import math
from stage3_common import result, NOT_EVALUATED, missing

DOMAIN="3D_VALUATION"
FIELDS=("pe","pb","ev_ebitda","earnings_yield","fcf_yield",
        "pe_5y_median","pb_5y_median","ev_ebitda_5y_median",
        "sector_pe","sector_pb","sector_ev_ebitda",
        "eps_growth","revenue_growth")

def _num(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _fresh(meta,analysis_date):
    raw=meta.get("as_of_date") if isinstance(meta,dict) else None
    if not raw:return "UNKNOWN",None
    try:
        d=date.fromisoformat(str(raw)); a=date.fromisoformat(str(analysis_date)); age=(a-d).days
        if age<0:return "FUTURE_INVALID",age
        return ("FRESH" if age<=120 else "STALE"),age
    except Exception:return "UNKNOWN",None

def _ratio(a,b):
    return None if not (_num(a) and _num(b)) or b<=0 else a/b

def _positive_ratio(a,b):
    # Valuation multiple comparisons are meaningful only when both
    # current and reference multiples are strictly positive.
    return None if not (_num(a) and _num(b)) or a<=0 or b<=0 else a/b

def _conf(cov,fresh):
    c="HIGH" if cov>=.8 else ("MODERATE" if cov>=.55 else ("LOW" if cov>=.3 else "INSUFFICIENT"))
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT","INSUFFICIENT":"INSUFFICIENT"}[c]
    return c

def _component_conf(state, domain_conf):
    # A component with no usable evidence cannot carry positive analytical confidence.
    return "INSUFFICIENT" if state==NOT_EVALUATED else domain_conf

def _relative_state(r):
    if r is None:return NOT_EVALUATED
    if r<=.75:return "CHEAP"
    if r>=1.30:return "EXPENSIVE"
    return "FAIR"

def evaluate_valuation(s,analysis_date="2026-09-17"):
    e=s.get("valuation_enrichment",{})
    if not isinstance(e,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"INVALID_VALUATION_PAYLOAD","components":{},"contradictions":[]}

    meta=e.get("metadata",{}) if isinstance(e.get("metadata",{}),dict) else {}
    fresh,age=_fresh(meta,analysis_date)
    present={k:e.get(k) for k in FIELDS if not missing(e.get(k))}
    invalid=[k for k,v in present.items() if not _num(v)]
    cov=sum(1 for k in FIELDS if _num(e.get(k)))/len(FIELDS)
    source=meta.get("source",e.get("source","UNKNOWN")); internal_mode="S1_CANONICAL_INTERNAL" in str(source)
    confidence_fields=("pe","pb","ev_ebitda","earnings_yield","fcf_yield","pe_5y_median","pb_5y_median","eps_growth","revenue_growth") if internal_mode else FIELDS
    conf_cov=sum(1 for k in confidence_fields if _num(e.get(k)))/len(confidence_fields)
    dq={"source":source,"as_of_date":meta.get("as_of_date"),"freshness":fresh,"age_days":age,
        "coverage":round(cov,4),"confidence_coverage":round(conf_cov,4),
        "confidence_method":"INTERNAL_CORE" if internal_mode else "FULL_ENRICHMENT","invalid_fields":invalid}
    if invalid:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"NONNUMERIC_VALUATION_FIELD","components":{},"contradictions":[],
                "data_quality":dq}

    g=lambda k:e.get(k) if _num(e.get(k)) else None
    pe,pb,ev=g("pe"),g("pb"),g("ev_ebitda")
    ey,fy=g("earnings_yield"),g("fcf_yield")
    peh,pbh,evh=g("pe_5y_median"),g("pb_5y_median"),g("ev_ebitda_5y_median")
    pes,pbs,evs=g("sector_pe"),g("sector_pb"),g("sector_ev_ebitda")
    eg,rg=g("eps_growth"),g("revenue_growth")

    abs_votes=[]
    if pe is not None and pe>0: abs_votes.append("CHEAP" if pe<=10 else ("EXPENSIVE" if pe>=30 else "FAIR"))
    if pb is not None and pb>0: abs_votes.append("CHEAP" if pb<=1 else ("EXPENSIVE" if pb>=4 else "FAIR"))
    if ev is not None and ev>0: abs_votes.append("CHEAP" if ev<=7 else ("EXPENSIVE" if ev>=18 else "FAIR"))
    if not abs_votes:absolute=NOT_EVALUATED
    elif abs_votes.count("CHEAP")>=2:absolute="CHEAP"
    elif abs_votes.count("EXPENSIVE")>=2:absolute="EXPENSIVE"
    else:absolute="FAIR_OR_MIXED"

    hist_ratios=(_positive_ratio(pe,peh),_positive_ratio(pb,pbh),_positive_ratio(ev,evh))
    hist=[_relative_state(x) for x in hist_ratios]
    hv=[x for x in hist if x!=NOT_EVALUATED]
    historical=NOT_EVALUATED if not hv else ("CHEAP" if hv.count("CHEAP")>=2 else ("EXPENSIVE" if hv.count("EXPENSIVE")>=2 else "FAIR_OR_MIXED"))

    sec_ratios=(_positive_ratio(pe,pes),_positive_ratio(pb,pbs),_positive_ratio(ev,evs))
    sec=[_relative_state(x) for x in sec_ratios]
    sv=[x for x in sec if x!=NOT_EVALUATED]
    sector_relative=NOT_EVALUATED if not sv else ("CHEAP" if sv.count("CHEAP")>=2 else ("EXPENSIVE" if sv.count("EXPENSIVE")>=2 else "FAIR_OR_MIXED"))

    if ey is None: earnings_yield_state=NOT_EVALUATED
    elif ey>=8: earnings_yield_state="ATTRACTIVE"
    elif ey<3: earnings_yield_state="LOW"
    else: earnings_yield_state="MODERATE"

    if fy is None: fcf_yield_state=NOT_EVALUATED
    elif fy>=7: fcf_yield_state="ATTRACTIVE"
    elif fy<2: fcf_yield_state="LOW"
    else: fcf_yield_state="MODERATE"

    # PEG-like comparison is meaningful only with positive PE and positive EPS growth.
    peg=_positive_ratio(pe,eg)
    if eg is None: growth_adjusted=NOT_EVALUATED
    elif eg<=0: growth_adjusted="NONPOSITIVE_GROWTH_CONTEXT"
    elif peg is None: growth_adjusted=NOT_EVALUATED
    elif peg<=1:growth_adjusted="ATTRACTIVE_RELATIVE_TO_GROWTH"
    elif peg>=2:growth_adjusted="RICH_RELATIVE_TO_GROWTH"
    else:growth_adjusted="BALANCED_RELATIVE_TO_GROWTH"

    lens=[absolute,historical,sector_relative]
    cheap=sum(x=="CHEAP" for x in lens); expensive=sum(x=="EXPENSIVE" for x in lens)
    if cheap and expensive: dispersion="CONFLICTING"
    elif cheap>=2: dispersion="CONSISTENTLY_CHEAP"
    elif expensive>=2: dispersion="CONSISTENTLY_EXPENSIVE"
    elif any(x not in {NOT_EVALUATED} for x in lens): dispersion="MIXED"
    else: dispersion=NOT_EVALUATED

    evidence_count=sum(x!=NOT_EVALUATED for x in (absolute,historical,sector_relative,earnings_yield_state,fcf_yield_state,growth_adjusted))
    evidence_state="ROBUST" if evidence_count>=5 else ("PARTIAL" if evidence_count>=3 else ("THIN" if evidence_count else NOT_EVALUATED))

    conf=_conf(conf_cov,fresh)
    comps={
      "absolute_valuation":result(absolute,[f"pe={pe}",f"pb={pb}",f"ev_ebitda={ev}"],_component_conf(absolute,conf)),
      "historical_valuation":result(historical,[f"pe_vs_5y={hist_ratios[0]}",f"pb_vs_5y={hist_ratios[1]}",f"ev_vs_5y={hist_ratios[2]}"],_component_conf(historical,conf)),
      "sector_relative_valuation":result(sector_relative,[f"pe_vs_sector={sec_ratios[0]}",f"pb_vs_sector={sec_ratios[1]}",f"ev_vs_sector={sec_ratios[2]}"],_component_conf(sector_relative,conf)),
      "earnings_yield":result(earnings_yield_state,[f"earnings_yield={ey}"],_component_conf(earnings_yield_state,conf)),
      "fcf_yield":result(fcf_yield_state,[f"fcf_yield={fy}"],_component_conf(fcf_yield_state,conf)),
      "growth_adjusted_context":result(growth_adjusted,[f"eps_growth={eg}",f"revenue_growth={rg}",f"peg_proxy={peg}"],_component_conf(growth_adjusted,conf)),
      "valuation_dispersion":result(dispersion,[f"absolute={absolute}",f"historical={historical}",f"sector_relative={sector_relative}"],_component_conf(dispersion,conf)),
      "evidence_sufficiency":result(evidence_state,[f"evaluated_lenses={evidence_count}"],_component_conf(evidence_state,conf))
    }
    contradictions=[]
    if absolute=="EXPENSIVE" and historical=="CHEAP": contradictions.append("ABSOLUTE_EXPENSIVE_BUT_HISTORICALLY_CHEAP")
    if absolute=="CHEAP" and sector_relative=="EXPENSIVE": contradictions.append("ABSOLUTE_CHEAP_BUT_SECTOR_EXPENSIVE")
    if fcf_yield_state=="ATTRACTIVE" and earnings_yield_state=="LOW": contradictions.append("ATTRACTIVE_FCF_YIELD_WITH_LOW_EARNINGS_YIELD")
    if growth_adjusted=="RICH_RELATIVE_TO_GROWTH" and absolute=="CHEAP": contradictions.append("ABSOLUTE_CHEAP_BUT_RICH_VS_GROWTH")
    severity="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")

    cheap_evidence=sum(x in {"CHEAP","ATTRACTIVE","ATTRACTIVE_RELATIVE_TO_GROWTH","CONSISTENTLY_CHEAP"} for x in
                       (absolute,historical,sector_relative,earnings_yield_state,fcf_yield_state,growth_adjusted,dispersion))
    rich_evidence=sum(x in {"EXPENSIVE","LOW","RICH_RELATIVE_TO_GROWTH","CONSISTENTLY_EXPENSIVE"} for x in
                       (absolute,historical,sector_relative,earnings_yield_state,fcf_yield_state,growth_adjusted,dispersion))
    if evidence_count<2: overall=NOT_EVALUATED
    elif cheap_evidence>=3 and rich_evidence==0: overall="CHEAP"
    elif rich_evidence>=3 and cheap_evidence==0: overall="EXPENSIVE"
    else: overall="MIXED_OR_FAIR"

    return {"domain":DOMAIN,"state":overall,"confidence":conf,"components":comps,
            "contradictions":contradictions,"contradiction_severity":severity,
            "data_quality":dq,"recommendation":None,"ranking":None}
