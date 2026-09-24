from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Dict, Iterable, Mapping, Optional, Tuple
from integration_pipeline.pipeline_contracts import Evidence, FreshnessState, PeriodType, QualityState

GATE_VERSION = "P4-R1"

@dataclass(frozen=True)
class MetricRule:
    metric_id: str
    allowed_periods: Tuple[PeriodType, ...]
    max_age_days: Optional[int] = None
    allowed_units: Tuple[str, ...] = ()
    allowed_currencies: Tuple[str, ...] = ()
    numeric: bool = True
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    applicability: str = "GENERAL"

@dataclass(frozen=True)
class GateDiagnostic:
    code: str
    evidence_id: str
    detail: Optional[str] = None

@dataclass(frozen=True)
class GateResult:
    accepted: Tuple[Evidence, ...] = ()
    rejected: Tuple[Evidence, ...] = ()
    diagnostics: Tuple[GateDiagnostic, ...] = ()

# Conservative registry: rules only where semantics are already locked.
DEFAULT_RULES: Dict[str, MetricRule] = {
    "gross_margin_ttm": MetricRule("gross_margin_ttm", (PeriodType.TTM,), 120, ("percent", "%")),
    "asset_turnover": MetricRule("asset_turnover", (PeriodType.TTM,), 120, ("ratio", "x"), min_value=0),
    "revenue_growth": MetricRule("revenue_growth", (PeriodType.QUARTER, PeriodType.TTM, PeriodType.FY), 120, ("percent", "%")),
    "revenue_ttm": MetricRule("revenue_ttm", (PeriodType.TTM,), 120, ("currency",), min_value=0),
    "ocf_ttm": MetricRule("ocf_ttm", (PeriodType.TTM,), 120, ("currency",)),
    "fcf_ttm": MetricRule("fcf_ttm", (PeriodType.TTM,), 120, ("currency",)),
    "net_income_ttm": MetricRule("net_income_ttm", (PeriodType.TTM,), 120, ("currency",)),
    "capex_ttm": MetricRule("capex_ttm", (PeriodType.TTM,), 120, ("currency",)),
    "cash_balance": MetricRule("cash_balance", (PeriodType.POINT_IN_TIME, PeriodType.QUARTER, PeriodType.FY), 120, ("currency",), min_value=0),
    "short_term_debt": MetricRule("short_term_debt", (PeriodType.POINT_IN_TIME, PeriodType.QUARTER, PeriodType.FY), 120, ("currency",), min_value=0),
    "interest_coverage": MetricRule("interest_coverage", (PeriodType.TTM,), 120, ("ratio", "x")),
    "pe": MetricRule("pe", (PeriodType.POINT_IN_TIME, PeriodType.DAILY), 120, ("ratio", "x")),
    "pb": MetricRule("pb", (PeriodType.POINT_IN_TIME, PeriodType.DAILY), 120, ("ratio", "x")),
    "ev_ebitda": MetricRule("ev_ebitda", (PeriodType.POINT_IN_TIME, PeriodType.DAILY), 120, ("ratio", "x")),
    "earnings_yield": MetricRule("earnings_yield", (PeriodType.TTM, PeriodType.POINT_IN_TIME), 120, ("percent", "%")),
    "fcf_yield": MetricRule("fcf_yield", (PeriodType.TTM, PeriodType.POINT_IN_TIME), 120, ("percent", "%")),
    "stock_return_1m": MetricRule("stock_return_1m", (PeriodType.DAILY,), 14, ("percent", "%")),
    "stock_return_3m": MetricRule("stock_return_3m", (PeriodType.DAILY,), 14, ("percent", "%")),
    "sector_breadth_pct": MetricRule("sector_breadth_pct", (PeriodType.DAILY, PeriodType.POINT_IN_TIME), 14, ("percent", "%"), min_value=0, max_value=100),
    "industry_breadth_pct": MetricRule("industry_breadth_pct", (PeriodType.DAILY, PeriodType.POINT_IN_TIME), 14, ("percent", "%"), min_value=0, max_value=100),
    "beta": MetricRule("beta", (PeriodType.DAILY, PeriodType.POINT_IN_TIME), 14, ("ratio", "x")),
    "max_drawdown_pct": MetricRule("max_drawdown_pct", (PeriodType.DAILY,), 14, ("percent", "%"), min_value=-100, max_value=0),
    "revenue_concentration_pct": MetricRule("revenue_concentration_pct", (PeriodType.TTM, PeriodType.FY), 120, ("percent", "%"), min_value=0, max_value=100),
    "adtv": MetricRule("adtv", (PeriodType.DAILY, PeriodType.POINT_IN_TIME), 14, ("currency",), min_value=0),
    "bid_ask_spread_pct": MetricRule("bid_ask_spread_pct", (PeriodType.DAILY, PeriodType.POINT_IN_TIME), 14, ("percent", "%"), min_value=0),
    "atr_pct": MetricRule("atr_pct", (PeriodType.DAILY, PeriodType.POINT_IN_TIME), 14, ("percent", "%"), min_value=0),
    "negative_event_probability": MetricRule("negative_event_probability", (PeriodType.EVENT, PeriodType.POINT_IN_TIME), 14, ("probability",), min_value=0, max_value=1),
    "data_coverage_pct": MetricRule("data_coverage_pct", (PeriodType.POINT_IN_TIME,), 14, ("percent", "%"), min_value=0, max_value=100),
}


def _as_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    return date.fromisoformat(value)


def _age_anchor(e: Evidence) -> Optional[date]:
    # Publication date controls availability for reports. Otherwise period_end is the evidence date.
    return _as_date(e.period.published_at) or _as_date(e.period.period_end)


def validate_evidence(e: Evidence, *, analysis_as_of: str,
                      rules: Mapping[str, MetricRule] = DEFAULT_RULES,
                      sector: Optional[str] = None) -> Tuple[GateDiagnostic, ...]:
    out=[]
    for err in e.validate(analysis_as_of):
        out.append(GateDiagnostic("CONTRACT_INVALID", e.evidence_id, err))
    if out:
        return tuple(out)

    # Non-value states are valid terminal states and are not forced through numeric semantics.
    if e.quality_state in {QualityState.UNAVAILABLE, QualityState.NOT_APPLICABLE}:
        return ()

    rule=rules.get(e.metric_id)
    if rule is None:
        # Unknown metrics remain admissible at P4 contract level; P5/P9 own mapping.
        return ()

    if e.period.period_type not in rule.allowed_periods:
        out.append(GateDiagnostic("PERIOD_TYPE_MISMATCH", e.evidence_id,
                                  f"{e.period.period_type.value} not in {[x.value for x in rule.allowed_periods]}"))

    if rule.allowed_units and (e.unit or "") not in rule.allowed_units:
        out.append(GateDiagnostic("UNIT_MISMATCH", e.evidence_id, str(e.unit)))
    if rule.allowed_currencies and (e.currency or "") not in rule.allowed_currencies:
        out.append(GateDiagnostic("CURRENCY_MISMATCH", e.evidence_id, str(e.currency)))

    v=e.normalized_value
    if rule.numeric:
        if isinstance(v, bool) or not isinstance(v, (int,float)):
            out.append(GateDiagnostic("NUMERIC_VALUE_REQUIRED", e.evidence_id, type(v).__name__))
        elif not isfinite(float(v)):
            out.append(GateDiagnostic("NON_FINITE_VALUE", e.evidence_id))
        else:
            fv=float(v)
            if rule.min_value is not None and fv < rule.min_value:
                out.append(GateDiagnostic("VALUE_BELOW_DOMAIN", e.evidence_id, str(rule.min_value)))
            if rule.max_value is not None and fv > rule.max_value:
                out.append(GateDiagnostic("VALUE_ABOVE_DOMAIN", e.evidence_id, str(rule.max_value)))

    if rule.max_age_days is not None:
        anchor=_age_anchor(e)
        if anchor is None:
            out.append(GateDiagnostic("FRESHNESS_DATE_MISSING", e.evidence_id))
        else:
            age=(date.fromisoformat(analysis_as_of)-anchor).days
            if age < 0:
                out.append(GateDiagnostic("FUTURE_DATA_LEAKAGE", e.evidence_id, str(age)))
            elif age > rule.max_age_days and e.freshness_state != FreshnessState.STALE:
                out.append(GateDiagnostic("STALE_STATE_NOT_PROPAGATED", e.evidence_id, f"age={age};max={rule.max_age_days}"))
            elif age <= rule.max_age_days and e.freshness_state == FreshnessState.STALE:
                out.append(GateDiagnostic("STALE_STATE_INCONSISTENT", e.evidence_id, f"age={age};max={rule.max_age_days}"))

    if e.freshness_state == FreshnessState.STALE and e.quality_state == QualityState.VALID:
        out.append(GateDiagnostic("STALE_CANNOT_BE_QUALITY_VALID", e.evidence_id))
    if e.quality_state == QualityState.STALE and e.freshness_state != FreshnessState.STALE:
        out.append(GateDiagnostic("QUALITY_FRESHNESS_STATE_MISMATCH", e.evidence_id))
    return tuple(out)


def run_gate(items: Iterable[Evidence], *, analysis_as_of: str,
             rules: Mapping[str, MetricRule] = DEFAULT_RULES,
             sector_by_symbol: Optional[Mapping[str,str]] = None) -> GateResult:
    accepted=[]; rejected=[]; diags=[]
    for e in items:
        sector=(sector_by_symbol or {}).get(e.symbol.upper())
        ds=validate_evidence(e, analysis_as_of=analysis_as_of, rules=rules, sector=sector)
        if ds:
            rejected.append(e); diags.extend(ds)
        else:
            accepted.append(e)
    return GateResult(tuple(accepted), tuple(rejected), tuple(diags))
