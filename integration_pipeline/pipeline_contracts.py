from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from enum import Enum
from math import isfinite
from typing import Any, Optional, Tuple

CONTRACT_VERSION = "P1-R1"

class QualityState(str, Enum):
    VALID="VALID"; STALE="STALE"; PARTIAL="PARTIAL"; CONFLICT="CONFLICT"; INVALID="INVALID"; UNAVAILABLE="UNAVAILABLE"; NOT_APPLICABLE="NOT_APPLICABLE"
class FreshnessState(str, Enum):
    FRESH="FRESH"; STALE="STALE"; UNKNOWN="UNKNOWN"; FUTURE_INVALID="FUTURE_INVALID"
class ConflictState(str, Enum):
    NONE="NONE"; CONSISTENT="CONSISTENT"; PERIOD_DIFFERENCE="PERIOD_DIFFERENCE"; EVIDENCE_CONFLICT="EVIDENCE_CONFLICT"; NOT_COMPARABLE="NOT_COMPARABLE"
class EvidenceOrigin(str, Enum):
    UPSTREAM_REUSE="UPSTREAM_REUSE"; UPSTREAM_DERIVED="UPSTREAM_DERIVED"; ENRICH_RAW="ENRICH_RAW"; ENRICH_DERIVED="ENRICH_DERIVED"; EVENT_EVIDENCE="EVENT_EVIDENCE"; LLM_DERIVED="LLM_DERIVED"
class PeriodType(str, Enum):
    POINT_IN_TIME="POINT_IN_TIME"; QUARTER="QUARTER"; TTM="TTM"; FY="FY"; YTD="YTD"; DAILY="DAILY"; EVENT="EVENT"; UNKNOWN="UNKNOWN"
class ScopeState(str, Enum):
    ELIGIBLE="ELIGIBLE"; CONDITIONAL="CONDITIONAL"; REVIEW="REVIEW"

@dataclass(frozen=True)
class PeriodRef:
    period_type: PeriodType
    period_start: Optional[str]=None
    period_end: Optional[str]=None
    published_at: Optional[str]=None
    def validate(self, analysis_as_of: str) -> Tuple[str,...]:
        errs=[]
        try: a=date.fromisoformat(analysis_as_of)
        except Exception: return ("INVALID_ANALYSIS_AS_OF",)
        for name,v in (("period_start",self.period_start),("period_end",self.period_end),("published_at",self.published_at)):
            if v is not None:
                try: date.fromisoformat(v)
                except Exception: errs.append(f"INVALID_{name.upper()}")
        if errs: return tuple(errs)
        if self.period_start and self.period_end and date.fromisoformat(self.period_start)>date.fromisoformat(self.period_end): errs.append("PERIOD_START_AFTER_END")
        if self.published_at and date.fromisoformat(self.published_at)>a: errs.append("FUTURE_DATA_LEAKAGE")
        return tuple(errs)

@dataclass(frozen=True)
class Provenance:
    source_id: str
    source_type: str
    source_reference: Optional[str]
    observed_at: str
    transform_id: Optional[str]=None
    transform_version: Optional[str]=None
    def validate(self) -> Tuple[str,...]:
        errs=[]
        if not self.source_id.strip(): errs.append("MISSING_SOURCE_ID")
        if not self.source_type.strip(): errs.append("MISSING_SOURCE_TYPE")
        try: datetime.fromisoformat(self.observed_at.replace("Z","+00:00"))
        except Exception: errs.append("INVALID_OBSERVED_AT")
        if bool(self.transform_id) != bool(self.transform_version): errs.append("INCOMPLETE_TRANSFORM_VERSIONING")
        return tuple(errs)

@dataclass(frozen=True)
class DependencyRef:
    metric_id: str
    evidence_id: str
    required: bool=True

@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    symbol: str
    metric_id: str
    raw_value: Any
    normalized_value: Any
    unit: Optional[str]
    currency: Optional[str]
    origin: EvidenceOrigin
    period: PeriodRef
    provenance: Provenance
    quality_state: QualityState
    freshness_state: FreshnessState
    conflict_state: ConflictState=ConflictState.NONE
    dependencies: Tuple[DependencyRef,...]=field(default_factory=tuple)
    notes: Tuple[str,...]=field(default_factory=tuple)
    def validate(self, analysis_as_of: str) -> Tuple[str,...]:
        errs=[]
        if not self.evidence_id.strip(): errs.append("MISSING_EVIDENCE_ID")
        if not self.symbol.strip(): errs.append("MISSING_SYMBOL")
        if not self.metric_id.strip(): errs.append("MISSING_METRIC_ID")
        errs.extend(self.period.validate(analysis_as_of)); errs.extend(self.provenance.validate())
        v=self.normalized_value
        if isinstance(v,bool): errs.append("BOOLEAN_NUMERIC_NOT_ALLOWED")
        elif isinstance(v,float) and not isfinite(v): errs.append("NON_FINITE_VALUE")
        if self.quality_state in {QualityState.UNAVAILABLE,QualityState.NOT_APPLICABLE} and v is not None: errs.append("NON_NULL_VALUE_FOR_NON_VALUE_STATE")
        if self.origin in {EvidenceOrigin.UPSTREAM_DERIVED,EvidenceOrigin.ENRICH_DERIVED}:
            if not self.dependencies: errs.append("DERIVED_EVIDENCE_WITHOUT_DEPENDENCIES")
            if not self.provenance.transform_id: errs.append("DERIVED_EVIDENCE_WITHOUT_FORMULA_VERSION")
        if self.freshness_state==FreshnessState.FUTURE_INVALID and self.quality_state==QualityState.VALID: errs.append("FUTURE_EVIDENCE_CANNOT_BE_VALID")
        return tuple(dict.fromkeys(errs))
    def to_dict(self):
        d=asdict(self)
        for k in ("origin","quality_state","freshness_state","conflict_state"): d[k]=getattr(self,k).value
        d["period"]["period_type"]=self.period.period_type.value
        return d

@dataclass(frozen=True)
class DeepAnalysisScope:
    analysis_as_of: str
    symbols: Tuple[str,...]
    allowed_stage2_states: Tuple[ScopeState,...]=(ScopeState.ELIGIBLE,ScopeState.CONDITIONAL,ScopeState.REVIEW)
    def validate(self) -> Tuple[str,...]:
        errs=[]
        try: date.fromisoformat(self.analysis_as_of)
        except Exception: errs.append("INVALID_ANALYSIS_AS_OF")
        cleaned=[s.strip().upper() for s in self.symbols if isinstance(s,str)]
        if len(cleaned)!=len(self.symbols) or any(not s for s in cleaned): errs.append("INVALID_SYMBOL")
        if len(set(cleaned))!=len(cleaned): errs.append("DUPLICATE_SYMBOL")
        return tuple(errs)

@dataclass(frozen=True)
class ContractEnvelope:
    scope: DeepAnalysisScope
    evidence: Tuple[Evidence,...]
    contract_version: str=CONTRACT_VERSION
    def validate(self) -> Tuple[str,...]:
        errs=list(self.scope.validate())
        scope=set(s.upper() for s in self.scope.symbols)
        seen=set()
        for e in self.evidence:
            if e.evidence_id in seen: errs.append("DUPLICATE_EVIDENCE_ID")
            seen.add(e.evidence_id)
            if e.symbol.upper() not in scope: errs.append(f"OUT_OF_SCOPE_EVIDENCE:{e.symbol}")
            errs.extend(f"{e.evidence_id}:{x}" for x in e.validate(self.scope.analysis_as_of))
        return tuple(dict.fromkeys(errs))
