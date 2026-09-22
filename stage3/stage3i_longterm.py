from __future__ import annotations
from math import isfinite

VERSION="S3I-LT-R1"
UNKNOWN="UNKNOWN"
OUTLOOKS={"POSITIVE","STABLE","CAUTIOUS","NEGATIVE","INSUFFICIENT"}

FWD_GROWTH=("expected_revenue_growth_yoy","expected_revenue_growth_2y_cagr")
FWD_EARNINGS=("expected_op_profit_growth_yoy","expected_op_profit_growth_2y_cagr",
              "expected_net_income_growth_yoy","expected_net_income_growth_2y_cagr",
              "expected_eps_growth_yoy","expected_eps_growth_2y_cagr")
FWD_VAL=("eps_forward","peg_forward")

def _finite(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(float(v))

def _num(fwd,k):
    v=(fwd or {}).get(k)
    return float(v) if _finite(v) else None

def _pair(yoy,cagr):
    if yoy is None and cagr is None:return "INSUFFICIENT"
    if yoy is None or cagr is None:return "DIRECTION_ONLY"
    if yoy>=0 and cagr>=0:return "SUSTAINED_GROWTH"
    if yoy>=0 and cagr<0:return "SHORT_TERM_REBOUND"
    if yoy<0 and cagr>=0:return "NEAR_TERM_WEAKNESS_MEDIUM_TERM_RECOVERY"
    return "FORWARD_DETERIORATION"

def _sign(v, pos=0.0):
    if v is None:return None
    return 1 if v>pos else (-1 if v<pos else 0)

def _forward_consistency(fwd):
    rev1=_num(fwd,"expected_revenue_growth_yoy"); rev2=_num(fwd,"expected_revenue_growth_2y_cagr")
    op1=_num(fwd,"expected_op_profit_growth_yoy"); op2=_num(fwd,"expected_op_profit_growth_2y_cagr")
    ni1=_num(fwd,"expected_net_income_growth_yoy"); ni2=_num(fwd,"expected_net_income_growth_2y_cagr")
    ep1=_num(fwd,"expected_eps_growth_yoy"); ep2=_num(fwd,"expected_eps_growth_2y_cagr")
    vals=[rev1,op1,ni1,ep1]
    known=[x for x in vals if x is not None]
    if not known:return "INSUFFICIENT"
    pos=sum(x>0 for x in known); neg=sum(x<0 for x in known)
    if len(known)>=3 and pos==len(known): state="BROAD_IMPROVEMENT"
    elif len(known)>=3 and neg==len(known): state="DETERIORATING"
    elif pos and neg: state="MIXED"
    else: state="STABLE"
    pairs=[_pair(rev1,rev2),_pair(op1,op2),_pair(ni1,ni2),_pair(ep1,ep2)]
    if state=="MIXED" and any(x=="SHORT_TERM_REBOUND" for x in pairs): state="REBOUND"
    return state

def _plausibility(fwd):
    vals={k:_num(fwd,k) for k in FWD_GROWTH+FWD_EARNINGS}
    known={k:v for k,v in vals.items() if v is not None}
    if not known:return {"state":"UNVERIFIED","reason_codes":["NO_FORWARD_GROWTH_EARNINGS"]}
    extreme=[k for k,v in known.items() if abs(v)>=300]
    rev=_num(fwd,"expected_revenue_growth_yoy")
    op=_num(fwd,"expected_op_profit_growth_yoy")
    ni=_num(fwd,"expected_net_income_growth_yoy")
    eps=_num(fwd,"expected_eps_growth_yoy")
    divergence=[]
    if eps is not None and eps>=100 and (rev is None or rev<20) and (op is None or op<20):
        divergence.append("EPS_SPIKE_WITHOUT_OPERATING_SUPPORT")
    if ni is not None and ni>=100 and (rev is None or rev<20) and (op is None or op<20):
        divergence.append("NET_INCOME_SPIKE_WITHOUT_OPERATING_SUPPORT")
    if extreme or divergence:
        return {"state":"QUESTIONABLE","reason_codes":
                [*(["EXTREME_FORWARD_VALUE"] if extreme else []),*divergence],
                "extreme_fields":extreme}
    return {"state":"PLAUSIBLE","reason_codes":[]}

def _ledger_state(syn,name):
    try:return syn["shared"]["evidence_ledger"][name]["state"]
    except Exception:return "UNKNOWN"

def _support(state):
    if state=="POSITIVE_STRONG":return 2
    if state=="POSITIVE_MODERATE":return 1
    if state=="NEGATIVE_MODERATE":return -1
    if state=="NEGATIVE_STRONG":return -2
    return 0

def _forward_score(fwd):
    vals=[_num(fwd,k) for k in FWD_GROWTH+FWD_EARNINGS]
    vals=[v for v in vals if v is not None]
    if not vals:return None
    # Directional only. Magnitudes are deliberately not extrapolated.
    signs=[1 if v>0 else (-1 if v<0 else 0) for v in vals]
    return sum(signs)/len(signs)

def _confidence(base, coverage, plausibility, consistency, structural_coverage, horizon):
    # Evidence-driven horizon decay: less forward evidence is usable as horizon lengthens.
    rel={"PLAUSIBLE":1.0,"QUESTIONABLE":0.70,"UNVERIFIED":0.55}[plausibility]
    cons={"BROAD_IMPROVEMENT":1.0,"STABLE":0.90,"REBOUND":0.82,"MIXED":0.72,
          "DETERIORATING":0.90,"INSUFFICIENT":0.55}.get(consistency,0.70)
    if horizon=="1Y": evid=.55*coverage+.25*rel+.20*cons
    elif horizon=="3Y": evid=.30*coverage+.25*rel+.20*cons+.25*structural_coverage
    else: evid=.10*coverage+.15*rel+.15*cons+.60*structural_coverage
    return max(0,min(100,round(.55*base+.45*(100*evid))))

def _outlook(score, confidence):
    if confidence<45:return "INSUFFICIENT"
    if score>=2:return "POSITIVE"
    if score>=0.5:return "STABLE"
    if score>-1.5:return "CAUTIOUS"
    return "NEGATIVE"

def evaluate_longterm(synthesis, dossier, forward_enrichment):
    if not isinstance(synthesis,dict) or not isinstance(dossier,dict) or not isinstance(forward_enrichment,dict):
        return {"status":"INVALID","reason":"INVALID_INPUT","recommendation":None,"ranking":None}
    lt=synthesis.get("long_term") or {}
    quality=lt.get("quality"); base_conf=lt.get("confidence",0)
    if quality is not None and not _finite(quality):
        return {"status":"INVALID","reason":"INVALID_S3H_QUALITY","recommendation":None,"ranking":None}
    if not _finite(base_conf): base_conf=0
    base_conf=float(base_conf)

    fwd={k:forward_enrichment.get(k) for k in FWD_GROWTH+FWD_EARNINGS+FWD_VAL if k in forward_enrichment}
    known=sum(_num(fwd,k) is not None for k in FWD_GROWTH+FWD_EARNINGS)
    coverage=known/len(FWD_GROWTH+FWD_EARNINGS)
    consistency=_forward_consistency(fwd)
    plaus=_plausibility(fwd)
    fscore=_forward_score(fwd)

    structural_names=("PROFITABILITY","CASH_QUALITY","FINANCIAL_STRENGTH","BUSINESS_SECTOR","RISK")
    structural=[_ledger_state(synthesis,x) for x in structural_names]
    structural_known=sum(x!="UNKNOWN" for x in structural)/len(structural)
    structural_score=sum(_support(x) for x in structural)

    catalyst=_support(_ledger_state(synthesis,"CATALYST"))
    valuation=_support(_ledger_state(synthesis,"VALUATION"))
    risk=_support(_ledger_state(synthesis,"RISK"))

    # 1Y emphasizes forward expectations + current catalyst/sector/risk.
    if fscore is None: score1=0.5*structural_score + catalyst + risk
    else: score1=2.2*fscore + .35*structural_score + catalyst + risk
    # 3Y blends forward persistence with durable current quality.
    score3=(1.1*(fscore or 0)) + .9*structural_score + .25*valuation
    # 5Y explicitly does not use B11 numeric growth magnitudes.
    score5=1.2*structural_score + .20*valuation

    c1=_confidence(base_conf,coverage,plaus["state"],consistency,structural_known,"1Y")
    c3=_confidence(base_conf,coverage,plaus["state"],consistency,structural_known,"3Y")
    c5=_confidence(base_conf,coverage,plaus["state"],consistency,structural_known,"5Y")

    o1="INSUFFICIENT" if known==0 else _outlook(score1,c1)
    o3=_outlook(score3,c3) if structural_known>=.4 else "INSUFFICIENT"
    o5=_outlook(score5,c5) if structural_known>=.6 else "INSUFFICIENT"

    drivers=[]; risks=[]
    if consistency=="BROAD_IMPROVEMENT":drivers.append("BROAD_BASED_FORWARD_IMPROVEMENT")
    if consistency=="REBOUND":drivers.append("FORWARD_REBOUND")
    if structural_score>=4:drivers.append("STRUCTURAL_QUALITY_SUPPORT")
    if _ledger_state(synthesis,"BUSINESS_SECTOR") in {"POSITIVE_STRONG","POSITIVE_MODERATE"}:drivers.append("SECTOR_SUPPORT")
    if consistency=="DETERIORATING":risks.append("FORWARD_DETERIORATION")
    if consistency=="MIXED":risks.append("MIXED_FORWARD_SIGNALS")
    if plaus["state"]!="PLAUSIBLE":risks.extend(plaus["reason_codes"])
    if risk<0:risks.append("ELEVATED_RISK_CONTEXT")
    if valuation<0:risks.append("VALUATION_PRESSURE")

    # DCA is context, never a new quality score.
    if quality is None:dca="CAUTIOUS"
    elif quality>=75 and o3 in {"POSITIVE","STABLE"} and valuation>=0 and plaus["state"]=="PLAUSIBLE":dca="FAVORABLE"
    elif valuation<0 or o3 in {"CAUTIOUS","NEGATIVE","INSUFFICIENT"} or plaus["state"]!="PLAUSIBLE":dca="CAUTIOUS"
    else:dca="NORMAL"

    return {
      "status":"COMPLETE","symbol":synthesis.get("symbol") or dossier.get("symbol"),
      "quality":quality,"base_confidence":lt.get("confidence"),
      "s3h_analytical_status":lt.get("analytical_status"),
      "forward_evidence":{
        "growth":{"revenue_pattern":_pair(_num(fwd,"expected_revenue_growth_yoy"),_num(fwd,"expected_revenue_growth_2y_cagr"))},
        "earnings":{
          "operating_profit_pattern":_pair(_num(fwd,"expected_op_profit_growth_yoy"),_num(fwd,"expected_op_profit_growth_2y_cagr")),
          "net_income_pattern":_pair(_num(fwd,"expected_net_income_growth_yoy"),_num(fwd,"expected_net_income_growth_2y_cagr")),
          "eps_pattern":_pair(_num(fwd,"expected_eps_growth_yoy"),_num(fwd,"expected_eps_growth_2y_cagr"))},
        "valuation_context":{"eps_forward":_num(fwd,"eps_forward"),"peg_forward":_num(fwd,"peg_forward")},
        "consistency":consistency,"coverage":round(coverage,4)},
      "plausibility":plaus,
      "outlook":{
        "1Y":{"state":o1,"confidence":c1},
        "3Y":{"state":o3,"confidence":c3},
        "5Y":{"state":o5,"confidence":c5,"basis":"STRUCTURAL_NOT_B11_EXTRAPOLATION"}},
      "forward_drivers":drivers,"forward_risks":list(dict.fromkeys(risks)),
      "dca_context":dca,
      "recommendation":None,"ranking":None
    }
