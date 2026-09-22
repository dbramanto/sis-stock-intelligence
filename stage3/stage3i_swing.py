from __future__ import annotations
import math

VERSION="S3I-SWING-R2-INTERNAL-FIRST"
READY="READY"; WAIT="WAIT"; NOT_ATTRACTIVE="NOT_ATTRACTIVE"; INSUFFICIENT_DATA="INSUFFICIENT_DATA"

def _finite(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))
def _domain(d,n):
 x=(d.get("domains") or {}).get(n,{}); return x if isinstance(x,dict) else {}
def _component(d,n):
 x=(d.get("components") or {}).get(n,{}); return x if isinstance(x,dict) else {}
def _state(d,n): return _component(d,n).get("state","NOT_EVALUATED")
def _rr(e,r,t):
 if not all(_finite(x) for x in (e,r,t)) or not (r<e<t): return None
 return round((t-e)/(e-r),2)
def _round_price(v): return round(float(v),2) if _finite(v) else None

def _internal_plan(synthesis,dossier,stock):
 sw=synthesis.get("swing") or {}; quality=sw.get("quality"); base_conf=sw.get("confidence")
 tech=_domain(dossier,"technical"); m=(stock.get("technical_enrichment") or {}).get("internal_market") or {}
 symbol=synthesis.get("symbol") or dossier.get("symbol") or stock.get("symbol")
 req=("price","ma20","ma50","atr14","adr14")
 if not isinstance(m,dict) or any(not _finite(m.get(k)) for k in req) or any(float(m[k])<=0 for k in req):
  return {"status":"COMPLETE","symbol":symbol,"quality":quality,"base_confidence":base_conf,"execution_status":INSUFFICIENT_DATA,
          "reason_codes":["INSUFFICIENT_INTERNAL_EXECUTION_EVIDENCE"],"current_price":None,"entry_area":None,"target_1":None,"target_2":None,
          "risk_boundary":None,"reward_risk":None,"execution_method":"INTERNAL_VOLATILITY","recommendation":None,"ranking":None}
 current=float(m["price"]); ma20=float(m["ma20"]); ma50=float(m["ma50"]); atr=float(m["atr14"]); adr=float(m["adr14"])
 trend=_state(tech,"trend"); momentum=_state(tech,"momentum"); participation=_state(tech,"participation"); rs=_state(tech,"relative_strength"); setup=_state(tech,"setup_entry")
 fresh=(tech.get("data_quality") or {}).get("freshness","UNKNOWN"); contradiction=tech.get("contradiction_severity","NONE")
 refs=[float(x) for x in (m.get("vwap"),ma20,m.get("previous_price"),m.get("low")) if _finite(x) and float(x)>0]
 below=[x for x in refs if x<=current]
 if not below: below=[ma20]
 center=sorted(below)[len(below)//2]
 envelope=min(atr,adr)/2
 low=max(min(below),center-envelope); high=min(current,max(max(below),center+envelope))
 if low>high: low=high=center
 entry={"low":_round_price(low),"high":_round_price(high),"reference":_round_price(center),"basis":"INTERNAL_REFERENCE_ZONE_PLUS_VOLATILITY"}
 risk_refs=[float(x) for x in (m.get("low"),ma20,ma50,m.get("vwap"),m.get("previous_price")) if _finite(x) and 0<float(x)<low]
 risk=max(risk_refs) if risk_refs else center-atr
 if not _finite(risk) or risk<=0 or risk>=center: risk=None
 # Targets are volatility objectives, never labelled historical resistance.
 t1=center+min(atr,adr)
 t2=center+max(atr,adr) if max(atr,adr)>min(atr,adr) else None
 # If today's range has already consumed ADR, do not force an extended target/readiness.
 hi=m.get("high"); lo=m.get("low"); range_used=(float(hi)-float(lo)) if _finite(hi) and _finite(lo) and float(hi)>=float(lo) else None
 range_exhausted=range_used is not None and range_used>=adr
 rr1=_rr(center,risk,t1); rr2=_rr(center,risk,t2)
 reasons=[]
 if sw.get("analytical_status")!="PASS": reasons.append("S3H_SWING_NOT_PASS")
 if fresh!="FRESH": reasons.append("TECHNICAL_DATA_NOT_FRESH")
 if contradiction in {"MATERIAL","SEVERE"}: reasons.append("UNRESOLVED_TECHNICAL_CONTRADICTION")
 if trend!="BULL": reasons.append("TREND_NOT_BULL")
 if risk is None: reasons.append("NO_DEFENSIBLE_RISK_BOUNDARY")
 if rr1 is None: reasons.append("RR_NOT_COMPUTABLE")
 if range_exhausted: reasons.append("CURRENT_RANGE_EXHAUSTED")
 extended=(setup=="EXTENDED") or (current-ma20>2*atr)
 if extended: reasons.append("AVOID_CHASING_EXTENDED_PRICE")
 if any(x in reasons for x in ("S3H_SWING_NOT_PASS","TECHNICAL_DATA_NOT_FRESH","UNRESOLVED_TECHNICAL_CONTRADICTION","TREND_NOT_BULL","NO_DEFENSIBLE_RISK_BOUNDARY","RR_NOT_COMPUTABLE")):
  status=WAIT if trend=="BULL" and risk is not None else INSUFFICIENT_DATA
 elif extended or range_exhausted:
  status=WAIT
 elif rr1<1.5:
  status=NOT_ATTRACTIVE; reasons.append("REWARD_RISK_BELOW_MINIMUM")
 elif participation in {"DISTRIBUTION","WEAK"} or momentum=="FADING" or rs=="DETERIORATING":
  status=WAIT; reasons.append("EXECUTION_CONFIRMATION_WEAK")
 else: status=READY
 return {"status":"COMPLETE","symbol":symbol,"quality":quality,"base_confidence":base_conf,"s3h_analytical_status":sw.get("analytical_status"),
         "execution_status":status,"execution_method":"INTERNAL_VOLATILITY","current_price":_round_price(current),"entry_area":entry,
         "target_1":_round_price(t1),"target_2":_round_price(t2),"risk_boundary":_round_price(risk),"risk_boundary_basis":"VOLATILITY_RISK_BOUNDARY",
         "reward_risk":{"target_1":rr1,"target_2":rr2},"execution_evidence":{"trend":trend,"momentum":momentum,"participation":participation,
         "relative_strength":rs,"setup":setup,"technical_freshness":fresh,"contradiction_severity":contradiction,"range_exhausted":range_exhausted},
         "reason_codes":list(dict.fromkeys(reasons)),"recommendation":None,"ranking":None}

def evaluate_swing(synthesis,dossier,stock):
 if not all(isinstance(x,dict) for x in (synthesis,dossier,stock)):
  return {"status":"INVALID","reason":"INVALID_INPUT","recommendation":None,"ranking":None}
 t=stock.get("technical_enrichment") or {}; hist=t.get("ohlcv") or []
 # Internal evidence is the default production path. External structural OHLCV remains optional future enrichment.
 if isinstance(t.get("internal_market"),dict) and t.get("internal_market"):
  return _internal_plan(synthesis,dossier,stock)
 # Frozen R1 structural behavior is retained when only historical OHLCV is supplied.
 from stage3i_swing_r1_legacy import evaluate_swing as legacy
 return legacy(synthesis,dossier,stock)
