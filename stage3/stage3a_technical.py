from datetime import date
import math
from stage3_common import result, NOT_EVALUATED, missing

DOMAIN="3A_TECHNICAL"

def _num(v):
    return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)

def _valid_bar(x):
    if not isinstance(x,dict): return False
    req=("open","high","low","close","volume")
    if any(k not in x or missing(x[k]) or not _num(x[k]) for k in req): return False
    o,h,l,c,v=(x[k] for k in req)
    return c>0 and v>=0 and h>=l and l<=o<=h and l<=c<=h

def _conf(n, fresh):
    c="HIGH" if n>=250 else ("MODERATE" if n>=120 else "LOW")
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT"}[c]
    return c

def _freshness(meta, analysis_date):
    raw=meta.get("as_of_date") if isinstance(meta,dict) else None
    if not raw:return "UNKNOWN",None
    try:
        d=date.fromisoformat(str(raw)); a=date.fromisoformat(str(analysis_date))
        age=(a-d).days
        if age<0:return "FUTURE_INVALID",age
        return ("FRESH" if age<=7 else "STALE"),age
    except Exception:return "UNKNOWN",None

def evaluate_technical(s, analysis_date="2026-09-17"):
    t=s.get("technical_enrichment",{})
    if not isinstance(t,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"INVALID_TECHNICAL_PAYLOAD","components":{},"contradictions":[]}
    hist=t.get("ohlcv",[])
    meta=t.get("metadata",{}) if isinstance(t.get("metadata",{}),dict) else {}
    source=meta.get("source",t.get("source","UNKNOWN"))
    fresh,age=_freshness(meta,analysis_date)
    dq={"source":source,"as_of_date":meta.get("as_of_date"),"freshness":fresh,"age_days":age,"coverage_bars":len(hist) if isinstance(hist,list) else 0}
    if not isinstance(hist,list) or len(hist)<60 or any(not _valid_bar(x) for x in hist):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"INSUFFICIENT_OR_MALFORMED_OHLCV","components":{},"contradictions":[],"data_quality":dq}
    # Date integrity if dates are supplied.
    dates=[x.get("date") for x in hist if "date" in x]
    if dates:
        try:
            parsed_dates=[date.fromisoformat(str(d)) for d in dates]
            date_integrity_ok=(
                len(dates)==len(hist)
                and len(set(parsed_dates))==len(parsed_dates)
                and parsed_dates==sorted(parsed_dates)
            )
        except (TypeError, ValueError):
            date_integrity_ok=False
        if not date_integrity_ok:
            return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"OHLCV_DATE_INTEGRITY_FAIL","components":{},"contradictions":[],"data_quality":dq}

    closes=[x["close"] for x in hist]; highs=[x["high"] for x in hist]; lows=[x["low"] for x in hist]; vols=[x["volume"] for x in hist]
    c=closes[-1]; n=len(hist); conf=_conf(n,fresh)
    ma20=sum(closes[-20:])/20; ma50=sum(closes[-50:])/50
    ma200=sum(closes[-200:])/200 if n>=200 else None
    prev20=sum(closes[-40:-20])/20
    trend="BULL" if c>ma20>ma50 and (ma200 is None or ma50>ma200) else ("BEAR" if c<ma20<ma50 and (ma200 is None or ma50<ma200) else "TRANSITION")

    # A2 Price structure: recent swing behavior.
    hi20=max(highs[-20:]); lo20=min(lows[-20:]); prev_hi=max(highs[-40:-20]); prev_lo=min(lows[-40:-20])
    if hi20>prev_hi and lo20>=prev_lo: structure="INTACT"
    elif hi20<prev_hi and lo20<prev_lo: structure="BROKEN"
    elif (hi20-prev_hi)/c < .03 and abs(lo20-prev_lo)/c < .03: structure="BASE"
    else: structure="WEAKENING"

    # A3 Momentum: explicit and independent state.
    sf=s.get("stage2",{}).get("source_features",{})
    rsi_d=sf.get("rsi_delta"); macd_d=sf.get("macd_delta")
    ret5=(c/closes[-6]-1) if n>=6 else None
    votes=[]
    for v in (rsi_d,macd_d,ret5):
        if _num(v): votes.append(1 if v>0 else (-1 if v<0 else 0))
    momentum="NOT_EVALUATED" if not votes else ("ACCELERATING" if sum(votes)>=2 else ("FADING" if sum(votes)<=-2 else "STABLE"))

    # A4 Participation.
    avgv=sum(vols[-20:])/20; rvol=vols[-1]/avgv if avgv>0 else None
    price_up=c>closes[-2]
    if rvol is None: participation="NOT_EVALUATED"
    elif rvol>=1.2 and price_up: participation="CONFIRMED"
    elif rvol>=1.2 and not price_up: participation="DISTRIBUTION"
    elif rvol<.8: participation="WEAK"
    else: participation="NEUTRAL"

    # A5 Relative strength.
    rs=sf.get("rs_trajectory","INSUFFICIENT")
    rs_state={"ACCELERATING":"IMPROVING","PERSISTENT LEADER":"LEADER","DETERIORATING":"DETERIORATING","MIXED":"NEUTRAL"}.get(rs,"NOT_EVALUATED")

    # A6 Volatility: recent true-range proxy vs preceding period.
    tr=[(hist[i]["high"]-hist[i]["low"])/hist[i]["close"] for i in range(n)]
    cur=sum(tr[-10:])/10; prev=sum(tr[-30:-10])/20 if n>=30 else cur
    ratio=cur/prev if prev>0 else None
    volatility="NOT_EVALUATED" if ratio is None else ("EXPANDING" if ratio>=1.35 else ("CONTRACTING" if ratio<=.70 else ("EXTREME" if cur>=.10 else "NORMAL")))

    # A7 Setup/entry context derived from prior evidence.
    resistance=max(highs[-60:-1]); support=min(lows[-20:]); dist_res=(resistance-c)/c
    if trend=="BULL" and c>resistance and participation=="CONFIRMED": setup="BREAKOUT"
    elif trend=="BULL" and abs(c-ma20)/c<=.03 and structure!="BROKEN": setup="PULLBACK"
    elif structure=="BASE": setup="BASE"
    elif trend=="BULL" and c>ma20*1.12: setup="EXTENDED"
    else: setup="NONE"
    entry={"BREAKOUT":"CONFIRMED_BREAKOUT_CONTEXT","PULLBACK":"PULLBACK_CONTEXT","BASE":"WAIT_FOR_BREAK","EXTENDED":"AVOID_CHASING_CONTEXT","NONE":"NO_CLEAR_ENTRY_CONTEXT"}[setup]

    # A8 structural invalidation, not generic ATR stop.
    invalid_level=support if trend!="BEAR" else max(highs[-20:])
    invalid_reason="break below recent structural support" if trend!="BEAR" else "break above recent structural resistance"

    contradictions=[]
    if trend=="BULL" and participation in {"WEAK","DISTRIBUTION"}: contradictions.append("BULL_TREND_WITH_WEAK_OR_NEGATIVE_PARTICIPATION")
    if trend=="BULL" and rs_state=="DETERIORATING": contradictions.append("BULL_TREND_WITH_DETERIORATING_RS")
    if momentum=="ACCELERATING" and structure=="BROKEN": contradictions.append("MOMENTUM_ACCELERATING_BUT_STRUCTURE_BROKEN")
    severity="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")

    comps={
      "trend":result(trend,[f"close={c:.4f}",f"ma20={ma20:.4f}",f"ma50={ma50:.4f}",f"ma20_slope={'RISING' if ma20>prev20 else 'FALLING'}"],conf),
      "price_structure":result(structure,[f"recent_high={hi20:.4f}",f"recent_low={lo20:.4f}"],conf),
      "momentum":result(momentum,[f"rsi_delta={rsi_d}",f"macd_delta={macd_d}",f"return_5d={ret5:.6f}"],conf),
      "participation":result(participation,[f"rvol={rvol:.4f}" if rvol is not None else "rvol=NA"],conf),
      "relative_strength":result(rs_state,[f"rs_trajectory={rs}"],conf),
      "volatility":result(volatility,[f"range_ratio={ratio:.4f}" if ratio is not None else "range_ratio=NA"],conf),
      "setup_entry":result(setup,[f"resistance={resistance:.4f}",f"distance_to_resistance={dist_res:.6f}"],conf,entry_context=entry),
      "invalidation":result("STRUCTURAL",[invalid_reason],conf,level=invalid_level)
    }
    return {"domain":DOMAIN,"state":trend,"confidence":conf,"components":comps,
            "contradictions":contradictions,"contradiction_severity":severity,"data_quality":dq,
            "recommendation":None,"ranking":None}
