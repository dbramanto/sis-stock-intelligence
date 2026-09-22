from __future__ import annotations

import math
from typing import Any, Mapping

from .contract import (
    CompanyContext, EvidenceRef, EvidenceState, EvaluationMode,
    Finding, FindingKind, Horizon,
)


def _missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


class EvidenceInterpreter:
    """Interpret S1 canonical evidence without screening, ranking, or scoring.

    This module deliberately owns semantics only. Thesis status, confidence,
    materiality and recommendations belong to later Stage-2/Stage-3 modules.
    """

    def __init__(self, record: Mapping[str, Any], company: CompanyContext | None = None):
        self.record = record
        symbol = str(record.get("symbol", "")).strip().upper()
        if not symbol:
            raise ValueError("S2 requires S1 canonical field 'symbol'")
        self.symbol = symbol
        self.company = company or CompanyContext(symbol=symbol)
        if self.company.symbol.strip().upper() != symbol:
            raise ValueError("company context symbol does not match canonical record")

    def evidence(self, field: str, *, applicable: bool = True) -> EvidenceRef:
        value = self.record.get(field)
        if not applicable:
            state = EvidenceState.NOT_APPLICABLE
        elif field in {"PE TTM", "PE Mean 5Y", "PE +1SD 5Y", "PE -1SD 5Y"} and self.record.get("B9 PE Semantic Validity") == "SPECIAL_TREATMENT":
            state = EvidenceState.SPECIAL_TREATMENT
        elif field in {"PBV", "Derived PBV", "PBV Mean 5Y", "PBV +1SD 5Y", "PBV -1SD 5Y"} and self.record.get("B9 PBV Semantic Validity") == "SPECIAL_TREATMENT":
            state = EvidenceState.SPECIAL_TREATMENT
        else:
            state = EvidenceState.MISSING if _missing(value) else EvidenceState.AVAILABLE
        return EvidenceRef(field=field, value=value, state=state)

    def directional(
        self, *, current: str, previous: str, horizon: Horizon, family: str, finding_id: str
    ) -> Finding:
        cur, prev = self.evidence(current), self.evidence(previous)
        refs = (cur, prev)
        if any(x.state != EvidenceState.AVAILABLE for x in refs):
            return Finding(finding_id, horizon, family, EvaluationMode.DIRECTIONAL, FindingKind.UNKNOWN,
                           f"Perubahan {current} belum dapat dinilai dari evidence yang tersedia.", refs)
        delta = float(cur.value) - float(prev.value)
        if math.isclose(delta, 0.0, rel_tol=1e-12, abs_tol=1e-12):
            text = f"{current} relatif stabil dibanding nilai sebelumnya."
        elif delta > 0:
            text = f"{current} meningkat dibanding nilai sebelumnya."
        else:
            text = f"{current} menurun dibanding nilai sebelumnya."
        return Finding(finding_id, horizon, family, EvaluationMode.DIRECTIONAL, FindingKind.CONTEXT, text, refs)

    def historical_band(
        self, *, current: str, low: str, mean: str, high: str, semantic_field: str,
        horizon: Horizon, family: str, finding_id: str
    ) -> Finding:
        refs = tuple(self.evidence(x) for x in (current, low, mean, high))
        semantic = self.record.get(semantic_field)
        if semantic == "SPECIAL_TREATMENT":
            return Finding(finding_id, horizon, family, EvaluationMode.HISTORICAL, FindingKind.UNKNOWN,
                           f"{current} memerlukan perlakuan khusus; perbandingan historis normal tidak digunakan.", refs)
        if semantic != "VALID_CONTEXT" or any(x.state != EvidenceState.AVAILABLE for x in refs):
            return Finding(finding_id, horizon, family, EvaluationMode.HISTORICAL, FindingKind.UNKNOWN,
                           f"Konteks historis {current} belum cukup untuk dinilai.", refs)
        cur, lo, mid, hi = map(lambda x: float(x.value), refs)
        if cur < lo:
            pos = "di bawah kisaran historis -1SD"
        elif cur > hi:
            pos = "di atas kisaran historis +1SD"
        elif cur < mid:
            pos = "di bawah rata-rata historis"
        elif cur > mid:
            pos = "di atas rata-rata historis"
        else:
            pos = "di sekitar rata-rata historis"
        return Finding(finding_id, horizon, family, EvaluationMode.HISTORICAL, FindingKind.CONTEXT,
                       f"{current} berada {pos}.", refs)

    def relation(
        self, *, left: str, right: str, horizon: Horizon, family: str, finding_id: str,
        relation_name: str
    ) -> Finding:
        a, b = self.evidence(left), self.evidence(right)
        refs = (a, b)
        if any(x.state != EvidenceState.AVAILABLE for x in refs):
            return Finding(finding_id, horizon, family, EvaluationMode.RELATIONAL, FindingKind.UNKNOWN,
                           f"{relation_name} belum dapat dinilai karena evidence belum lengkap.", refs)
        return Finding(finding_id, horizon, family, EvaluationMode.RELATIONAL, FindingKind.CONTEXT,
                       f"{relation_name} siap dinilai dari evidence canonical tanpa mengubah nilai S1.", refs)
