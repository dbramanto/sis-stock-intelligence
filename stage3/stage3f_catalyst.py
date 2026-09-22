from datetime import date
import math
from stage3_common import result, NOT_EVALUATED

DOMAIN="3F_CATALYST"
VALID_DIR={"POSITIVE","NEGATIVE","NEUTRAL","MIXED"}
VALID_MAT={"LOW","MODERATE","HIGH","CRITICAL"}
VALID_STATUS={"UPCOMING","ONGOING","COMPLETED","RUMORED"}
VALID_PRICED={"NOT_PRICED_IN","PARTIALLY_PRICED_IN","LIKELY_PRICED_IN","UNKNOWN"}

def _num(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _parse_date(v):
    try:return date.fromisoformat(str(v))
    except Exception:return None

def _fresh(meta,analysis_date):
    raw=meta.get("as_of_date") if isinstance(meta,dict) else None
    if not raw:return "UNKNOWN",None
    d=_parse_date(raw); a=_parse_date(analysis_date)
    if not d or not a:return "UNKNOWN",None
    age=(a-d).days
    if age<0:return "FUTURE_INVALID",age
    return ("FRESH" if age<=7 else "STALE"),age

def _conf(cov,fresh):
    c="HIGH" if cov>=.80 else ("MODERATE" if cov>=.55 else ("LOW" if cov>=.30 else "INSUFFICIENT"))
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT","INSUFFICIENT":"INSUFFICIENT"}[c]
    return c

def evaluate_catalyst(s,analysis_date="2026-09-17"):
    e=s.get("catalyst_enrichment",{})
    if not isinstance(e,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"INVALID_CATALYST_PAYLOAD","components":{},"contradictions":[]}
    meta=e.get("metadata",{}) if isinstance(e.get("metadata",{}),dict) else {}
    fresh,age=_fresh(meta,analysis_date)
    events=e.get("events",[])
    if not isinstance(events,list):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"INVALID_EVENTS_PAYLOAD","components":{},"contradictions":[],
                "data_quality":{"source":meta.get("source","UNKNOWN"),"freshness":fresh,"age_days":age}}

    valid=[]; invalid=[]
    a=_parse_date(analysis_date)
    for i,x in enumerate(events):
        if not isinstance(x,dict):
            invalid.append((i,"EVENT_NOT_OBJECT")); continue
        direction=x.get("direction")
        materiality=x.get("materiality")
        status=x.get("status")
        prob=x.get("probability")
        priced=x.get("priced_in","UNKNOWN")
        raw_event_date=x.get("event_date")
        ed=_parse_date(raw_event_date) if raw_event_date is not None else None
        if direction not in VALID_DIR: invalid.append((i,"INVALID_DIRECTION")); continue
        if materiality not in VALID_MAT: invalid.append((i,"INVALID_MATERIALITY")); continue
        if status not in VALID_STATUS: invalid.append((i,"INVALID_STATUS")); continue
        if not _num(prob) or not 0<=prob<=1: invalid.append((i,"INVALID_PROBABILITY")); continue
        if priced not in VALID_PRICED: invalid.append((i,"INVALID_PRICED_IN")); continue
        if raw_event_date is not None and ed is None:
            invalid.append((i,"INVALID_EVENT_DATE")); continue
        if status=="UPCOMING":
            if ed is None:
                invalid.append((i,"MISSING_UPCOMING_EVENT_DATE")); continue
            if a is None:
                invalid.append((i,"INVALID_ANALYSIS_DATE")); continue
            if ed<a:
                invalid.append((i,"UPCOMING_EVENT_DATE_IN_PAST")); continue
        if status=="COMPLETED":
            if ed is None:
                invalid.append((i,"MISSING_COMPLETED_EVENT_DATE")); continue
            if a is None:
                invalid.append((i,"INVALID_ANALYSIS_DATE")); continue
            if ed>a:
                invalid.append((i,"COMPLETED_EVENT_DATE_IN_FUTURE")); continue
        y=dict(x); y["_date"]=ed
        valid.append(y)

    dq={"source":meta.get("source",e.get("source","UNKNOWN")),"as_of_date":meta.get("as_of_date"),
        "freshness":fresh,"age_days":age,"events_total":len(events),
        "events_valid":len(valid),"events_invalid":len(invalid),"invalid_events":invalid}
    if invalid:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"MALFORMED_CATALYST_EVENT","components":{},"contradictions":[],
                "data_quality":dq}
    if not valid:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT",
                "reason":"NO_CATALYST_EVIDENCE","components":{},"contradictions":[],
                "data_quality":dq,"recommendation":None,"ranking":None}

    types=sorted({str(x.get("type","UNSPECIFIED")) for x in valid})
    inventory="DOCUMENTED"
    dirs={x["direction"] for x in valid if x["direction"]!="NEUTRAL"}
    if not dirs: direction_state="NEUTRAL"
    elif dirs=={"POSITIVE"}:direction_state="POSITIVE"
    elif dirs=={"NEGATIVE"}:direction_state="NEGATIVE"
    else:direction_state="MIXED"

    rank={"LOW":1,"MODERATE":2,"HIGH":3,"CRITICAL":4}
    strongest=max(valid,key=lambda x:rank[x["materiality"]])
    materiality_state=strongest["materiality"]

    days=[]
    for x in valid:
        if x["_date"] and a: days.append((x["_date"]-a).days)
    upcoming=[d for d in days if d>=0]
    if upcoming:
        nearest=min(upcoming)
        timing="IMMINENT" if nearest<=7 else ("NEAR_TERM" if nearest<=30 else "LONGER_TERM")
    elif any(x["status"]=="ONGOING" for x in valid): nearest=None; timing="ONGOING"
    elif days: nearest=None; timing="PAST_EVENT"
    else: nearest=None; timing="UNSCHEDULED"

    probs=[x["probability"] for x in valid]
    weighted=sum(x["probability"]*rank[x["materiality"]] for x in valid)/sum(rank[x["materiality"]] for x in valid)
    probability_state="HIGH" if weighted>=.75 else ("MODERATE" if weighted>=.45 else "LOW")

    priced={x["priced_in"] for x in valid}
    if priced=={"LIKELY_PRICED_IN"}: priced_state="LIKELY_PRICED_IN"
    elif "NOT_PRICED_IN" in priced and "LIKELY_PRICED_IN" in priced: priced_state="MIXED"
    elif "NOT_PRICED_IN" in priced: priced_state="NOT_PRICED_IN"
    elif "PARTIALLY_PRICED_IN" in priced: priced_state="PARTIALLY_PRICED_IN"
    else: priced_state="UNKNOWN"

    completed_old=[]
    for x in valid:
        if x["status"]=="COMPLETED" and x["_date"] and a:
            completed_old.append((a-x["_date"]).days>30)
    relevance="STALE_EVENT_SET" if completed_old and all(completed_old) and all(x["status"]=="COMPLETED" for x in valid) else "CURRENT_OR_FORWARD"

    score=0
    for x in valid:
        sign=1 if x["direction"]=="POSITIVE" else (-1 if x["direction"]=="NEGATIVE" else 0)
        priced_factor=.35 if x["priced_in"]=="LIKELY_PRICED_IN" else (.65 if x["priced_in"]=="PARTIALLY_PRICED_IN" else 1)
        score += sign*rank[x["materiality"]]*x["probability"]*priced_factor
    if abs(score)<.5: net="BALANCED_OR_WEAK"
    elif score>0: net="POSITIVE"
    else: net="NEGATIVE"

    coverage=sum([bool(types),direction_state is not None,materiality_state is not None,
                  timing is not None,bool(probs),priced_state is not None,relevance is not None,net is not None])/8
    conf=_conf(coverage,fresh)
    comps={
      "event_inventory":result(inventory,[f"types={types}",f"events={len(valid)}"],conf),
      "direction":result(direction_state,[f"directions={sorted(dirs)}"],conf),
      "materiality":result(materiality_state,[f"strongest_type={strongest.get('type')}",f"materiality={materiality_state}"],conf),
      "event_window":result(timing,[f"nearest_upcoming_days={nearest}"],conf),
      "probability_confidence":result(probability_state,[f"weighted_probability={weighted:.4f}"],conf),
      "priced_in":result(priced_state,[f"priced_in_states={sorted(priced)}"],conf),
      "event_relevance":result(relevance,[f"freshness={fresh}"],conf),
      "net_catalyst_context":result(net,[f"weighted_net={score:.4f}"],conf)
    }
    contradictions=[]
    if direction_state=="POSITIVE" and priced_state=="LIKELY_PRICED_IN": contradictions.append("POSITIVE_CATALYST_LIKELY_PRICED_IN")
    if direction_state=="MIXED" and materiality_state in {"HIGH","CRITICAL"}: contradictions.append("MATERIAL_OPPOSING_CATALYSTS")
    if probability_state=="LOW" and materiality_state in {"HIGH","CRITICAL"}: contradictions.append("HIGH_MATERIALITY_LOW_PROBABILITY")
    if relevance=="STALE_EVENT_SET": contradictions.append("CATALYST_SET_NO_LONGER_FORWARD_LOOKING")
    severity="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")
    return {"domain":DOMAIN,"state":net,"confidence":conf,"components":comps,
            "contradictions":contradictions,"contradiction_severity":severity,
            "data_quality":dq,"recommendation":None,"ranking":None}
