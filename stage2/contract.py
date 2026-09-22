from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Horizon(str, Enum):
    SWING = "SWING"
    LONG_TERM = "LONG_TERM"


class EvidenceState(str, Enum):
    AVAILABLE = "AVAILABLE"
    MISSING = "MISSING"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SPECIAL_TREATMENT = "SPECIAL_TREATMENT"


class EvaluationMode(str, Enum):
    ABSOLUTE = "ABSOLUTE"
    RELATIONAL = "RELATIONAL"
    HISTORICAL = "HISTORICAL"
    DIRECTIONAL = "DIRECTIONAL"


class FindingKind(str, Enum):
    SUPPORT = "SUPPORT"
    CONTRADICTION = "CONTRADICTION"
    RISK = "RISK"
    CONTEXT = "CONTEXT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CompanyContext:
    symbol: str
    business_context: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class EvidenceRef:
    field: str
    value: Any
    state: EvidenceState
    source_stage: str = "S1"


@dataclass(frozen=True)
class Finding:
    finding_id: str
    horizon: Horizon
    family: str
    mode: EvaluationMode
    kind: FindingKind
    summary: str
    evidence: tuple[EvidenceRef, ...]
    materiality: str = "UNASSESSED"


@dataclass
class ThesisPackage:
    symbol: str
    horizon: Horizon
    thesis_status: str = "UNASSESSED"
    confidence: str = "UNASSESSED"
    main_reasons: list[str] = field(default_factory=list)
    key_contradictions: list[str] = field(default_factory=list)
    key_risks: list[str] = field(default_factory=list)
    invalidation_condition: list[str] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
