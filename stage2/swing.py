from __future__ import annotations

import math
from typing import Any, Iterable

from .contract import EvaluationMode, Finding, FindingKind, Horizon
from .interpreter import EvidenceInterpreter


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) else x


class SwingResearch:
    """Stage-2 Swing research over one S1 canonical record.

    Ownership is deliberately narrow: research findings only.  It does not
    screen, rank, score, create a thesis status, or issue a recommendation.
    """

    horizon = Horizon.SWING

    def __init__(self, interpreter: EvidenceInterpreter):
        self.i = interpreter

    def _finding(self, fid: str, family: str, kind: FindingKind, summary: str,
                 fields: Iterable[str], mode: EvaluationMode = EvaluationMode.RELATIONAL,
                 materiality: str = "UNASSESSED") -> Finding:
        refs = tuple(self.i.evidence(f) for f in fields)
        return Finding(fid, self.horizon, family, mode, kind, summary, refs, materiality)

    def trend(self) -> Finding:
        fs = ("Price", "Price MA20", "Price MA50", "Price MA100", "Price MA200")
        vals = [_num(self.i.record.get(f)) for f in fs]
        if vals[0] is None or vals[1] is None or vals[2] is None:
            return self._finding("S2.SW.TREND.001", "TREND", FindingKind.UNKNOWN,
                                 "Struktur tren belum dapat dinilai karena evidence utama belum lengkap.", fs)
        price, ma20, ma50, ma100, ma200 = vals
        if price > ma20 > ma50 and (ma100 is None or ma50 >= ma100) and (ma200 is None or ma100 is None or ma100 >= ma200):
            return self._finding("S2.SW.TREND.001", "TREND", FindingKind.SUPPORT,
                                 "Struktur harga mendukung tren Swing yang positif.", fs, materiality="MODERATE")
        if price < ma20 < ma50 and (ma100 is None or ma50 <= ma100):
            return self._finding("S2.SW.TREND.001", "TREND", FindingKind.CONTRADICTION,
                                 "Struktur harga menunjukkan tren Swing yang melemah.", fs, materiality="MATERIAL")
        return self._finding("S2.SW.TREND.001", "TREND", FindingKind.CONTEXT,
                             "Struktur tren masih campuran dan belum menunjukkan arah yang sepenuhnya selaras.", fs)

    def momentum(self) -> list[Finding]:
        out: list[Finding] = []
        rsi, prsi = _num(self.i.record.get("RSI14")), _num(self.i.record.get("Previous RSI14"))
        macd, pmacd = _num(self.i.record.get("MACD")), _num(self.i.record.get("Previous MACD"))
        adx, dip, dim = (_num(self.i.record.get(x)) for x in ("ADX14", "DI+", "DI-"))
        if rsi is None or prsi is None:
            out.append(self._finding("S2.SW.MOM.001", "MOMENTUM", FindingKind.UNKNOWN,
                                     "Arah momentum RSI belum dapat dinilai.", ("RSI14", "Previous RSI14"), EvaluationMode.DIRECTIONAL))
        else:
            kind = FindingKind.SUPPORT if rsi >= 50 and rsi >= prsi else (FindingKind.CONTRADICTION if rsi < 50 and rsi <= prsi else FindingKind.CONTEXT)
            text = "Momentum RSI menguat dan berada pada area positif." if kind == FindingKind.SUPPORT else ("Momentum RSI melemah dan berada di bawah area netral." if kind == FindingKind.CONTRADICTION else "Momentum RSI masih positif tetapi arah perubahannya belum sepenuhnya mendukung.")
            out.append(self._finding("S2.SW.MOM.001", "MOMENTUM", kind, text,
                                     ("RSI14", "Previous RSI14"), EvaluationMode.DIRECTIONAL,
                                     materiality="MODERATE" if kind in (FindingKind.SUPPORT, FindingKind.CONTRADICTION) else "UNASSESSED"))
        if macd is None or pmacd is None:
            out.append(self._finding("S2.SW.MOM.002", "MOMENTUM", FindingKind.UNKNOWN,
                                     "Arah MACD belum dapat dinilai.", ("MACD", "Previous MACD"), EvaluationMode.DIRECTIONAL))
        else:
            kind = FindingKind.SUPPORT if macd > pmacd else (FindingKind.CONTRADICTION if macd < pmacd else FindingKind.CONTEXT)
            out.append(self._finding("S2.SW.MOM.002", "MOMENTUM", kind,
                                     "MACD menguat dibanding nilai sebelumnya." if kind == FindingKind.SUPPORT else ("MACD melemah dibanding nilai sebelumnya." if kind == FindingKind.CONTRADICTION else "MACD relatif stabil."),
                                     ("MACD", "Previous MACD"), EvaluationMode.DIRECTIONAL,
                                     materiality="MINOR" if kind in (FindingKind.SUPPORT, FindingKind.CONTRADICTION) else "UNASSESSED"))
        if None in (adx, dip, dim):
            out.append(self._finding("S2.SW.MOM.003", "MOMENTUM", FindingKind.UNKNOWN,
                                     "Kekuatan dan arah tren ADX/DI belum dapat dinilai.", ("ADX14", "DI+", "DI-")))
        else:
            if adx >= 20 and dip > dim:
                kind, text = FindingKind.SUPPORT, "Kekuatan tren dan arah DI mendukung pergerakan positif."
            elif adx >= 20 and dim > dip:
                kind, text = FindingKind.CONTRADICTION, "Kekuatan tren lebih banyak mendukung tekanan turun."
            else:
                kind, text = FindingKind.CONTEXT, "Kekuatan tren belum cukup tegas untuk menjadi konfirmasi utama."
            out.append(self._finding("S2.SW.MOM.003", "MOMENTUM", kind, text, ("ADX14", "DI+", "DI-"),
                                     materiality="MODERATE" if kind in (FindingKind.SUPPORT, FindingKind.CONTRADICTION) else "UNASSESSED"))
        return out

    def participation(self) -> Finding:
        fields = ("Volume", "Volume MA20", "Value", "ADTV30", "ADTV90")
        vol, vma, value, a30, a90 = [_num(self.i.record.get(f)) for f in fields]
        if vol is None or vma is None or a30 is None:
            return self._finding("S2.SW.PART.001", "PARTICIPATION", FindingKind.UNKNOWN,
                                 "Dukungan transaksi belum dapat dinilai karena evidence utama belum lengkap.", fields)
        support = vol >= vma
        persistence = a90 is None or a30 >= 0.75 * a90
        if support and persistence:
            return self._finding("S2.SW.PART.001", "PARTICIPATION", FindingKind.SUPPORT,
                                 "Aktivitas transaksi mendukung pergerakan harga dan likuiditas relatif terjaga.", fields, materiality="MODERATE")
        if not support and a90 is not None and a30 < 0.5 * a90:
            return self._finding("S2.SW.PART.001", "PARTICIPATION", FindingKind.CONTRADICTION,
                                 "Dukungan transaksi melemah dibanding aktivitas normalnya.", fields, materiality="MODERATE")
        return self._finding("S2.SW.PART.001", "PARTICIPATION", FindingKind.CONTEXT,
                             "Aktivitas transaksi belum memberikan konfirmasi yang kuat.", fields)

    def relative_strength(self) -> Finding:
        fields = ("RS Line 1M", "RS Line 3M", "RS Line 6M", "RS Line 9M", "RS Line 1Y")
        vals = [_num(self.i.record.get(f)) for f in fields]
        avail = [v for v in vals[:4] if v is not None]
        if len(avail) < 2:
            return self._finding("S2.SW.RS.001", "RELATIVE_STRENGTH", FindingKind.UNKNOWN,
                                 "Kekuatan relatif belum dapat dinilai dengan evidence yang cukup.", fields)
        # RS line values are interpreted by sign/direction only; returns are not double-counted here.
        pos = sum(v > 0 for v in avail)
        neg = sum(v < 0 for v in avail)
        if pos >= max(2, len(avail) - 1):
            kind, text = FindingKind.SUPPORT, "Kekuatan relatif mendukung saham dibanding benchmark pada beberapa horizon."
        elif neg >= max(2, len(avail) - 1):
            kind, text = FindingKind.CONTRADICTION, "Kekuatan relatif melemah terhadap benchmark pada beberapa horizon."
        else:
            kind, text = FindingKind.CONTEXT, "Kekuatan relatif masih campuran antar-horizon."
        return self._finding("S2.SW.RS.001", "RELATIVE_STRENGTH", kind, text, fields,
                             materiality="MODERATE" if kind in (FindingKind.SUPPORT, FindingKind.CONTRADICTION) else "UNASSESSED")

    def flow(self) -> Finding:
        fields = ("Foreign Flow", "Net Foreign Buy / Sell", "1 Month Net Foreign Flow", "3 Month Net Foreign Flow", "Bandar Accum/Dist", "Bandar Value")
        foreign = [_num(self.i.record.get(f)) for f in fields[:4]]
        bandar = _num(self.i.record.get("Bandar Accum/Dist"))
        available = [v for v in foreign if v is not None]
        if not available and bandar is None:
            return self._finding("S2.SW.FLOW.001", "FLOW", FindingKind.UNKNOWN,
                                 "Arah aliran dana belum dapat dinilai dari evidence yang tersedia.", fields)
        pos, neg = sum(v > 0 for v in available), sum(v < 0 for v in available)
        if bandar is not None:
            pos += bandar > 0; neg += bandar < 0
        if pos >= 3 and pos > neg:
            kind, text = FindingKind.SUPPORT, "Aliran dana secara umum mendukung pergerakan saham."
        elif neg >= 3 and neg > pos:
            kind, text = FindingKind.CONTRADICTION, "Aliran dana menunjukkan tekanan yang berlawanan dengan tesis kenaikan."
        else:
            kind, text = FindingKind.CONTEXT, "Aliran dana masih campuran dan belum menjadi konfirmasi utama."
        return self._finding("S2.SW.FLOW.001", "FLOW", kind, text, fields,
                             materiality="MODERATE" if kind in (FindingKind.SUPPORT, FindingKind.CONTRADICTION) else "UNASSESSED")

    def volatility_risk(self) -> Finding:
        fields = ("ATR14", "ADR14", "Beta 3Y", "StdDev 3Y", "52W High", "52W Low", "Price")
        atr, adr, beta, sd, hi, lo, price = [_num(self.i.record.get(f)) for f in fields]
        if price in (None, 0) or (atr is None and adr is None):
            return self._finding("S2.SW.RISK.001", "VOLATILITY_RISK", FindingKind.UNKNOWN,
                                 "Risiko pergerakan belum dapat dinilai dengan evidence yang cukup.", fields)
        atr_pct = abs(atr / price) * 100 if atr is not None else None
        # No universal 'good/bad' volatility threshold: flag only clearly elevated combinations.
        elevated = ((atr_pct is not None and atr_pct >= 7) or (adr is not None and abs(adr) >= 7))
        very_high_beta = beta is not None and beta >= 1.8
        if elevated and very_high_beta:
            return self._finding("S2.SW.RISK.001", "VOLATILITY_RISK", FindingKind.RISK,
                                 "Pergerakan harga relatif agresif sehingga risiko Swing perlu mendapat perhatian lebih.", fields,
                                 materiality="MODERATE")
        if elevated:
            return self._finding("S2.SW.RISK.001", "VOLATILITY_RISK", FindingKind.RISK,
                                 "Volatilitas meningkat dan dapat memperbesar risiko pergerakan harga.", fields,
                                 materiality="MINOR")
        return self._finding("S2.SW.RISK.001", "VOLATILITY_RISK", FindingKind.CONTEXT,
                             "Volatilitas belum menunjukkan risiko ekstrem dari evidence yang tersedia.", fields)

    def research(self) -> list[Finding]:
        findings = [self.trend(), *self.momentum(), self.participation(),
                    self.relative_strength(), self.flow(), self.volatility_risk()]
        # Stable IDs are the lineage contract and prevent accidental duplicate votes.
        ids = [f.finding_id for f in findings]
        if len(ids) != len(set(ids)):
            raise RuntimeError("duplicate Swing finding_id")
        return findings
