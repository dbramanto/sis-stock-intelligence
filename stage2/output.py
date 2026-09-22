from __future__ import annotations

from dataclasses import asdict
from typing import Iterable

from .contract import Horizon, ThesisPackage

_ALLOWED_STATUS = {"CONFIRMED","PARTIALLY_CONFIRMED","WEAKENED","INVALIDATED","INSUFFICIENT_EVIDENCE"}
_ALLOWED_CONF = {"HIGH","MEDIUM","LOW"}


def _lineage(p: ThesisPackage) -> list[dict]:
    out=[]
    for f in p.findings:
        out.append({
            "finding_id": f.finding_id,
            "family": f.family,
            "kind": f.kind.value,
            "mode": f.mode.value,
            "materiality": f.materiality,
            "evidence": [
                {"field": e.field, "state": e.state.value, "source_stage": e.source_stage}
                for e in f.evidence
            ],
        })
    return out


def serialize_thesis(p: ThesisPackage) -> dict:
    if p.thesis_status not in _ALLOWED_STATUS:
        raise ValueError(f"invalid thesis_status: {p.thesis_status}")
    if p.confidence not in _ALLOWED_CONF:
        raise ValueError(f"invalid confidence: {p.confidence}")
    return {
        "ticker": p.symbol,
        "horizon": p.horizon.value,
        "thesis_status": p.thesis_status,
        "confidence": p.confidence,
        "main_reasons": list(p.main_reasons),
        "key_contradictions": list(p.key_contradictions),
        "key_risks": list(p.key_risks),
        "invalidation_condition": list(p.invalidation_condition),
        "evidence_lineage": _lineage(p),
    }


def build_research_package(packages: Iterable[ThesisPackage]) -> list[dict]:
    """Final S2 -> S3 contract. No ranking, score, or recommendation."""
    items=list(packages)
    seen=set()
    for p in items:
        key=(p.symbol, p.horizon.value)
        if key in seen:
            raise ValueError(f"duplicate thesis package: {key}")
        seen.add(key)
    # Stable deterministic output only; alphabetical ordering is not ranking.
    return [serialize_thesis(p) for p in sorted(items, key=lambda x:(x.symbol, x.horizon.value))]


def build_symbol_research_package(symbol: str, swing: ThesisPackage, long_term: ThesisPackage) -> dict:
    if swing.symbol != symbol or long_term.symbol != symbol:
        raise ValueError("symbol mismatch")
    if swing.horizon != Horizon.SWING or long_term.horizon != Horizon.LONG_TERM:
        raise ValueError("expected independent SWING and LONG_TERM packages")
    return {
        "ticker": symbol,
        "swing": serialize_thesis(swing),
        "long_term": serialize_thesis(long_term),
    }
