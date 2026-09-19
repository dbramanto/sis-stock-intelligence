
from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any, Iterable, Mapping, Protocol
import math

class AcquisitionState(str, Enum):
    ACQUIRED = "ACQUIRED"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"
    REJECTED = "REJECTED"

@dataclass(frozen=True)
class AcquisitionRequest:
    symbols: tuple[str, ...]
    analysis_as_of: str
    dataset: str

@dataclass(frozen=True)
class RawRecord:
    symbol: str
    dataset: str
    payload: Mapping[str, Any]
    source_id: str
    source_type: str
    source_reference: str | None
    observed_at: str
    as_of_date: str | None = None
    period_type: str | None = None

@dataclass(frozen=True)
class AcquisitionResult:
    provider_id: str
    dataset: str
    state: AcquisitionState
    requested_symbols: tuple[str, ...]
    records: tuple[RawRecord, ...]
    missing_symbols: tuple[str, ...]
    errors: tuple[str, ...]

    def to_dict(self):
        d = asdict(self)
        d["state"] = self.state.value
        return d

class ProviderAdapter(Protocol):
    provider_id: str
    supported_datasets: frozenset[str]
    def fetch(self, request: AcquisitionRequest) -> Iterable[RawRecord]: ...

def _clean_symbols(symbols: Iterable[str]) -> tuple[str, ...]:
    out=[]
    seen=set()
    for raw in symbols:
        s=str(raw).strip().upper()
        if not s:
            raise ValueError("empty symbol")
        if s in seen:
            raise ValueError(f"duplicate requested symbol: {s}")
        seen.add(s); out.append(s)
    if not out:
        raise ValueError("empty acquisition scope")
    return tuple(out)

def acquire(adapter: ProviderAdapter, request: AcquisitionRequest) -> AcquisitionResult:
    symbols=_clean_symbols(request.symbols)
    if request.dataset not in adapter.supported_datasets:
        return AcquisitionResult(adapter.provider_id, request.dataset, AcquisitionState.REJECTED,
                                 symbols, (), symbols, ("dataset not supported by provider",))
    try:
        raw=list(adapter.fetch(AcquisitionRequest(symbols, request.analysis_as_of, request.dataset)))
    except Exception as exc:
        # Provider failure must degrade gracefully; it must never delete the requested universe.
        return AcquisitionResult(adapter.provider_id, request.dataset, AcquisitionState.UNAVAILABLE,
                                 symbols, (), symbols, (f"provider failure: {type(exc).__name__}",))

    allowed=set(symbols)
    records=[]
    seen=set()
    errors=[]
    for rec in raw:
        s=rec.symbol.strip().upper()
        if s not in allowed:
            errors.append(f"out-of-scope record rejected: {s}")
            continue
        key=(s, rec.dataset, rec.source_id, rec.as_of_date, rec.period_type)
        if key in seen:
            errors.append(f"duplicate raw record rejected: {s}")
            continue
        if rec.dataset != request.dataset:
            errors.append(f"dataset mismatch rejected: {s}")
            continue
        if not rec.source_id or not rec.source_type or not rec.observed_at:
            errors.append(f"incomplete provenance rejected: {s}")
            continue
        records.append(RawRecord(s, rec.dataset, dict(rec.payload), rec.source_id, rec.source_type,
                                 rec.source_reference, rec.observed_at, rec.as_of_date, rec.period_type))
        seen.add(key)

    present={r.symbol for r in records}
    missing=tuple(s for s in symbols if s not in present)
    if not records:
        state=AcquisitionState.UNAVAILABLE if not errors else AcquisitionState.REJECTED
    elif missing or errors:
        state=AcquisitionState.PARTIAL
    else:
        state=AcquisitionState.ACQUIRED
    return AcquisitionResult(adapter.provider_id, request.dataset, state, symbols,
                             tuple(records), missing, tuple(errors))

class MemoryAdapter:
    """Deterministic test/reference adapter. Real IDX/OHLCV adapters implement the same contract."""
    def __init__(self, provider_id: str, supported_datasets: Iterable[str], records: Iterable[RawRecord], fail=False):
        self.provider_id=provider_id
        self.supported_datasets=frozenset(supported_datasets)
        self._records=tuple(records)
        self._fail=fail
    def fetch(self, request: AcquisitionRequest):
        if self._fail:
            raise ConnectionError("simulated provider outage")
        wanted=set(request.symbols)
        return [r for r in self._records if r.symbol.upper() in wanted and r.dataset == request.dataset]

class ProviderRegistry:
    def __init__(self):
        self._providers={}
    def register(self, adapter: ProviderAdapter):
        if adapter.provider_id in self._providers:
            raise ValueError("duplicate provider_id")
        self._providers[adapter.provider_id]=adapter
    def get(self, provider_id: str):
        return self._providers[provider_id]
    def providers_for(self, dataset: str):
        return tuple(sorted(p.provider_id for p in self._providers.values()
                            if dataset in p.supported_datasets))
