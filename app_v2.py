from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sys
import streamlit as st

from stage1.clipboard import parse_clipboard_text
from stage1.pipeline import run_stage1, validate_batch
from stage1.history import get_snapshot_batch, list_snapshots, load_snapshot, save_validated_snapshot
from stage2.runner import run_stage2

_APP_ROOT = Path(__file__).resolve().parent
for _p in (_APP_ROOT / "integration_pipeline", _APP_ROOT / "stage3"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
from integration_pipeline.pipeline_p10_orchestrator import run_pipeline
from stage3.stage3_e2e_runner import run_stage3_universe

st.set_page_config(page_title="SIS v2 — Input Data", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

st.markdown(r"""
<style>
:root{--sis-blue:#1769e8;--sis-navy:#10243b;--sis-border:#dbe5f1;--sis-soft:#f5f8fc;--sis-text:#13233a;--sis-muted:#637188;--sis-green:#159447;}
.stApp{background:#f3f6fb;color:var(--sis-text)}
[data-testid="stHeader"]{background:transparent}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#10243b 0%,#122a45 100%);border-right:0}
[data-testid="stSidebar"] *{color:#eef5ff}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{margin:0}
.block-container{max-width:1440px;padding:1.2rem 1.8rem 3rem}
.sis-brand{padding:12px 5px 20px}.sis-logo{font-size:2rem;font-weight:850;letter-spacing:-.04em}.sis-logo span{color:#3e8cff}.sis-sub{font-size:.78rem;opacity:.78;margin-top:2px}.sis-tag{font-size:.68rem;opacity:.62;margin-top:8px}
.navitem{padding:11px 13px;border-radius:10px;margin:5px 0;font-size:.92rem}.navactive{background:linear-gradient(90deg,#1266e9,#317ff1);font-weight:750}.navoff{opacity:.72}.navfuture{opacity:.45}
.sis-top{display:flex;justify-content:space-between;align-items:center;background:white;border:1px solid var(--sis-border);border-radius:15px;padding:14px 18px;margin-bottom:16px;box-shadow:0 5px 20px rgba(27,61,103,.05)}
.phase{display:inline-block;background:#1769e8;color:white;border-radius:8px;padding:8px 14px;font-weight:750;margin-right:14px}.top-title{font-weight:820;font-size:1.22rem}.top-sub{font-size:.78rem;color:var(--sis-muted);margin-top:2px}.market{background:#eef4ff;border-radius:10px;padding:8px 12px;font-weight:700}.market small{display:block;color:var(--sis-muted);font-weight:500}
.card{background:white;border:1px solid var(--sis-border);border-radius:16px;padding:18px 20px;box-shadow:0 5px 18px rgba(27,61,103,.045);margin-bottom:14px}.card-title{font-size:1.08rem;font-weight:820;margin-bottom:2px}.card-sub{color:var(--sis-muted);font-size:.82rem;margin-bottom:12px}
.tip{background:#eef5ff;border:1px solid #d8e7ff;border-radius:15px;padding:16px 18px;margin-bottom:14px}.tip h4{color:#1769e8;margin:0 0 10px}.tiprow{display:flex;gap:10px;margin:10px 0;font-size:.82rem}.tipnum{min-width:26px;height:26px;border-radius:50%;background:#cfe1ff;color:#1769e8;display:flex;align-items:center;justify-content:center;font-weight:800}.safe{background:#eaf9f0;border:1px solid #ccefd9;border-radius:14px;padding:14px 16px;color:#176b39;font-size:.82rem;margin-bottom:14px}.safe b{font-size:.94rem}.section-title{font-size:1.05rem;font-weight:820;margin:5px 0 8px}.stepbar{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 12px}.step{padding:7px 10px;border-radius:8px;background:#edf1f6;color:#607086;font-size:.76rem;font-weight:700}.step.done{background:#e7f7ed;color:#168143}.step.bad{background:#fff0f0;color:#c53c3c}.step.current{background:#eaf2ff;color:#1769e8}
.statusbox{border-radius:12px;padding:11px 13px;font-size:.82rem;margin:8px 0}.warn{background:#fff8e7;border:1px solid #f3dfac}.ok{background:#eaf9f0;border:1px solid #ccefd9;color:#176b39}.badbox{background:#fff0f0;border:1px solid #f2cccc;color:#a93131}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:8px}.flowitem{text-align:center;background:#f7f9fc;border:1px solid var(--sis-border);border-radius:11px;padding:10px 7px;font-size:.72rem}.flowitem b{display:block;font-size:.82rem;margin-bottom:2px}
.smallnote{font-size:.72rem;color:var(--sis-muted)}
[data-testid="stMetric"]{background:white;border:1px solid var(--sis-border);border-radius:12px;padding:10px 12px}
.stButton>button[kind="primary"]{border-radius:10px;font-weight:800;min-height:46px;background:#1769e8;border-color:#1769e8}
.stTextArea textarea,.stTextInput input{border-radius:10px;background:#fbfcfe}
</style>
""", unsafe_allow_html=True)


def _canonical_map(df):
    out={}
    for _,row in df.iterrows():
        d=row.to_dict(); symbol=str(d.get("symbol","")).strip().upper()
        if symbol: out[symbol]=d
    return out

def _run_stage3(canonical,packages,analysis_as_of):
    p10=run_pipeline(stage2_records=packages,analysis_as_of=analysis_as_of,canonical_by_symbol=_canonical_map(canonical))
    if p10.state=="BLOCKED": return {"status":"BLOCKED","diagnostics":list(p10.diagnostics)}
    return run_stage3_universe(list(p10.payloads),analysis_date=analysis_as_of,top_n=3)

def _friendly(issue):
    s=str(issue)
    if "MISSING_SYMBOL_COLUMN" in s:return "Kolom Symbol/kode saham belum terbaca."
    if "DUPLICATE_SYMBOL" in s:return "Ada kode saham yang tercatat lebih dari satu kali."
    if "MISSING_COLUMNS:" in s:return "Ada kolom wajib yang belum ditemukan pada data."
    if "UNIVERSE_MISMATCH" in s:return "Daftar saham antar B tidak sama. Pastikan B1–B11 berasal dari screening yang sama."
    if "UNIVERSE_INCOMPLETE" in s:return "Jumlah saham yang terbaca tidak sesuai dengan universe B1."
    if "AMBIGUOUS_NUMERIC_FORMAT" in s or "INVALID_NUMERIC" in s:return "Ada angka yang tidak dapat dibaca dengan aman."
    if "CONTROL_SANITY" in s:return "Ada nilai kontrol yang berada di luar batas yang masuk akal."
    return "Data belum lolos pemeriksaan keamanan SIS."

def _clear_analysis_state():
    for key in ("v2_stage1","v2_packages","v2_stage3","v2_snapshot_id","v2_blocked"):
        st.session_state.pop(key,None)

def _market_label():
    now=datetime.now()
    wd=now.weekday(); hm=now.hour*60+now.minute
    opened=wd<5 and (9*60)<=hm<=(16*60)
    return ("Market Buka","Sebaiknya input setelah market tutup") if opened else ("Market Tutup","Waktu terbaik untuk input data")

with st.sidebar:
    st.markdown('<div class="sis-brand"><div class="sis-logo">📈 <span>SIS</span></div><div class="sis-sub">Stock Intelligence System</div><div class="sis-tag">Analisis Cerdas, Keputusan Lebih Baik</div></div>',unsafe_allow_html=True)
    st.markdown('<div class="navitem navfuture">⌂ &nbsp; Beranda <small>(D0)</small></div>',unsafe_allow_html=True)
    st.markdown('<div class="navitem navactive">▣ &nbsp; Input Data</div>',unsafe_allow_html=True)
    st.markdown('<div class="navitem navoff">▥ &nbsp; Hasil Analisis <small>(D2)</small></div>',unsafe_allow_html=True)
    st.markdown('<div class="navitem navoff">⌁ &nbsp; Monitoring <small>(D4)</small></div>',unsafe_allow_html=True)
    st.markdown('<div class="navitem navoff">◷ &nbsp; Riwayat</div>',unsafe_allow_html=True)
    st.markdown('<div class="navitem navoff">▤ &nbsp; Panduan</div>',unsafe_allow_html=True)
    st.markdown('<br><br><div class="smallnote" style="color:#aebed1">“Data hari ini, keputusan lebih baik untuk esok.”<br><br>SIS v2.0 · D1 Candidate</div>',unsafe_allow_html=True)

market,market_sub=_market_label()
now=datetime.now()
st.markdown(f'''<div class="sis-top"><div><span class="phase">Fase D1</span><span class="top-title">Input Data & Snapshot</span><div class="top-sub" style="margin-left:100px">Masukkan hasil screening Stockbit untuk memulai analisis SIS</div></div><div style="display:flex;gap:16px;align-items:center"><div style="font-size:.8rem"><b>{now.strftime('%d %B %Y')}</b><br><span style="color:#637188">{now.strftime('%H:%M')} WIB</span></div><div class="market">◐ {market}<small>{market_sub}</small></div></div></div>''',unsafe_allow_html=True)

left,right=st.columns([1.75,1],gap="large")
with right:
    st.markdown('''<div class="tip"><h4>💡 Tips Input Data</h4><div class="tiprow"><span class="tipnum">1</span><span><b>Lakukan input setelah market tutup</b><br>Analisis siap sebelum sesi berikutnya.</span></div><div class="tiprow"><span class="tipnum">2</span><span><b>Gunakan hasil screening terbaru</b><br>Gunakan B1–B11 dari sesi yang sama.</span></div><div class="tiprow"><span class="tipnum">3</span><span><b>Tidak perlu format khusus</b><br>SIS membaca hasil copy tabel Stockbit.</span></div><div class="tiprow"><span class="tipnum">4</span><span><b>Data harus lengkap</b><br>Snapshot resmi hanya dibuat setelah seluruh guard PASS.</span></div></div><div class="safe"><b>✓ Aman & Tervalidasi</b><br>Input invalid tidak dapat menimpa snapshot valid sebelumnya.</div>''',unsafe_allow_html=True)
    st.markdown('<div class="card"><div class="card-title">◷ Riwayat Input Terakhir</div><div class="card-sub">Snapshot yang sudah tervalidasi</div>',unsafe_allow_html=True)
    history=list_snapshots(validated_only=True)
    if not history: st.caption("Belum ada snapshot tervalidasi.")
    else:
        for x in history[:4]:
            created=x.get("created_at","")[:16].replace("T"," ")
            st.markdown(f"**{created}** &nbsp; · &nbsp; VALIDATED")
        labels={f'{x["created_at"][:19].replace("T"," ")} · {x["snapshot_id"][-12:]}':x["snapshot_id"] for x in history}
        selected_history=st.selectbox("Pilih snapshot",list(labels),label_visibility="collapsed")
        if st.button("Muat snapshot",use_container_width=True):
            snap=load_snapshot(labels[selected_history])
            for bi in range(1,12): st.session_state[f"v2_b{bi}"]=get_snapshot_batch(snap,bi)
            md=snap.get("metadata") or {}
            if md.get("filter_fingerprint"): st.session_state["loaded_filter_fp"]=str(md["filter_fingerprint"])
            _clear_analysis_state(); st.rerun()
    st.markdown('</div>',unsafe_allow_html=True)

with left:
    st.markdown('<div class="card-title">🗄️ Input Data Screening</div><div class="card-sub">Masukkan hasil screening B1–B11 dari Stockbit. Setiap bagian diperiksa sebelum dapat diproses.</div>',unsafe_allow_html=True)
    filter_fp=st.text_input("Label sesi screening",value=st.session_state.get("loaded_filter_fp","S0-6FILTER"),help="Identitas/konteks screening; menjadi bagian identitas snapshot.")
    raw_inputs={}; parsed={}; issues_by_batch={}
    st.markdown('<div class="section-title">Data Screening B1–B11</div>',unsafe_allow_html=True)
    tabs=st.tabs([f"B{i}" for i in range(1,12)])
    for i,tab in enumerate(tabs,1):
        with tab:
            text=st.text_area(f"Data B{i}",height=190,key=f"v2_b{i}",placeholder=f"Tempel data B{i} dari Stockbit di sini…")
            raw_inputs[i]=text
            if not text.strip(): st.caption("Belum diisi")
            else:
                df,parse_issues=parse_clipboard_text(text); schema_issues=validate_batch(df,i) if not parse_issues else []
                all_issues=list(parse_issues)+list(schema_issues)
                if all_issues:
                    issues_by_batch[i]=all_issues; st.error("Data belum valid")
                    for item in dict.fromkeys(_friendly(x) for x in all_issues): st.caption(f"• {item}")
                else: parsed[i]=df; st.success(f"B{i} terbaca · {len(df)} saham")

    filled=sum(bool(raw_inputs.get(i,"").strip()) for i in range(1,12)); valid_batches=len(parsed); expected_total=len(parsed[1]) if 1 in parsed else 0
    steps=[]
    for i in range(1,12):
        cls="done" if i in parsed else ("bad" if i in issues_by_batch else "current" if i==filled+1 else "")
        steps.append(f'<span class="step {cls}">B{i} {"✓" if i in parsed else ""}</span>')
    st.markdown('<div class="stepbar">'+''.join(steps)+'</div>',unsafe_allow_html=True)
    c1,c2,c3=st.columns(3); c1.metric("Data terisi",f"{filled}/11"); c2.metric("Lolos pemeriksaan",f"{valid_batches}/11"); c3.metric("Universe saham",expected_total if expected_total else "—")
    if filled<11: st.markdown('<div class="statusbox warn">Lengkapi seluruh B1–B11. Data belum lengkap tidak dapat menjadi snapshot resmi.</div>',unsafe_allow_html=True)
    elif issues_by_batch: st.markdown('<div class="statusbox badbox">Ada data yang belum valid. Perbaiki bagian bertanda merah.</div>',unsafe_allow_html=True)
    else: st.markdown('<div class="statusbox ok">✓ B1–B11 lolos pemeriksaan awal. Siap menjalankan validasi silang dan analisis SIS.</div>',unsafe_allow_html=True)
    run_clicked=st.button("▶  VALIDASI & PROSES DATA  →",type="primary",use_container_width=True,disabled=not(filled==11 and valid_batches==11))
    st.markdown('<div class="smallnote" style="text-align:center">🔒 Data hanya menjadi snapshot resmi setelah seluruh validasi dan analisis PASS.</div>',unsafe_allow_html=True)

if run_clicked:
    _clear_analysis_state()
    with st.status("Memeriksa data dan menjalankan SIS…",expanded=True) as status:
        st.write("1/4 · Validasi silang B1–B11"); s1=run_stage1(parsed,expected_total=int(expected_total),filter_fingerprint=filter_fp)
        if s1.get("status")!="PASS": st.session_state["v2_blocked"]=[_friendly(x) for x in s1.get("issues",[])]; status.update(label="Dihentikan — data belum valid",state="error")
        else:
            st.write("2/4 · Analisis Stage 2"); s2=run_stage2(s1["canonical"])
            if s2.status!="PASS": st.session_state["v2_blocked"]=["Analisis Stage 2 belum selesai dengan aman. Snapshot tidak dibuat."]; status.update(label="Dihentikan — analisis belum lengkap",state="error")
            else:
                st.write("3/4 · Analisis dan ranking Stage 3"); s3=_run_stage3(s1["canonical"],s2.packages,date.today().isoformat())
                if s3.get("status")!="COMPLETE": st.session_state["v2_blocked"]=["Analisis Stage 3 belum COMPLETE. Snapshot tidak dibuat."]; status.update(label="Dihentikan — analisis belum lengkap",state="error")
                else:
                    st.write("4/4 · Membentuk snapshot tervalidasi")
                    snap=save_validated_snapshot(raw_inputs,canonical=s1["canonical"],validation_status=s1["status"],metadata={"expected_total":int(expected_total),"filter_fingerprint":filter_fp,"analysis_status":"COMPLETE","analysis_as_of":date.today().isoformat()})
                    st.session_state["v2_stage1"]=s1; st.session_state["v2_packages"]=s2.packages; st.session_state["v2_stage3"]=s3; st.session_state["v2_snapshot_id"]=snap["snapshot_id"]
                    status.update(label="Data valid · analisis selesai · snapshot resmi siap",state="complete",expanded=False)

if st.session_state.get("v2_blocked"):
    st.error("Proses dihentikan. Snapshot resmi tidak dibuat.")
    for msg in dict.fromkeys(st.session_state["v2_blocked"]): st.write(f"• {msg}")
if st.session_state.get("v2_snapshot_id"):
    st.success("Snapshot tervalidasi berhasil disiapkan.")
    a,b,c=st.columns(3); a.metric("Status","VALIDATED"); b.metric("Saham",expected_total); c.metric("ID Snapshot",st.session_state["v2_snapshot_id"][-12:])

st.markdown('''<div class="card" style="margin-top:18px"><div class="section-title">⚑ Alur Proses (Background)</div><div class="flow"><div class="flowitem"><b>1 · Parsing</b>Membaca B1–B11</div><div class="flowitem"><b>2 · Validasi</b>Guard data</div><div class="flowitem"><b>3 · Snapshot</b>Hanya jika valid</div><div class="flowitem"><b>4 · Analisis SIS</b>Stage 1 → 2 → 3</div><div class="flowitem"><b>5 · Hasil Siap</b>Workspace D2</div></div></div>''',unsafe_allow_html=True)
