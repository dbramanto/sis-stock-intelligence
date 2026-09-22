from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Any

import pandas as pd

from .contract import CompanyContext, Horizon
from .interpreter import EvidenceInterpreter
from .swing import SwingResearch
from .longterm import LongTermResearch
from .thesis import ThesisBuilder
from .output import build_symbol_research_package


@dataclass(frozen=True)
class Stage2RunResult:
    status: str
    packages: list[dict]
    issues: list[str]


def _ctx(symbol: str, contexts: Mapping[str, CompanyContext] | None) -> CompanyContext:
    if not contexts:
        return CompanyContext(symbol=symbol)
    c = contexts.get(symbol) or contexts.get(symbol.upper())
    return c if c is not None else CompanyContext(symbol=symbol)


def run_stage2(canonical: pd.DataFrame, company_contexts: Mapping[str, CompanyContext] | None = None) -> Stage2RunResult:
    """Run complete S2 research/thesis/output over an S1 canonical dataset.

    S2 does not screen, rank, score, or issue trading recommendations. Input N is
    dynamic; an empty canonical dataset is a valid no-candidate result.
    """
    if not isinstance(canonical, pd.DataFrame):
        raise TypeError("canonical must be a pandas DataFrame")
    if canonical.empty:
        return Stage2RunResult(status="PASS", packages=[], issues=[])
    if "symbol" not in canonical.columns:
        return Stage2RunResult(status="BLOCKED", packages=[], issues=["S1 canonical field 'symbol' is required"])

    symbols = canonical["symbol"].astype(str).str.strip().str.upper()
    if (symbols == "").any():
        return Stage2RunResult(status="BLOCKED", packages=[], issues=["blank symbol in S1 canonical"])
    if symbols.duplicated().any():
        dup = sorted(set(symbols[symbols.duplicated(keep=False)].tolist()))
        return Stage2RunResult(status="BLOCKED", packages=[], issues=[f"duplicate canonical symbol(s): {', '.join(dup)}"])

    packages: list[dict] = []
    issues: list[str] = []
    for (_, row), symbol in zip(canonical.iterrows(), symbols):
        record: dict[str, Any] = row.to_dict()
        record["symbol"] = symbol
        try:
            interpreter = EvidenceInterpreter(record, _ctx(symbol, company_contexts))
            swing_findings = SwingResearch(interpreter).research()
            long_findings = LongTermResearch(interpreter).research()
            swing_thesis = ThesisBuilder(symbol, Horizon.SWING, swing_findings).build()
            long_thesis = ThesisBuilder(symbol, Horizon.LONG_TERM, long_findings).build()
            packages.append(build_symbol_research_package(symbol, swing_thesis, long_thesis))
        except Exception as exc:
            issues.append(f"{symbol}: {type(exc).__name__}: {exc}")

    return Stage2RunResult(status="PASS" if not issues else "BLOCKED", packages=packages if not issues else [], issues=issues)
