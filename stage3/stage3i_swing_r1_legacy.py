from __future__ import annotations
import math

VERSION="S3I-SWING-R1"
READY="READY"; WAIT="WAIT"; NOT_ATTRACTIVE="NOT_ATTRACTIVE"; INSUFFICIENT_DATA="INSUFFICIENT_DATA"

def _finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))

def _domain(dossier,name):
    x=(dossier.get("domains") or {}).get(name,{})
    return x if isinstance(x,dict) else {}

def _component(domain,name):
    x=(domain.get("components") or {}).get(name,{})
    return x if isinstance(x,dict) else {}

def _state(domain,name):
    return _component(domain,name).get("state","NOT_EVALUATED")

def _extract_evidence_number(component,prefix):
    for x in component.get("evidence") or []:
        if isinstance(x,str) and x.startswith(prefix+"="):
            try:
                v=float(x.split("=",1)[1])
                return v if math.isfinite(v) else None
            except Exception:
                pass
    return None

def _valid_bar(x):
    if not isinstance(x,dict): return False
    for k in ("open","high","low","close","volume"):
        if k not in x or not _finite(x[k]): return False
    o,h,l,c,v=(float(x[k]) for k in ("open","high","low","close","volume"))
    return c>0 and v>=0 and h>=l and l<=o<=h and l<=c<=h

def _levels(hist,current):
    # Structural overhead swing highs from completed rolling windows.
    # No fixed-percentage targets are invented.
    highs=[float(x["high"]) for x in hist]
    lows=[float(x["low"]) for x in hist]
    candidates=[]
    n=len(hist)
    for i in range(2,n-2):
        h=highs[i]
        if h>=highs[i-1] and h>=highs[i-2] and h>=highs[i+1] and h>=highs[i+2] and h>current:
            candidates.append(h)
    # Cluster near-identical levels to avoid fake T1/T2 duplication.
    candidates=sorted(candidates)
    uniq=[]
    for v in candidates:
        if not uniq or abs(v-uniq[-1])/current>=0.015:
            uniq.append(v)
    return uniq[:2]

def _entry_area(setup,current,ma20,resistance,support):
    if setup=="BREAKOUT":
        # Entry waits near proven breakout structure, not arbitrary chasing.
        ref=resistance if _finite(resistance) else None
        if ref is None:return None
        lo=min(ref,current); hi=max(ref,current)
        return {"low":round(lo,4),"high":round(hi,4),"reference":round(ref,4),"basis":"BREAKOUT_RESISTANCE_RETEST"}
    if setup=="PULLBACK":
        if not _finite(ma20):return None
        lo=min(ma20,current); hi=max(ma20,current)
        return {"low":round(lo,4),"high":round(hi,4),"reference":round(ma20,4),"basis":"MA20_PULLBACK_CONTEXT"}
    if setup=="BASE":
        if not _finite(resistance):return None
        return {"low":round(resistance,4),"high":round(resistance,4),"reference":round(resistance,4),"basis":"WAIT_FOR_BASE_BREAKOUT"}
    if setup=="EXTENDED":
        if not _finite(ma20):return None
        return {"low":round(ma20,4),"high":round(ma20,4),"reference":round(ma20,4),"basis":"WAIT_FOR_NORMALIZATION_TO_MA20"}
    return None

def _rr(entry,risk,target):
    if not all(_finite(x) for x in (entry,risk,target)):return None
    if not (risk<entry<target):return None
    den=entry-risk
    return round((target-entry)/den,2) if den>0 else None

def evaluate_swing(synthesis,dossier,stock):
    if not all(isinstance(x,dict) for x in (synthesis,dossier,stock)):
        return {"status":"INVALID","reason":"INVALID_INPUT","recommendation":None,"ranking":None}
    sw=synthesis.get("swing") or {}
    quality=sw.get("quality"); base_conf=sw.get("confidence")
    tech=_domain(dossier,"technical")
    comps=tech.get("components") or {}
    t=stock.get("technical_enrichment") or {}
    hist=t.get("ohlcv") or []
    if not isinstance(hist,list) or len(hist)<60 or any(not _valid_bar(x) for x in hist):
        return {"status":"COMPLETE","symbol":synthesis.get("symbol") or dossier.get("symbol") or stock.get("symbol"),
                "quality":quality,"base_confidence":base_conf,"execution_status":INSUFFICIENT_DATA,
                "reason_codes":["INSUFFICIENT_OR_MALFORMED_OHLCV"],"current_price":None,
                "entry_area":None,"target_1":None,"target_2":None,"risk_boundary":None,
                "reward_risk":None,"recommendation":None,"ranking":None}

    current=float(hist[-1]["close"])
    trend=_state(tech,"trend"); structure=_state(tech,"price_structure")
    momentum=_state(tech,"momentum"); participation=_state(tech,"participation")
    rs=_state(tech,"relative_strength"); setup=_state(tech,"setup_entry")
    fresh=(tech.get("data_quality") or {}).get("freshness","UNKNOWN")
    contradiction=tech.get("contradiction_severity","NONE")

    trend_c=_component(tech,"trend"); setup_c=_component(tech,"setup_entry")
    ma20=_extract_evidence_number(trend_c,"ma20")
    resistance=_extract_evidence_number(setup_c,"resistance")
    inv=_component(tech,"invalidation").get("level")
    support=float(inv) if _finite(inv) else None

    entry=_entry_area(setup,current,ma20,resistance,support)
    entry_ref=entry["reference"] if entry else None
    risk=support if _finite(support) and _finite(entry_ref) and support<entry_ref else None

    targets=_levels(hist,entry_ref if _finite(entry_ref) else current)
    t1=targets[0] if len(targets)>0 else None
    t2=targets[1] if len(targets)>1 else None
    rr1=_rr(entry_ref,risk,t1); rr2=_rr(entry_ref,risk,t2)

    reasons=[]
    if sw.get("analytical_status")!="PASS": reasons.append("S3H_SWING_NOT_PASS")
    if fresh!="FRESH": reasons.append("TECHNICAL_DATA_NOT_FRESH")
    if contradiction in {"MATERIAL","SEVERE"}: reasons.append("UNRESOLVED_TECHNICAL_CONTRADICTION")
    if trend!="BULL": reasons.append("TREND_NOT_BULL")
    if structure=="BROKEN": reasons.append("STRUCTURE_BROKEN")
    if setup=="NONE": reasons.append("NO_CLEAR_ENTRY_CONTEXT")
    if entry is None: reasons.append("NO_DEFENSIBLE_ENTRY_AREA")
    if risk is None: reasons.append("NO_DEFENSIBLE_RISK_BOUNDARY")
    if t1 is None: reasons.append("NO_DEFENSIBLE_STRUCTURAL_TARGET")
    if rr1 is None: reasons.append("RR_NOT_COMPUTABLE")

    # Execution status is deterministic and separate from S3H quality.
    if setup=="EXTENDED":
        status=WAIT
        reasons.append("AVOID_CHASING_EXTENDED_PRICE")
    elif setup=="BASE":
        status=WAIT
        reasons.append("WAIT_FOR_BREAKOUT_CONFIRMATION")
    elif any(x in reasons for x in ("S3H_SWING_NOT_PASS","TECHNICAL_DATA_NOT_FRESH",
                                    "UNRESOLVED_TECHNICAL_CONTRADICTION","TREND_NOT_BULL",
                                    "STRUCTURE_BROKEN","NO_CLEAR_ENTRY_CONTEXT",
                                    "NO_DEFENSIBLE_ENTRY_AREA","NO_DEFENSIBLE_RISK_BOUNDARY")):
        status=WAIT if entry is not None and trend=="BULL" and structure!="BROKEN" else INSUFFICIENT_DATA
    elif t1 is None or rr1 is None:
        status=INSUFFICIENT_DATA
    elif rr1<1.5:
        status=NOT_ATTRACTIVE
        reasons.append("REWARD_RISK_BELOW_MINIMUM")
    elif setup in {"BREAKOUT","PULLBACK"}:
        # Participation/momentum/RS can prevent READY but do not create prices.
        if participation in {"DISTRIBUTION","WEAK"} or momentum=="FADING" or rs=="DETERIORATING":
            status=WAIT
            reasons.append("EXECUTION_CONFIRMATION_WEAK")
        else:
            status=READY
    else:
        status=WAIT

    return {
      "status":"COMPLETE","symbol":synthesis.get("symbol") or dossier.get("symbol") or stock.get("symbol"),
      "quality":quality,"base_confidence":base_conf,"s3h_analytical_status":sw.get("analytical_status"),
      "execution_status":status,"current_price":round(current,4),
      "entry_area":entry,"target_1":round(t1,4) if t1 is not None else None,
      "target_2":round(t2,4) if t2 is not None else None,
      "risk_boundary":round(risk,4) if risk is not None else None,
      "reward_risk":{"target_1":rr1,"target_2":rr2},
      "execution_evidence":{"trend":trend,"structure":structure,"momentum":momentum,
        "participation":participation,"relative_strength":rs,"setup":setup,
        "technical_freshness":fresh,"contradiction_severity":contradiction},
      "reason_codes":list(dict.fromkeys(reasons)),
      "recommendation":None,"ranking":None
    }
