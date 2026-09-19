
from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Optional
import math

class ReconciliationState(str, Enum):
    CONSISTENT = "CONSISTENT"
    PERIOD_DIFFERENCE = "PERIOD_DIFFERENCE"
    EVIDENCE_CONFLICT = "EVIDENCE_CONFLICT"
    NOT_COMPARABLE = "NOT_COMPARABLE"

@dataclass(frozen=True)
class ComparableEvidence:
    symbol: str
    metric_id: str
    value: Optional[float]
    unit: Optional[str] = None
    currency: Optional[str] = None
    period_type: Optional[str] = None
    period_start: Optional[str] = None
    period_end: Optional[str] = None
    adjustment_basis: Optional[str] = None
    source_id: Optional[str] = None
    quality_state: str = "VALID"

@dataclass(frozen=True)
class ReconciliationResult:
    symbol: str
    metric_id: str
    state: ReconciliationState
    upstream: ComparableEvidence
    candidate: ComparableEvidence
    absolute_difference: Optional[float]
    relative_difference: Optional[float]
    tolerance_used: Optional[float]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d

DEFAULT_REL_TOLERANCE = 0.01
DEFAULT_ABS_TOLERANCE = 1e-9

# Metric-specific tolerances are deliberately conservative and can be versioned later.
METRIC_REL_TOLERANCE = {
    "debt_equity": 0.02,
    "roic": 0.02,
    "npm": 0.02,
    "eps_growth": 0.03,
    "earnings_yield": 0.02,
    "fcf_ttm": 0.01,
    "net_income_ttm": 0.01,
    "adtv": 0.02,
    "atr_pct": 0.02,
    "distance_ma200_pct": 0.02,
}

def _finite_number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))

def _norm(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    return s.upper() if s else None

def _same_definition(a: ComparableEvidence, b: ComparableEvidence) -> bool:
    return a.symbol.upper() == b.symbol.upper() and a.metric_id == b.metric_id

def _period_relation(a: ComparableEvidence, b: ComparableEvidence) -> str:
    at, bt = _norm(a.period_type), _norm(b.period_type)
    if at != bt:
        return "DIFFERENT"
    # If both carry explicit boundaries, they must match.
    if a.period_start and b.period_start and a.period_start != b.period_start:
        return "DIFFERENT"
    if a.period_end and b.period_end and a.period_end != b.period_end:
        return "DIFFERENT"
    return "SAME"

def _semantic_comparable(a: ComparableEvidence, b: ComparableEvidence) -> tuple[bool, str]:
    if not _same_definition(a, b):
        return False, "symbol or metric definition differs"
    if _norm(a.unit) != _norm(b.unit):
        return False, "unit differs"
    if _norm(a.currency) != _norm(b.currency):
        return False, "currency differs"
    if _norm(a.adjustment_basis) != _norm(b.adjustment_basis):
        return False, "adjustment basis differs"
    if a.quality_state in {"INVALID", "UNAVAILABLE", "NOT_APPLICABLE"}:
        return False, f"upstream quality is {a.quality_state}"
    if b.quality_state in {"INVALID", "UNAVAILABLE", "NOT_APPLICABLE"}:
        return False, f"candidate quality is {b.quality_state}"
    if not _finite_number(a.value) or not _finite_number(b.value):
        return False, "numeric values are not both finite"
    return True, ""

def reconcile(
    upstream: ComparableEvidence,
    candidate: ComparableEvidence,
    *,
    relative_tolerance: Optional[float] = None,
    absolute_tolerance: float = DEFAULT_ABS_TOLERANCE,
) -> ReconciliationResult:
    comparable, reason = _semantic_comparable(upstream, candidate)
    if not comparable:
        return ReconciliationResult(
            upstream.symbol, upstream.metric_id, ReconciliationState.NOT_COMPARABLE,
            upstream, candidate, None, None, None, reason
        )

    if _period_relation(upstream, candidate) == "DIFFERENT":
        return ReconciliationResult(
            upstream.symbol, upstream.metric_id, ReconciliationState.PERIOD_DIFFERENCE,
            upstream, candidate, None, None, None,
            "same metric but period definition/boundary differs"
        )

    a, b = float(upstream.value), float(candidate.value)
    abs_diff = abs(a - b)
    scale = max(abs(a), abs(b), absolute_tolerance)
    rel_diff = abs_diff / scale
    tol = relative_tolerance
    if tol is None:
        tol = METRIC_REL_TOLERANCE.get(upstream.metric_id, DEFAULT_REL_TOLERANCE)

    consistent = abs_diff <= absolute_tolerance or rel_diff <= tol
    state = ReconciliationState.CONSISTENT if consistent else ReconciliationState.EVIDENCE_CONFLICT
    return ReconciliationResult(
        upstream.symbol, upstream.metric_id, state, upstream, candidate,
        abs_diff, rel_diff, tol,
        "values within tolerance" if consistent else "same-period comparable values exceed tolerance"
    )

def reconcile_many(pairs):
    # Pure function: never mutates or selects a winner.
    return [reconcile(a, b) for a, b in pairs]
