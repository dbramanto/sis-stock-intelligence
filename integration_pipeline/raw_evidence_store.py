from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple
from pipeline_contracts import Evidence, EvidenceOrigin, QualityState

STORE_VERSION = "P3-R1"
RAW_ORIGINS = {EvidenceOrigin.ENRICH_RAW, EvidenceOrigin.EVENT_EVIDENCE}

@dataclass(frozen=True)
class StoreDiagnostic:
    code: str
    evidence_id: Optional[str] = None
    detail: Optional[str] = None

@dataclass(frozen=True)
class IngestResult:
    accepted_ids: Tuple[str, ...] = ()
    rejected_ids: Tuple[str, ...] = ()
    diagnostics: Tuple[StoreDiagnostic, ...] = ()

class RawEvidenceStore:
    """In-memory append-only store for validated raw enrichment evidence.

    P3 owns storage/provenance integrity only. It does not derive metrics,
    reconcile conflicts, choose providers, or build Stage 3 payloads.
    """
    def __init__(self, *, analysis_as_of: str, scope_symbols: Iterable[str]):
        self.analysis_as_of = analysis_as_of
        syms = tuple(str(s).strip().upper() for s in scope_symbols)
        if any(not s for s in syms) or len(set(syms)) != len(syms):
            raise ValueError("INVALID_STORE_SCOPE")
        self._scope = frozenset(syms)
        self._items: Dict[str, Evidence] = {}

    @property
    def size(self) -> int:
        return len(self._items)

    @property
    def scope_symbols(self) -> Tuple[str, ...]:
        return tuple(sorted(self._scope))

    def get(self, evidence_id: str) -> Optional[Evidence]:
        return self._items.get(evidence_id)

    def all(self) -> Tuple[Evidence, ...]:
        return tuple(self._items[k] for k in sorted(self._items))

    def by_symbol(self, symbol: str) -> Tuple[Evidence, ...]:
        s = str(symbol).strip().upper()
        return tuple(e for e in self.all() if e.symbol.upper() == s)

    def by_metric(self, metric_id: str, *, symbol: Optional[str] = None) -> Tuple[Evidence, ...]:
        m = str(metric_id).strip()
        s = str(symbol).strip().upper() if symbol is not None else None
        return tuple(e for e in self.all() if e.metric_id == m and (s is None or e.symbol.upper() == s))

    def ingest(self, evidence: Evidence) -> IngestResult:
        eid = getattr(evidence, "evidence_id", "") or "<UNKNOWN>"
        diags = []
        if not isinstance(evidence, Evidence):
            return IngestResult(rejected_ids=(eid,), diagnostics=(StoreDiagnostic("INVALID_EVIDENCE_OBJECT", eid),))
        if evidence.symbol.upper() not in self._scope:
            return IngestResult(rejected_ids=(eid,), diagnostics=(StoreDiagnostic("OUT_OF_SCOPE_EVIDENCE", eid, evidence.symbol),))
        if evidence.origin not in RAW_ORIGINS:
            return IngestResult(rejected_ids=(eid,), diagnostics=(StoreDiagnostic("NON_RAW_ORIGIN_REJECTED", eid, evidence.origin.value),))
        errs = evidence.validate(self.analysis_as_of)
        if errs:
            return IngestResult(rejected_ids=(eid,), diagnostics=tuple(StoreDiagnostic("CONTRACT_INVALID", eid, x) for x in errs))
        if eid in self._items:
            # Append-only/idempotent: exact replay is harmless; divergent replay is blocked.
            if self._items[eid] == evidence:
                return IngestResult(accepted_ids=(eid,), diagnostics=(StoreDiagnostic("IDEMPOTENT_REPLAY", eid),))
            return IngestResult(rejected_ids=(eid,), diagnostics=(StoreDiagnostic("DUPLICATE_EVIDENCE_ID_CONFLICT", eid),))
        self._items[eid] = evidence
        return IngestResult(accepted_ids=(eid,))

    def ingest_many(self, evidence_items: Iterable[Evidence]) -> IngestResult:
        accepted=[]; rejected=[]; diags=[]
        for e in evidence_items:
            r=self.ingest(e)
            accepted.extend(r.accepted_ids); rejected.extend(r.rejected_ids); diags.extend(r.diagnostics)
        return IngestResult(tuple(accepted), tuple(rejected), tuple(diags))

    def provenance_completeness(self) -> Tuple[StoreDiagnostic, ...]:
        out=[]
        for e in self.all():
            for err in e.provenance.validate():
                out.append(StoreDiagnostic("PROVENANCE_INVALID", e.evidence_id, err))
            if not e.provenance.source_reference:
                out.append(StoreDiagnostic("SOURCE_REFERENCE_MISSING", e.evidence_id))
        return tuple(out)
