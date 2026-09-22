from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from .contract import Finding, FindingKind, Horizon, ThesisPackage

_MAT = {"UNASSESSED": 0, "MINOR": 1, "MODERATE": 2, "MATERIAL": 3}


class ThesisBuilder:
    """Convert research findings into a thesis package.

    This module does not re-read S1 evidence, screen/rank symbols, or issue
    trading recommendations. It reasons only over upstream S2 findings.
    """

    def __init__(self, symbol: str, horizon: Horizon, findings: Iterable[Finding]):
        self.symbol = symbol
        self.horizon = horizon
        self.findings = list(findings)
        if any(f.horizon != horizon for f in self.findings):
            raise ValueError("mixed horizon findings are not allowed")
        ids = [f.finding_id for f in self.findings]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate finding_id")

    @staticmethod
    def _material(f: Finding) -> int:
        return _MAT.get((f.materiality or "UNASSESSED").upper(), 0)

    def _family_state(self):
        fam = defaultdict(list)
        for f in self.findings:
            fam[f.family].append(f)
        return fam

    def _confidence(self) -> str:
        # Confidence is evidence sufficiency/consistency, not attractiveness.
        relevant = [f for f in self.findings if f.family != "BUSINESS_CONTEXT"]
        if not relevant:
            return "LOW"
        unknown = sum(f.kind == FindingKind.UNKNOWN for f in relevant)
        known = len(relevant) - unknown
        coverage = known / len(relevant)
        # Opposing findings can be a valid research result; they do not by
        # themselves lower confidence. Missing evidence does.
        if coverage >= 0.85:
            return "HIGH"
        if coverage >= 0.60:
            return "MEDIUM"
        return "LOW"

    def _status(self) -> str:
        if not self.findings:
            return "INSUFFICIENT_EVIDENCE"
        relevant = [f for f in self.findings if f.family != "BUSINESS_CONTEXT"]
        known = [f for f in relevant if f.kind != FindingKind.UNKNOWN]
        if len(known) < max(2, (len(relevant) + 2) // 3):
            return "INSUFFICIENT_EVIDENCE"

        material_contra = [f for f in known if f.kind == FindingKind.CONTRADICTION and self._material(f) >= 3]
        support_families = {f.family for f in known if f.kind == FindingKind.SUPPORT}
        contra_families = {f.family for f in known if f.kind == FindingKind.CONTRADICTION}
        risk_families = {f.family for f in known if f.kind == FindingKind.RISK}

        # Invalidation first: material contradiction in a core family is never
        # outvoted by numerous positive sub-findings.
        if material_contra:
            if len(material_contra) >= 2 or not support_families:
                return "INVALIDATED"
            return "WEAKENED"

        # Non-material contradictions are interpreted by breadth across
        # independent families, not raw finding count.
        if len(contra_families) >= 2:
            return "WEAKENED"
        if len(contra_families) == 1:
            return "PARTIALLY_CONFIRMED" if len(support_families) >= 2 else "WEAKENED"

        if support_families:
            # Risks/context do not erase a supported thesis, but prevent an
            # unconditional CONFIRMED when material enough to matter.
            material_risk = any(f.kind == FindingKind.RISK and self._material(f) >= 2 for f in known)
            if material_risk:
                return "PARTIALLY_CONFIRMED"
            # Require breadth across independent research families.
            min_breadth = 3 if self.horizon == Horizon.SWING else 3
            if len(support_families) >= min_breadth:
                return "CONFIRMED"
            return "PARTIALLY_CONFIRMED"

        return "WEAKENED"

    @staticmethod
    def _invalidation_text(f: Finding) -> str:
        templates = {
            "TREND": "Struktur tren utama berbalik bearish secara material (harga dan MA utama kehilangan susunan positif).",
            "MOMENTUM": "Momentum utama berbalik negatif secara persisten dan menjadi contradiction material.",
            "PARTICIPATION": "Partisipasi transaksi melemah material sehingga pergerakan tidak lagi didukung volume/likuiditas.",
            "RELATIVE_STRENGTH": "Kekuatan relatif berubah negatif secara konsisten pada beberapa horizon utama.",
            "FLOW": "Aliran dana berubah menjadi tekanan jual yang konsisten dan material.",
            "VOLATILITY_RISK": "Risiko volatilitas meningkat ke tingkat material dan merusak asumsi risiko Swing.",
            "GROWTH": "Pertumbuhan pendapatan/laba berubah menjadi tekanan negatif yang konsisten pada horizon terbaru dan lebih panjang.",
            "PROFITABILITY": "Margin operasi atau margin laba berubah negatif secara material.",
            "CAPITAL_EFFICIENCY": "ROIC dan mayoritas ukuran pengembalian modal/aset berubah negatif secara material.",
            "FINANCIAL_STRENGTH": "Ekuitas/coverage/liquiditas memburuk hingga menunjukkan tekanan material pada kemampuan memenuhi kewajiban.",
            "CASH_QUALITY": "Laba tidak lagi didukung arus kas operasi atau kualitas kas memburuk secara material.",
            "VALUATION": "Asumsi valuasi kehilangan validitas semantik atau berubah ekstrem tanpa dukungan fundamental yang sepadan.",
        }
        return templates.get(f.family, f"Evidence inti pada {f.family} berubah menjadi contradiction material.")

    def _invalidation_conditions(self, status: str, support: list[Finding], contra: list[Finding]) -> list[str]:
        # Conditions must be traceable to actual research families; never emit
        # an empty or generic catch-all for a thesis that has been assessed.
        material_contra = [f for f in contra if self._material(f) >= 3]
        if material_contra:
            return [self._invalidation_text(f) for f in material_contra[:3]]
        if status in {"CONFIRMED", "PARTIALLY_CONFIRMED"}:
            out=[]; seen=set()
            for f in support:
                if f.family in seen: continue
                out.append(self._invalidation_text(f)); seen.add(f.family)
                if len(out) == 3: break
            return out or ["Evidence pendukung utama belum cukup untuk menetapkan kondisi invalidasi spesifik."]
        if status == "WEAKENED":
            out=[]; seen=set()
            for f in contra:
                if f.family in seen: continue
                out.append(self._invalidation_text(f)); seen.add(f.family)
                if len(out) == 3: break
            return out or ["Evidence yang tersedia belum membentuk kondisi invalidasi spesifik di luar status tesis yang sudah melemah."]
        return ["Evidence belum cukup untuk menetapkan kondisi invalidasi yang dapat diuji."]

    def build(self) -> ThesisPackage:
        status = self._status()
        confidence = self._confidence()
        support = [f for f in self.findings if f.kind == FindingKind.SUPPORT]
        contra = sorted(
            (f for f in self.findings if f.kind == FindingKind.CONTRADICTION),
            key=self._material, reverse=True,
        )
        risks = sorted(
            (f for f in self.findings if f.kind == FindingKind.RISK),
            key=self._material, reverse=True,
        )

        # Keep user-facing reasons concise; full lineage remains in findings.
        main_reasons = []
        seen = set()
        for f in support:
            if f.family not in seen:
                main_reasons.append(f.summary); seen.add(f.family)
            if len(main_reasons) == 4: break
        key_contradictions = [f.summary for f in contra[:3]]
        key_risks = [f.summary for f in risks[:3]]

        invalidation = self._invalidation_conditions(status, support, contra)

        return ThesisPackage(
            symbol=self.symbol,
            horizon=self.horizon,
            thesis_status=status,
            confidence=confidence,
            main_reasons=main_reasons,
            key_contradictions=key_contradictions,
            key_risks=key_risks,
            invalidation_condition=invalidation,
            findings=list(self.findings),
        )
