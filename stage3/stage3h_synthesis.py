from __future__ import annotations

NOT_EVALUATED = "NOT_EVALUATED"
CONF_NUM = {"INSUFFICIENT": 0.20, "LOW": 0.45, "MODERATE": 0.70, "HIGH": 0.95}

POS_STRONG = "POSITIVE_STRONG"
POS_MOD = "POSITIVE_MODERATE"
NEUTRAL = "NEUTRAL"
NEG_MOD = "NEGATIVE_MODERATE"
NEG_STRONG = "NEGATIVE_STRONG"
UNKNOWN = "UNKNOWN"

def _domain(dossier, name):
    x=(dossier.get("domains") or {}).get(name,{})
    return x if isinstance(x,dict) else {}

def _component(domain, name):
    x=(domain.get("components") or {}).get(name,{})
    return x if isinstance(x,dict) else {}

def _state(domain, component=None):
    x=_component(domain,component) if component else domain
    return x.get("state",NOT_EVALUATED)

def _conf(domain, component=None):
    x=_component(domain,component) if component else domain
    return CONF_NUM.get(x.get("confidence","INSUFFICIENT"),0.20)

def _family(state, confidence, sources):
    return {"state":state,"confidence":round(float(confidence),4),"sources":list(sources)}

def _map_positive(s, strong, moderate=(), negative=(), severe=()):
    if s in strong:return POS_STRONG
    if s in moderate:return POS_MOD
    if s in severe:return NEG_STRONG
    if s in negative:return NEG_MOD
    if s in {NOT_EVALUATED,None,"UNKNOWN"}:return UNKNOWN
    return NEUTRAL

def _ledger(d):
    t=_domain(d,"technical"); b=_domain(d,"business"); c=_domain(d,"cash_flow")
    v=_domain(d,"valuation"); s=_domain(d,"sector"); k=_domain(d,"catalyst"); r=_domain(d,"risk")

    trend=_map_positive(_state(t,"trend"),{"BULL"},{"TRANSITION"},{"BEAR"})
    mom_states=[_state(t,x) for x in ("momentum","participation")]
    if any(x=="DISTRIBUTION" for x in mom_states): mom=NEG_STRONG
    elif any(x in {"FADING","WEAK"} for x in mom_states): mom=NEG_MOD
    elif all(x in {"ACCELERATING","CONFIRMED"} for x in mom_states): mom=POS_STRONG
    elif any(x in {"ACCELERATING","CONFIRMED"} for x in mom_states): mom=POS_MOD
    elif all(x in {NOT_EVALUATED,"UNKNOWN"} for x in mom_states): mom=UNKNOWN
    else:mom=NEUTRAL

    rs=_map_positive(_state(t,"relative_strength"),{"LEADER"},{"IMPROVING"},{"DETERIORATING"})
    profit=_map_positive(_state(b,"profitability"),{"STRONG"},{"MIXED"},{"WEAK"})
    fs=_map_positive(_state(b,"financial_strength"),{"STRONG"},{"MIXED"},{"WEAK"})

    cash_states=[_state(c,x) for x in ("ocf_quality","fcf_quality","cash_conversion","fcf_sustainability","cash_trend_consistency","cash_stress")]
    cash_bad=sum(x in {"WEAK","SUSTAINED_NEGATIVE","DETERIORATING","HIGH"} for x in cash_states)
    cash_good=sum(x in {"STRONG","SUSTAINED_POSITIVE","IMPROVING","LOW","DIVERGENT_POSITIVE_CASH"} for x in cash_states)
    if not any(x not in {NOT_EVALUATED,"UNKNOWN"} for x in cash_states): cash=UNKNOWN
    elif cash_bad>=3:cash=NEG_STRONG
    elif cash_bad>=1:cash=NEG_MOD
    elif cash_good>=4:cash=POS_STRONG
    elif cash_good>=2:cash=POS_MOD
    else:cash=NEUTRAL

    val_state=_state(v)
    valuation=_map_positive(val_state,{"CHEAP"},{"MIXED_OR_FAIR"},{"EXPENSIVE"})
    sector=_map_positive(_state(s),{"TAILWIND"},{"MIXED"},{"HEADWIND"})
    catalyst=_map_positive(_state(k),{"POSITIVE"},{"BALANCED_OR_WEAK","MIXED"},{"NEGATIVE"})

    risk_state=_state(r)
    risk = NEG_STRONG if risk_state=="HIGH" else (NEG_MOD if risk_state=="MODERATE" else (POS_MOD if risk_state=="LOW" else UNKNOWN))

    return {
      "PROFITABILITY":_family(profit,_conf(b,"profitability"),["business.profitability"]),
      "CASH_QUALITY":_family(cash,_conf(c),["cash_flow"]),
      "FINANCIAL_STRENGTH":_family(fs,_conf(b,"financial_strength"),["business.financial_strength"]),
      "PRICE_TREND":_family(trend,_conf(t,"trend"),["technical.trend"]),
      "MOMENTUM_PARTICIPATION":_family(mom,min(_conf(t,"momentum"),_conf(t,"participation")),["technical.momentum","technical.participation"]),
      "RELATIVE_STRENGTH":_family(rs,_conf(t,"relative_strength"),["technical.relative_strength"]),
      "VALUATION":_family(valuation,_conf(v),["valuation"]),
      "BUSINESS_SECTOR":_family(sector,_conf(s),["sector"]),
      "CATALYST":_family(catalyst,_conf(k),["catalyst"]),
      "RISK":_family(risk,_conf(r),["risk"])
    }

def _quality(fams, core, context):
    score_map={POS_STRONG:95,POS_MOD:82,NEUTRAL:70,NEG_MOD:55,NEG_STRONG:35}
    core_vals=[score_map[fams[x]["state"]] for x in core if fams[x]["state"]!=UNKNOWN]
    ctx_vals=[score_map[fams[x]["state"]] for x in context if fams[x]["state"]!=UNKNOWN]
    if not core_vals:return None
    core_score=sum(core_vals)/len(core_vals)
    ctx_score=sum(ctx_vals)/len(ctx_vals) if ctx_vals else core_score
    risk=fams["RISK"]["state"]
    risk_adj={POS_MOD:2,NEUTRAL:0,NEG_MOD:-5,NEG_STRONG:-10,UNKNOWN:0}.get(risk,0)
    return max(0,min(100,round(.85*core_score+.15*ctx_score+risk_adj)))

def _confidence(fams, core, context):
    names=list(core)+list(context)+["RISK"]
    vals=[fams[x]["confidence"] for x in names if fams[x]["state"]!=UNKNOWN]
    coverage=sum(fams[x]["state"]!=UNKNOWN for x in core)/len(core)
    if not vals:return 0
    return round(100*(sum(vals)/len(vals))*coverage)

def _contradiction(d):
    cross=list(d.get("cross_engine_contradictions") or [])
    severe=False; material=False
    for dom in (d.get("domains") or {}).values():
        if not isinstance(dom,dict):continue
        sev=dom.get("contradiction_severity","NONE")
        if sev=="SEVERE":severe=True
        elif sev=="MATERIAL":material=True
    if severe:return "SEVERE"
    if material or len(cross)>=2:return "MATERIAL"
    if cross:return "WATCH"
    return "NONE"

def _horizon(fams, core, context, d):
    q=_quality(fams,core,context)
    conf=_confidence(fams,core,context)
    positive=sum(fams[x]["state"] in {POS_STRONG,POS_MOD} for x in core)
    unknown=sum(fams[x]["state"]==UNKNOWN for x in core)
    negstrong=sum(fams[x]["state"]==NEG_STRONG for x in core)
    breadth_required=2 if len(core)==3 else 3
    breadth=positive>=breadth_required and negstrong==0
    contradiction=_contradiction(d)
    dq=d.get("data_quality") or {}
    failures=list(dq.get("failed_domains") or [])
    stale=list(dq.get("stale_or_future_domains") or [])
    review_protected=bool(d.get("review_protected"))
    data_invalid=bool(failures)
    if q is None:
        status="REVIEW"
    elif review_protected or data_invalid or unknown>0 or not breadth or contradiction in {"MATERIAL","SEVERE"} or conf<80:
        status="REVIEW"
    elif q>=75:
        status="PASS"
    elif q<65 and conf>=80:
        status="LOW_QUALITY"
    else:
        status="REVIEW"
    return {
      "quality":q,"confidence":conf,
      "core_coverage":{"positive":positive,"required":breadth_required,"unknown":unknown,"negative_strong":negstrong,"pass":breadth},
      "contradiction_status":contradiction,"analytical_status":status,
      "reason_codes":{
        "review_protected":review_protected,"failed_domains":failures,"stale_or_future_domains":stale,
        "core_unknown":unknown,"breadth_pass":breadth
      }
    }

def synthesize(dossier):
    if not isinstance(dossier,dict):
        return {"synthesis_status":"INVALID","reason":"INVALID_DOSSIER_PAYLOAD","recommendation":None,"ranking":None}
    if dossier.get("stage3_status")=="BLOCKED":
        return {"symbol":dossier.get("symbol"),"synthesis_status":"INVALID","reason":dossier.get("reason","UPSTREAM_BLOCKED"),"recommendation":None,"ranking":None}
    fams=_ledger(dossier)
    swing=_horizon(fams,("PRICE_TREND","MOMENTUM_PARTICIPATION","RELATIVE_STRENGTH"),("BUSINESS_SECTOR","CATALYST"),dossier)
    long_term=_horizon(fams,("PROFITABILITY","CASH_QUALITY","FINANCIAL_STRENGTH","VALUATION"),("BUSINESS_SECTOR","CATALYST"),dossier)
    return {
      "symbol":dossier.get("symbol"),"synthesis_status":"COMPLETE",
      "swing":swing,"long_term":long_term,
      "shared":{
        "evidence_ledger":fams,
        "risk_families":{"RISK":fams["RISK"]},
        "data_quality":dossier.get("data_quality",{}),
        "s2_prior_resolution":"REVIEW_PRESERVED" if dossier.get("review_protected") else "PRIOR_NOT_ADDITIVE"
      },
      "recommendation":None,"ranking":None
    }
