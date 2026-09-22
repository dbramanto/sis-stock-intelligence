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

def _internal_conf(m, fresh):
    required=("price","ma20","ma50","rsi14","macd","adx14","di_plus","di_minus","volume","volume_ma20","atr14","adr14")
    cov=sum(_num(m.get(k)) for k in required)/len(required)
    c="HIGH" if cov>=.85 else ("MODERATE" if cov>=.65 else ("LOW" if cov>=.40 else "INSUFFICIENT"))
    if fresh in {"STALE","UNKNOWN","FUTURE_INVALID"}:
        c={"HIGH":"MODERATE","MODERATE":"LOW","LOW":"INSUFFICIENT","INSUFFICIENT":"INSUFFICIENT"}[c]
    return c,cov


def _evaluate_internal(t, analysis_date):
    m=t.get("internal_market",{})
    meta=t.get("metadata",{}) if isinstance(t.get("metadata",{}),dict) else {}
    if not isinstance(m,dict) or not m:
        return None
    fresh,age=_freshness(meta,analysis_date); conf,cov=_internal_conf(m,fresh)
    dq={"source":meta.get("source","S1_CANONICAL_INTERNAL"),"as_of_date":meta.get("as_of_date"),
        "freshness":fresh,"age_days":age,"coverage":round(cov,4),"mode":"INTERNAL_MARKET_EVIDENCE",
        "structural_enrichment":"UNAVAILABLE_OPTIONAL"}
    price=m.get("price"); ma20=m.get("ma20"); ma50=m.get("ma50"); ma100=m.get("ma100"); ma200=m.get("ma200")
    if not all(_num(x) and x>0 for x in (price,ma20,ma50)):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"INSUFFICIENT_INTERNAL_TREND_EVIDENCE","components":{},"contradictions":[],"data_quality":dq}
    bull=price>ma20>ma50 and (not _num(ma100) or ma50>ma100) and (not _num(ma200) or ma100>ma200 if _num(ma100) else ma50>ma200)
    bear=price<ma20<ma50 and (not _num(ma100) or ma50<ma100)
    trend="BULL" if bull else ("BEAR" if bear else "TRANSITION")

    rsi=m.get("rsi14"); prsi=m.get("previous_rsi14"); macd=m.get("macd"); pmacd=m.get("previous_macd")
    votes=[]
    if _num(rsi) and _num(prsi): votes.append(1 if rsi>prsi else (-1 if rsi<prsi else 0))
    if _num(macd) and _num(pmacd): votes.append(1 if macd>pmacd else (-1 if macd<pmacd else 0))
    if _num(rsi): votes.append(1 if rsi>50 else (-1 if rsi<50 else 0))
    momentum="NOT_EVALUATED" if not votes else ("ACCELERATING" if sum(votes)>=2 else ("FADING" if sum(votes)<=-2 else "STABLE"))

    vol=m.get("volume"); vma=m.get("volume_ma20"); prev=m.get("previous_price")
    rvol=vol/vma if _num(vol) and _num(vma) and vma>0 else None
    price_up=_num(prev) and price>prev
    if rvol is None: participation="NOT_EVALUATED"
    elif rvol>=1.2 and price_up: participation="CONFIRMED"
    elif rvol>=1.2 and not price_up: participation="DISTRIBUTION"
    elif rvol<.8: participation="WEAK"
    else: participation="NEUTRAL"

    rs3,rs6,rs9=(m.get("rs_3m"),m.get("rs_6m"),m.get("rs_9m"))
    if all(_num(x) for x in (rs3,rs6,rs9)):
        rs_state="IMPROVING" if rs3>rs6>rs9 else ("DETERIORATING" if rs3<rs6<rs9 else "NEUTRAL")
    elif _num(rs3) and _num(rs6):
        # Partial trajectory remains usable directional evidence; missing 9M is UNKNOWN, not a negative signal.
        rs_state="IMPROVING" if rs3>rs6 else ("DETERIORATING" if rs3<rs6 else "NEUTRAL")
    else: rs_state="NOT_EVALUATED"

    atr,adr=m.get("atr14"),m.get("adr14")
    atr_pct=atr/price if _num(atr) and atr>=0 else None; adr_pct=adr/price if _num(adr) and adr>=0 else None
    vr=[x for x in (atr_pct,adr_pct) if x is not None]
    volatility="NOT_EVALUATED" if not vr else ("EXTREME" if max(vr)>=.10 else ("HIGH" if max(vr)>=.06 else "NORMAL"))

    # No historical support/resistance is claimed in internal-only mode.
    structure="UNKNOWN"
    vwap=m.get("vwap"); low=m.get("low")
    distance=abs(price-ma20)
    if trend=="BULL" and _num(atr) and atr>0 and price>=ma20 and distance<=atr:
        setup="PULLBACK"
    elif trend=="BULL" and _num(atr) and atr>0 and price-ma20>2*atr:
        setup="EXTENDED"
    else: setup="NONE"
    entry={"PULLBACK":"PULLBACK_CONTEXT","EXTENDED":"AVOID_CHASING_CONTEXT","NONE":"NO_CLEAR_ENTRY_CONTEXT"}[setup]
    inv_candidates=[x for x in (low,ma20,ma50,vwap) if _num(x) and x<price]
    inv=max(inv_candidates) if inv_candidates else None

    contradictions=[]
    if trend=="BULL" and participation in {"WEAK","DISTRIBUTION"}: contradictions.append("BULL_TREND_WITH_WEAK_OR_NEGATIVE_PARTICIPATION")
    if trend=="BULL" and rs_state=="DETERIORATING": contradictions.append("BULL_TREND_WITH_DETERIORATING_RS")
    if _num(m.get("di_plus")) and _num(m.get("di_minus")) and trend=="BULL" and m["di_minus"]>m["di_plus"]: contradictions.append("BULL_TREND_WITH_NEGATIVE_DI_DIRECTION")
    severity="NONE" if not contradictions else ("MATERIAL" if len(contradictions)>=2 else "MINOR")
    comps={
      "trend":result(trend,[f"price={price}",f"ma20={ma20}",f"ma50={ma50}",f"ma100={ma100}",f"ma200={ma200}"],conf),
      "price_structure":result(structure,["historical_structure=UNAVAILABLE_OPTIONAL"],"INSUFFICIENT"),
      "momentum":result(momentum,[f"rsi14={rsi}",f"previous_rsi14={prsi}",f"macd={macd}",f"previous_macd={pmacd}"],conf),
      "participation":result(participation,[f"rvol={rvol}"],conf),
      "relative_strength":result(rs_state,[f"rs_3m={rs3}",f"rs_6m={rs6}",f"rs_9m={rs9}"],conf),
      "volatility":result(volatility,[f"atr_pct={atr_pct}",f"adr_pct={adr_pct}"],conf),
      "setup_entry":result(setup,[f"price={price}",f"ma20={ma20}",f"atr14={atr}"],conf,entry_context=entry,method="INTERNAL_VOLATILITY"),
      "invalidation":result("VOLATILITY_REFERENCE" if inv is not None else NOT_EVALUATED,["not_historical_structural_stop"],conf if inv is not None else "INSUFFICIENT",level=inv)
    }
    return {"domain":DOMAIN,"state":trend,"confidence":conf,"components":comps,"contradictions":contradictions,
            "contradiction_severity":severity,"data_quality":dq,"recommendation":None,"ranking":None}

def evaluate_technical(s, analysis_date="2026-09-17"):
    t=s.get("technical_enrichment",{})
    if not isinstance(t,dict):
        return {"domain":DOMAIN,"state":NOT_EVALUATED,"confidence":"INSUFFICIENT","reason":"INVALID_TECHNICAL_PAYLOAD","components":{},"contradictions":[]}
    hist=t.get("ohlcv",[])
    # Historical OHLCV is optional enrichment. Internal canonical market evidence is the default path.
    if not isinstance(hist,list) or len(hist)<60 or any(not _valid_bar(x) for x in hist):
        internal=_evaluate_internal(t,analysis_date)
        if internal is not None:
            return internal
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
