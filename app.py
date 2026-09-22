import streamlit as st
from stage1.clipboard import parse_clipboard_text
from stage1.pipeline import run_stage1, validate_batch
from stage1.schema import BATCHES
from stage1.history import save_snapshot, list_snapshots, load_snapshot, get_snapshot_batch
from stage2.runner import run_stage2

# Stage 3 deployment layer. Paths are local to this deployment artifact.
import sys
from pathlib import Path
_APP_ROOT = Path(__file__).resolve().parent
for _p in (_APP_ROOT / "integration_pipeline", _APP_ROOT / "stage3"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from integration_pipeline.pipeline_p10_orchestrator import run_pipeline
from stage3.stage3_e2e_runner import run_stage3_universe
from stage3.opportunity_funnel_ui import render_opportunity_funnel

st.set_page_config(page_title="SIS — Stock Intelligence System", layout="wide")

STATUS_LABELS = {
    "CONFIRMED": "Terkonfirmasi",
    "PARTIALLY_CONFIRMED": "Terkonfirmasi sebagian",
    "WEAKENED": "Melemah",
    "INVALIDATED": "Tidak terkonfirmasi",
    "INSUFFICIENT_EVIDENCE": "Data belum cukup",
}
CONF_LABELS = {"HIGH": "Tinggi", "MEDIUM": "Sedang", "LOW": "Rendah"}


def friendly_input_issue(issue: str) -> str:
    s = str(issue)
    batch = s.split(":", 1)[0] if s.startswith("B") and ":" in s else ""

    if "MISSING_SYMBOL_COLUMN" in s:
        return f"{batch}: kolom Symbol/kode saham belum terbaca." if batch else "Kolom Symbol/kode saham belum terbaca."
    if "DUPLICATE_SYMBOL" in s:
        return f"{batch}: ada kode saham yang tercatat lebih dari satu kali." if batch else "Ada kode saham yang tercatat lebih dari satu kali."
    if "MISSING_COLUMNS:" in s:
        cols = [x.strip() for x in s.split("MISSING_COLUMNS:", 1)[1].split(",") if x.strip()]
        detail = "; ".join(cols)
        return f"{batch}: kolom berikut belum ditemukan: {detail}." if batch else f"Kolom berikut belum ditemukan: {detail}."
    if "AMBIGUOUS_NUMERIC_FORMAT" in s or "INVALID_NUMERIC" in s:
        parts = s.split(":")
        if len(parts) >= 4 and parts[0].startswith("B"):
            b, symbol = parts[0], parts[1]
            field = ":".join(parts[2:-1])
            return f"{b} — {symbol} — {field}: nilai belum dapat dibaca dengan aman."
        return "Ada angka yang formatnya belum dapat dibaca dengan aman. Periksa kembali data yang ditempel."
    return f"{batch}: sebagian data belum dapat dibaca dengan aman." if batch else "Sebagian data belum dapat dibaca dengan aman. Periksa kembali input."


def friendly_stage1_issue(issue: str) -> str:
    s = str(issue)
    if "MISSING_REQUIRED_BATCH" in s:
        return "Belum semua bagian data B1–B11 tersedia."
    if "UNIVERSE_MISMATCH" in s:
        return "Daftar saham antarbagian data tidak sama. Pastikan seluruh B1–B11 berasal dari hasil screening yang sama."
    if "UNIVERSE_INCOMPLETE" in s:
        return "Jumlah saham yang terbaca belum sama dengan jumlah hasil screening."
    if "PRICE_CONFLICT" in s:
        symbol = s.split(":", 1)[0]
        return f"Data harga {symbol} berbeda antarbagian input. Gunakan data dari sesi pengambilan yang sama."
    if "CONTROL_CONFLICT" in s:
        symbol = s.split(":", 1)[0]
        return f"Ada data {symbol} yang tidak konsisten antarbagian input dan perlu diperiksa kembali."
    if "EXPECTED_UNIVERSE_TOTAL_NOT_PROVIDED" in s or "INVALID_EXPECTED_UNIVERSE_TOTAL" in s:
        return "Jumlah hasil screening belum valid."
    return "Ada ketidaksesuaian data yang perlu diperiksa sebelum analisis dapat dilanjutkan."


def unique_messages(messages):
    return list(dict.fromkeys(messages))


def render_notice(title, messages):
    st.error(title)
    for msg in unique_messages(messages):
        st.write(f"• {msg}")


def render_horizon(data: dict):
    c1, c2 = st.columns(2)
    c1.metric("Status tesis", STATUS_LABELS.get(data["thesis_status"], data["thesis_status"]))
    c2.metric("Keyakinan evidence", CONF_LABELS.get(data["confidence"], data["confidence"]))

    if data.get("main_reasons"):
        st.markdown("**Alasan utama**")
        for item in data["main_reasons"]:
            st.write(f"• {item}")
    if data.get("key_contradictions"):
        st.markdown("**Hal yang melemahkan tesis**")
        for item in data["key_contradictions"]:
            st.write(f"• {item}")
    if data.get("key_risks"):
        st.markdown("**Risiko utama**")
        for item in data["key_risks"]:
            st.write(f"• {item}")
    if data.get("invalidation_condition"):
        st.markdown("**Kapan tesis perlu dievaluasi ulang**")
        for item in data["invalidation_condition"]:
            st.write(f"• {item}")



def _canonical_map(df):
    out = {}
    for _, row in df.iterrows():
        d = row.to_dict()
        symbol = str(d.get("symbol", "")).strip().upper()
        if symbol:
            out[symbol] = d
    return out


def run_stage3_from_current_analysis(s1_canonical, s2_packages, analysis_as_of, top_n=3):
    p10 = run_pipeline(
        stage2_records=s2_packages,
        analysis_as_of=analysis_as_of,
        canonical_by_symbol=_canonical_map(s1_canonical),
    )
    if p10.state == "BLOCKED":
        return {"status": "BLOCKED", "stage": "P10", "diagnostics": list(p10.diagnostics)}
    s3 = run_stage3_universe(list(p10.payloads), analysis_date=analysis_as_of, top_n=top_n)
    return {
        "status": s3.get("status"),
        "counts": {"s1": len(s1_canonical), "s2": len(s2_packages), "p10": len(p10.payloads)},
        "p10_state": p10.state,
        "p10_diagnostics": list(p10.diagnostics),
        "stage3": s3,
    }


def _fmt_price(v):
    if v is None:
        return "—"
    try:
        number = float(v)
        if number.is_integer():
            return f"{number:,.0f}".replace(",", ".")
        return f"{number:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    except (TypeError, ValueError):
        return str(v)


def _human_state(v):
    labels = {
        "PASS": "Kuat", "REVIEW": "Perlu perhatian", "LOW_QUALITY": "Kualitas rendah",
        "READY": "Siap dipertimbangkan", "WAIT": "Menunggu momen yang lebih baik",
        "NOT_ATTRACTIVE": "Belum menarik", "INSUFFICIENT_DATA": "Data belum cukup",
        "POSITIVE": "Positif", "STABLE": "Stabil", "CAUTIOUS": "Hati-hati", "NEGATIVE": "Negatif",
        "FAVORABLE": "Mendukung", "NORMAL": "Normal", "NEGATIVE_MODERATE": "Risiko moderat",
        "NEGATIVE_STRONG": "Risiko tinggi", "POSITIVE_MODERATE": "Risiko relatif rendah",
        "POSITIVE_STRONG": "Sangat mendukung", "NEUTRAL": "Netral", "UNKNOWN": "Belum diketahui",
    }
    return labels.get(str(v), str(v).replace("_", " ").title() if v is not None else "—")


def _reason_text(code):
    labels = {
        "S3H_SWING_NOT_PASS": "Kualitas analisis Swing belum memenuhi seluruh syarat utama.",
        "TECHNICAL_DATA_NOT_FRESH": "Data teknikal belum cukup mutakhir untuk keputusan eksekusi.",
        "UNRESOLVED_TECHNICAL_CONTRADICTION": "Masih ada sinyal teknikal yang saling bertentangan.",
        "TREND_NOT_BULL": "Tren harga belum menunjukkan struktur naik yang cukup kuat.",
        "NO_DEFENSIBLE_RISK_BOUNDARY": "Batas risiko yang dapat dipertanggungjawabkan belum terbentuk.",
        "RR_NOT_COMPUTABLE": "Rasio potensi hasil terhadap risiko belum dapat dihitung dengan andal.",
        "CURRENT_RANGE_EXHAUSTED": "Rentang pergerakan saat ini sudah cukup lebar; mengejar harga meningkatkan risiko.",
        "AVOID_CHASING_EXTENDED_PRICE": "Harga sudah terlalu jauh dari area referensi; lebih baik menunggu.",
        "REWARD_RISK_BELOW_MINIMUM": "Potensi hasil dibanding risikonya belum memenuhi batas minimum.",
        "EXECUTION_CONFIRMATION_WEAK": "Konfirmasi momentum/partisipasi pasar belum cukup kuat.",
        "INSUFFICIENT_INTERNAL_EXECUTION_EVIDENCE": "Data internal belum cukup untuk menentukan rencana entry yang andal.",
        "BROAD_BASED_FORWARD_IMPROVEMENT": "Ekspektasi pertumbuhan ke depan membaik secara luas.",
        "FORWARD_REBOUND": "Terdapat indikasi pemulihan pada proyeksi ke depan.",
        "STRUCTURAL_QUALITY_SUPPORT": "Kualitas fundamental struktural mendukung prospek jangka panjang.",
        "SECTOR_SUPPORT": "Kondisi sektor memberi dukungan terhadap prospek.",
        "FORWARD_DETERIORATION": "Proyeksi ke depan menunjukkan pelemahan.",
        "MIXED_FORWARD_SIGNALS": "Proyeksi ke depan masih memberikan sinyal yang bercampur.",
        "ELEVATED_RISK_CONTEXT": "Konteks risiko masih perlu diperhatikan.",
        "VALUATION_PRESSURE": "Valuasi memberi tekanan terhadap daya tarik saat ini.",
        "NO_FORWARD_GROWTH_EARNINGS": "Data proyeksi pertumbuhan/laba ke depan belum tersedia.",
        "EXTREME_FORWARD_VALUE": "Sebagian proyeksi memiliki nilai ekstrem dan perlu kehati-hatian.",
        "EPS_SPIKE_WITHOUT_OPERATING_SUPPORT": "Lonjakan EPS belum didukung perbaikan operasi yang sebanding.",
        "NET_INCOME_SPIKE_WITHOUT_OPERATING_SUPPORT": "Lonjakan laba bersih belum didukung perbaikan operasi yang sebanding.",
    }
    return labels.get(str(code), str(code).replace("_", " ").capitalize())


def _package_for(packages, symbol):
    return next((p for p in (packages or []) if str(p.get("ticker", "")).upper() == str(symbol).upper()), None)


def _candidate_for(stage3, symbol):
    return next((x for x in (stage3.get("candidates") or []) if str(x.get("symbol", "")).upper() == str(symbol).upper()), None)


def _render_thesis_block(package, horizon):
    if not package:
        return
    data = package.get(horizon) or {}
    if not data:
        return
    if data.get("main_reasons"):
        st.markdown("**Alasan utama**")
        for item in data["main_reasons"]:
            st.write(f"• {item}")
    if data.get("key_contradictions"):
        st.markdown("**Hal yang melemahkan analisis**")
        for item in data["key_contradictions"]:
            st.write(f"• {item}")
    if data.get("key_risks"):
        st.markdown("**Risiko utama**")
        for item in data["key_risks"]:
            st.write(f"• {item}")
    if data.get("invalidation_condition"):
        st.markdown("**Kapan analisis perlu dievaluasi ulang**")
        for item in data["invalidation_condition"]:
            st.write(f"• {item}")


def _render_swing_detail(candidate, package):
    syn = (candidate or {}).get("synthesis") or {}
    sw = syn.get("swing") or {}
    ex = (candidate or {}).get("swing_execution") or {}
    status = ex.get("execution_status")
    reasons = ex.get("reason_codes") or []
    action = {
        "READY": "SIAP BELI JIKA HARGA SESUAI",
        "NOT_ATTRACTIVE": "JANGAN BELI DULU",
        "INSUFFICIENT_DATA": "JANGAN BELI DULU",
    }.get(status)
    if status == "WAIT":
        if "AVOID_CHASING_EXTENDED_PRICE" in reasons or "CURRENT_RANGE_EXHAUSTED" in reasons:
            action = "TUNGGU HARGA"
        else:
            action = "TUNGGU KONFIRMASI"
    if not action:
        action = _human_state(status)
    st.markdown("**Saran SIS**")
    st.write(f"**{action}**")
    if reasons:
        st.markdown("**Kenapa**")
        for code in reasons:
            st.write(f"• {_reason_text(code)}")
    entry = ex.get("entry_area") or {}
    st.markdown("**Rencana harga**")
    if entry:
        st.write(f"Area beli: {_fmt_price(entry.get('low'))} – {_fmt_price(entry.get('high'))}")
        st.write(f"Target 1: {_fmt_price(ex.get('target_1'))} | Target 2: {_fmt_price(ex.get('target_2'))}")
        st.write(f"Batas risiko: {_fmt_price(ex.get('risk_boundary'))}")
        rr = ex.get("reward_risk") or {}
        st.caption(f"Rasio Imbal Hasil/Risiko — Target 1: {rr.get('target_1', '—')} | Target 2: {rr.get('target_2', '—')}")
    else:
        st.info("Data saat ini belum cukup untuk menentukan area entry dan batas risiko yang andal.")
    with st.expander("Lihat detail analisis", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("Kualitas analisis", sw.get("quality", "—"))
        c2.metric("Tingkat keyakinan", sw.get("confidence", "—"))
        c3.metric("Status teknis", _human_state(status))
        _render_thesis_block(package, "swing")


def _longterm_decision_label(candidate):
    syn = (candidate or {}).get("synthesis") or {}
    base = syn.get("long_term") or {}
    lt = (candidate or {}).get("longterm_outlook") or {}
    if base.get("analytical_status") != "PASS" or lt.get("status") != "COMPLETE":
        return "BELUM LAYAK"
    dca = lt.get("dca_context")
    o3 = ((lt.get("outlook") or {}).get("3Y") or {}).get("state")
    valuation = (((syn.get("shared") or {}).get("evidence_ledger") or {}).get("VALUATION") or {}).get("state", "UNKNOWN")
    risk = (((syn.get("shared") or {}).get("evidence_ledger") or {}).get("RISK") or {}).get("state", "UNKNOWN")
    if risk == "NEGATIVE_STRONG" or o3 == "NEGATIVE":
        return "BELUM LAYAK"
    if dca == "FAVORABLE" and o3 in {"POSITIVE", "STABLE"} and valuation not in {"NEGATIVE_MODERATE", "NEGATIVE_STRONG"}:
        return "LAYAK DIBELI"
    if valuation in {"NEGATIVE_MODERATE", "NEGATIVE_STRONG"}:
        return "BAGUS, TUNGGU HARGA"
    return "PERTIMBANGKAN / TUNGGU"


def _longterm_price_label(candidate):
    syn = (candidate or {}).get("synthesis") or {}
    valuation = (((syn.get("shared") or {}).get("evidence_ledger") or {}).get("VALUATION") or {}).get("state", "UNKNOWN")
    return {
        "POSITIVE_STRONG": "Murah / diskon",
        "POSITIVE_MODERATE": "Menarik",
        "NEUTRAL": "Wajar",
        "NEGATIVE_MODERATE": "Agak mahal",
        "NEGATIVE_STRONG": "Mahal",
        "UNKNOWN": "Belum dapat dinilai",
    }.get(valuation, "Belum dapat dinilai")



def _longterm_summary_fields(candidate):
    syn = (candidate or {}).get("synthesis") or {}
    lt = (candidate or {}).get("longterm_outlook") or {}
    evidence = ((syn.get("shared") or {}).get("evidence_ledger") or {})

    out = lt.get("outlook") or {}
    s1 = ((out.get("1Y") or {}).get("state"))
    s3 = ((out.get("3Y") or {}).get("state"))
    s5 = ((out.get("5Y") or {}).get("state"))
    states = [s for s in (s1, s3, s5) if s]
    if not states:
        prospect = "Belum cukup data"
    elif s3 == "NEGATIVE" or s5 == "NEGATIVE":
        prospect = "Negatif"
    elif s3 == "POSITIVE" and s5 == "POSITIVE":
        prospect = "Positif"
    elif s3 in {"POSITIVE", "STABLE"} and s5 in {"POSITIVE", "STABLE"}:
        prospect = "Stabil"
    else:
        prospect = "Hati-hati"

    business_domain = (candidate or {}).get("dossier", {}).get("domains", {}).get("business", {})
    business_state = business_domain.get("state", "NOT_EVALUATED") if isinstance(business_domain, dict) else "NOT_EVALUATED"
    business = {
        "STRONG": "Baik",
        "MIXED": "Cukup",
        "WEAK": "Perlu perhatian",
        "NOT_EVALUATED": "Belum cukup data",
    }.get(business_state, "Belum cukup data")

    risk_state = (evidence.get("RISK") or {}).get("state", "UNKNOWN")
    risk = {
        "POSITIVE_STRONG": "Rendah",
        "POSITIVE_MODERATE": "Relatif rendah",
        "NEUTRAL": "Normal",
        "NEGATIVE_MODERATE": "Moderat",
        "NEGATIVE_STRONG": "Tinggi",
        "UNKNOWN": "Belum cukup data",
    }.get(risk_state, "Belum cukup data")

    accumulation = {
        "FAVORABLE": "Mendukung",
        "NORMAL": "Normal",
        "CAUTIOUS": "Hati-hati",
    }.get(lt.get("dca_context"), "Belum cukup data")

    return {"prospect": prospect, "business": business, "risk": risk, "accumulation": accumulation}


def _render_longterm_detail(candidate, package):
    syn = (candidate or {}).get("synthesis") or {}
    base = syn.get("long_term") or {}
    lt = (candidate or {}).get("longterm_outlook") or {}
    risk = ((syn.get("shared") or {}).get("risk_families") or {}).get("RISK", {}).get("state")
    summary = _longterm_summary_fields(candidate)
    action = _longterm_decision_label(candidate)

    st.markdown("**Ringkasan keputusan**")
    c1, c2 = st.columns(2)
    c1.metric("Prospek jangka panjang", summary.get("prospect"))
    c1.metric("Kualitas bisnis", summary.get("business"))
    c2.metric("Risiko", summary.get("risk"))
    c2.metric("Konteks akumulasi", summary.get("accumulation"))

    st.markdown("**Saran SIS**")
    st.write(f"**{action}**")

    if action != "LAYAK DIBELI":
        st.markdown("**Apa yang menahan keputusan?**")
        blockers = []
        if summary.get("accumulation") == "Hati-hati":
            blockers.append("Konteks akumulasi masih hati-hati.")
        if summary.get("risk") in {"Moderat", "Tinggi"}:
            blockers.append(f"Risiko masih berada pada tingkat {summary.get('risk').lower()}.")
        valuation = (((syn.get("shared") or {}).get("evidence_ledger") or {}).get("VALUATION") or {}).get("state", "UNKNOWN")
        if valuation in {"NEGATIVE_MODERATE", "NEGATIVE_STRONG"}:
            blockers.append("Valuasi belum cukup mendukung untuk keputusan beli.")
        if not blockers:
            blockers.append("Bukti yang tersedia belum cukup kuat untuk meningkatkan keputusan menjadi Layak Dibeli.")
        for item in blockers:
            st.write(f"• {item}")

    out = lt.get("outlook") or {}
    st.markdown("**Prospek rinci**")
    cols = st.columns(3)
    for col, horizon, label in zip(cols, ("1Y", "3Y", "5Y"), ("1 Tahun", "3 Tahun", "5 Tahun")):
        x = out.get(horizon) or {}
        col.metric(f"Prospek {label}", _human_state(x.get("state")), f"Keyakinan {x.get('confidence', '—')}")
    drivers = lt.get("forward_drivers") or []
    risks = lt.get("forward_risks") or []
    if drivers:
        st.markdown("**Faktor pendukung**")
        for code in drivers:
            st.write(f"• {_reason_text(code)}")
    if risks:
        st.markdown("**Risiko utama**")
        for code in risks:
            st.write(f"• {_reason_text(code)}")
    with st.expander("Lihat detail analisis", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Kualitas analisis", base.get("quality", "—"))
        c2.metric("Tingkat keyakinan", base.get("confidence", "—"))
        c3.metric("Risiko", _human_state(risk))
        c4.metric("Konteks akumulasi", _human_state(lt.get("dca_context")))
        _render_thesis_block(package, "long_term")
        fwd = lt.get("forward_evidence") or {}
        if fwd:
            st.markdown("**Data pendukung prospek**")
            consistency_labels = {"BROAD_IMPROVEMENT": "Membaik secara luas", "Broad Improvement": "Membaik secara luas"}
            raw_consistency = fwd.get("consistency")
            st.write(f"Konsistensi proyeksi: {consistency_labels.get(str(raw_consistency), _human_state(raw_consistency))}")
            st.write(f"Cakupan data pendukung: {round(float(fwd.get('coverage', 0))*100)}%")
            val = fwd.get("valuation_context") or {}
            st.write(f"Estimasi laba per saham ke depan (EPS): {_fmt_price(val.get('eps_forward'))} | Rasio PEG ke depan: {_fmt_price(val.get('peg_forward'))}")


def render_final_results(result, packages):
    if not isinstance(result, dict) or result.get("status") != "COMPLETE":
        st.error("Analisis belum dapat diselesaikan.")
        return
    stage3 = result.get("stage3") or {}
    ranking = stage3.get("ranking") or {}
    swing = ranking.get("swing") or {}
    long_term = ranking.get("long_term") or {}
    candidates = stage3.get("candidates") or []

    st.subheader("Hasil Analisis SIS")
    counts = result.get("counts") or {}
    st.caption(f"{counts.get('p10', 0)} saham selesai dianalisis. Pemeriksaan, analisis, dan pemeringkatan dijalankan otomatis di background.")

    # Power Screener funnel: presentation only; Stage 3 remains the analytical source of truth.
    def _select_funnel_symbol(symbol, horizon):
        if horizon == "swing":
            st.session_state["final_swing_symbol"] = symbol
        else:
            st.session_state["final_lt_symbol"] = symbol

    render_opportunity_funnel(st, stage3, on_symbol=_select_funnel_symbol)
    st.divider()
    st.markdown("### Analisis Lengkap per Saham")

    swing_tab, lt_tab = st.tabs(["Swing", "Jangka Panjang"])
    with swing_tab:
        top = swing.get("top") or []
        watch = swing.get("watch") or []
        if not top:
            st.info("Belum ada kandidat Swing yang memenuhi seluruh kriteria untuk siap dipertimbangkan pada snapshot ini.")
        options = []
        labels = {}
        for row in top:
            sym = row.get("symbol")
            options.append(sym); labels[sym] = f"#{row.get('rank')} {sym} — Siap dipertimbangkan"
        for row in watch:
            sym = row.get("symbol")
            if sym not in labels:
                options.append(sym); labels[sym] = f"{sym} — {_human_state(row.get('execution_status'))}"
        for candidate in candidates:
            sym = candidate.get("symbol")
            if sym and sym not in labels:
                options.append(sym)
                labels[sym] = f"{sym} — Semua saham lain tetap dapat dibuka"
        if options:
            selected = st.selectbox("Pilih saham untuk melihat analisis Swing", options, format_func=lambda x: labels.get(x, x), key="final_swing_symbol")
            cand = _candidate_for(stage3, selected)
            st.subheader(f"{selected} — Analisis Swing", anchor=False)
            _render_swing_detail(cand, _package_for(packages, selected))
        else:
            st.caption("Belum ada kandidat Swing yang dapat ditampilkan.")

    with lt_tab:
        top = long_term.get("top") or []
        if not top:
            st.info("Belum ada kandidat Jangka Panjang yang memenuhi kriteria ranking pada snapshot ini.")
        labels = {row.get("symbol"): f"#{row.get('rank')} {row.get('symbol')} — Analisis jangka panjang" for row in top}
        lt_options = [row.get("symbol") for row in top if row.get("symbol")]
        for candidate in candidates:
            sym = candidate.get("symbol")
            if sym and sym not in labels:
                lt_options.append(sym)
                labels[sym] = f"{sym} — Lihat analisis lengkap"
        if lt_options:
            selected = st.selectbox("Pilih saham untuk melihat analisis Jangka Panjang", lt_options, format_func=lambda x: labels.get(x, x), key="final_lt_symbol")
            cand = _candidate_for(stage3, selected)
            st.subheader(f"{selected} — Analisis Jangka Panjang", anchor=False)
            _render_longterm_detail(cand, _package_for(packages, selected))

    st.caption("Kualitas analisis menunjukkan kekuatan kandidat berdasarkan data pendukung. Tingkat keyakinan menunjukkan seberapa yakin SIS terhadap penilaian tersebut. Keduanya dinilai terpisah dan tidak digabungkan menjadi satu nilai akhir.")


st.title("SIS — Stock Intelligence System")
st.caption("Masukkan hasil screening, lalu jalankan analisis. Pemeriksaan dan penyiapan data dilakukan otomatis di background.")
st.info("📌 Input data B1–B11 wajib dilakukan setelah market tutup agar data antarbagian berasal dari kondisi pasar yang sama dan mengurangi ketidaksesuaian data input.")

filter_fp = st.text_input("Label sesi screening", value="S0-6FILTER")

with st.expander("Riwayat Input", expanded=False):
    history = list_snapshots()
    if history:
        labels = {f'{x["created_at"][:19].replace("T", " ")} | {x["status"]} | {x["snapshot_id"][-12:]}': x["snapshot_id"] for x in history}
        sel = st.selectbox("Pilih riwayat data", list(labels.keys()))
        if st.button("Muat Riwayat"):
            snap = load_snapshot(labels[sel])
            for bi in range(1, 12):
                st.session_state[f"paste_b{bi}"] = get_snapshot_batch(snap, bi)
            metadata = snap.get("metadata") or {}
            if metadata.get("expected_total"):
                st.session_state["loaded_expected_total"] = int(metadata["expected_total"])
            if metadata.get("filter_fingerprint"):
                st.session_state["loaded_filter_fp"] = str(metadata["filter_fingerprint"])
            st.rerun()
    else:
        st.caption("Belum ada riwayat input.")

raw_inputs = {}
parsed = {}
input_issues = []
with st.expander("Data Screening B1–B11", expanded=True):
    tabs = st.tabs([f"B{i}" for i in range(1, 12)])
    for i, tab in enumerate(tabs, 1):
        with tab:
            text = st.text_area(f"Data B{i}", height=180, key=f"paste_b{i}")
            raw_inputs[i] = text
            if not text.strip():
                continue
            df, issues = parse_clipboard_text(text)
            schema_issues = validate_batch(df, i) if not issues else []
            all_issues = list(issues) + list(schema_issues)
            if all_issues:
                input_issues.extend(all_issues)
                st.warning("Data pada bagian ini perlu diperiksa sebelum analisis dijalankan.")
            else:
                parsed[i] = df
                st.caption(f"Data terbaca: {len(df)} saham")

# Jumlah saham ditentukan otomatis dari universe B1.
# Kesamaan universe B1-B11 tetap divalidasi secara strict oleh Stage 1.
expected_total = len(parsed[1]) if 1 in parsed else 0

c_save, c_run = st.columns([1, 2])
with c_save:
    if st.button("Simpan ke Riwayat", use_container_width=True):
        if all(raw_inputs.get(i, "").strip() for i in range(1, 12)):
            snap = save_snapshot(raw_inputs, metadata={"expected_total": int(expected_total), "filter_fingerprint": filter_fp})
            st.success(f'Input tersimpan ({snap["snapshot_id"][-12:]}).')
        else:
            st.warning("Lengkapi B1–B11 sebelum menyimpan.")

with c_run:
    run_clicked = st.button("Run Analysis", type="primary", use_container_width=True)

if run_clicked:
    st.session_state.pop("analysis_packages", None)
    st.session_state.pop("stage3_result", None)
    if not all(raw_inputs.get(i, "").strip() for i in range(1, 12)):
        render_notice("Analisis belum dapat dijalankan", ["Lengkapi seluruh bagian data B1–B11 terlebih dahulu."])
    elif input_issues:
        render_notice("Ada data yang perlu diperiksa", [friendly_input_issue(x) for x in input_issues])
    elif len(parsed) != 11:
        render_notice("Analisis belum dapat dijalankan", ["Sebagian data belum berhasil disiapkan. Periksa kembali B1–B11."])
    else:
        with st.status("Menjalankan analisis SIS…", expanded=True) as status:
            st.write("Memeriksa kelengkapan dan konsistensi data…")
            s1 = run_stage1(parsed, expected_total=int(expected_total), filter_fingerprint=filter_fp)
            if s1["status"] != "PASS":
                status.update(label="Analisis dihentikan — data perlu diperiksa", state="error")
                st.session_state["analysis_blocked"] = [friendly_stage1_issue(x) for x in s1.get("issues", [])]
            else:
                st.write("Menyiapkan data untuk analisis…")
                st.write("Menganalisis kandidat Swing dan Jangka Panjang…")
                s2 = run_stage2(s1["canonical"])
                if s2.status != "PASS":
                    status.update(label="Analisis belum dapat diselesaikan", state="error")
                    st.session_state["analysis_blocked"] = ["SIS belum dapat menyelesaikan analisis untuk seluruh saham. Silakan jalankan kembali atau periksa input."]
                else:
                    st.session_state["analysis_packages"] = s2.packages
                    st.write("Menyelesaikan analisis dan pemeringkatan…")
                    from datetime import date
                    s3_result = run_stage3_from_current_analysis(
                        s1["canonical"], s2.packages, analysis_as_of=date.today().isoformat(), top_n=3
                    )
                    if s3_result.get("status") != "COMPLETE":
                        status.update(label="Analisis belum dapat diselesaikan", state="error")
                        st.session_state["analysis_blocked"] = ["SIS belum dapat menyelesaikan seluruh analisis. Silakan jalankan kembali atau periksa input."]
                    else:
                        st.session_state["stage3_result"] = s3_result
                        st.session_state.pop("analysis_blocked", None)
                        status.update(label="Analisis selesai", state="complete", expanded=False)

if st.session_state.get("analysis_blocked"):
    render_notice("Data perlu diperiksa sebelum analisis dilanjutkan", st.session_state["analysis_blocked"])

if "stage3_result" in st.session_state:
    st.divider()
    render_final_results(st.session_state["stage3_result"], st.session_state.get("analysis_packages", []))
