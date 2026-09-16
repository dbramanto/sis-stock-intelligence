from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import math
import re

B1_COLS = [
    "volume","volume_ma20","price_ma20","price_ma50","rsi14","adtv30","price",
    "price_ma200","adx14","di_plus14","di_minus14","macd","prev_macd","prev_rsi14",
    "atr14","adr14","value","rs3m","rs6m","rs9m"
]
B2_COLS = [
    "volume","volume_ma20","price_ma20","price_ma50","rsi14","adtv30","price",
    "npm_ttm","roic_ttm","piotroski","earnings_yield_ttm","de_quarter","eps_yoy"
]
B3_COLS = [
    "volume","volume_ma20","price_ma20","price_ma50","rsi14","adtv30","price",
    "ocf_q","fcf_ttm","fcf_q","ni_q","ni_annual","ni_ttm","ni_ytd"
]

SYMBOL_RE = re.compile(r"^[A-Z]{4}$")

def _num(x: str) -> Optional[float]:
    s = x.strip()
    if s in {"", "-", "—", "N/A", "NA"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1].strip()
    pct = s.endswith("%")
    if pct:
        s = s[:-1]
    mult = 1.0
    if s.endswith(" B"):
        mult, s = 1e9, s[:-2]
    elif s.endswith(" M"):
        mult, s = 1e6, s[:-2]
    s = s.replace(",", "").strip()
    try:
        v = float(s) * mult
    except ValueError:
        return None
    return -v if neg else v

def parse_fixture(text: str) -> Dict[int, Dict[str, Dict[str, Optional[float]]]]:
    parts = re.split(r"(?m)^Batch ([123])\s*$", text)
    out: Dict[int, Dict[str, Dict[str, Optional[float]]]] = {}
    colmap = {1:B1_COLS, 2:B2_COLS, 3:B3_COLS}
    for i in range(1, len(parts), 2):
        batch = int(parts[i])
        lines = [x.strip() for x in parts[i+1].splitlines() if x.strip()]
        rows: Dict[str, Dict[str, Optional[float]]] = {}
        for j, line in enumerate(lines[:-1]):
            if SYMBOL_RE.fullmatch(line) and "\t" in lines[j+1]:
                vals = lines[j+1].split("\t")
                cols = colmap[batch]
                if len(vals) != len(cols):
                    raise ValueError(f"Batch {batch} {line}: expected {len(cols)} metrics, got {len(vals)}")
                if line in rows:
                    raise ValueError(f"Batch {batch}: duplicate symbol {line}")
                rows[line] = {c:_num(v) for c,v in zip(cols, vals)}
        out[batch] = rows
    return out

def integrity_gate(batches: Dict[int, Dict[str, Dict[str, Optional[float]]]]) -> Dict[str, Any]:
    if set(batches) != {1,2,3}:
        return {"state":"BLOCKED","reason":"missing_batch"}
    sets = [set(batches[i]) for i in (1,2,3)]
    universe = set.union(*sets)
    complete = set.intersection(*sets)
    conflicts = []
    for sym in sorted(complete):
        prices = [batches[i][sym]["price"] for i in (1,2,3)]
        known = [p for p in prices if p is not None]
        if len(known) >= 2 and len(set(known)) > 1:
            conflicts.append(sym)
    if conflicts:
        return {"state":"BLOCKED","reason":"price_conflict","symbols":conflicts,
                "complete":len(complete),"universe":len(universe)}
    return {"state":"PASS" if len(complete)==len(universe) else "REVIEW",
            "reason":"complete" if len(complete)==len(universe) else "partial_universe",
            "complete":len(complete),"universe":len(universe)}

def _grade(v: Optional[float], bands: List[Tuple[float,float]]) -> Optional[float]:
    if v is None: return None
    score = 0.0
    for threshold, points in bands:
        if v >= threshold: score = points
    return score

def _mean_known(xs: List[Optional[float]]) -> Tuple[Optional[float], float]:
    known = [x for x in xs if x is not None]
    if not known: return None, 0.0
    return sum(known)/len(known), len(known)/len(xs)

def evaluate_symbol(sym: str, batches: Dict[int, Dict[str, Dict[str, Optional[float]]]]) -> Dict[str, Any]:
    b1,b2,b3 = (batches[i].get(sym,{}) for i in (1,2,3))
    if not (b1 and b2 and b3):
        return {"symbol":sym,"data_state":"PARTIAL","stage2_state":"NOT_EVALUATED"}

    # Technical evidence: daily/swing context only.
    trend = 100.0 if b1["price"] > b1["price_ma20"] > b1["price_ma50"] else 0.0
    ma200 = None if b1["price_ma200"] is None else (100.0 if b1["price"] > b1["price_ma200"] else 0.0)
    adx = _grade(b1["adx14"], [(0,0),(20,35),(25,70),(35,100)])
    di = 100.0 if b1["di_plus14"] > b1["di_minus14"] else 0.0
    macd = 100.0 if b1["macd"] > b1["prev_macd"] else 0.0
    rsi = b1["rsi14"]
    rsi_score = None if rsi is None else (100.0 if 55 <= rsi <= 68 else 70.0 if 50 <= rsi < 55 or 68 < rsi <= 70 else 25.0)
    rs3 = _grade(b1["rs3m"], [(0,0),(50,40),(80,70),(90,100)])
    rs6 = _grade(b1["rs6m"], [(0,0),(50,40),(80,70),(90,100)])
    technical, tech_conf = _mean_known([trend,ma200,adx,di,macd,rsi_score,rs3,rs6])

    rvol = None if not b1["volume_ma20"] else b1["volume"]/b1["volume_ma20"]
    rvol_score = _grade(rvol, [(0,0),(1,50),(1.2,75),(1.5,100)])
    adtv_score = _grade(b1["adtv30"], [(0,0),(5e9,50),(10e9,75),(25e9,100)])
    participation, part_conf = _mean_known([rvol_score,adtv_score])

    npm = _grade(b2["npm_ttm"], [(-1e99,0),(0,50),(5,70),(10,100)])
    roic = _grade(b2["roic_ttm"], [(-1e99,0),(0,40),(8,70),(15,100)])
    pio = _grade(b2["piotroski"], [(0,0),(5,50),(7,80),(8,100)])
    ey = _grade(b2["earnings_yield_ttm"], [(-1e99,0),(0,50),(5,75),(10,100)])
    eps = _grade(b2["eps_yoy"], [(-1e99,0),(0,50),(10,70),(25,100)])
    de = b2["de_quarter"]
    de_score = None if de is None else (100.0 if de <= .5 else 75.0 if de <= 1 else 40.0 if de <= 2 else 0.0)
    fundamental, fund_conf = _mean_known([npm,roic,pio,ey,eps,de_score])

    cash_items = [
        None if b3[k] is None else (100.0 if b3[k] > 0 else 0.0)
        for k in ("ocf_q","fcf_ttm","fcf_q","ni_q","ni_ttm","ni_ytd")
    ]
    cash, cash_conf = _mean_known(cash_items)

    flags: List[Dict[str,str]] = []
    def flag(code,severity,evidence):
        flags.append({"code":code,"severity":severity,"evidence":evidence})

    # RC3 severity calibration. Borderline negatives are warnings, not automatically HIGH risk.
    npmv=b2["npm_ttm"]
    if npmv is not None and npmv < 0:
        flag("NEGATIVE_MARGIN","HIGH" if npmv < -5 else "WARNING",
             f"NPM TTM {npmv:.2f}%")

    roicv=b2["roic_ttm"]
    if roicv is not None and roicv < 0:
        flag("NEGATIVE_ROIC","HIGH" if roicv < -3 else "WARNING",
             f"ROIC TTM {roicv:.2f}%")

    epsv=b2["eps_yoy"]
    if epsv is not None and epsv < 0:
        sev="HIGH" if epsv < -50 else "WARNING" if epsv < -10 else "WATCH"
        flag("NEGATIVE_EPS_GROWTH",sev,f"EPS YoY {epsv:.2f}%")

    # Cash-flow contradictions remain important, but persistence determines severity.
    ni_ttm=b3["ni_ttm"]; fcf_ttm=b3["fcf_ttm"]; ni_q=b3["ni_q"]; ocf_q=b3["ocf_q"]; fcf_q=b3["fcf_q"]
    if ni_ttm is not None and ni_ttm > 0 and fcf_ttm is not None and fcf_ttm < 0:
        persistent = (fcf_q is not None and fcf_q < 0)
        flag("PROFIT_WITH_NEGATIVE_FCF","HIGH" if persistent else "WARNING",
             "NI TTM positive while FCF TTM negative" + ("; quarterly FCF also negative" if persistent else ""))
    if ni_q is not None and ni_q > 0 and ocf_q is not None and ocf_q < 0:
        flag("PROFIT_WITH_NEGATIVE_OCF","WARNING","Quarterly NI positive while quarterly OCF negative")
    if ni_ttm is not None and ni_ttm < 0:
        flag("TTM_NET_LOSS","HIGH","Net Income TTM negative")
    if fcf_ttm is not None and fcf_ttm < 0:
        flag("NEGATIVE_FCF_TTM","WARNING","FCF TTM negative")

    # RC4: group related findings so one underlying problem is not counted twice.
    FAMILY = {
        "NEGATIVE_MARGIN":"PROFITABILITY",
        "NEGATIVE_ROIC":"PROFITABILITY",
        "TTM_NET_LOSS":"PROFITABILITY",
        "NEGATIVE_EPS_GROWTH":"GROWTH",
        "PROFIT_WITH_NEGATIVE_FCF":"CASH_QUALITY",
        "PROFIT_WITH_NEGATIVE_OCF":"CASH_QUALITY",
        "NEGATIVE_FCF_TTM":"CASH_QUALITY",
    }
    severity_rank={"WATCH":1,"WARNING":2,"HIGH":3}
    family_risk={}
    for f in flags:
        fam=FAMILY.get(f["code"], f["code"])
        prev=family_risk.get(fam)
        if prev is None or severity_rank[f["severity"]] > severity_rank[prev]:
            family_risk[fam]=f["severity"]

    high_families=sum(v=="HIGH" for v in family_risk.values())
    warning_families=sum(v=="WARNING" for v in family_risk.values())
    watch_families=sum(v=="WATCH" for v in family_risk.values())

    # Decision is based on independent risk families, not raw flag count.
    if high_families >= 2:
        eligibility="REVIEW"
    elif high_families >= 1:
        eligibility="CONDITIONAL"
    elif warning_families >= 2:
        eligibility="CONDITIONAL"
    else:
        eligibility="ELIGIBLE"

    # Separate horizon scores; no universal total score.
    swing = .60*technical + .20*participation + .10*fundamental + .10*cash
    longterm = .15*technical + .05*participation + .45*fundamental + .35*cash

    def raw_priority(score):
        return "HIGH" if score >= 75 else "MEDIUM" if score >= 55 else "LOW"

    def effective_priority(raw: str, horizon: str) -> str:
        if eligibility == "REVIEW":
            return "REVIEW"
        if eligibility == "CONDITIONAL" and raw == "HIGH":
            return "CONDITIONAL_HIGH"
        if horizon == "long_term" and high_families >= 1 and raw in {"HIGH","MEDIUM"}:
            return "CONDITIONAL"
        return raw

    swing_raw = raw_priority(swing)
    lt_raw = raw_priority(longterm)
    swing_conf = .60*tech_conf + .20*part_conf + .10*fund_conf + .10*cash_conf
    lt_conf = .15*tech_conf + .05*part_conf + .45*fund_conf + .35*cash_conf

    return {
        "symbol":sym, "data_state":"COMPLETE", "stage2_state":"EVALUATED",
        "features":{"rvol":rvol},
        "blocks":{
            "technical":round(technical,2),"participation":round(participation,2),
            "fundamental":round(fundamental,2),"cash_quality":round(cash,2)
        },
        "red_flags":flags,
        "risk_families":family_risk,
        "eligibility":eligibility,
        "confidence":{
            "technical":round(tech_conf,2),"participation":round(part_conf,2),
            "fundamental":round(fund_conf,2),"cash_quality":round(cash_conf,2),
            "swing":round(swing_conf,2),"long_term":round(lt_conf,2)
        },
        "horizons":{
            "intraday":{"state":"NOT_EVALUATED","reason":"fixture contains no intraday/microstructure data"},
            "swing":{"raw_score":round(swing,2),"raw_priority":swing_raw,
                     "effective_priority":effective_priority(swing_raw,"swing")},
            "long_term":{"raw_score":round(longterm,2),"raw_priority":lt_raw,
                         "effective_priority":effective_priority(lt_raw,"long_term")}
        }
    }

def evaluate_universe(text: str) -> Dict[str, Any]:
    batches = parse_fixture(text)
    gate = integrity_gate(batches)
    symbols = sorted(set().union(*(set(v) for v in batches.values())))
    if gate["state"] == "BLOCKED":
        return {"integrity":gate,"results":[]}
    return {"integrity":gate,"results":[evaluate_symbol(s,batches) for s in symbols]}
