from __future__ import annotations

"""User-facing funnel for SIS Power Screener.

Presentation only: this module does not create a new analytical score and does not
change Stage 1/2/3 decisions. It translates frozen Stage 3 outputs into simple
Indonesian decision language and keeps Swing and Long-Term independent.
"""

VERSION = "SIS-OPPORTUNITY-FUNNEL-RC1"


def _symbol(rec):
    return str((rec or {}).get("symbol") or "").strip().upper()


def _candidate_map(stage3):
    return {_symbol(x): x for x in (stage3.get("candidates") or []) if _symbol(x)}


def _risk_state(syn):
    try:
        return syn["shared"]["evidence_ledger"]["RISK"]["state"]
    except Exception:
        return "UNKNOWN"


def _valuation_state(syn):
    try:
        return syn["shared"]["evidence_ledger"]["VALUATION"]["state"]
    except Exception:
        return "UNKNOWN"


def _price_label(state):
    return {
        "POSITIVE_STRONG": "Murah / diskon",
        "POSITIVE_MODERATE": "Menarik",
        "NEUTRAL": "Wajar",
        "NEGATIVE_MODERATE": "Agak mahal",
        "NEGATIVE_STRONG": "Mahal",
        "UNKNOWN": "Belum dapat dinilai",
    }.get(state, "Belum dapat dinilai")


def _swing_action(candidate):
    ex = (candidate or {}).get("swing_execution") or {}
    status = ex.get("execution_status")
    reasons = set(ex.get("reason_codes") or [])
    if status == "READY":
        return "SIAP BELI JIKA HARGA SESUAI"
    if status == "WAIT":
        if "AVOID_CHASING_EXTENDED_PRICE" in reasons or "CURRENT_RANGE_EXHAUSTED" in reasons:
            return "TUNGGU HARGA"
        return "TUNGGU KONFIRMASI"
    return "JANGAN BELI DULU"


def _longterm_action(candidate):
    syn = (candidate or {}).get("synthesis") or {}
    base = syn.get("long_term") or {}
    lt = (candidate or {}).get("longterm_outlook") or {}
    if base.get("analytical_status") != "PASS" or lt.get("status") != "COMPLETE":
        return "BELUM LAYAK"
    dca = lt.get("dca_context")
    o3 = ((lt.get("outlook") or {}).get("3Y") or {}).get("state")
    valuation = _valuation_state(syn)
    risk = _risk_state(syn)
    if risk == "NEGATIVE_STRONG" or o3 == "NEGATIVE":
        return "BELUM LAYAK"
    if dca == "FAVORABLE" and o3 in {"POSITIVE", "STABLE"} and valuation not in {"NEGATIVE_MODERATE", "NEGATIVE_STRONG"}:
        return "LAYAK DIBELI"
    if valuation in {"NEGATIVE_MODERATE", "NEGATIVE_STRONG"}:
        return "BAGUS, TUNGGU HARGA"
    return "PERTIMBANGKAN / TUNGGU"


def _swing_row(candidate, rank=None):
    ex = (candidate or {}).get("swing_execution") or {}
    return {
        "rank": rank,
        "symbol": _symbol(candidate),
        "action": _swing_action(candidate),
        "current_price": ex.get("current_price"),
        "entry_area": ex.get("entry_area"),
        "target_1": ex.get("target_1"),
        "target_2": ex.get("target_2"),
        "risk_boundary": ex.get("risk_boundary"),
        "reward_risk": ex.get("reward_risk"),
        "reason_codes": list(ex.get("reason_codes") or []),
    }



def _longterm_business_quality(candidate):
    syn = (candidate or {}).get("synthesis") or {}
    state = ((((syn.get("shared") or {}).get("evidence_ledger") or {}).get("BUSINESS") or {}).get("state", "UNKNOWN"))
    return {
        "POSITIVE_STRONG": "Sangat baik",
        "POSITIVE_MODERATE": "Baik",
        "NEUTRAL": "Cukup",
        "NEGATIVE_MODERATE": "Perlu perhatian",
        "NEGATIVE_STRONG": "Lemah",
        "UNKNOWN": "Belum cukup data",
    }.get(state, "Belum cukup data")


def _longterm_prospect_summary(candidate):
    lt = (candidate or {}).get("longterm_outlook") or {}
    out = lt.get("outlook") or {}
    s1 = ((out.get("1Y") or {}).get("state"))
    s3 = ((out.get("3Y") or {}).get("state"))
    s5 = ((out.get("5Y") or {}).get("state"))
    states = [s for s in (s1, s3, s5) if s]
    if not states:
        return "Belum cukup data"
    if s3 == "NEGATIVE" or s5 == "NEGATIVE":
        return "Negatif"
    if s3 == "POSITIVE" and s5 == "POSITIVE":
        return "Positif"
    if s3 in {"POSITIVE", "STABLE"} and s5 in {"POSITIVE", "STABLE"}:
        return "Stabil"
    return "Hati-hati"


def _longterm_risk_summary(candidate):
    syn = (candidate or {}).get("synthesis") or {}
    state = _risk_state(syn)
    return {
        "POSITIVE_STRONG": "Rendah",
        "POSITIVE_MODERATE": "Relatif rendah",
        "NEUTRAL": "Normal",
        "NEGATIVE_MODERATE": "Moderat",
        "NEGATIVE_STRONG": "Tinggi",
        "UNKNOWN": "Belum cukup data",
    }.get(state, "Belum cukup data")


def _longterm_accumulation_context(candidate):
    lt = (candidate or {}).get("longterm_outlook") or {}
    return {
        "FAVORABLE": "Mendukung",
        "NORMAL": "Normal",
        "CAUTIOUS": "Hati-hati",
    }.get(lt.get("dca_context"), "Belum cukup data")


def _longterm_row(candidate, rank=None):
    syn = (candidate or {}).get("synthesis") or {}
    lt = (candidate or {}).get("longterm_outlook") or {}
    ex = (candidate or {}).get("swing_execution") or {}
    return {
        "rank": rank,
        "symbol": _symbol(candidate),
        "action": _longterm_action(candidate),
        "current_price": ex.get("current_price"),
        "price_assessment": _price_label(_valuation_state(syn)),
        "valuation_state": _valuation_state(syn),
        "prospect_summary": _longterm_prospect_summary(candidate),
        "business_quality": _longterm_business_quality(candidate),
        "risk_summary": _longterm_risk_summary(candidate),
        "accumulation_context": _longterm_accumulation_context(candidate),
        "outlook": lt.get("outlook"),
        "risk_state": _risk_state(syn),
        "dca_context": lt.get("dca_context"),
        "forward_drivers": list(lt.get("forward_drivers") or []),
        "forward_risks": list(lt.get("forward_risks") or []),
    }


def build_opportunity_funnel(stage3, top_n=3):
    """Build Top-3 + all-stock views without altering analytical ranking.

    Top lists follow final_ranking_engine exactly. All-stock view preserves every
    COMPLETE Stage 3 candidate and adds only user-facing labels.
    """
    if not isinstance(stage3, dict) or not isinstance(top_n, int) or top_n < 1:
        return {"status": "INVALID", "reason": "INVALID_INPUT"}
    cmap = _candidate_map(stage3)
    ranking = stage3.get("ranking") or {}
    swing_top = []
    for r in ((ranking.get("swing") or {}).get("top") or [])[:top_n]:
        c = cmap.get(str(r.get("symbol") or "").upper())
        if c:
            swing_top.append(_swing_row(c, r.get("rank")))
    long_top = []
    for r in ((ranking.get("long_term") or {}).get("top") or [])[:top_n]:
        c = cmap.get(str(r.get("symbol") or "").upper())
        if c:
            long_top.append(_longterm_row(c, r.get("rank")))

    all_swing = [_swing_row(c) for c in cmap.values()]
    all_long = [_longterm_row(c) for c in cmap.values()]
    return {
        "status": "COMPLETE",
        "version": VERSION,
        "policy": "PRESENTATION_ONLY_NO_NEW_SCORE",
        "candidate_count": len(cmap),
        "swing": {"top3": swing_top, "all": all_swing},
        "long_term": {"top3": long_top, "all": all_long},
    }
