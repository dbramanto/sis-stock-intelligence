import streamlit as st, pandas as pd
from sis_core import parse,norm,merge,eng,duplicate_symbols,dedupe_for_merge,batch_coverage,align_to_expected,conflict_details,systematic_conflict_diagnosis,missing_value_details,align_batches_with_evidence
from stage2_adapter import run_stage2
from snapshot_history import SnapshotStore, SnapshotError
from pathlib import Path

st.set_page_config(page_title="SIS MVP",layout="wide")
st.title("SIS — Stock Intelligence System")
st.caption("RC1.1.1 + STAGE 2 LOGIC FREEZE • data integrity • horizon screening • risk families")

if "x" not in st.session_state:
 st.session_state.x=pd.DataFrame();st.session_state.raw=pd.DataFrame();st.session_state.conf=[];st.session_state.conf_detail=pd.DataFrame();st.session_state.null_detail=pd.DataFrame();st.session_state.schema_diag=[];st.session_state.coverage=pd.DataFrame();st.session_state.blocked=False;st.session_state.gate_state="PASS";st.session_state.stage2=None;st.session_state.active_snapshot=None

SNAPSHOT_ROOT=Path(".sis_history")
snapshot_store=SnapshotStore(SNAPSHOT_ROOT)

def display_table(df,height=None,numbered=False):
 d=df.copy()
 if numbered and not d.empty:
  d.insert(0,"No.",range(1,len(d)+1))
 kwargs={"use_container_width":True,"hide_index":True}
 if height is not None: kwargs["height"]=height
 st.dataframe(d,**kwargs)

from app_schema import EXPECTED

def reset_processing_state():
 # Clear every derived object before each PROCESS run so failed/reduced input
 # can never reuse candidates or Stage 2 results from a previous run.
 st.session_state.x=pd.DataFrame()
 st.session_state.raw=pd.DataFrame()
 st.session_state.conf=[]
 st.session_state.conf_detail=pd.DataFrame()
 st.session_state.null_detail=pd.DataFrame()
 st.session_state.schema_diag=[]
 st.session_state.coverage=pd.DataFrame()
 st.session_state.blocked=True
 st.session_state.gate_state="BLOCKED"
 st.session_state.stage2=None

p=st.sidebar.radio("Menu",["Import","History","Validation","Candidates","Stage 2","Stock Intelligence"])

if p=="Import":
 st.subheader("01 · IMPORT DATA")
 st.caption("Snapshot disimpan per trading day. Jam input hanya metadata audit.")
 trading_date=st.date_input("Trading Date",help="Tanggal perdagangan yang direpresentasikan oleh B1–B3, bukan waktu Anda melakukan input.")
 tabs=st.tabs(["Batch 1 Technical/RS","Batch 2 Fundamental","Batch 3 Cash Flow"]);v=[]
 for i,a in enumerate(tabs):
  with a:v.append(st.text_area("Paste tabel Stockbit",height=280,key=str(i)))
 if st.button("PROCESS SIS",type="primary",use_container_width=True):
  reset_processing_state()
  parsed=[parse(q) for q in v]
  aligned,schema_diag,alignment_gate=align_batches_with_evidence(parsed,EXPECTED)
  st.session_state.schema_diag=schema_diag
  ds=[norm(d) for d in aligned];st.session_state.null_detail=missing_value_details(aligned,ds);fatal=bool(alignment_gate.get("blocked"))
  if alignment_gate.get("blocked"):
   st.error("SCHEMA ALIGNMENT: BLOCKED — " + alignment_gate.get("message","periksa format kolom."))
  for i,d in enumerate(ds):
   missing=[c for c in EXPECTED[i] if c not in d.columns]
   dup=duplicate_symbols(d)
   if d.empty or missing:
    fatal=True;st.error(f"Batch {i+1}: FAIL — {len(d)} rows — missing: {', '.join(missing) if missing else 'data tidak terbaca'}")
   else:
    st.success(f"Batch {i+1}: PASS — {d.Symbol.nunique()} unique symbols — {len(EXPECTED[i])-1} metrics")
    diag=schema_diag[i] if i < len(schema_diag) else {}
    if diag.get("realigned"):
     st.info(f"Batch {i+1}: format kolom berhasil dinormalisasi ke SIS schema.")
   if dup:
    fatal=True;st.error(f"Batch {i+1}: DUPLICATE SYMBOL — {', '.join(dup)} — processing BLOCKED sampai data diperbaiki.")
  if fatal:
   st.error("DATA INTEGRITY GATE: BLOCKED — lengkapi/perbaiki Batch 1–3 sebelum Stage 2.")
  if not fatal and not any(d.empty for d in ds):
   safe=[dedupe_for_merge(d) for d in ds];cov=batch_coverage(safe);st.session_state.coverage=cov
   complete=int((cov["Data Confidence"]=="COMPLETE").sum());partial=len(cov)-complete
   if partial==0:st.success(f"Cross-Batch Integrity: PASS — {complete}/{len(cov)} symbols COMPLETE")
   else:st.warning(f"Cross-Batch Integrity: REVIEW — {complete} COMPLETE / {partial} PARTIAL — partial candidates tetap disimpan.")
   raw,cf=merge(safe);st.session_state.raw=raw;st.session_state.conf=cf
   detail=conflict_details(safe);st.session_state.conf_detail=detail
   diagnosis=systematic_conflict_diagnosis(detail,len(cov))
   x=eng(raw).merge(cov[["Symbol","Batch Coverage","Data Confidence"]],on="Symbol",how="left")
   price_conf=any(q.get("Field")=="Price" for q in cf)
   st.session_state.blocked=fatal or price_conf
   nonprice_conflict=(not detail.empty) and not price_conf
   st.session_state.gate_state="BLOCKED" if st.session_state.blocked else ("REVIEW" if (partial or nonprice_conflict) else "PASS")
   x["Execution State"]="AVAILABLE"
   if st.session_state.blocked:x["Execution State"]="BLOCKED"
   else:x.loc[x["Data Confidence"]!="COMPLETE","Execution State"]="DATA REVIEW"
   for q in cf:
    if q.get("Field")=="Price":x.loc[x.Symbol==q["Symbol"],"Execution State"]="BLOCKED"
   st.session_state.x=x
   st.session_state.stage2=run_stage2(safe) if not fatal and not price_conf else None
   if st.session_state.stage2 is not None and st.session_state.gate_state=="REVIEW":
    st.session_state.stage2["integrity"]["state"]="REVIEW"
   if not detail.empty:
    price_rows=detail[detail["Field"]=="Price"]
    affected=detail["Symbol"].nunique()
    if price_conf:
     st.error(f"DATA INTEGRITY: BLOCKED — {len(detail)} conflict detail(s), {len(price_rows)} Price conflict(s), {affected} saham terdampak.")
    else:
     st.warning(f"DATA INTEGRITY: REVIEW — {len(detail)} conflict detail(s), {affected} saham terdampak.")
    st.warning(diagnosis["message"])
    st.markdown("**Conflict Details — nilai aktual per batch**")
    display_table(detail,numbered=True)
   validation_snapshot={"gate_state":st.session_state.gate_state,"symbols":len(x),"conflicts":len(detail),"partial_symbols":partial,"schema_realigned_batches":[d.get("batch") for d in schema_diag if d.get("realigned")]}
   try:
    snap=snapshot_store.save_daily_snapshot(trading_date=trading_date,raw_batches=v,normalized_batches=safe,merged_stage1=x,validation=validation_snapshot,source="MANUAL_STOCKBIT")
    st.session_state.active_snapshot={"snapshot_id":snap.snapshot_id,"trading_date":snap.trading_date,"revision":snap.revision,"gate_state":snap.gate_state}
    st.info(f"Snapshot aktif: {snap.snapshot_id} • Trading Day {snap.trading_date}")
   except SnapshotError as exc:
    st.warning(f"Snapshot tidak disimpan: {exc}")
   st.success(f"{len(raw)} saham berhasil diproses tanpa membuang partial candidate.")

elif p=="History":
 st.subheader("02 · DAILY HISTORY")
 st.caption("Satu baris mewakili satu trading day. Revisi pada hari yang sama tidak membuat baris harian baru.")
 st.warning("History pada Streamlit bersifat sementara. Unduh backup secara berkala agar salinan tetap tersimpan di perangkat lokal.")
 rows=snapshot_store.list_daily()
 if rows:
  newest=rows[0].get("trading_date","history")
  backup=snapshot_store.export_backup()
  st.download_button("DOWNLOAD ALL HISTORY (.ZIP)",data=backup,file_name=f"SIS_HISTORY_BACKUP_{newest}.zip",mime="application/zip",use_container_width=True)
 if not rows:
  st.info("Belum ada snapshot harian.")
 else:
  h=pd.DataFrame(rows)
  cols=[c for c in ["trading_date","snapshot_id","revision","gate_state","status","source","created_at"] if c in h.columns]
  display_table(h[cols],numbered=True)
  dates=[r.get("trading_date") for r in rows if r.get("trading_date")]
  chosen=st.selectbox("Lihat snapshot",dates,key="history_trading_date")
  try:
   payload=snapshot_store.load_effective(chosen)
   st.write({"snapshot_id":payload.get("snapshot_id"),"trading_date":payload.get("trading_date"),"revision":payload.get("revision"),"gate_state":payload.get("validation",{}).get("gate_state"),"source":payload.get("source"),"created_at":payload.get("created_at")})
  except SnapshotError as exc:
   st.error(str(exc))

elif p=="Validation":
 if st.session_state.x.empty:st.warning("Import dahulu.")
 else:
  a,b,c,d=st.columns(4);a.metric("Symbols",len(st.session_state.x));b.metric("NULL",len(st.session_state.null_detail));c.metric("Conflicts",len(st.session_state.conf_detail));d.metric("Gate",st.session_state.gate_state)
  if not st.session_state.coverage.empty:display_table(st.session_state.coverage,numbered=True)
  if not st.session_state.conf_detail.empty:
   st.markdown("**Conflict Details — nilai aktual per batch**")
   display_table(st.session_state.conf_detail,numbered=True)
  else:st.success("Tidak ada konflik nilai antar-batch.")
  if not st.session_state.null_detail.empty:
   st.markdown("**Missing Data Details — nilai sumber yang tidak tersedia**")
   st.caption("NULL bukan otomatis error. SIS tidak mengisi nilai yang memang tidak tersedia dari sumber; dampaknya dinilai pada confidence/Stage 2 sesuai metric terkait.")
   display_table(st.session_state.null_detail,numbered=True)
  realigned=[d for d in st.session_state.schema_diag if d.get("realigned")]
  if realigned:
   st.info("Format kolom dinormalisasi otomatis: " + ", ".join(f"Batch {d['batch']}" for d in realigned) + ".")

elif p=="Candidates":
 x=st.session_state.x
 if x.empty:st.warning("Belum ada hasil.")
 else:
  counts=x["Execution State"].value_counts().to_dict() if "Execution State" in x else {}
  st.subheader("Candidates — Hasil Integrity Gate")
  st.caption("Daftar ini adalah kandidat data yang diteruskan setelah validasi, bukan peringkat atau rekomendasi beli/jual.")
  a,b,c,d=st.columns(4)
  a.metric("Candidates",len(x));b.metric("AVAILABLE",counts.get("AVAILABLE",0));c.metric("DATA REVIEW",counts.get("DATA REVIEW",0));d.metric("BLOCKED",counts.get("BLOCKED",0))
  display_table(x,height=600,numbered=True)

elif p=="Stage 2":
 s2=st.session_state.stage2
 if not s2:
  st.warning("Stage 2 belum tersedia. Proses Batch 1–3 terlebih dahulu; jika BLOCKED, perbaiki datanya.")
 else:
  gate=s2["integrity"];results=s2["results"]
  st.subheader("Stage 2 — Penyaringan Lanjutan")
  a,b,c,d=st.columns(4);a.metric("Data",gate["state"])
  b.metric("ELIGIBLE",sum(r.get("eligibility")=="ELIGIBLE" for r in results))
  c.metric("CONDITIONAL",sum(r.get("eligibility")=="CONDITIONAL" for r in results))
  d.metric("REVIEW",sum(r.get("eligibility")=="REVIEW" for r in results))
  rows=[]
  for r in results:
   if r.get("stage2_state")!="EVALUATED":
    rows.append({"Symbol":r["symbol"],"Status":"DATA REVIEW","Swing":"—","Long-Term":"—","Catatan":"Data belum lengkap"});continue
   sw=r["horizons"]["swing"];lt=r["horizons"]["long_term"]
   fam=", ".join(f"{k}: {v}" for k,v in r.get("risk_families",{}).items()) or "Tidak ada risiko utama"
   rows.append({"Symbol":r["symbol"],"Status":r["eligibility"],"Swing":f"{sw['raw_score']:.2f} / {sw['effective_priority']}","Long-Term":f"{lt['raw_score']:.2f} / {lt['effective_priority']}","Catatan":fam})
  display_table(pd.DataFrame(rows),height=520,numbered=True)
  sym=st.selectbox("Lihat alasan saham",sorted(r["symbol"] for r in results),key="stage2_symbol")
  r=next(q for q in results if q["symbol"]==sym)
  if r.get("stage2_state")!="EVALUATED":st.warning("Data saham ini belum lengkap, sehingga Stage 2 tidak memberi penilaian.")
  else:
   st.markdown(f"### {sym} — {r['eligibility']}")
   a,b,c,d=st.columns(4);a.metric("Technical",r["blocks"]["technical"]);b.metric("Participation",r["blocks"]["participation"]);c.metric("Fundamental",r["blocks"]["fundamental"]);d.metric("Cash Quality",r["blocks"]["cash_quality"])
   st.write("**Hal yang perlu diperhatikan:**")
   if not r["red_flags"]:st.success("Tidak ada red flag dari Batch 1–3.")
   else:
    for f in r["red_flags"]:st.write(f"• {f['severity']} — {f['evidence']}")
   st.caption("Stage 2 adalah penyaringan prioritas analisis, bukan rekomendasi beli/jual. Intraday belum dinilai.")

else:
 x=st.session_state.x
 if x.empty:st.warning("Belum ada hasil.")
 else:
  s=st.selectbox("Symbol",sorted(x.Symbol.unique()));r=x[x.Symbol==s].iloc[0];st.header(s)
  a,b,c,d=st.columns(4);a.metric("Price",r.get("Price","N/A"));b.metric("RVOL",round(r.RVOL,2) if pd.notna(r.RVOL) else "N/A");c.metric("RS",r["RS Trajectory"]);d.metric("Execution",r["Execution State"])
  if r["Data Confidence"]!="COMPLETE":st.warning("PARTIAL DATA — kandidat dipertahankan, tetapi confidence diturunkan dan perlu review.")
  st.subheader("WHY")
  if pd.notna(r.RVOL) and r.RVOL>1:st.write("• Volume > Volume MA20.")
  if r["RS Trajectory"]=="ACCELERATING":st.write("• RS9 → RS6 → RS3 accelerating.")
  if pd.notna(r["RSI Delta"]) and r["RSI Delta"]>0:st.write("• RSI membaik.")
  if st.session_state.conf and any(q["Symbol"]==s for q in st.session_state.conf):st.error("DATA CONFLICT — review wajib; Price conflict memblokir execution.")
