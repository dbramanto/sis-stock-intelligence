from __future__ import annotations

import math
from typing import Any, Iterable

from .contract import EvaluationMode, Finding, FindingKind, Horizon
from .interpreter import EvidenceInterpreter


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool): return None
    try: x=float(v)
    except (TypeError, ValueError): return None
    return None if math.isnan(x) else x


class LongTermResearch:
    """Stage-2 Long-Term research over one S1 canonical record.

    Produces research findings only. It does not screen, rank, score, assign a
    thesis status, or issue a recommendation.
    """
    horizon=Horizon.LONG_TERM
    def __init__(self, interpreter: EvidenceInterpreter): self.i=interpreter

    def _finding(self,fid:str,family:str,kind:FindingKind,summary:str,fields:Iterable[str],
                 mode:EvaluationMode=EvaluationMode.RELATIONAL,materiality:str="UNASSESSED") -> Finding:
        return Finding(fid,self.horizon,family,mode,kind,summary,
                       tuple(self.i.evidence(f) for f in fields),materiality)

    def growth(self) -> list[Finding]:
        fields=("Revenue Quarterly YoY","Revenue Annual YoY","Revenue Growth 3Y",
                "Net Income Quarterly YoY","Net Income Annual YoY",
                "EPS Quarter YoY","EPS Annual YoY","EPS 3Y CAGR")
        vals={f:_num(self.i.record.get(f)) for f in fields}
        available=[v for v in vals.values() if v is not None]
        if len(available)<4:
            return [self._finding("S2.LT.GROWTH.001","GROWTH",FindingKind.UNKNOWN,
                    "Pertumbuhan belum dapat dinilai dengan evidence yang cukup.",fields)]
        recent=[vals[f] for f in ("Revenue Quarterly YoY","Net Income Quarterly YoY","EPS Quarter YoY") if vals[f] is not None]
        annual=[vals[f] for f in ("Revenue Annual YoY","Net Income Annual YoY","EPS Annual YoY") if vals[f] is not None]
        long=[vals[f] for f in ("Revenue Growth 3Y","EPS 3Y CAGR") if vals[f] is not None]
        pos=lambda xs: bool(xs) and sum(x>0 for x in xs)>=max(1,len(xs)-1)
        neg=lambda xs: bool(xs) and sum(x<0 for x in xs)>=max(1,len(xs)-1)
        if pos(recent) and pos(annual) and (not long or pos(long)):
            kind,text,mat=FindingKind.SUPPORT,"Pertumbuhan pendapatan/laba relatif selaras pada horizon terbaru dan lebih panjang.","MODERATE"
        elif neg(recent) and (neg(annual) or neg(long)):
            kind,text,mat=FindingKind.CONTRADICTION,"Pertumbuhan terbaru dan rekam yang lebih panjang sama-sama menunjukkan tekanan.","MATERIAL"
        elif pos(recent) and (neg(annual) or neg(long)):
            kind,text,mat=FindingKind.CONTEXT,"Pertumbuhan terbaru membaik, tetapi belum konsisten dengan rekam yang lebih panjang.","UNASSESSED"
        elif neg(recent) and (pos(annual) or pos(long)):
            kind,text,mat=FindingKind.CONTRADICTION,"Pertumbuhan terbaru melemah meskipun rekam yang lebih panjang masih lebih baik.","MODERATE"
        else:
            kind,text,mat=FindingKind.CONTEXT,"Pertumbuhan masih campuran antar-horizon dan belum membentuk pola yang konsisten.","UNASSESSED"
        return [self._finding("S2.LT.GROWTH.001","GROWTH",kind,text,fields,EvaluationMode.DIRECTIONAL,materiality=mat)]

    def profitability(self) -> Finding:
        fields=("Gross Margin TTM","Operating Margin TTM","Net Profit Margin TTM","Avg Net Profit Margin 5Y")
        gm,om,nm,avg=[_num(self.i.record.get(f)) for f in fields]
        if nm is None or om is None:
            return self._finding("S2.LT.PROFIT.001","PROFITABILITY",FindingKind.UNKNOWN,
                                 "Profitabilitas belum dapat dinilai karena evidence utama belum lengkap.",fields)
        if nm>0 and om>0 and (avg is None or nm>=avg):
            kind,text,mat=FindingKind.SUPPORT,"Profitabilitas positif dan margin laba tidak berada di bawah kemampuan historisnya.","MODERATE"
        elif nm<0 or om<0:
            kind,text,mat=FindingKind.CONTRADICTION,"Profitabilitas menunjukkan tekanan karena margin utama berada pada area negatif.","MATERIAL"
        elif avg is not None and nm<avg:
            kind,text,mat=FindingKind.CONTEXT,"Perusahaan masih mencetak margin positif, tetapi margin laba berada di bawah rata-rata historisnya.","UNASSESSED"
        else:
            kind,text,mat=FindingKind.CONTEXT,"Profitabilitas positif tetapi belum memberi konfirmasi kualitas yang kuat.","UNASSESSED"
        return self._finding("S2.LT.PROFIT.001","PROFITABILITY",kind,text,fields,EvaluationMode.HISTORICAL,materiality=mat)

    def capital_efficiency(self) -> Finding:
        fields=("ROIC TTM","ROE TTM","ROCE TTM","ROA TTM","Asset Turnover","Avg ROE 3Y")
        roic,roe,roce,roa,turn,avgroe=[_num(self.i.record.get(f)) for f in fields]
        core=[x for x in (roic,roe,roce,roa) if x is not None]
        if len(core)<2:
            return self._finding("S2.LT.EFF.001","CAPITAL_EFFICIENCY",FindingKind.UNKNOWN,
                                 "Efisiensi modal belum dapat dinilai dengan evidence yang cukup.",fields)
        positive=sum(x>0 for x in core); negative=sum(x<0 for x in core)
        if roic is not None and roic>0 and positive>=max(2,len(core)-1):
            kind,text,mat=FindingKind.SUPPORT,"Pengembalian modal dan aset secara umum menunjukkan efisiensi yang positif.","MODERATE"
        elif negative>=max(2,len(core)-1) or (roic is not None and roic<0):
            kind,text,mat=FindingKind.CONTRADICTION,"Efisiensi penggunaan modal menunjukkan tekanan pada beberapa ukuran utama.","MATERIAL"
        else:
            kind,text,mat=FindingKind.CONTEXT,"Efisiensi modal masih campuran dan belum memberikan konfirmasi yang kuat.","UNASSESSED"
        return self._finding("S2.LT.EFF.001","CAPITAL_EFFICIENCY",kind,text,fields,materiality=mat)

    def financial_strength(self) -> Finding:
        fields=("Cash","Short Term Investments","Current Assets","Current Liabilities",
                "Short Term Debt Quarter","Long Term Debt Quarter","Total Debt Quarter","Total Equity Quarter",
                "Interest Coverage TTM","Finance Cost TTM")
        cash,sti,ca,cl,sd,ld,debt,equity,ic,fc=[_num(self.i.record.get(f)) for f in fields]
        if debt is None or equity is None:
            return self._finding("S2.LT.FIN.001","FINANCIAL_STRENGTH",FindingKind.UNKNOWN,
                                 "Kekuatan keuangan belum dapat dinilai karena evidence utama belum lengkap.",fields)
        liquid=(cash or 0)+(sti or 0)
        liquidity_ok=(ca is not None and cl is not None and ca>=cl)
        coverage_bad=(ic is not None and ic<1)
        equity_bad=equity<=0
        debt_pressure=debt>0 and liquid<debt and not liquidity_ok
        if equity_bad or coverage_bad:
            kind,text,mat=FindingKind.CONTRADICTION,"Struktur keuangan menunjukkan tekanan material pada kemampuan penyangga kewajiban.","MATERIAL"
        elif debt_pressure:
            kind,text,mat=FindingKind.RISK,"Utang lebih besar daripada likuiditas yang tersedia dan posisi lancar belum memberi bantalan kuat.","MODERATE"
        elif liquidity_ok and (ic is None or ic>=1):
            kind,text,mat=FindingKind.SUPPORT,"Likuiditas dan kemampuan menanggung kewajiban belum menunjukkan tekanan utama.","MODERATE"
        else:
            kind,text,mat=FindingKind.CONTEXT,"Kekuatan keuangan masih memerlukan konteks tambahan sebelum menjadi konfirmasi utama.","UNASSESSED"
        return self._finding("S2.LT.FIN.001","FINANCIAL_STRENGTH",kind,text,fields,materiality=mat)

    def cash_quality(self) -> Finding:
        fields=("Net Income TTM","Cash From Operations TTM","Operating Cash Flow Quarter","CAPEX TTM","Free Cash Flow TTM")
        ni,ocf,ocfq,capex,fcf=[_num(self.i.record.get(f)) for f in fields]
        if ni is None or ocf is None:
            return self._finding("S2.LT.CASH.001","CASH_QUALITY",FindingKind.UNKNOWN,
                                 "Kualitas laba dan arus kas belum dapat dinilai karena evidence utama belum lengkap.",fields)
        if ni>0 and ocf>0 and (fcf is None or fcf>=0):
            kind,text,mat=FindingKind.SUPPORT,"Laba positif didukung arus kas operasi; kualitas kas secara umum mendukung laba.","MODERATE"
        elif ni>0 and ocf<=0:
            kind,text,mat=FindingKind.CONTRADICTION,"Laba positif belum didukung arus kas operasi, sehingga kualitas laba perlu dicermati.","MATERIAL"
        elif ni>0 and ocf>0 and fcf is not None and fcf<0:
            kind,text,mat=FindingKind.RISK,"Arus kas operasi positif, tetapi arus kas bebas masih tertekan setelah kebutuhan investasi.","MODERATE"
        elif ni<=0 and ocf>0:
            kind,text,mat=FindingKind.CONTEXT,"Laba masih tertekan, tetapi operasi tetap menghasilkan kas; pola ini memerlukan konteks lebih lanjut.","UNASSESSED"
        else:
            kind,text,mat=FindingKind.CONTRADICTION,"Laba dan arus kas operasi sama-sama belum mendukung kualitas fundamental.","MATERIAL"
        return self._finding("S2.LT.CASH.001","CASH_QUALITY",kind,text,fields,materiality=mat)

    def valuation(self) -> list[Finding]:
        out=[]
        out.append(self.i.historical_band(current="PE TTM",low="PE -1SD 5Y",mean="PE Mean 5Y",high="PE +1SD 5Y",
                   semantic_field="B9 PE Semantic Validity",horizon=self.horizon,family="VALUATION",finding_id="S2.LT.VAL.001"))
        out.append(self.i.historical_band(current="PBV",low="PBV -1SD 5Y",mean="PBV Mean 5Y",high="PBV +1SD 5Y",
                   semantic_field="B9 PBV Semantic Validity",horizon=self.horizon,family="VALUATION",finding_id="S2.LT.VAL.002"))
        fields=("EV/EBITDA TTM","Earnings Yield TTM","Forward PE","PEG")
        avail=sum(_num(self.i.record.get(f)) is not None for f in fields)
        out.append(self._finding("S2.LT.VAL.003","VALUATION",FindingKind.CONTEXT if avail>=2 else FindingKind.UNKNOWN,
                    "Valuasi lintas-multiple tersedia sebagai konteks, bukan sebagai keputusan murah/mahal yang berdiri sendiri." if avail>=2 else "Konteks valuasi lintas-multiple belum cukup lengkap.",fields))
        return out

    def business_context(self) -> Finding:
        # Sector applicability comes only from explicit CompanyContext.
        # Never infer company type from populated or missing B10 fields.
        ctx = (self.i.company.business_context or "").strip().upper()
        groups = {
            "BANKING": ("NIM", "CASA Ratio", "NPL Gross", "CAR", "LDR"),
            "MINING": ("Mining Properties",),
            "PLANTATION": ("Plantations",),
            "PROPERTY": ("Investment Properties",),
            "OIL_GAS": ("Oil and Gas Assets",),
        }
        fields = tuple(x for xs in groups.values() for x in xs)
        if not ctx:
            return self._finding("S2.LT.CTX.001", "BUSINESS_CONTEXT", FindingKind.UNKNOWN,
                "Konteks bisnis khusus belum tersedia; applicability evidence sektoral tidak ditebak.", fields)
        applicable = set(groups.get(ctx, ()))
        refs = tuple(self.i.evidence(f, applicable=f in applicable) for f in fields)
        if ctx in groups:
            text = f"Konteks bisnis {ctx} digunakan untuk menentukan applicability evidence sektoral."
        else:
            text = f"Konteks bisnis {ctx} tersedia, tetapi belum memiliki aturan evidence sektoral khusus."
        return Finding("S2.LT.CTX.001", self.horizon, "BUSINESS_CONTEXT",
            EvaluationMode.RELATIONAL, FindingKind.CONTEXT, text, refs, "UNASSESSED")

    def research(self) -> list[Finding]:
        findings=[*self.growth(),self.profitability(),self.capital_efficiency(),self.financial_strength(),
                  self.cash_quality(),*self.valuation(),self.business_context()]
        ids=[f.finding_id for f in findings]
        if len(ids)!=len(set(ids)): raise RuntimeError("duplicate Long-Term finding_id")
        return findings
