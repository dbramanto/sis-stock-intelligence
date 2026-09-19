from datetime import date
import math
from stage3_common import result, NOT_EVALUATED, missing

DOMAIN="3C_CASH"
FIELDS=("ocf_ttm","fcf_ttm","net_income_ttm","ocf_prev_ttm","fcf_prev_ttm",
        "net_income_prev_ttm","capex_ttm","revenue_ttm","cash_balance","short_term_debt")

def _num(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def _ratio(a,b):
    return None if not (_num(a) and _num(b)) or b==0 else a/b

def _fresh(meta,analysis_date):
    raw=meta.get("as_of_date") if isinstance(meta,dict) else None
    if not raw:return "UNKNOWN",None
    try:
        d=date.fromisoformat(str(raw)); a=date.fromisoformat(str(analysis_date)); age=(a-d).days
        if age<0:return "FUTURE_INVALID",age
        return ("FRESH" if age<=120 else "STALE"),age
    except Exception:return "UNKNOWN",None

def _conf(cov,fresh):
    c="HIGH" if cov>=.8 else ("MODERATE" if cov>=.55 else ("LOW" if cov>=.3 else "INSUFFICIENT"))
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT","INSUFFICIENT":"INSUFFICIENT"}[c]
    return c

def evaluate_cash(s,analysis_date="2026-09-17"):
    e=s.get("cash_enrichment",{})
    if not isinstance(e,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"INVALID_CASH_PAYLOAD","components":{},"contradictions":[]}
    meta=e.get("metadata",{}) if isinstance(e.get("metadata",{}),dict) else {}
    fresh,age=_fresh(meta,analysis_date)
    # Integrity layer: supplied values must be finite numerics.  Use explicit
    # None detection here so NaN is not silently treated as missing.
    present={k:e.get(k) for k in FIELDS if e.get(k) is not None}
    invalid=[k for k,v in present.items() if not _num(v)]

    # Domain semantics for scale/balance fields used as ratio denominators.
    # Revenue cannot be negative; cash and short-term debt are balance magnitudes
    # and therefore cannot be negative under this enrichment contract.
    semantic_invalid=[]
    if _num(e.get("revenue_ttm")) and e.get("revenue_ttm") < 0:
        semantic_invalid.append("revenue_ttm")
    if _num(e.get("cash_balance")) and e.get("cash_balance") < 0:
        semantic_invalid.append("cash_balance")
    if _num(e.get("short_term_debt")) and e.get("short_term_debt") < 0:
        semantic_invalid.append("short_term_debt")
    invalid=invalid + [k for k in semantic_invalid if k not in invalid]
    cov=sum(1 for k in FIELDS if _num(e.get(k)))/len(FIELDS)
    dq={"source":meta.get("source",e.get("source","UNKNOWN")),"as_of_date":meta.get("as_of_date"),
        "freshness":fresh,"age_days":age,"coverage":round(cov,4),"invalid_fields":invalid}
    if invalid:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"INVALID_CASH_FIELD","components":{},"contradictions":[],"data_quality":dq}

    g=lambda k:e.get(k) if _num(e.get(k)) else None
    ocf,fcf,ni=g("ocf_ttm"),g("fcf_ttm"),g("net_income_ttm")
    pocf,pfcf,pni=g("ocf_prev_ttm"),g("fcf_prev_ttm"),g("net_income_prev_ttm")
    capex,rev,cash,std=g("capex_ttm"),g("revenue_ttm"),g("cash_balance"),g("short_term_debt")

    # C1 OCF quality
    ocf_state=NOT_EVALUATED if ocf is None else ("STRONG" if ocf>0 else "WEAK")

    # C2 FCF quality
    fcf_state=NOT_EVALUATED if fcf is None else ("STRONG" if fcf>0 else "WEAK")

    # C3 Cash conversion (distinct from 3B profitability)
    conv=_ratio(ocf,ni)
    if conv is None: conv_state=NOT_EVALUATED
    elif ni<0 and ocf>0: conv_state="DIVERGENT_POSITIVE_CASH"
    elif ni>0 and conv>=1: conv_state="STRONG"
    elif ni>0 and conv>=.7: conv_state="MIXED"
    else: conv_state="WEAK"

    # C4 Profit-cash divergence
    if ni is None or ocf is None: div_state=NOT_EVALUATED
    elif ni>0 and ocf<0: div_state="NEGATIVE_DIVERGENCE"
    elif ni<0 and ocf>0: div_state="POSITIVE_DIVERGENCE"
    else: div_state="ALIGNED"

    # C5 FCF sustainability
    if fcf is None or pfcf is None: sust=NOT_EVALUATED
    elif fcf>0 and pfcf>0: sust="SUSTAINED_POSITIVE"
    elif fcf<0 and pfcf<0: sust="SUSTAINED_NEGATIVE"
    elif fcf>pfcf: sust="IMPROVING"
    else: sust="DETERIORATING"

    # C6 Cash trend / consistency
    pairs=[(ocf,pocf),(fcf,pfcf)]
    usable=[(a,b) for a,b in pairs if a is not None and b is not None]
    if not usable: trend=NOT_EVALUATED
    else:
        up=sum(a>=b for a,b in usable); down=sum(a<b for a,b in usable)
        trend="IMPROVING" if up==len(usable) else ("DETERIORATING" if down==len(usable) else "MIXED")

    # C7 Capital intensity: capex burden relative to OCF/revenue, not capital allocation judgment.
    capex_abs=abs(capex) if capex is not None else None
    capex_ocf=_ratio(capex_abs,abs(ocf)) if ocf not in (None,0) else None
    capex_rev=_ratio(capex_abs,rev) if rev not in (None,0) else None
    if capex_ocf is None and capex_rev is None: intensity=NOT_EVALUATED
    elif (capex_ocf is not None and capex_ocf>=.8) or (capex_rev is not None and capex_rev>=.20): intensity="HIGH"
    elif (capex_ocf is not None and capex_ocf<=.35) or (capex_rev is not None and capex_rev<=.08): intensity="LOW"
    else: intensity="MODERATE"

    # C8 Cash stress: short-term cash coverage + negative cash generation.
    coverage=_ratio(cash,std)
    stress_votes=[]
    if coverage is not None: stress_votes.append(1 if coverage<1 else (-1 if coverage>=2 else 0))
    if ocf is not None: stress_votes.append(1 if ocf<0 else -1)
    if fcf is not None: stress_votes.append(1 if fcf<0 else 0)
    if not stress_votes: stress=NOT_EVALUATED
    elif sum(stress_votes)>=2: stress="HIGH"
    elif sum(stress_votes)<=-1: stress="LOW"
    else: stress="MODERATE"

    conf=_conf(cov,fresh)
    comps={
      "ocf_quality":result(ocf_state,[f"ocf_ttm={ocf}"],conf),
      "fcf_quality":result(fcf_state,[f"fcf_ttm={fcf}"],conf),
      "cash_conversion":result(conv_state,[f"ocf_net_income_ratio={conv}"],conf),
      "profit_cash_divergence":result(div_state,[f"net_income_ttm={ni}",f"ocf_ttm={ocf}"],conf),
      "fcf_sustainability":result(sust,[f"fcf_ttm={fcf}",f"fcf_prev_ttm={pfcf}"],conf),
      "cash_trend_consistency":result(trend,[f"ocf_prev_ttm={pocf}",f"fcf_prev_ttm={pfcf}"],conf),
      "capital_intensity":result(intensity,[f"capex_ocf_ratio={capex_ocf}",f"capex_revenue_ratio={capex_rev}"],conf),
      "cash_stress":result(stress,[f"cash_short_term_debt_coverage={coverage}"],conf)
    }
    contradictions=[]
    if ni is not None and ni>0 and ocf is not None and ocf<0: contradictions.append("POSITIVE_PROFIT_WITH_NEGATIVE_OCF")
    if ocf is not None and ocf>0 and fcf is not None and fcf<0: contradictions.append("POSITIVE_OCF_WITH_NEGATIVE_FCF")
    if trend=="IMPROVING" and stress=="HIGH": contradictions.append("IMPROVING_CASH_TREND_WITH_HIGH_LIQUIDITY_STRESS")
    severity="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")

    bad=sum(x in {"WEAK","NEGATIVE_DIVERGENCE","SUSTAINED_NEGATIVE","DETERIORATING","HIGH"} for x in
            (ocf_state,fcf_state,div_state,sust,trend,stress))
    good=sum(x in {"STRONG","ALIGNED","SUSTAINED_POSITIVE","IMPROVING","LOW"} for x in
             (ocf_state,fcf_state,conv_state,div_state,sust,trend,stress))
    overall="WEAK" if bad>=3 else ("STRONG" if good>=4 and bad==0 else ("MIXED" if good+bad>0 else NOT_EVALUATED))
    return {"domain":DOMAIN,"state":overall,"confidence":conf,"components":comps,
            "contradictions":contradictions,"contradiction_severity":severity,
            "data_quality":dq,"recommendation":None,"ranking":None}
