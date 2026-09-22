from __future__ import annotations
import math

VERSION="SIS-FINAL-RANKING-R1"
OUTLOOK_RANK={"POSITIVE":4,"STABLE":3,"CAUTIOUS":2,"NEGATIVE":1,"INSUFFICIENT":0}
DCA_RANK={"FAVORABLE":2,"NORMAL":1,"CAUTIOUS":0}
RISK_RANK={"POSITIVE_STRONG":5,"POSITIVE_MODERATE":4,"NEUTRAL":3,"UNKNOWN":2,
           "NEGATIVE_MODERATE":1,"NEGATIVE_STRONG":0}

def _finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))

def _risk_state(synthesis):
    try:return synthesis["shared"]["evidence_ledger"]["RISK"]["state"]
    except Exception:return "UNKNOWN"

def _symbol(rec):
    for x in (rec.get("synthesis"),rec.get("swing_execution"),rec.get("longterm_outlook"),rec):
        if isinstance(x,dict) and x.get("symbol"): return str(x["symbol"])
    return ""

def _swing_key(rec):
    s=rec["synthesis"]; e=rec["swing_execution"]
    sw=s.get("swing") or {}
    q=sw.get("quality"); conf=sw.get("confidence")
    rr=e.get("reward_risk") or {}
    rr1=rr.get("target_1"); rr2=rr.get("target_2")
    return (
      float(q) if _finite(q) else -1,
      float(rr1) if _finite(rr1) else -1,
      float(conf) if _finite(conf) else -1,
      float(rr2) if _finite(rr2) else -1,
      RISK_RANK.get(_risk_state(s),2),
      # symbol handled separately for ascending deterministic tie-break
    )

def _lt_key(rec):
    s=rec["synthesis"]; lt=rec["longterm_outlook"]
    base=s.get("long_term") or {}
    q=base.get("quality"); conf=base.get("confidence")
    out=lt.get("outlook") or {}
    return (
      float(q) if _finite(q) else -1,
      float(conf) if _finite(conf) else -1,
      OUTLOOK_RANK.get((out.get("3Y") or {}).get("state"),0),
      OUTLOOK_RANK.get((out.get("5Y") or {}).get("state"),0),
      OUTLOOK_RANK.get((out.get("1Y") or {}).get("state"),0),
      DCA_RANK.get(lt.get("dca_context"),0),
      RISK_RANK.get(_risk_state(s),2),
    )

def _stable_desc(records,keyfn):
    # First symbol ascending, then stable descending sort by analytical tuple.
    rows=sorted(records,key=lambda r:_symbol(r))
    return sorted(rows,key=keyfn,reverse=True)

def rank_candidates(records,top_n=3):
    if not isinstance(records,list) or not isinstance(top_n,int) or top_n<1:
        return {"status":"INVALID","reason":"INVALID_INPUT","swing":{},"long_term":{}}
    swing_ok=[]; swing_watch=[]; swing_rejected=[]
    lt_ok=[]; lt_watch=[]; lt_rejected=[]

    for rec in records:
        if not isinstance(rec,dict):
            continue
        syn=rec.get("synthesis") or {}
        se=rec.get("swing_execution") or {}
        le=rec.get("longterm_outlook") or {}
        symbol=_symbol(rec)

        sw=(syn.get("swing") or {})
        if sw.get("analytical_status")=="PASS" and se.get("status")=="COMPLETE" and se.get("execution_status")=="READY":
            swing_ok.append(rec)
        elif se.get("execution_status")=="WAIT" or sw.get("analytical_status")=="REVIEW":
            swing_watch.append({"symbol":symbol,"analytical_status":sw.get("analytical_status"),
                                "execution_status":se.get("execution_status")})
        else:
            swing_rejected.append({"symbol":symbol,"analytical_status":sw.get("analytical_status"),
                                   "execution_status":se.get("execution_status")})

        ltb=(syn.get("long_term") or {})
        if ltb.get("analytical_status")=="PASS" and le.get("status")=="COMPLETE":
            lt_ok.append(rec)
        elif ltb.get("analytical_status")=="REVIEW" or le.get("status")=="COMPLETE":
            lt_watch.append({"symbol":symbol,"analytical_status":ltb.get("analytical_status"),
                             "outlook_status":le.get("status")})
        else:
            lt_rejected.append({"symbol":symbol,"analytical_status":ltb.get("analytical_status"),
                                "outlook_status":le.get("status")})

    sr=_stable_desc(swing_ok,_swing_key)[:top_n]
    lr=_stable_desc(lt_ok,_lt_key)[:top_n]

    swing_ranked=[]
    for i,r in enumerate(sr,1):
        syn=r["synthesis"]; e=r["swing_execution"]; sw=syn["swing"]
        swing_ranked.append({
          "rank":i,"symbol":_symbol(r),"quality":sw.get("quality"),"confidence":sw.get("confidence"),
          "execution_status":e.get("execution_status"),"entry_area":e.get("entry_area"),
          "target_1":e.get("target_1"),"target_2":e.get("target_2"),
          "risk_boundary":e.get("risk_boundary"),"reward_risk":e.get("reward_risk"),
          "residual_risk":_risk_state(syn)})

    lt_ranked=[]
    for i,r in enumerate(lr,1):
        syn=r["synthesis"]; le=r["longterm_outlook"]; base=syn["long_term"]
        lt_ranked.append({
          "rank":i,"symbol":_symbol(r),"quality":base.get("quality"),"confidence":base.get("confidence"),
          "outlook":le.get("outlook"),"dca_context":le.get("dca_context"),
          "residual_risk":_risk_state(syn)})

    return {
      "status":"COMPLETE","ranking_policy":"LEXICOGRAPHIC_NO_NEW_SCORE",
      "swing":{"top":swing_ranked,"eligible_count":len(swing_ok),
               "watch":swing_watch,"rejected_for_current_ranking":swing_rejected},
      "long_term":{"top":lt_ranked,"eligible_count":len(lt_ok),
                   "watch":lt_watch,"rejected_for_current_ranking":lt_rejected},
      "recommendation":None
    }
