
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
                         *, ohlcv=None, business_context=None, sector_context=None,
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
    technical={"ohlcv":hist,"metadata":tech_meta}

    fundamental=_numeric_payload(idx,FUNDAMENTAL_FIELDS,analysis_as_of)
    if isinstance(business_context,Mapping):
        fundamental["business_context"]=dict(business_context)

    cash=_numeric_payload(idx,CASH_FIELDS,analysis_as_of)
    valuation=_numeric_payload(idx,VALUATION_FIELDS,analysis_as_of)

    sector=_numeric_payload(idx,SECTOR_NUMERIC,analysis_as_of)
    if isinstance(sector_context,Mapping):
        for k in ("sector","industry","commodity_exposure","macro_exposure"):
            if k in sector_context: sector[k]=sector_context[k]

    risk=_numeric_payload(idx,RISK_NUMERIC,analysis_as_of)
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
    }

def validate_payload_shape(p):
    required=("symbol","stage2","technical_enrichment","fundamental_enrichment","cash_enrichment",
              "valuation_enrichment","sector_enrichment","catalyst_enrichment","risk_enrichment")
    return isinstance(p,dict) and all(k in p and isinstance(p[k],dict) for k in required[1:]) and bool(p.get("symbol"))
