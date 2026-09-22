
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Mapping
from copy import deepcopy
from datetime import date
import math

FUNDAMENTAL_FIELDS=("npm","roic","eps_growth","revenue_growth","debt_equity","fscore",
"asset_turnover","gross_margin","gross_margin_3y_avg","roic_3y_avg","share_count_growth",
"dividend_payout","reinvestment_rate")
CASH_FIELDS=("ocf_ttm","fcf_ttm","net_income_ttm","ocf_prev_ttm","fcf_prev_ttm",
"net_income_prev_ttm","capex_ttm","revenue_ttm","cash_balance","short_term_debt")
VALUATION_FIELDS=("pe","pb","ev_ebitda","earnings_yield","fcf_yield","pe_5y_median",
"pb_5y_median","ev_ebitda_5y_median","sector_pe","sector_pb","sector_ev_ebitda",
"eps_growth","revenue_growth")
SECTOR_NUMERIC=("sector_return_1m","sector_return_3m","industry_return_1m","industry_return_3m",
"stock_return_1m","stock_return_3m","sector_breadth_pct","industry_breadth_pct",
"commodity_change_3m","macro_sensitivity")
RISK_NUMERIC=("beta","max_drawdown_pct","sector_volatility_pct","revenue_concentration_pct",
"debt_equity","interest_coverage","cash_short_debt_coverage","adtv","bid_ask_spread_pct",
"pe_premium_pct","distance_ma200_pct","atr_pct","negative_event_probability","data_coverage_pct")

FORWARD_FIELDS=(
    "expected_revenue_growth_2y_cagr","expected_revenue_growth_yoy",
    "expected_op_profit_growth_yoy","expected_op_profit_growth_2y_cagr",
    "expected_net_income_growth_yoy","expected_net_income_growth_2y_cagr",
    "expected_eps_growth_yoy","expected_eps_growth_2y_cagr",
    "eps_forward","peg_forward",
)


INTERNAL_MARKET_FIELDS={
    "price":"Price","previous_price":"Previous Price","open":"Open","high":"High","low":"Low","vwap":"VWAP",
    "ma20":"Price MA20","ma50":"Price MA50","ma100":"Price MA100","ma200":"Price MA200",
    "rsi14":"RSI14","previous_rsi14":"Previous RSI14","macd":"MACD","previous_macd":"Previous MACD",
    "adx14":"ADX14","di_plus":"DI+","di_minus":"DI-","atr14":"ATR14","adr14":"ADR14",
    "volume":"Volume","previous_volume":"Previous Volume","volume_ma20":"Volume MA20",
    "adtv30":"ADTV30","adtv90":"ADTV90","rs_3m":"RS Line 3M","rs_6m":"RS Line 6M","rs_9m":"RS Line 9M",
}
CANONICAL_DOMAIN_MAP={
 "fundamental_enrichment":{
   "npm":"Net Profit Margin TTM","roic":"ROIC TTM","eps_growth":"EPS Annual YoY",
   "revenue_growth":"Revenue Annual YoY","fscore":"Piotroski Score","asset_turnover":"Asset Turnover",
   "gross_margin":"Gross Margin TTM","dividend_payout":"Payout Ratio"},
 "cash_enrichment":{
   "ocf_ttm":"Cash From Operations TTM","fcf_ttm":"Derived Free Cash Flow TTM",
   "net_income_ttm":"Net Income TTM","capex_ttm":"CAPEX TTM","revenue_ttm":"Revenue TTM",
   "cash_balance":"Cash","short_term_debt":"Short Term Debt Quarter"},
 "valuation_enrichment":{
   "pe":"PE TTM","pb":"Derived PBV","ev_ebitda":"Derived EV/EBITDA TTM",
   "earnings_yield":"Derived Earnings Yield TTM","pe_5y_median":"PE Mean 5Y",
   "pb_5y_median":"PBV Mean 5Y","eps_growth":"EPS Annual YoY","revenue_growth":"Revenue Annual YoY"},
 "risk_enrichment":{
   "beta":"Beta 3Y","adtv":"ADTV30"},
 "forward_enrichment":{
   "expected_revenue_growth_2y_cagr":"Expected Revenue (Growth: 2Y CAGR)",
   "expected_revenue_growth_yoy":"Expected Revenue (Growth: YoY)",
   "expected_op_profit_growth_yoy":"Expected Op. Profit (Growth: YoY)",
   "expected_op_profit_growth_2y_cagr":"Expected Op. Profit (Growth: 2Y CAGR)",
   "expected_net_income_growth_yoy":"Expected Net Income (Growth: YoY)",
   "expected_net_income_growth_2y_cagr":"Expected Net Income (Growth: 2Y CAGR)",
   "expected_eps_growth_yoy":"Expected EPS (Growth: YoY)",
   "expected_eps_growth_2y_cagr":"Expected EPS (Growth: 2Y CAGR)",
   "eps_forward":"EPS (Forward)","peg_forward":"PEG (Forward)"}
}

def _canon_num(record, key):
    v=record.get(key) if isinstance(record,Mapping) else None
    return v if _finite(v) else None

def _overlay_internal(target, record, mapping, analysis_as_of):
    if not isinstance(record,Mapping): return target
    out=dict(target)
    used=False
    for dst,src in mapping.items():
        v=_canon_num(record,src)
        if v is not None and dst not in out:
            out[dst]=v; used=True
    if used:
        old=out.get("metadata",{}) if isinstance(out.get("metadata"),Mapping) else {}
        sources=[x for x in (old.get("source"),"S1_CANONICAL_INTERNAL") if x and x!="UNKNOWN"]
        out["metadata"]={"source":"+".join(dict.fromkeys(sources)) or "S1_CANONICAL_INTERNAL",
                         "as_of_date":old.get("as_of_date") or analysis_as_of}
    return out


def _safe_ratio_num(a,b,scale=1.0):
    return None if not (_finite(a) and _finite(b)) or float(b)==0 else float(a)/float(b)*scale

def _derive_internal_domains(record, fundamental, valuation, risk, analysis_as_of):
    if not isinstance(record,Mapping): return fundamental,valuation,risk
    fundamental=dict(fundamental); valuation=dict(valuation); risk=dict(risk)
    debt=_canon_num(record,"Derived Total Debt"); equity=_canon_num(record,"Total Equity Quarter")
    de=_safe_ratio_num(debt,equity)
    if de is not None and de>=0: fundamental.setdefault("debt_equity",de); risk.setdefault("debt_equity",de)
    ic=_canon_num(record,"Interest Coverage TTM")
    if ic is not None: risk.setdefault("interest_coverage",ic)
    cash=_canon_num(record,"Cash"); std=_canon_num(record,"Short Term Debt Quarter")
    cc=_safe_ratio_num(cash,std)
    if cc is not None and cc>=0: risk.setdefault("cash_short_debt_coverage",cc)
    price=_canon_num(record,"Price"); ma200=_canon_num(record,"Price MA200"); atr=_canon_num(record,"ATR14")
    dma=_safe_ratio_num((price-ma200) if _finite(price) and _finite(ma200) else None,ma200,100.0)
    if dma is not None: risk.setdefault("distance_ma200_pct",dma)
    atrp=_safe_ratio_num(atr,price,100.0)
    if atrp is not None and atrp>=0: risk.setdefault("atr_pct",atrp)
    fcf=_canon_num(record,"Derived Free Cash Flow TTM"); mcap=_canon_num(record,"Market Cap")
    fy=_safe_ratio_num(fcf,mcap,100.0)
    if fy is not None: valuation.setdefault("fcf_yield",fy)
    # Coverage is descriptive lineage, not a quality score: proportion of a locked internal evidence checklist present.
    checklist=("Price","Price MA20","Price MA50","Price MA200","ATR14","ADTV30","Beta 3Y","Interest Coverage TTM",
               "Cash","Short Term Debt Quarter","Derived Total Debt","Total Equity Quarter","PE TTM","Derived Free Cash Flow TTM","Market Cap")
    cov=100.0*sum(_finite(record.get(k)) for k in checklist)/len(checklist)
    risk.setdefault("data_coverage_pct",cov)
    for out in (fundamental,valuation,risk):
        if any(k!="metadata" for k in out):
            meta=out.get("metadata",{}) if isinstance(out.get("metadata"),Mapping) else {}
            out["metadata"]={"source":meta.get("source") or "S1_CANONICAL_INTERNAL","as_of_date":meta.get("as_of_date") or analysis_as_of}
    return fundamental,valuation,risk

VALID_CATALYST_DIR={"POSITIVE","NEGATIVE","NEUTRAL"}
VALID_CATALYST_MAT={"LOW","MODERATE","HIGH","CRITICAL"}
VALID_CATALYST_STATUS={"UPCOMING","ONGOING","COMPLETED"}
VALID_PRICED={"LIKELY_PRICED_IN","PARTIALLY_PRICED_IN","NOT_PRICED_IN","UNKNOWN"}

def _finite(v): return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(float(v))

@dataclass(frozen=True)
class MetricEvidence:
    metric_id:str
    value:Any
    quality_state:str="VALID"
    source_id:str="UNKNOWN"
    as_of_date:str|None=None

def _accepted(e:MetricEvidence)->bool:
    # Stage3 has no field-level conflict/partial channel. Never flatten those
    # states into ordinary numeric evidence.
    return e.quality_state in {"VALID","STALE"} and (
        e.value is not None and (not isinstance(e.value,(int,float)) or _finite(e.value))
    )

def _index(items:Iterable[MetricEvidence]):
    out={}
    for e in items:
        if e.metric_id in out: raise ValueError(f"duplicate metric evidence: {e.metric_id}")
        out[e.metric_id]=e
    return out

def _metadata(selected, fallback_as_of=None):
    sources=sorted({e.source_id for e in selected if e.source_id})
    dates=sorted({e.as_of_date for e in selected if e.as_of_date})
    return {"source":"+".join(sources) if sources else "UNKNOWN",
            # Conservative domain freshness: the oldest selected evidence controls the
            # domain metadata so newer fields cannot mask stale evidence.
            "as_of_date":dates[0] if dates else fallback_as_of}

def _numeric_payload(idx, fields, fallback_as_of=None):
    chosen=[idx[k] for k in fields if k in idx and _accepted(idx[k]) and _finite(idx[k].value)]
    p={e.metric_id:e.value for e in chosen}
    p["metadata"]=_metadata(chosen,fallback_as_of)
    return p

def build_stage3_payload(symbol:str, stage2:Mapping[str,Any], evidence:Iterable[MetricEvidence],
                         *, ohlcv=None, canonical_record=None, business_context=None, sector_context=None,
                         catalyst_events=None, analysis_as_of=None):
    sym=str(symbol).strip().upper()
    if not sym: raise ValueError("empty symbol")
    if not isinstance(stage2,Mapping): raise TypeError("stage2 must be mapping")
    idx=_index(evidence)

    # 3A exact outer contract: ohlcv + metadata. Stage2 source_features remain available to frozen 3A.
    hist=list(ohlcv or [])
    tech_meta={"source":"UNKNOWN","as_of_date":analysis_as_of}
    if hist:
        # Optional per-series evidence metadata can be supplied under synthetic OHLCV_META.
        em=idx.get("OHLCV_META")
        if em and _accepted(em) and isinstance(em.value,Mapping):
            d=em.value.get("as_of_date")
            try:
                if d and analysis_as_of and date.fromisoformat(str(d)) > date.fromisoformat(str(analysis_as_of)):
                    d=None
            except Exception:
                d=None
            tech_meta={"source":str(em.value.get("source","UNKNOWN")),
                       "as_of_date":d}
    internal_market={}
    if isinstance(canonical_record,Mapping):
        internal_market={dst:v for dst,src in INTERNAL_MARKET_FIELDS.items()
                         if (v:=_canon_num(canonical_record,src)) is not None}
    technical={"ohlcv":hist,"internal_market":internal_market,"metadata":tech_meta}
    if internal_market and not hist:
        technical["metadata"]={"source":"S1_CANONICAL_INTERNAL","as_of_date":analysis_as_of}

    fundamental=_numeric_payload(idx,FUNDAMENTAL_FIELDS,analysis_as_of)
    fundamental=_overlay_internal(fundamental,canonical_record,CANONICAL_DOMAIN_MAP["fundamental_enrichment"],analysis_as_of)
    if isinstance(business_context,Mapping):
        fundamental["business_context"]=dict(business_context)

    cash=_numeric_payload(idx,CASH_FIELDS,analysis_as_of)
    cash=_overlay_internal(cash,canonical_record,CANONICAL_DOMAIN_MAP["cash_enrichment"],analysis_as_of)
    valuation=_numeric_payload(idx,VALUATION_FIELDS,analysis_as_of)
    valuation=_overlay_internal(valuation,canonical_record,CANONICAL_DOMAIN_MAP["valuation_enrichment"],analysis_as_of)
    forward=_numeric_payload(idx,FORWARD_FIELDS,analysis_as_of)
    forward=_overlay_internal(forward,canonical_record,CANONICAL_DOMAIN_MAP["forward_enrichment"],analysis_as_of)

    sector=_numeric_payload(idx,SECTOR_NUMERIC,analysis_as_of)
    if isinstance(sector_context,Mapping):
        for k in ("sector","industry","commodity_exposure","macro_exposure"):
            if k in sector_context: sector[k]=sector_context[k]

    risk=_numeric_payload(idx,RISK_NUMERIC,analysis_as_of)
    risk=_overlay_internal(risk,canonical_record,CANONICAL_DOMAIN_MAP["risk_enrichment"],analysis_as_of)
    fundamental,valuation,risk=_derive_internal_domains(canonical_record,fundamental,valuation,risk,analysis_as_of)
    if isinstance(sector_context,Mapping):
        # Risk contextual states are distinct from 3E raw context objects.
        for k in ("sector_context","cyclicality","valuation_context","opportunity_context"):
            if k in sector_context: risk[k]=sector_context[k]

    # Catalyst frozen contract is stricter than P8 extraction. Only fully supported structured
    # events are forwarded. Unknown probability/materiality/priced-in is NOT fabricated.
    forwarded=[]
    event_dates=[]
    for x in list(catalyst_events or []):
        if not isinstance(x,Mapping): continue
        status=x.get("status")
        event_date=x.get("event_date")
        published=x.get("published_at") or x.get("as_of_date")
        temporal_ok=True
        try:
            ad=date.fromisoformat(str(analysis_as_of))
            ed=date.fromisoformat(str(event_date)) if event_date else None
            pd=date.fromisoformat(str(published)) if published else None
            if pd and pd>ad: temporal_ok=False
            if status=="UPCOMING" and (ed is None or ed<ad): temporal_ok=False
            if status=="COMPLETED" and (ed is None or ed>ad): temporal_ok=False
        except Exception:
            temporal_ok=False
        if (temporal_ok and x.get("direction") in VALID_CATALYST_DIR and
            x.get("materiality") in VALID_CATALYST_MAT and
            status in VALID_CATALYST_STATUS and
            _finite(x.get("probability")) and 0<=float(x["probability"])<=1 and
            x.get("priced_in","UNKNOWN") in VALID_PRICED):
            y={k:v for k,v in x.items() if not str(k).startswith("_")}
            forwarded.append(y)
            if published: event_dates.append(str(published))
    catalyst={"events":forwarded,"metadata":{"source":"DISCLOSURE_PIPELINE",
                                             "as_of_date":min(event_dates) if event_dates else None}}

    return {
        "symbol":sym,
        "stage2":deepcopy(dict(stage2)),  # deep immutable copy semantics: never recalculated
        "technical_enrichment":technical,
        "fundamental_enrichment":fundamental,
        "cash_enrichment":cash,
        "valuation_enrichment":valuation,
        "sector_enrichment":sector,
        "catalyst_enrichment":catalyst,
        "risk_enrichment":risk,
        "forward_enrichment":forward,
    }

def validate_payload_shape(p):
    required=("symbol","stage2","technical_enrichment","fundamental_enrichment","cash_enrichment",
              "valuation_enrichment","sector_enrichment","catalyst_enrichment","risk_enrichment",
              "forward_enrichment")
    return isinstance(p,dict) and all(k in p and isinstance(p[k],dict) for k in required[1:]) and bool(p.get("symbol"))
