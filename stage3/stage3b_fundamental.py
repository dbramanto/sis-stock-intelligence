from datetime import date
import math
from stage3_common import result, NOT_EVALUATED, missing

DOMAIN="3B_FUNDAMENTAL"
NUMERIC_FIELDS=("npm","roic","eps_growth","revenue_growth","debt_equity","fscore",
                "asset_turnover","gross_margin","gross_margin_3y_avg","roic_3y_avg",
                "share_count_growth","dividend_payout","reinvestment_rate")

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

def _coverage(e,fields):
    have=sum(1 for f in fields if _num(e.get(f)))
    return have/len(fields) if fields else 0

def _confidence(cov,fresh):
    c="HIGH" if cov>=.80 else ("MODERATE" if cov>=.55 else ("LOW" if cov>=.30 else "INSUFFICIENT"))
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT","INSUFFICIENT":"INSUFFICIENT"}[c]
    return c

def _state(score,valid):
    if not valid:return NOT_EVALUATED
    return "STRONG" if score>=2 else ("WEAK" if score<=-2 else "MIXED")

def _context_value(v):
    return isinstance(v,str) and bool(v.strip()) and v.strip().upper()!="UNKNOWN"

def evaluate_fundamental(s,analysis_date="2026-09-17"):
    e=s.get("fundamental_enrichment",{})
    if not isinstance(e,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"INVALID_FUNDAMENTAL_PAYLOAD","components":{},"contradictions":[]}

    meta=e.get("metadata",{}) if isinstance(e.get("metadata",{}),dict) else {}
    fresh,age=_fresh(meta,analysis_date)
    source=meta.get("source",e.get("source","UNKNOWN"))
    present={k:v for k,v in e.items() if k in NUMERIC_FIELDS and v is not None}
    invalid=[k for k,v in present.items() if not _num(v)]
    dq={"source":source,"as_of_date":meta.get("as_of_date"),"freshness":fresh,"age_days":age,
        "coverage":round(_coverage(e,NUMERIC_FIELDS),4),"invalid_fields":invalid}
    if invalid:
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"NONNUMERIC_FUNDAMENTAL_FIELD","components":{},"contradictions":[],"data_quality":dq}

    def val(k): return e.get(k) if _num(e.get(k)) else None

    npm,roic=val("npm"),val("roic")
    pscore=sum([1 if npm is not None and npm>=10 else (-1 if npm is not None and npm<0 else 0),
                1 if roic is not None and roic>=12 else (-1 if roic is not None and roic<5 else 0)])
    profitability=_state(pscore,[x for x in (npm,roic) if x is not None])

    eps,rev=val("eps_growth"),val("revenue_growth")
    gscore=sum(1 if x is not None and x>=10 else (-1 if x is not None and x<0 else 0) for x in (eps,rev))
    growth=_state(gscore,[x for x in (eps,rev) if x is not None])

    ato=val("asset_turnover"); gm=val("gross_margin")
    escore=sum([1 if ato is not None and ato>=1 else (-1 if ato is not None and ato<.4 else 0),
                1 if gm is not None and gm>=20 else (-1 if gm is not None and gm<5 else 0)])
    efficiency=_state(escore,[x for x in (ato,gm) if x is not None])

    de,fs=val("debt_equity"),val("fscore")
    bscore=sum([1 if de is not None and de<=1 else (-1 if de is not None and de>2 else 0),
                1 if fs is not None and fs>=7 else (-1 if fs is not None and fs<=3 else 0)])
    financial_strength=_state(bscore,[x for x in (de,fs) if x is not None])

    gm3,roic3=val("gross_margin_3y_avg"),val("roic_3y_avg")
    qvotes=[]
    if gm is not None and gm3 is not None:qvotes.append(1 if gm>=gm3*.90 else -1)
    if roic is not None and roic3 is not None:qvotes.append(1 if roic>=roic3*.85 else -1)
    earnings_quality=_state(sum(qvotes),qvotes)

    dvotes=[]
    if gm is not None and gm3 is not None: dvotes.append(1 if abs(gm-gm3)<=max(5,abs(gm3)*.25) else -1)
    if roic is not None and roic3 is not None: dvotes.append(1 if roic3>=8 else -1)
    durability=_state(sum(dvotes),dvotes)

    scg,rr,dp=val("share_count_growth"),val("reinvestment_rate"),val("dividend_payout")
    avotes=[]
    if scg is not None: avotes.append(1 if scg<=1 else (-1 if scg>5 else 0))
    if rr is not None: avotes.append(1 if 0<=rr<=100 else -1)
    if dp is not None: avotes.append(1 if 0<=dp<=80 else (-1 if dp>120 else 0))
    capital_allocation=_state(sum(avotes),avotes)

    bc=e.get("business_context",{})
    if isinstance(bc,dict) and bc:
        raw=(bc.get("competitive_position"),bc.get("business_model"),bc.get("cyclicality"))
        valid=[_context_value(x) for x in raw]
        moat=raw[0].strip() if valid[0] else "UNKNOWN"
        model=raw[1].strip() if valid[1] else "UNKNOWN"
        cyc=raw[2].strip() if valid[2] else "UNKNOWN"
        if all(valid):
            context_state="DOCUMENTED"; context_conf="HIGH"
        elif any(valid):
            context_state="DOCUMENTED"; context_conf="MODERATE"
        else:
            context_state=NOT_EVALUATED; context_conf="INSUFFICIENT"
    else:
        moat=model=cyc="UNKNOWN"; context_state=NOT_EVALUATED; context_conf="INSUFFICIENT"

    components={
      "profitability":result(profitability,[f"npm={npm}",f"roic={roic}"],"MODERATE"),
      "growth":result(growth,[f"eps_growth={eps}",f"revenue_growth={rev}"],"MODERATE"),
      "efficiency":result(efficiency,[f"asset_turnover={ato}",f"gross_margin={gm}"],"MODERATE"),
      "financial_strength":result(financial_strength,[f"debt_equity={de}",f"fscore={fs}"],"MODERATE"),
      "earnings_quality":result(earnings_quality,[f"gross_margin_3y_avg={gm3}",f"roic_3y_avg={roic3}"],"MODERATE"),
      "durability":result(durability,[f"gross_margin={gm}",f"gross_margin_3y_avg={gm3}",f"roic_3y_avg={roic3}"],"MODERATE"),
      "capital_allocation":result(capital_allocation,[f"share_count_growth={scg}",f"reinvestment_rate={rr}",f"dividend_payout={dp}"],"MODERATE"),
      "business_context":result(context_state,[f"competitive_position={moat}",f"business_model={model}",f"cyclicality={cyc}"],context_conf)
    }
    evaluated=[v["state"] for v in components.values() if v["state"] not in {NOT_EVALUATED,"DOCUMENTED"}]
    strong=evaluated.count("STRONG"); weak=evaluated.count("WEAK")
    overall="STRONG" if evaluated and strong>=4 and weak==0 else ("WEAK" if evaluated and weak>=3 else ("MIXED" if evaluated else NOT_EVALUATED))
    conf=_confidence(dq["coverage"],fresh)
    contradictions=[]
    if profitability=="STRONG" and growth=="WEAK": contradictions.append("STRONG_PROFITABILITY_WITH_WEAK_GROWTH")
    if growth=="STRONG" and capital_allocation=="WEAK": contradictions.append("STRONG_GROWTH_WITH_WEAK_CAPITAL_ALLOCATION")
    if profitability=="STRONG" and durability=="WEAK": contradictions.append("CURRENT_PROFITABILITY_WITH_WEAK_DURABILITY")
    sev="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")
    return {"domain":DOMAIN,"state":overall,"confidence":conf,"components":components,
            "contradictions":contradictions,"contradiction_severity":sev,"data_quality":dq,
            "recommendation":None,"ranking":None}
