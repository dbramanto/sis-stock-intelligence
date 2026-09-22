from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple
from pipeline_contracts import (
    ConflictState, DeepAnalysisScope, DependencyRef, Evidence, EvidenceOrigin,
    FreshnessState, PeriodRef, PeriodType, Provenance, QualityState, ScopeState,
)

MAPPER_VERSION = "P2-R2-PRODUCTION-COMPAT"

# Only fields whose semantics are already known from frozen Stage 1/2 are mapped.
# Stage 2 block scores/states are preserved as upstream evidence, never recomputed.
STAGE2_BLOCKS = ("technical", "participation", "fundamental", "cash_quality")

@dataclass(frozen=True)
class UpstreamMapResult:
    scope: DeepAnalysisScope
    evidence: Tuple[Evidence, ...]
    excluded: Tuple[Tuple[str, str], ...] = ()  # (symbol, reason)
    diagnostics: Tuple[str, ...] = ()


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper()


def _stage2_state(rec: Mapping[str, Any]) -> Optional[ScopeState]:
    raw = rec.get("eligibility", rec.get("stage2_state"))
    if raw is None:
        return None
    s = str(raw).strip().upper()
    try:
        return ScopeState(s)
    except ValueError:
        return None


def _prov(source_ref: Optional[str] = None) -> Provenance:
    return Provenance(
        source_id="SIS_STAGE2_R3_1",
        source_type="UPSTREAM_FROZEN",
        source_reference=source_ref or "stage2://frozen-output",
        observed_at="2026-09-18T00:00:00+07:00",
    )


def _period(analysis_as_of: str) -> PeriodRef:
    return PeriodRef(PeriodType.POINT_IN_TIME, period_end=analysis_as_of, published_at=analysis_as_of)


def _ev(symbol: str, metric_id: str, value: Any, analysis_as_of: str, *, unit: Optional[str] = None,
        quality: QualityState = QualityState.VALID, notes: Sequence[str] = ()) -> Evidence:
    eid = f"UP:{symbol}:{metric_id}"
    return Evidence(
        evidence_id=eid,
        symbol=symbol,
        metric_id=metric_id,
        raw_value=value,
        normalized_value=value,
        unit=unit,
        currency=None,
        origin=EvidenceOrigin.UPSTREAM_REUSE,
        period=_period(analysis_as_of),
        provenance=_prov(),
        quality_state=quality,
        freshness_state=FreshnessState.UNKNOWN,
        conflict_state=ConflictState.NONE,
        notes=tuple(notes),
    )


def _get_score(block: Any) -> Any:
    if isinstance(block, Mapping):
        for k in ("score", "value"):
            if k in block:
                return block[k]
    return block if isinstance(block, (int, float)) and not isinstance(block, bool) else None


def _get_state(block: Any) -> Optional[str]:
    if isinstance(block, Mapping):
        for k in ("state", "status", "priority"):
            if block.get(k) is not None:
                return str(block[k])
    return None


def _production_package(rec: Mapping[str, Any]) -> bool:
    return bool(_norm_symbol(rec.get("ticker"))) and isinstance(rec.get("swing"), Mapping) and isinstance(rec.get("long_term"), Mapping)


def _thesis_evidence(symbol: str, horizon: str, block: Mapping[str, Any], analysis_as_of: str) -> list[Evidence]:
    """Preserve production S2 thesis as prior evidence without inventing eligibility or scores."""
    out=[]
    status=block.get("thesis_status")
    confidence=block.get("confidence")
    if status is not None:
        out.append(_ev(symbol, f"stage2_{horizon}_thesis_status", str(status), analysis_as_of,
                       notes=("IMMUTABLE_S2_PRIOR","NON_ADDITIVE_PRIOR")))
    if confidence is not None:
        out.append(_ev(symbol, f"stage2_{horizon}_confidence", str(confidence), analysis_as_of,
                       notes=("IMMUTABLE_S2_PRIOR","NON_ADDITIVE_PRIOR")))
    return out


def map_stage2_output(records: Iterable[Mapping[str, Any]], analysis_as_of: str,
                      allowed_states: Tuple[ScopeState, ...] = (ScopeState.ELIGIBLE, ScopeState.CONDITIONAL, ScopeState.REVIEW)) -> UpstreamMapResult:
    """Translate Stage 2 output into P1 evidence contracts.

    Production contract (preferred): ``ticker`` + independent ``swing`` and
    ``long_term`` thesis packages.  Every valid production package remains in
    deep-analysis scope; S2 is research/prior and is not converted into a new
    eligibility gate or score.

    Legacy contract remains accepted for frozen regression fixtures only.
    This mapper is transport/normalization only and never recalculates a thesis,
    score, confidence, eligibility, priority, or recommendation.
    """
    rows=list(records)
    symbols=[]; evidence=[]; excluded=[]; diagnostics=[]; seen=set()

    for i,rec in enumerate(rows):
        if not isinstance(rec,Mapping):
            diagnostics.append(f"ROW_{i}:INVALID_RECORD"); continue

        if _production_package(rec):
            symbol=_norm_symbol(rec.get("ticker"))
            if symbol in seen:
                diagnostics.append(f"{symbol}:DUPLICATE_STAGE2_SYMBOL"); continue
            seen.add(symbol); symbols.append(symbol)
            evidence.extend(_thesis_evidence(symbol,"swing",rec["swing"],analysis_as_of))
            evidence.extend(_thesis_evidence(symbol,"long_term",rec["long_term"],analysis_as_of))
            continue

        # Legacy compatibility path: preserve the frozen R1 behavior exactly.
        symbol=_norm_symbol(rec.get("symbol"))
        if not symbol:
            diagnostics.append(f"ROW_{i}:MISSING_SYMBOL"); continue
        if symbol in seen:
            diagnostics.append(f"{symbol}:DUPLICATE_STAGE2_SYMBOL"); continue
        seen.add(symbol)
        state=_stage2_state(rec)
        if state is None:
            diagnostics.append(f"{symbol}:INVALID_STAGE2_STATE"); continue
        if state not in allowed_states:
            excluded.append((symbol,f"STATE_NOT_IN_SCOPE:{state.value}")); continue
        symbols.append(symbol)
        evidence.append(_ev(symbol,"stage2_eligibility",state.value,analysis_as_of,notes=("IMMUTABLE_UPSTREAM_STATE",)))
        if rec.get("data_state") is not None:
            evidence.append(_ev(symbol,"stage2_data_state",str(rec["data_state"]),analysis_as_of,notes=("IMMUTABLE_UPSTREAM_STATE",)))
        if rec.get("confidence") is not None:
            evidence.append(_ev(symbol,"stage2_confidence",rec["confidence"],analysis_as_of,unit="score",notes=("IMMUTABLE_UPSTREAM_VALUE",)))
        for name in STAGE2_BLOCKS:
            block=rec.get(name)
            if block is None: continue
            score=_get_score(block)
            if score is not None:
                evidence.append(_ev(symbol,f"stage2_{name}_score",score,analysis_as_of,unit="score",notes=("SCREENING_EVIDENCE",)))
            bstate=_get_state(block)
            if bstate is not None:
                evidence.append(_ev(symbol,f"stage2_{name}_state",bstate,analysis_as_of,notes=("SCREENING_EVIDENCE",)))
        for h in ("swing","longterm","long_term"):
            block=rec.get(h)
            if block is None: continue
            score=_get_score(block)
            if score is not None:
                evidence.append(_ev(symbol,f"stage2_{h}_score",score,analysis_as_of,unit="score",notes=("PRELIMINARY_STAGE2_HORIZON",)))
            bstate=_get_state(block)
            if bstate is not None:
                evidence.append(_ev(symbol,f"stage2_{h}_state",bstate,analysis_as_of,notes=("PRELIMINARY_STAGE2_HORIZON",)))

    scope=DeepAnalysisScope(analysis_as_of=analysis_as_of,symbols=tuple(symbols),allowed_stage2_states=allowed_states)
    return UpstreamMapResult(scope,tuple(evidence),tuple(excluded),tuple(diagnostics))

