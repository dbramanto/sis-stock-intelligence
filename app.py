from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
import importlib.util
from zoneinfo import ZoneInfo
import json
import sys
import logging
from logging.handlers import RotatingFileHandler
import streamlit as st

_APP_ROOT = Path(__file__).resolve().parent
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from stage1.clipboard import parse_clipboard_text
from stage1.pipeline import run_stage1, validate_batch
from stage1.history import get_snapshot_batch, list_snapshots, load_snapshot, save_validated_snapshot, update_snapshot_analysis
from stage2.runner import run_stage2

for _p in (_APP_ROOT / "integration_pipeline", _APP_ROOT / "stage3"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from integration_pipeline.pipeline_p10_orchestrator import run_pipeline
from stage3.stage3_e2e_runner import run_stage3_universe
from stage3.result_store import save_analysis_result, load_analysis_result, result_exists
from stage3.opportunity_funnel_ui import render_opportunity_funnel, render_stock_detail

st.set_page_config(page_title="SIS v2 — Input Data", page_icon="📊", layout="wide", initial_sidebar_state="collapsed")

_LOG_DIR = _APP_ROOT / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "sis_runtime.log"

def _build_logger():
    logger = logging.getLogger("SIS.RUNTIME")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(fmt)
        logger.addHandler(console)
        file_handler = RotatingFileHandler(_LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    return logger

LOG = _build_logger()

def _log_issues(stage, issues):
    items = list(issues or [])
    LOG.error("[%s] BLOCKED | issue_count=%d", stage, len(items))
    for item in items:
        LOG.error("[%s] ISSUE | %s", stage, item)

if "sis_theme" not in st.session_state:
    st.session_state.sis_theme = "light"

def _toggle_theme():
    st.session_state.sis_theme = "dark" if st.session_state.sis_theme == "light" else "light"

def _peer_universe_total(parsed):
    """Return dynamic universe size only when all B1-B11 symbol sets agree exactly."""
    if set(parsed) != set(range(1, 12)):
        return 0
    sets = []
    for i in range(1, 12):
        df = parsed[i]
        symbol_col = next((c for c in df.columns if str(c).strip().lower() == "symbol"), None)
        if symbol_col is None:
            return 0
        symbols = {str(x).strip().upper() for x in df[symbol_col].tolist() if str(x).strip()}
        sets.append(symbols)
    first = sets[0]
    return len(first) if first and all(s == first for s in sets[1:]) else 0

def _canonical_map(df):
    out = {}
    for _, row in df.iterrows():
        d = row.to_dict(); symbol = str(d.get("symbol", "")).strip().upper()
        if symbol: out[symbol] = d
    return out

def _run_stage3(canonical, packages, analysis_as_of):
    LOG.info("[P10] START | packages=%d | as_of=%s", len(packages), analysis_as_of)
    p10 = run_pipeline(stage2_records=packages, analysis_as_of=analysis_as_of, canonical_by_symbol=_canonical_map(canonical))
    LOG.info("[P10] END | state=%s | payloads=%d | diagnostics=%d | rejected=%d", p10.state, len(p10.payloads), len(p10.diagnostics), len(p10.rejected_evidence_ids))
    for item in p10.diagnostics:
        LOG.warning("[P10] DIAGNOSTIC | %s", item)
    if p10.state == "BLOCKED":
        return {"status": "BLOCKED", "blocked_stage": "P10", "diagnostics": list(p10.diagnostics)}
    LOG.info("[S3] START | payloads=%d | top_n=3", len(p10.payloads))
    result = run_stage3_universe(list(p10.payloads), analysis_date=analysis_as_of, top_n=3)
    LOG.info("[S3] END | status=%s | candidates=%s | blocked=%d", result.get("status"), result.get("candidate_count"), len(result.get("blocked", [])))
    for item in result.get("blocked", []):
        LOG.warning("[S3] BLOCKED_CANDIDATE | %s", item)
    return result

def _friendly(issue):
    s = str(issue)
    if "MISSING_SYMBOL_COLUMN" in s: return "Kolom Symbol/kode saham belum terbaca."
    if "DUPLICATE_SYMBOL" in s: return "Ada kode saham yang tercatat lebih dari satu kali."
    if "MISSING_COLUMNS:" in s: return "Ada kolom wajib yang belum ditemukan pada data."
    if "UNIVERSE_MISMATCH" in s: return "Daftar saham antar B tidak sama. Pastikan B1–B11 berasal dari screening yang sama."
    if "UNIVERSE_INCOMPLETE" in s: return "Jumlah saham antar batch tidak konsisten dengan universe sesi yang tervalidasi."
    if "AMBIGUOUS_NUMERIC_FORMAT" in s or "INVALID_NUMERIC" in s: return "Ada angka yang tidak dapat dibaca dengan aman."
    if "CONTROL_SANITY" in s: return "Ada nilai kontrol di luar batas yang masuk akal."
    return "Data belum lolos pemeriksaan keamanan SIS."

def _clear_analysis_state():
    for key in ("v2_stage1", "v2_packages", "v2_stage3", "v2_snapshot_id", "v2_blocked", "v2_detail_symbol", "v2_detail_horizon"):
        st.session_state.pop(key, None)

JAKARTA_TZ = ZoneInfo("Asia/Jakarta")

def _jakarta_now():
    return datetime.now(JAKARTA_TZ)

def _market_label(now=None):
    now = now or _jakarta_now()
    hm = now.hour * 60 + now.minute
    weekday = now.weekday() < 5
    # Practical IDX session window in WIB for user-facing status.
    opened = weekday and 9 * 60 <= hm < 16 * 60
    if opened:
        return ("Market Buka", "Input direkomendasikan setelah market tutup", "open")
    return ("Market Tutup", "Waktu terbaik untuk input data", "closed")

def _last_closed_market_date(now=None):
    now = now or _jakarta_now()
    d = now.date()
    hm = now.hour * 60 + now.minute
    # During an open weekday session, today's closing data is not final yet.
    if now.weekday() < 5 and 9 * 60 <= hm < 16 * 60:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d

def _theme_css(theme):
    dark = theme == "dark"
    bg = "#081525" if dark else "#eef5fb"
    surface = "#0f2238" if dark else "#ffffff"
    surface2 = "#132a44" if dark else "#f6faff"
    text = "#edf5ff" if dark else "#102b4e"
    muted = "#9fb1c7" if dark else "#60738b"
    border = "#29425e" if dark else "#d8e5f1"
    shadow = "0 10px 28px rgba(0,0,0,.22)" if dark else "0 8px 24px rgba(28,73,117,.10)"
    return f"""
<style>
:root{{--bg:{bg};--surface:{surface};--surface2:{surface2};--text:{text};--muted:{muted};--border:{border};--blue:#1473e6;--blue2:#0b5fc5;--green:#079455;--amber:#f5a300;--red:#dc3545;--shadow:{shadow};}}
html,body,[class*="css"],.stApp{{font-family:Inter,Segoe UI,Arial,sans-serif;}}
.stApp{{background:var(--bg);color:var(--text)}}
[data-testid="stHeader"]{{height:0;background:transparent}}
[data-testid="stToolbar"],[data-testid="stDecoration"],#MainMenu,footer{{display:none!important}}
[data-testid="stSidebar"]{{display:none!important}}
.block-container{{max-width:1540px;padding:0 18px 28px!important}}
.sis-header{{margin:0 -18px 14px;padding:12px 24px;background:linear-gradient(115deg,#0a315d,#0b477e 60%,#07345e);color:white;display:flex;align-items:center;gap:26px;min-height:74px;box-shadow:0 5px 18px rgba(0,33,70,.22)}}
.brand{{display:flex;align-items:center;gap:14px;min-width:300px}}.brandmark{{font:900 42px Georgia,serif;letter-spacing:-2px}}.brandtext b{{font-size:16px}}.brandtext small{{display:block;font-size:11px;opacity:.86;margin-top:4px}}
.nav{{display:flex;gap:7px;flex:1}}.navitem{{padding:11px 14px;border-radius:8px;font-size:13px;color:#dcecff}}.navitem.active{{background:rgba(50,139,229,.32);font-weight:800;color:white}}
.hstatus{{display:flex;gap:10px;align-items:center}}.datebox,.readybox{{border:1px solid rgba(255,255,255,.25);border-radius:9px;padding:8px 12px;font-size:11px;line-height:1.35}}.datebox b,.readybox b{{font-size:12px}}.readybox{{background:#079455;border-color:#079455}}
.hero{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:17px 20px;box-shadow:var(--shadow);margin-bottom:12px}}.hero h1{{font-size:25px;margin:0;color:var(--text);letter-spacing:-.3px}}.hero p{{font-size:13px;color:var(--muted);margin:4px 0 0}}
.sectionhead{{display:flex;align-items:center;justify-content:space-between;margin:0 0 9px}}.sectionhead h3{{font-size:15px;margin:0;color:var(--text)}}.eyebrow{{font-size:11px;color:var(--blue);font-weight:800;text-transform:uppercase;letter-spacing:.08em}}
.info-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:10px}}.info{{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:10px 12px}}.info b{{display:block;font-size:18px;color:var(--text)}}.info span{{font-size:11px;color:var(--muted)}}
.guard{{background:rgba(7,148,85,.10);border:1px solid rgba(7,148,85,.24);border-radius:9px;padding:10px 12px;color:var(--text);font-size:12px}}.guard b{{color:#079455}}
.tipcard{{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px;box-shadow:var(--shadow);margin-bottom:10px}}.tiprow{{display:flex;gap:10px;padding:7px 0;border-bottom:1px solid var(--border);font-size:12px;color:var(--text)}}.tiprow:last-child{{border:0}}.tipnum{{width:23px;height:23px;display:grid;place-items:center;border-radius:50%;background:rgba(20,115,230,.12);color:var(--blue);font-weight:800;flex:none}}
[data-testid="stVerticalBlockBorderWrapper"]{{background:var(--surface);border-color:var(--border)!important;border-radius:12px!important;box-shadow:var(--shadow)}}
label,p,.stMarkdown{{color:var(--text)}}
.stTextInput input,.stTextArea textarea,[data-baseweb="select"]>div{{background:var(--surface2)!important;color:var(--text)!important;border-color:var(--border)!important}}
.stTextArea textarea{{font-family:"Cascadia Mono",Consolas,monospace;font-size:12px;line-height:1.45}}
[data-baseweb="tab-list"]{{gap:5px;background:var(--surface2);padding:5px;border:1px solid var(--border);border-radius:9px}}
button[data-baseweb="tab"]{{height:34px;border-radius:7px;padding:0 12px;color:var(--muted)}}button[data-baseweb="tab"][aria-selected="true"]{{background:var(--blue)!important;color:white!important;font-weight:800}}
[data-testid="stMetric"]{{background:var(--surface2);border:1px solid var(--border);border-radius:9px;padding:8px 11px}}[data-testid="stMetricLabel"]{{color:var(--muted)}}[data-testid="stMetricValue"]{{color:var(--text);font-size:20px}}
.stButton>button{{border-radius:8px;border:1px solid var(--border);font-weight:750;background:var(--surface)!important;color:var(--text)!important}}.stButton>button:hover{{border-color:var(--blue)!important;color:var(--blue)!important}}.stButton>button[kind="primary"]{{background:linear-gradient(180deg,#2383ee,#0d66cf)!important;color:white!important;border:0;min-height:44px}}
.flow{{display:grid;grid-template-columns:repeat(5,1fr);gap:7px}}.flow>div{{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:9px;text-align:center;font-size:11px;color:var(--muted)}}.flow b{{display:block;color:var(--text);font-size:12px;margin-bottom:2px}}
.sis-footer{{display:flex;justify-content:space-between;padding:13px 2px;color:var(--muted);font-size:10px}}
@media(max-width:900px){{.brand{{min-width:auto}}.brandtext,.nav,.readybox{{display:none}}.sis-header{{gap:10px}}.hstatus{{margin-left:auto}}.info-grid,.flow{{grid-template-columns:1fr}}}}
</style>"""

st.markdown(_theme_css(st.session_state.sis_theme), unsafe_allow_html=True)
now = _jakarta_now()
market, market_sub, market_state = _market_label(now)
closed_date = _last_closed_market_date(now)
header_label = "Data penutupan terakhir yang dianalisis:" if market_state == "open" else "Data penutupan yang dianalisis:"

st.markdown(f'''<div class="sis-header"><div class="brand"><div class="brandmark">SIS</div><div class="brandtext"><b>Smart Investment Screener</b><small>Analisis hari ini, rencana untuk esok.</small></div></div><div class="nav"><div class="navitem">⌂ &nbsp;Beranda</div><div class="navitem active">▤ &nbsp;Input Data</div><div class="navitem">▥ &nbsp;Hasil Screening</div><div class="navitem">◷ &nbsp;Riwayat</div><div class="navitem">ⓘ &nbsp;Panduan</div></div><div class="hstatus"><div class="datebox">▣ &nbsp; {header_label}<br><b>{closed_date.strftime('%d %B %Y')}</b><br>({market})</div><div class="readybox">✓ &nbsp;<b>D1 Input & Snapshot</b><br>{market_sub}</div></div></div>''', unsafe_allow_html=True)

head_l, head_r = st.columns([8.8,1.2], vertical_alignment="center")
with head_l:
    st.markdown('''<div class="hero"><div class="eyebrow">Fase D1 · Data Foundation</div><h1>Input Data & Snapshot SIS</h1><p>Masukkan hasil screening B1–B11. SIS hanya membuat snapshot resmi setelah data dan seluruh guard validasi dinyatakan aman.</p></div>''', unsafe_allow_html=True)
with head_r:
    st.button("☀ Light" if st.session_state.sis_theme == "dark" else "☾ Dark", on_click=_toggle_theme, use_container_width=True)

main, side = st.columns([2.15, .85], gap="medium")

with side:
    st.markdown('''<div class="tipcard"><div class="sectionhead"><h3>💡 Panduan Input</h3></div><div class="tiprow"><span class="tipnum">1</span><span><b>Input setelah market tutup</b><br>Gunakan data penutupan terbaru.</span></div><div class="tiprow"><span class="tipnum">2</span><span><b>B1–B11 harus satu sesi</b><br>Universe saham harus konsisten.</span></div><div class="tiprow"><span class="tipnum">3</span><span><b>Copy langsung dari Stockbit</b><br>Tidak perlu mengubah format manual.</span></div><div class="tiprow"><span class="tipnum">4</span><span><b>Guard tidak boleh dilewati</b><br>Data invalid tidak menjadi snapshot.</span></div></div>''', unsafe_allow_html=True)
    history = list_snapshots(validated_only=True)
    with st.container(border=True):
        st.markdown("### ◷ Riwayat Snapshot")
        st.caption("Hanya snapshot yang sudah tervalidasi.")
        if not history:
            st.info("Belum ada snapshot tervalidasi.")
        else:
            labels = {}
            for x in history[:8]:
                snap = load_snapshot(x["snapshot_id"])
                md = snap.get("metadata") or {}
                analysis_status = md.get("analysis_status") or "PENDING"
                total = md.get("expected_total") or "—"
                stamp = x["created_at"][:16].replace("T"," ")
                labels[f"{stamp} · {total} saham · {analysis_status}"] = x["snapshot_id"]
            selected_history = st.selectbox("Snapshot", list(labels), label_visibility="collapsed")
            selected_snapshot_id = labels[selected_history]
            selected_snap = load_snapshot(selected_snapshot_id)
            selected_md = selected_snap.get("metadata") or {}
            s1, s2, s3 = st.columns(3)
            s1.metric("Status analisis", selected_md.get("analysis_status") or "PENDING")
            s2.metric("Jumlah saham", selected_md.get("expected_total") or "—")
            s3.metric("Sesi", selected_md.get("filter_fingerprint") or "—")
            st.download_button(
                "⬇ Unduh Snapshot",
                data=json.dumps(selected_snap, ensure_ascii=False, indent=2),
                file_name=f"{selected_snapshot_id}.json",
                mime="application/json",
                use_container_width=True,
            )
            if result_exists(selected_snapshot_id):
                st.caption("Hasil analisis tersimpan dan dapat dimuat bersama snapshot ini.")
            else:
                st.caption("Snapshot input valid tersedia. Hasil analisis belum tersimpan untuk snapshot ini.")
            if st.button("Muat Snapshot", use_container_width=True):
                snap = selected_snap
                for bi in range(1, 12): st.session_state[f"v2_b{bi}"] = get_snapshot_batch(snap, bi)
                md = snap.get("metadata") or {}
                if md.get("filter_fingerprint"): st.session_state["loaded_filter_fp"] = str(md["filter_fingerprint"])
                _clear_analysis_state()
                st.session_state["v2_snapshot_id"] = snap["snapshot_id"]
                if result_exists(snap["snapshot_id"]):
                    try:
                        st.session_state["v2_stage3"] = load_analysis_result(snap["snapshot_id"])["stage3"]
                    except Exception as exc:
                        LOG.error("[D2] LOAD FAILED | id=%s | error=%s", snap["snapshot_id"], exc)
                st.rerun()
    st.markdown('''<div class="guard"><b>✓ Validated Snapshot Guard</b><br>Snapshot lama boleh digantikan hanya oleh data yang lolos pemeriksaan. Input invalid tidak dapat merusak snapshot valid.</div>''', unsafe_allow_html=True)

with main:
    with st.container(border=True):
        st.markdown('<div class="sectionhead"><div><div class="eyebrow">Screening Source</div><h3>Data Screening B1–B11</h3></div></div>', unsafe_allow_html=True)
        filter_fp = st.text_input("Label sesi screening", value=st.session_state.get("loaded_filter_fp", "S0-6FILTER"), help="Identitas screening yang menjadi bagian dari snapshot.")
        raw_inputs, parsed, issues_by_batch = {}, {}, {}
        tabs = st.tabs([f"B{i}" for i in range(1, 12)])
        for i, tab in enumerate(tabs, 1):
            with tab:
                text = st.text_area(f"Data B{i}", height=230, key=f"v2_b{i}", placeholder=f"Tempel hasil screening Stockbit B{i} di sini…")
                raw_inputs[i] = text
                if text.strip():
                    df, parse_issues = parse_clipboard_text(text)
                    schema_issues = validate_batch(df, i) if not parse_issues else []
                    all_issues = list(parse_issues) + list(schema_issues)
                    if all_issues:
                        issues_by_batch[i] = all_issues; st.error("Data B%d belum valid." % i)
                        for item in dict.fromkeys(_friendly(x) for x in all_issues): st.caption("• " + item)
                    else:
                        parsed[i] = df; st.success(f"B{i} valid · {len(df)} saham terbaca")
                else:
                    st.caption(f"B{i} belum diisi.")

        filled = sum(bool(raw_inputs.get(i, "").strip()) for i in range(1, 12))
        valid_batches = len(parsed); expected_total = _peer_universe_total(parsed)
        st.markdown('<div class="info-grid">' +
            f'<div class="info"><b>{filled}/11</b><span>Data terisi</span></div>' +
            f'<div class="info"><b>{valid_batches}/11</b><span>Lolos pemeriksaan awal</span></div>' +
            f'<div class="info"><b>{expected_total if expected_total else "—"}</b><span>Universe saham</span></div></div>', unsafe_allow_html=True)
        if filled < 11: st.warning("Lengkapi B1–B11. Snapshot resmi belum dapat dibuat.")
        elif issues_by_batch: st.error("Ada batch yang belum valid. Perbaiki bagian yang ditandai sebelum diproses.")
        else: st.success("B1–B11 lolos pemeriksaan awal. Siap untuk validasi silang dan analisis SIS.")
        run_clicked = st.button("▶  VALIDASI & PROSES DATA", type="primary", use_container_width=True, disabled=not (filled == 11 and valid_batches == 11))
        st.caption("🔒 Snapshot resmi tersimpan otomatis segera setelah Stage 1 PASS. Status analisis diperbarui pada snapshot yang sama saat Stage 2/P10/Stage 3 berjalan.")

if run_clicked:
    _clear_analysis_state()
    LOG.info("[RUN] START | expected_total=%d | filter=%s | batches=%d", int(expected_total), filter_fp, len(parsed))
    with st.status("SIS sedang memvalidasi data…", expanded=True) as status:
        st.write("1/4 · Validasi silang B1–B11")
        LOG.info("[S1] START | cross-validation B1-B11")
        s1 = run_stage1(parsed, expected_total=int(expected_total), filter_fingerprint=filter_fp)
        LOG.info("[S1] END | status=%s | issues=%d | canonical_rows=%d", s1.get("status"), len(s1.get("issues", [])), len(s1.get("canonical", [])))
        if s1.get("status") != "PASS":
            _log_issues("S1", s1.get("issues", []))
            LOG.error("[RUN] STOP | Stage2/Stage3 NOT EXECUTED")
            st.session_state["v2_blocked"] = [_friendly(x) for x in s1.get("issues", [])]
            status.update(label="Dihentikan — data belum valid", state="error")
        else:
            LOG.info("[SNAPSHOT] AUTO-SAVE START | trigger=S1_PASS")
            snap = save_validated_snapshot(raw_inputs, canonical=s1["canonical"], validation_status=s1["status"], metadata={"expected_total": int(expected_total), "filter_fingerprint": filter_fp, "analysis_status": "PENDING", "analysis_as_of": date.today().isoformat()})
            st.session_state["v2_snapshot_id"] = snap["snapshot_id"]
            LOG.info("[SNAPSHOT] AUTO-SAVED | id=%s | analysis_status=%s", snap["snapshot_id"], (snap.get("metadata") or {}).get("analysis_status"))
            st.write("2/4 · Snapshot valid tersimpan otomatis · Analisis Stage 2")
            LOG.info("[S2] START | canonical_rows=%d", len(s1["canonical"]))
            s2 = run_stage2(s1["canonical"])
            LOG.info("[S2] END | status=%s | packages=%d", s2.status, len(s2.packages))
            if s2.status != "PASS":
                LOG.error("[S2] BLOCKED | status=%s", s2.status)
                LOG.error("[RUN] STOP | Stage3 NOT EXECUTED")
                update_snapshot_analysis(snap["snapshot_id"], "S2_BLOCKED")
                LOG.warning("[SNAPSHOT] STATUS | id=%s | analysis_status=S2_BLOCKED", snap["snapshot_id"])
                st.session_state["v2_blocked"] = ["Analisis Stage 2 belum selesai dengan aman. Snapshot input valid tetap tersimpan."]
                status.update(label="Dihentikan — Stage 2 belum PASS", state="error")
            else:
                st.write("3/4 · Analisis dan ranking Stage 3")
                s3 = _run_stage3(s1["canonical"], s2.packages, date.today().isoformat())
                if s3.get("status") != "COMPLETE":
                    _log_issues("S3", s3.get("diagnostics", []))
                    blocked_stage = "P10_BLOCKED" if s3.get("blocked_stage") == "P10" else "S3_BLOCKED"
                    update_snapshot_analysis(snap["snapshot_id"], blocked_stage, metadata_updates={"stage3_diagnostics": s3.get("diagnostics", [])})
                    LOG.error("[RUN] STOP | validated snapshot retained | id=%s", snap["snapshot_id"])
                    st.session_state["v2_blocked"] = ["Analisis Stage 3 belum COMPLETE. Snapshot input valid tetap tersimpan."]
                    status.update(label="Dihentikan — Stage 3 belum COMPLETE", state="error")
                else:
                    st.write("4/4 · Simpan hasil analisis dan finalisasi snapshot")
                    LOG.info("[D2] RESULT SAVE START | id=%s", snap["snapshot_id"])
                    try:
                        saved_result = save_analysis_result(snap["snapshot_id"], s3, date.today().isoformat())
                        LOG.info("[D2] RESULT SAVED | id=%s | digest=%s", snap["snapshot_id"], saved_result.get("stage3_digest"))
                    except Exception as exc:
                        LOG.exception("[D2] RESULT SAVE FAILED | id=%s", snap["snapshot_id"])
                        update_snapshot_analysis(snap["snapshot_id"], "S3_BLOCKED", metadata_updates={"result_persistence_error": str(exc)})
                        st.session_state["v2_blocked"] = ["Analisis selesai, tetapi hasil belum dapat disimpan dengan aman. Snapshot input valid tetap tersimpan."]
                        status.update(label="Dihentikan — hasil analisis belum tersimpan", state="error")
                        st.stop()
                    snap = update_snapshot_analysis(snap["snapshot_id"], "COMPLETE", metadata_updates={"analysis_as_of": date.today().isoformat(), "stage2_status": s2.status, "stage3_status": s3.get("status"), "stage3_candidate_count": s3.get("candidate_count"), "stage3_blocked_count": len(s3.get("blocked", [])), "result_persisted": True, "result_digest": saved_result.get("stage3_digest")})
                    st.session_state["v2_stage1"] = s1; st.session_state["v2_packages"] = s2.packages; st.session_state["v2_stage3"] = s3; st.session_state["v2_snapshot_id"] = snap["snapshot_id"]
                    LOG.info("[SNAPSHOT] FINALIZED | id=%s | analysis_status=COMPLETE", snap["snapshot_id"])
                    LOG.info("[RUN] COMPLETE | S1=PASS | S2=PASS | S3=COMPLETE")
                    status.update(label="Data valid · analisis selesai · snapshot resmi siap", state="complete", expanded=False)

if st.session_state.get("v2_blocked"):
    if st.session_state.get("v2_snapshot_id"):
        st.error("Analisis dihentikan, tetapi snapshot input yang sudah tervalidasi tetap tersimpan.")
    else:
        st.error("Proses dihentikan. Snapshot resmi tidak dibuat karena Stage 1 belum PASS.")
    for msg in dict.fromkeys(st.session_state["v2_blocked"]): st.write("• " + msg)
if st.session_state.get("v2_snapshot_id"):
    st.success("Snapshot tervalidasi berhasil disiapkan.")
    a, b, c = st.columns(3); a.metric("Status", "VALIDATED"); b.metric("Saham", expected_total); c.metric("Snapshot", st.session_state["v2_snapshot_id"][-10:])
    try:
        active_snap = load_snapshot(st.session_state["v2_snapshot_id"])
        st.download_button(
            "⬇ Unduh Snapshot Valid",
            data=json.dumps(active_snap, ensure_ascii=False, indent=2),
            file_name=f'{st.session_state["v2_snapshot_id"]}.json',
            mime="application/json",
        )
    except Exception as exc:
        LOG.warning("[SNAPSHOT] DOWNLOAD PREP FAILED | id=%s | error=%s", st.session_state.get("v2_snapshot_id"), exc)

if st.session_state.get("v2_stage3"):
    st.markdown("---")
    def _open_result_symbol(symbol, horizon):
        st.session_state["v2_detail_symbol"] = symbol
        st.session_state["v2_detail_horizon"] = horizon
    render_opportunity_funnel(st, st.session_state["v2_stage3"], on_symbol=_open_result_symbol)
    if st.session_state.get("v2_detail_symbol"):
        render_stock_detail(st, st.session_state["v2_stage3"], st.session_state["v2_detail_symbol"], st.session_state.get("v2_detail_horizon", "swing"))

st.markdown('<div class="sis-footer"><span><b>SIS</b> · Smart Investment Screener &nbsp; | &nbsp; Analisis berbasis data penutupan. Bukan ajakan jual beli saham.</span><span>Investasi yang baik dimulai dari informasi yang tepat.</span></div>', unsafe_allow_html=True)
