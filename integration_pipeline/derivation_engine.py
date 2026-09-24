from __future__ import annotations
from dataclasses import dataclass
from math import isfinite, log, sqrt
from statistics import mean, median
from typing import Callable, Dict, Iterable, Mapping, Optional, Sequence, Tuple
from datetime import date

from integration_pipeline.pipeline_contracts import (
    ConflictState, DependencyRef, Evidence, EvidenceOrigin, FreshnessState,
    PeriodRef, PeriodType, Provenance, QualityState,
)

ENGINE_VERSION = "P5-R1"

class DerivationError(ValueError): pass

@dataclass(frozen=True)
class FormulaSpec:
    metric_id: str
    formula_id: str
    formula_version: str
    dependencies: Tuple[str, ...]
    period_type: PeriodType
    unit: str
    calculator: Callable[[Mapping[str, float]], float]


def _finite(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(float(v)):
        raise DerivationError(f"INVALID_DEPENDENCY_VALUE:{name}")
    return float(v)

def _nz(v, name):
    x=_finite(v,name)
    if x == 0: raise DerivationError(f"ZERO_DENOMINATOR:{name}")
    return x

def _positive(v, name):
    x=_finite(v,name)
    if x <= 0: raise DerivationError(f"NON_POSITIVE_DENOMINATOR:{name}")
    return x

# Locked deterministic formulas. Capex is normalized as positive cash outflow magnitude.
def gross_margin(v): return _finite(v['gross_profit_ttm'],'gross_profit_ttm')/_positive(v['revenue_ttm'],'revenue_ttm')*100.0
def asset_turnover(v): return _finite(v['revenue_ttm'],'revenue_ttm')/_positive(v['average_total_assets'],'average_total_assets')
def revenue_growth(v): return (_finite(v['revenue_current'],'revenue_current')/_positive(v['revenue_prior_comparable'],'revenue_prior_comparable')-1.0)*100.0
def interest_coverage(v): return _finite(v['ebit_ttm'],'ebit_ttm')/_positive(v['interest_expense_ttm'],'interest_expense_ttm')
def cash_short_debt(v): return _finite(v['cash_balance'],'cash_balance')/_positive(v['short_term_debt'],'short_term_debt')
def pe(v): return _finite(v['price'],'price')/_positive(v['eps_ttm'],'eps_ttm')
def pb(v): return _finite(v['market_cap'],'market_cap')/_positive(v['book_equity'],'book_equity')
def enterprise_value(v): return _finite(v['market_cap'],'market_cap')+_finite(v['total_debt'],'total_debt')-_finite(v['cash_balance'],'cash_balance')
def ev_ebitda(v): return _finite(v['enterprise_value'],'enterprise_value')/_positive(v['ebitda_ttm'],'ebitda_ttm')
def fcf_yield(v): return _finite(v['fcf_ttm'],'fcf_ttm')/_positive(v['market_cap'],'market_cap')*100.0
def distance_ma200(v): return (_finite(v['price'],'price')/_positive(v['price_ma200'],'price_ma200')-1.0)*100.0
def atr_pct(v): return _finite(v['atr14'],'atr14')/_positive(v['price'],'price')*100.0

FORMULAS: Dict[str, FormulaSpec] = {
    'gross_margin_ttm': FormulaSpec('gross_margin_ttm','GM_TTM','1',('gross_profit_ttm','revenue_ttm'),PeriodType.TTM,'percent',gross_margin),
    'asset_turnover': FormulaSpec('asset_turnover','ASSET_TURNOVER_TTM','1',('revenue_ttm','average_total_assets'),PeriodType.TTM,'ratio',asset_turnover),
    'revenue_growth': FormulaSpec('revenue_growth','REVENUE_GROWTH_YOY','1',('revenue_current','revenue_prior_comparable'),PeriodType.TTM,'percent',revenue_growth),
    'interest_coverage': FormulaSpec('interest_coverage','INTEREST_COVERAGE_TTM','1',('ebit_ttm','interest_expense_ttm'),PeriodType.TTM,'ratio',interest_coverage),
    'cash_short_debt_coverage': FormulaSpec('cash_short_debt_coverage','CASH_ST_DEBT_COVERAGE','1',('cash_balance','short_term_debt'),PeriodType.POINT_IN_TIME,'ratio',cash_short_debt),
    'pe': FormulaSpec('pe','PE_TTM','1',('price','eps_ttm'),PeriodType.POINT_IN_TIME,'ratio',pe),
    'pb': FormulaSpec('pb','PB_CURRENT','1',('market_cap','book_equity'),PeriodType.POINT_IN_TIME,'ratio',pb),
    'enterprise_value': FormulaSpec('enterprise_value','EV','1',('market_cap','total_debt','cash_balance'),PeriodType.POINT_IN_TIME,'currency',enterprise_value),
    'ev_ebitda': FormulaSpec('ev_ebitda','EV_EBITDA_TTM','1',('enterprise_value','ebitda_ttm'),PeriodType.POINT_IN_TIME,'ratio',ev_ebitda),
    'fcf_yield': FormulaSpec('fcf_yield','FCF_YIELD_TTM','1',('fcf_ttm','market_cap'),PeriodType.POINT_IN_TIME,'percent',fcf_yield),
    'distance_ma200_pct': FormulaSpec('distance_ma200_pct','DIST_MA200','1',('price','price_ma200'),PeriodType.POINT_IN_TIME,'percent',distance_ma200),
    'atr_pct': FormulaSpec('atr_pct','ATR_PCT','1',('atr14','price'),PeriodType.POINT_IN_TIME,'percent',atr_pct),
}

BAD_DEP_STATES={QualityState.INVALID,QualityState.UNAVAILABLE,QualityState.NOT_APPLICABLE,QualityState.CONFLICT}

def _quality_from_dependencies(deps: Sequence[Evidence]) -> Tuple[QualityState, FreshnessState]:
    qs={d.quality_state for d in deps}; fs={d.freshness_state for d in deps}
    if QualityState.INVALID in qs: return QualityState.INVALID, FreshnessState.UNKNOWN
    if QualityState.CONFLICT in qs: return QualityState.CONFLICT, FreshnessState.UNKNOWN
    if QualityState.UNAVAILABLE in qs: return QualityState.UNAVAILABLE, FreshnessState.UNKNOWN
    if QualityState.NOT_APPLICABLE in qs: return QualityState.NOT_APPLICABLE, FreshnessState.UNKNOWN
    if QualityState.STALE in qs or FreshnessState.STALE in fs: return QualityState.STALE, FreshnessState.STALE
    if QualityState.PARTIAL in qs: return QualityState.PARTIAL, FreshnessState.UNKNOWN if FreshnessState.UNKNOWN in fs else FreshnessState.FRESH
    return QualityState.VALID, FreshnessState.FRESH if fs and fs <= {FreshnessState.FRESH} else FreshnessState.UNKNOWN

def _latest_date(values: Iterable[Optional[str]]) -> Optional[str]:
    xs=[x for x in values if x]
    return max(xs) if xs else None

def derive_metric(symbol: str, metric_id: str, dependencies: Mapping[str,Evidence], *, analysis_as_of: str) -> Evidence:
    if metric_id not in FORMULAS: raise DerivationError(f"UNKNOWN_FORMULA:{metric_id}")
    spec=FORMULAS[metric_id]
    missing=[m for m in spec.dependencies if m not in dependencies]
    if missing: raise DerivationError("MISSING_DEPENDENCIES:"+','.join(missing))
    deps=[dependencies[m] for m in spec.dependencies]
    if any(d.symbol.upper()!=symbol.upper() for d in deps): raise DerivationError("CROSS_SYMBOL_DEPENDENCY")
    q,f=_quality_from_dependencies(deps)
    deprefs=tuple(DependencyRef(d.metric_id,d.evidence_id,True) for d in deps)
    period_end=_latest_date(d.period.period_end for d in deps)
    published_at=_latest_date(d.period.published_at for d in deps)
    prov=Provenance(
        source_id="SIS_DERIVATION_ENGINE", source_type="PYTHON_DETERMINISTIC", source_reference=None,
        observed_at=deps[0].provenance.observed_at, transform_id=spec.formula_id, transform_version=spec.formula_version)
    # Terminal dependency state propagates without fabricating a numeric result.
    if q in {QualityState.INVALID,QualityState.UNAVAILABLE,QualityState.NOT_APPLICABLE,QualityState.CONFLICT}:
        return Evidence(f"DER:{symbol.upper()}:{metric_id}:{spec.formula_version}",symbol.upper(),metric_id,None,None,spec.unit,None,
            EvidenceOrigin.ENRICH_DERIVED,PeriodRef(spec.period_type,period_end=period_end,published_at=published_at),prov,q,f,
            ConflictState.EVIDENCE_CONFLICT if q==QualityState.CONFLICT else ConflictState.NONE,deprefs,("DEPENDENCY_STATE_PROPAGATED",))
    vals={m:_finite(dependencies[m].normalized_value,m) for m in spec.dependencies}
    try: result=spec.calculator(vals)
    except DerivationError:
        raise
    if not isfinite(result): raise DerivationError("NON_FINITE_DERIVED_RESULT")
    return Evidence(f"DER:{symbol.upper()}:{metric_id}:{spec.formula_version}",symbol.upper(),metric_id,result,result,spec.unit,None,
        EvidenceOrigin.ENRICH_DERIVED,PeriodRef(spec.period_type,period_end=period_end,published_at=published_at),prov,q,f,ConflictState.NONE,deprefs)


def _validate_quarter_sequence(ends: Sequence[str]) -> None:
    ds=sorted(date.fromisoformat(x) for x in ends)
    gaps=[(b-a).days for a,b in zip(ds,ds[1:])]
    if any(g < 60 or g > 120 for g in gaps):
        raise DerivationError("TTM_QUARTERS_NOT_CONSECUTIVE")
    if (ds[-1]-ds[0]).days < 250 or (ds[-1]-ds[0]).days > 310:
        raise DerivationError("TTM_WINDOW_INVALID")

def derive_historical_median(symbol: str, metric_id: str, history: Sequence[Evidence], *, min_points: int=12) -> Evidence:
    allowed={'pe_5y_median','pb_5y_median','ev_ebitda_5y_median'}
    if metric_id not in allowed: raise DerivationError("INVALID_HISTORICAL_MEDIAN_METRIC")
    if len(history) < min_points: raise DerivationError("INSUFFICIENT_HISTORICAL_POINTS")
    if any(e.symbol.upper()!=symbol.upper() for e in history): raise DerivationError("CROSS_SYMBOL_DEPENDENCY")
    q,f=_quality_from_dependencies(history)
    deps=tuple(DependencyRef(e.metric_id,e.evidence_id,True) for e in history)
    prov=Provenance("SIS_DERIVATION_ENGINE","PYTHON_DETERMINISTIC",None,history[-1].provenance.observed_at,"HISTORICAL_MEDIAN","1")
    if q in {QualityState.INVALID,QualityState.UNAVAILABLE,QualityState.NOT_APPLICABLE,QualityState.CONFLICT}:
        return Evidence(f"DER:{symbol.upper()}:{metric_id}:1",symbol.upper(),metric_id,None,None,"ratio",None,EvidenceOrigin.ENRICH_DERIVED,
            PeriodRef(PeriodType.POINT_IN_TIME,period_start=min(e.period.period_end for e in history if e.period.period_end),period_end=max(e.period.period_end for e in history if e.period.period_end)),prov,q,f,ConflictState.NONE,deps,("DEPENDENCY_STATE_PROPAGATED",))
    vals=[_finite(e.normalized_value,e.metric_id) for e in history]
    result=float(median(vals))
    return Evidence(f"DER:{symbol.upper()}:{metric_id}:1",symbol.upper(),metric_id,result,result,"ratio",None,EvidenceOrigin.ENRICH_DERIVED,
        PeriodRef(PeriodType.POINT_IN_TIME,period_start=min(e.period.period_end for e in history if e.period.period_end),period_end=max(e.period.period_end for e in history if e.period.period_end)),prov,q,f,ConflictState.NONE,deps)

def max_drawdown_pct(prices: Sequence[float]) -> float:
    if len(prices)<2: raise DerivationError("INSUFFICIENT_PRICE_HISTORY")
    xs=[_positive(x,'adjusted_close') for x in prices]
    peak=xs[0]; worst=0.0
    for x in xs:
        peak=max(peak,x); worst=min(worst,(x/peak-1.0)*100.0)
    return worst

def annualized_volatility_pct(prices: Sequence[float], trading_days: int=252) -> float:
    if len(prices)<3: raise DerivationError("INSUFFICIENT_PRICE_HISTORY")
    xs=[_positive(x,'adjusted_close') for x in prices]
    rs=[log(b/a) for a,b in zip(xs,xs[1:])]
    mu=mean(rs); var=sum((r-mu)**2 for r in rs)/(len(rs)-1)
    return sqrt(var)*sqrt(trading_days)*100.0

def beta_from_prices(stock_prices: Sequence[float], benchmark_prices: Sequence[float]) -> float:
    if len(stock_prices)!=len(benchmark_prices) or len(stock_prices)<3: raise DerivationError("BETA_HISTORY_MISMATCH")
    s=[_positive(x,'stock_adjusted_close') for x in stock_prices]; b=[_positive(x,'benchmark_adjusted_close') for x in benchmark_prices]
    sr=[log(y/x) for x,y in zip(s,s[1:])]; br=[log(y/x) for x,y in zip(b,b[1:])]
    bm=mean(br); sm=mean(sr); denom=sum((x-bm)**2 for x in br)
    if denom<=0: raise DerivationError("ZERO_BENCHMARK_VARIANCE")
    return sum((x-sm)*(y-bm) for x,y in zip(sr,br))/denom

def derive_ttm(symbol: str, metric_id: str, quarters: Sequence[Evidence], *, analysis_as_of: str, capex_outflow_magnitude: bool=False) -> Evidence:
    if len(quarters)!=4: raise DerivationError("TTM_REQUIRES_EXACTLY_4_QUARTERS")
    if any(q.symbol.upper()!=symbol.upper() for q in quarters): raise DerivationError("CROSS_SYMBOL_DEPENDENCY")
    if any(q.period.period_type!=PeriodType.QUARTER for q in quarters): raise DerivationError("TTM_REQUIRES_QUARTER_INPUT")
    ends=[q.period.period_end for q in quarters]
    if any(x is None for x in ends) or len(set(ends))!=4: raise DerivationError("TTM_QUARTER_DATES_INVALID")
    _validate_quarter_sequence(ends)
    qstate,fstate=_quality_from_dependencies(quarters)
    deps=tuple(DependencyRef(q.metric_id,q.evidence_id,True) for q in quarters)
    formula_id="CAPEX_TTM_SUM_ABS" if capex_outflow_magnitude else "TTM_4Q_SUM"
    prov=Provenance("SIS_DERIVATION_ENGINE","PYTHON_DETERMINISTIC",None,quarters[0].provenance.observed_at,formula_id,"1")
    if qstate in {QualityState.INVALID,QualityState.UNAVAILABLE,QualityState.NOT_APPLICABLE,QualityState.CONFLICT}:
        return Evidence(f"DER:{symbol.upper()}:{metric_id}:1",symbol.upper(),metric_id,None,None,"currency",quarters[0].currency,EvidenceOrigin.ENRICH_DERIVED,
            PeriodRef(PeriodType.TTM,period_start=min(ends),period_end=max(ends),published_at=_latest_date(x.period.published_at for x in quarters)),prov,qstate,fstate,
            ConflictState.EVIDENCE_CONFLICT if qstate==QualityState.CONFLICT else ConflictState.NONE,deps,("DEPENDENCY_STATE_PROPAGATED",))
    values=[_finite(q.normalized_value,q.metric_id) for q in quarters]
    result=sum(abs(v) for v in values) if capex_outflow_magnitude else sum(values)
    return Evidence(f"DER:{symbol.upper()}:{metric_id}:1",symbol.upper(),metric_id,result,result,"currency",quarters[0].currency,EvidenceOrigin.ENRICH_DERIVED,
        PeriodRef(PeriodType.TTM,period_start=min(ends),period_end=max(ends),published_at=_latest_date(x.period.published_at for x in quarters)),prov,qstate,fstate,ConflictState.NONE,deps)


def derive_return(symbol: str, metric_id: str, current: Evidence, prior: Evidence, *, trading_days: int) -> Evidence:
    if metric_id not in {'stock_return_1m','stock_return_3m'}: raise DerivationError("INVALID_RETURN_METRIC")
    if current.symbol.upper()!=symbol.upper() or prior.symbol.upper()!=symbol.upper(): raise DerivationError("CROSS_SYMBOL_DEPENDENCY")
    if current.period.period_type!=PeriodType.DAILY or prior.period.period_type!=PeriodType.DAILY: raise DerivationError("RETURN_REQUIRES_DAILY_PRICE")
    q,f=_quality_from_dependencies((current,prior)); deps=(DependencyRef(current.metric_id,current.evidence_id),DependencyRef(prior.metric_id,prior.evidence_id))
    prov=Provenance("SIS_DERIVATION_ENGINE","PYTHON_DETERMINISTIC",None,current.provenance.observed_at,f"ADJ_RETURN_{trading_days}D","1")
    if q in {QualityState.INVALID,QualityState.UNAVAILABLE,QualityState.NOT_APPLICABLE,QualityState.CONFLICT}:
        return Evidence(f"DER:{symbol.upper()}:{metric_id}:1",symbol.upper(),metric_id,None,None,"percent",None,EvidenceOrigin.ENRICH_DERIVED,
            PeriodRef(PeriodType.DAILY,period_start=prior.period.period_end,period_end=current.period.period_end),prov,q,f,ConflictState.NONE,deps,("DEPENDENCY_STATE_PROPAGATED",))
    c=_finite(current.normalized_value,'adjusted_close_current'); p=_positive(prior.normalized_value,'adjusted_close_prior')
    result=(c/p-1)*100.0
    return Evidence(f"DER:{symbol.upper()}:{metric_id}:1",symbol.upper(),metric_id,result,result,"percent",None,EvidenceOrigin.ENRICH_DERIVED,
        PeriodRef(PeriodType.DAILY,period_start=prior.period.period_end,period_end=current.period.period_end),prov,q,f,ConflictState.NONE,deps)
