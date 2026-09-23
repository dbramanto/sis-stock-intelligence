from __future__ import annotations

from datetime import date
from pathlib import Path
import sys
import streamlit as st

from stage1.clipboard import parse_clipboard_text
from stage1.pipeline import run_stage1, validate_batch
from stage1.history import (
    get_snapshot_batch,
    list_snapshots,
    load_snapshot,
    save_validated_snapshot,
)
from stage2.runner import run_stage2

_APP_ROOT = Path(__file__).resolve().parent
for _p in (_APP_ROOT / "integration_pipeline", _APP_ROOT / "stage3"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from integration_pipeline.pipeline_p10_orchestrator import run_pipeline
from stage3.stage3_e2e_runner import run_stage3_universe

st.set_page_config(page_title="SIS v2 — Input Data", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container {max-width: 1220px; padding-top: 1.5rem; padding-bottom: 3rem;}
[data-testid="stMetric"] {border:1px solid rgba(128,128,128,.22); border-radius:14px; padding:14px 16px;}
.sis-head {padding:18px 22px; border:1px solid rgba(128,128,128,.22); border-radius:18px; margin-bottom:16px;}
.sis-kicker {font-size:.78rem; letter-spacing:.12em; font-weight:700; opacity:.65;}
.sis-title {font-size:1.75rem; font-weight:760; margin:.15rem 0 .25rem 0;}
.sis-muted {opacity:.72;}
.sis-ok {padding:12px 15px; border-radius:12px; background:rgba(46,160,67,.10); border:1px solid rgba(46,160,67,.28);}
.sis-warn {padding:12px 15px; border-radius:12px; background:rgba(210,153,34,.10); border:1px solid rgba(210,153,34,.28);}
</style>
""", unsafe_allow_html=True)


def _canonical_map(df):
    out = {}
    for _, row in df.iterrows():
        d = row.to_dict()
        symbol = str(d.get("symbol", "")).strip().upper()
        if symbol:
            out[symbol] = d
    return out


def _run_stage3(canonical, packages, analysis_as_of):
    p10 = run_pipeline(
        stage2_records=packages,
        analysis_as_of=analysis_as_of,
        canonical_by_symbol=_canonical_map(canonical),
    )
    if p10.state == "BLOCKED":
        return {"status": "BLOCKED", "diagnostics": list(p10.diagnostics)}
    return run_stage3_universe(list(p10.payloads), analysis_date=analysis_as_of, top_n=3)


def _friendly(issue):
    s = str(issue)
    if "MISSING_SYMBOL_COLUMN" in s:
        return "Kolom Symbol/kode saham belum terbaca."
    if "DUPLICATE_SYMBOL" in s:
        return "Ada kode saham yang tercatat lebih dari satu kali."
    if "MISSING_COLUMNS:" in s:
        return "Ada kolom wajib yang belum ditemukan pada data."
    if "UNIVERSE_MISMATCH" in s:
        return "Daftar saham antar B tidak sama. Pastikan B1–B11 berasal dari screening yang sama."
    if "UNIVERSE_INCOMPLETE" in s:
        return "Jumlah saham yang terbaca tidak sesuai dengan universe B1."
    if "AMBIGUOUS_NUMERIC_FORMAT" in s or "INVALID_NUMERIC" in s:
        return "Ada angka yang tidak dapat dibaca dengan aman."
    if "CONTROL_SANITY" in s:
        return "Ada nilai kontrol yang berada di luar batas yang masuk akal."
    return "Data belum lolos pemeriksaan keamanan SIS."


def _clear_analysis_state():
    for key in ("v2_stage1", "v2_packages", "v2_stage3", "v2_snapshot_id", "v2_blocked"):
        st.session_state.pop(key, None)


st.markdown("""
<div class="sis-head">
  <div class="sis-kicker">SIS v2 · D1</div>
  <div class="sis-title">Input Data & Snapshot</div>
  <div class="sis-muted">Masukkan B1–B11. SIS hanya membuat snapshot resmi setelah seluruh data dan analisis lolos pemeriksaan.</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### SIS v2")
    st.markdown("**Input Data**  · aktif")
    st.caption("Hasil Analisis · D2")
    st.caption("Monitoring · D4")
    st.caption("Riwayat")
    st.caption("Panduan")
    st.divider()
    st.caption("Beranda (D0) dibangun setelah seluruh modul dashboard selesai.")

filter_fp = st.text_input("Label sesi screening", value=st.session_state.get("loaded_filter_fp", "S0-6FILTER"), help="Identitas/konteks screening. Dipakai sebagai bagian identitas snapshot.")

history = list_snapshots(validated_only=True)
with st.expander("Snapshot tervalidasi", expanded=False):
    if not history:
        st.caption("Belum ada snapshot tervalidasi.")
    else:
        labels = {
            f'{x["created_at"][:19].replace("T", " ")} · {x["snapshot_id"][-12:]}': x["snapshot_id"]
            for x in history
        }
        selected_history = st.selectbox("Pilih snapshot", list(labels))
        if st.button("Muat snapshot", use_container_width=True):
            snap = load_snapshot(labels[selected_history])
            for bi in range(1, 12):
                st.session_state[f"v2_b{bi}"] = get_snapshot_batch(snap, bi)
            metadata = snap.get("metadata") or {}
            if metadata.get("filter_fingerprint"):
                st.session_state["loaded_filter_fp"] = str(metadata["filter_fingerprint"])
            _clear_analysis_state()
            st.rerun()

raw_inputs = {}
parsed = {}
issues_by_batch = {}

st.markdown("### Data Screening B1–B11")
tabs = st.tabs([f"B{i}" for i in range(1, 12)])
for i, tab in enumerate(tabs, 1):
    with tab:
        text = st.text_area(
            f"Data B{i}",
            height=210,
            key=f"v2_b{i}",
            placeholder=f"Tempel data B{i} dari Stockbit di sini…",
        )
        raw_inputs[i] = text
        if not text.strip():
            st.caption("Belum diisi")
            continue
        df, parse_issues = parse_clipboard_text(text)
        schema_issues = validate_batch(df, i) if not parse_issues else []
        all_issues = list(parse_issues) + list(schema_issues)
        if all_issues:
            issues_by_batch[i] = all_issues
            st.error("Data belum valid")
            for item in dict.fromkeys(_friendly(x) for x in all_issues):
                st.caption(f"• {item}")
        else:
            parsed[i] = df
            st.success(f"B{i} terbaca · {len(df)} saham")

filled = sum(bool(raw_inputs.get(i, "").strip()) for i in range(1, 12))
valid_batches = len(parsed)
expected_total = len(parsed[1]) if 1 in parsed else 0

st.divider()
c1, c2, c3, c4 = st.columns(4)
c1.metric("B terisi", f"{filled}/11")
c2.metric("B lolos awal", f"{valid_batches}/11")
c3.metric("Universe B1", expected_total if expected_total else "—")
c4.metric("Snapshot resmi", "Siap diuji" if valid_batches == 11 else "Belum")

if filled < 11:
    st.markdown('<div class="sis-warn">Lengkapi seluruh B1–B11. Data yang belum lengkap tidak dapat menjadi snapshot resmi.</div>', unsafe_allow_html=True)
elif issues_by_batch:
    st.markdown('<div class="sis-warn">Ada bagian yang belum valid. Perbaiki bagian bertanda merah sebelum proses dijalankan.</div>', unsafe_allow_html=True)
else:
    st.markdown('<div class="sis-ok">B1–B11 lolos pemeriksaan awal. Validasi silang dan analisis lengkap akan dijalankan sebelum snapshot resmi dibuat.</div>', unsafe_allow_html=True)

run_clicked = st.button(
    "VALIDASI & PROSES SIS",
    type="primary",
    use_container_width=True,
    disabled=not (filled == 11 and valid_batches == 11),
)

if run_clicked:
    _clear_analysis_state()
    with st.status("Memeriksa data dan menjalankan SIS…", expanded=True) as status:
        st.write("1/4 · Validasi silang B1–B11")
        s1 = run_stage1(parsed, expected_total=int(expected_total), filter_fingerprint=filter_fp)
        if s1.get("status") != "PASS":
            st.session_state["v2_blocked"] = [_friendly(x) for x in s1.get("issues", [])]
            status.update(label="Dihentikan — data belum valid", state="error")
        else:
            st.write("2/4 · Analisis Stage 2")
            s2 = run_stage2(s1["canonical"])
            if s2.status != "PASS":
                st.session_state["v2_blocked"] = ["Analisis Stage 2 belum selesai dengan aman. Snapshot tidak dibuat."]
                status.update(label="Dihentikan — analisis belum lengkap", state="error")
            else:
                st.write("3/4 · Analisis dan ranking Stage 3")
                s3 = _run_stage3(s1["canonical"], s2.packages, date.today().isoformat())
                if s3.get("status") != "COMPLETE":
                    st.session_state["v2_blocked"] = ["Analisis Stage 3 belum COMPLETE. Snapshot tidak dibuat."]
                    status.update(label="Dihentikan — analisis belum lengkap", state="error")
                else:
                    st.write("4/4 · Membentuk snapshot tervalidasi")
                    snap = save_validated_snapshot(
                        raw_inputs,
                        canonical=s1["canonical"],
                        validation_status=s1["status"],
                        metadata={
                            "expected_total": int(expected_total),
                            "filter_fingerprint": filter_fp,
                            "analysis_status": "COMPLETE",
                            "analysis_as_of": date.today().isoformat(),
                        },
                    )
                    st.session_state["v2_stage1"] = s1
                    st.session_state["v2_packages"] = s2.packages
                    st.session_state["v2_stage3"] = s3
                    st.session_state["v2_snapshot_id"] = snap["snapshot_id"]
                    status.update(label="Data valid · analisis selesai · snapshot resmi siap", state="complete", expanded=False)

if st.session_state.get("v2_blocked"):
    st.error("Proses dihentikan. Snapshot resmi tidak dibuat.")
    for msg in dict.fromkeys(st.session_state["v2_blocked"]):
        st.write(f"• {msg}")

if st.session_state.get("v2_snapshot_id"):
    st.success("Snapshot tervalidasi berhasil disiapkan.")
    a, b, c = st.columns(3)
    a.metric("Status", "VALIDATED")
    b.metric("Saham", expected_total)
    c.metric("ID Snapshot", st.session_state["v2_snapshot_id"][-12:])
    st.caption("Hasil analisis lengkap akan menjadi workspace D2. D1 tidak menduplikasi tampilan ranking/detail saham.")
