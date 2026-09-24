
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence
from integration_pipeline.pipeline_contracts import Evidence, QualityState
from integration_pipeline.upstream_mapper import map_stage2_output
from integration_pipeline.raw_evidence_store import RawEvidenceStore
from integration_pipeline.validation_gate import run_gate
from integration_pipeline.derivation_engine import derive_metric, DerivationError
from integration_pipeline.pipeline_p6_reconciliation import ComparableEvidence, reconcile
from integration_pipeline.pipeline_p9_payload import MetricEvidence, build_stage3_payload, validate_payload_shape

@dataclass(frozen=True)
class DerivationRequest:
    symbol: str
    metric_id: str
    dependency_metric_ids: tuple[str,...]

@dataclass(frozen=True)
class PipelineRunResult:
    state: str
    scope_symbols: tuple[str,...]
    payloads: tuple[dict,...]
    diagnostics: tuple[str,...]
    rejected_evidence_ids: tuple[str,...]
    reconciliation_states: tuple[tuple[str,str,str],...]

def _ce(e: Evidence) -> ComparableEvidence:
    return ComparableEvidence(
        symbol=e.symbol, metric_id=e.metric_id, value=e.normalized_value,
        unit=e.unit, currency=e.currency, period_type=e.period.period_type.value,
        period_start=e.period.period_start, period_end=e.period.period_end,
        adjustment_basis=None, source_id=e.provenance.source_id,
        quality_state=e.quality_state.value
    )

STAGE3_METRIC_ALIAS = {
    # Pipeline keeps semantic TTM suffix; frozen 3B contract names this field gross_margin.
    "gross_margin_ttm": "gross_margin",
}

def _me(e: Evidence) -> MetricEvidence:
    metric_id = STAGE3_METRIC_ALIAS.get(e.metric_id, e.metric_id)
    return MetricEvidence(metric_id,e.normalized_value,e.quality_state.value,
                          e.provenance.source_id,e.period.period_end)

def run_pipeline(*, stage2_records: Iterable[Mapping[str,Any]], analysis_as_of: str,
                 raw_evidence: Iterable[Evidence]=(), derivations: Sequence[DerivationRequest]=(),
                 ohlcv_by_symbol: Mapping[str,list]|None=None,
                 canonical_by_symbol: Mapping[str,Mapping]|None=None,
                 business_context_by_symbol: Mapping[str,Mapping]|None=None,
                 sector_context_by_symbol: Mapping[str,Mapping]|None=None,
                 catalyst_events_by_symbol: Mapping[str,list]|None=None) -> PipelineRunResult:
    diagnostics=[]
    mapped=map_stage2_output(stage2_records,analysis_as_of)
    diagnostics.extend(mapped.diagnostics)
    if mapped.scope.validate():
        return PipelineRunResult("BLOCKED",(),(),tuple(mapped.scope.validate()),(),())
    scope=tuple(mapped.scope.symbols)
    if not scope:
        return PipelineRunResult("BLOCKED",(),(),tuple(diagnostics+["EMPTY_DEEP_ANALYSIS_SCOPE"]),(),())

    # P3 append-only raw evidence store.
    store=RawEvidenceStore(analysis_as_of=analysis_as_of,scope_symbols=scope)
    ing=store.ingest_many(raw_evidence)
    diagnostics.extend(f"P3:{d.code}:{d.evidence_id or ''}" for d in ing.diagnostics)

    # P4 semantic/period/freshness gate.
    gated=run_gate(store.all(),analysis_as_of=analysis_as_of)
    diagnostics.extend(f"P4:{d.code}:{d.evidence_id}" for d in gated.diagnostics)
    accepted=list(gated.accepted)
    # Preserve rejection lineage from both P3 contract/store gate and P4 semantic gate.
    rejected_ids=list(ing.rejected_ids)+[e.evidence_id for e in gated.rejected]

    # P5 deterministic derivation plan. Dependencies must already be accepted evidence.
    derived=[]
    by_symbol={}
    for e in accepted:
        by_symbol.setdefault(e.symbol.upper(),{}).setdefault(e.metric_id,[]).append(e)
    for req in derivations:
        sym=req.symbol.upper()
        deps={}
        ambiguous=False
        for mid in req.dependency_metric_ids:
            xs=by_symbol.get(sym,{}).get(mid,[])
            if len(xs)!=1:
                diagnostics.append(f"P5:{sym}:{req.metric_id}:DEPENDENCY_{mid}_COUNT_{len(xs)}")
                ambiguous=True; break
            deps[mid]=xs[0]
        if ambiguous: continue
        try:
            d=derive_metric(sym,req.metric_id,deps,analysis_as_of=analysis_as_of)
            derived.append(d)
            by_symbol.setdefault(sym,{}).setdefault(d.metric_id,[]).append(d)
        except DerivationError as exc:
            diagnostics.append(f"P5:{sym}:{req.metric_id}:{exc}")

    # P6 reconciliation only when an upstream evidence metric and enrichment metric
    # share the same metric_id. No winner is selected.
    rec_states=[]
    upstream_by={}
    for e in mapped.evidence:
        upstream_by.setdefault((e.symbol.upper(),e.metric_id),[]).append(e)
    for e in accepted+derived:
        ups=upstream_by.get((e.symbol.upper(),e.metric_id),[])
        for u in ups:
            rr=reconcile(_ce(u),_ce(e))
            rec_states.append((e.symbol.upper(),e.metric_id,rr.state.value))

    # P9 payload builder. Stage2 source object is passed through by symbol.
    s2rows={str(x.get("ticker",x.get("symbol",""))).strip().upper():dict(x) for x in stage2_records
            if isinstance(x,Mapping) and str(x.get("ticker",x.get("symbol",""))).strip()}
    payloads=[]
    for sym in scope:
        evs=[_me(e) for e in accepted+derived if e.symbol.upper()==sym]
        p=build_stage3_payload(
            sym,s2rows[sym],evs,
            ohlcv=(ohlcv_by_symbol or {}).get(sym,[]),
            canonical_record=(canonical_by_symbol or {}).get(sym),
            business_context=(business_context_by_symbol or {}).get(sym),
            sector_context=(sector_context_by_symbol or {}).get(sym),
            catalyst_events=(catalyst_events_by_symbol or {}).get(sym,[]),
            analysis_as_of=analysis_as_of)
        if not validate_payload_shape(p):
            diagnostics.append(f"P9:{sym}:INVALID_PAYLOAD_SHAPE")
            continue
        payloads.append(p)

    state="PASS"
    if rejected_ids or diagnostics:
        state="PARTIAL"
    if len(payloads)!=len(scope):
        state="BLOCKED"
    return PipelineRunResult(state,scope,tuple(payloads),tuple(diagnostics),
                             tuple(rejected_ids),tuple(rec_states))
