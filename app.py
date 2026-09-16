import streamlit as st, pandas as pd
from sis_core import parse,norm,merge,eng,duplicate_symbols,dedupe_for_merge,batch_coverage
st.set_page_config(page_title="SIS MVP",layout="wide")
st.title("SIS — Stock Intelligence System")
st.caption("MVP RC1.1.1 HARDENED • explicit duplicates • partial-universe confidence • conflict blocking")
if "x" not in st.session_state:
 st.session_state.x=pd.DataFrame();st.session_state.conf=[];st.session_state.coverage=pd.DataFrame();st.session_state.blocked=False
EXPECTED=[
 ["Symbol","Volume","Volume MA 20","Price MA 20","Price MA 50","RSI (14)","ADTV 30","Price","Price MA 200","Average Directional Index 14","Average Directional Index DI+ 14","Average Directional Index DI- 14","MACD (12,26)","Previous MACD (12,26)","Previous RSI (14)","Average True Range 14","Average Daily Range 14","Value","Rank (RS 3m)","Rank (RS 6m)","Rank (RS 9m)"],
 ["Symbol","Volume","Volume MA 20","Price MA 20","Price MA 50","RSI (14)","ADTV 30","Price","Net Profit Margin (TTM)(%)","Return On Invested Capital (TTM)","Piotroski F-Score","Earnings Yield (TTM)","Debt to Equity Ratio (Quarter)","EPS (TTM YoY Growth)"],
 ["Symbol","Volume","Volume MA 20","Price MA 20","Price MA 50","RSI (14)","ADTV 30","Price","Operating Cash Flow (Quarter)","Free cash flow (TTM)","Free cash flow (Quarter)","Net Income (Quarter)","Net Income (Annual)","Net Income (TTM)","Net Income (YTD)"]]
p=st.sidebar.radio("Menu",["Import","Validation","Candidates","Stock Intelligence"])
if p=="Import":
 tabs=st.tabs(["Batch 1 Technical/RS","Batch 2 Fundamental","Batch 3 Cash Flow"]);v=[]
 for i,a in enumerate(tabs):
  with a:v.append(st.text_area("Paste tabel Stockbit",height=280,key=str(i)))
 if st.button("PROCESS SIS",type="primary",use_container_width=True):
  parsed=[parse(q) for q in v];ds=[norm(d) for d in parsed];fatal=False;dups={}
  for i,d in enumerate(ds):
   missing=[c for c in EXPECTED[i] if c not in d.columns]
   dup=duplicate_symbols(d);dups[i+1]=dup
   if d.empty or missing:
    fatal=True;st.error(f"Batch {i+1}: FAIL — {len(d)} rows — missing: {', '.join(missing) if missing else 'data tidak terbaca'}")
   else:st.success(f"Batch {i+1}: PASS — {d.Symbol.nunique()} unique symbols — {len(EXPECTED[i])-1} metrics")
   if dup:
    fatal=True;st.error(f"Batch {i+1}: DUPLICATE SYMBOL — {', '.join(dup)} — processing/execution BLOCKED sampai data diperbaiki.")
  if not any(d.empty for d in ds):
   safe=[dedupe_for_merge(d) for d in ds];cov=batch_coverage(safe);st.session_state.coverage=cov
   complete=int((cov["Data Confidence"]=="COMPLETE").sum());partial=len(cov)-complete
   if partial==0:st.success(f"Cross-Batch Integrity: PASS — {complete}/{len(cov)} symbols COMPLETE")
   else:st.warning(f"Cross-Batch Integrity: REVIEW — {complete} COMPLETE / {partial} PARTIAL — partial candidates tetap disimpan.")
   raw,cf=merge(safe);st.session_state.raw=raw;st.session_state.conf=cf
   x=eng(raw).merge(cov[["Symbol","Batch Coverage","Data Confidence"]],on="Symbol",how="left")
   price_conf=any(q.get("Field")=="Price" for q in cf)
   st.session_state.blocked=fatal or price_conf
   x["Execution State"]="AVAILABLE"
   if st.session_state.blocked:x["Execution State"]="BLOCKED"
   else:x.loc[x["Data Confidence"]!="COMPLETE","Execution State"]="DATA REVIEW"
   for q in cf:
    if q.get("Field")=="Price":x.loc[x.Symbol==q["Symbol"],"Execution State"]="BLOCKED"
   st.session_state.x=x
   if cf:
    st.error(f"{len(cf)} cross-batch conflict(s) ditemukan. Price conflict = BLOCKED.")
   if fatal:st.error("DATA INTEGRITY GATE: BLOCKED — perbaiki duplicate/schema error sebelum execution.")
   else:st.success(f"{len(raw)} saham berhasil diproses tanpa membuang partial candidate.")
elif p=="Validation":
 if st.session_state.x.empty:st.warning("Import dahulu.")
 else:
  a,b,c,d=st.columns(4);a.metric("Symbols",len(st.session_state.x));b.metric("NULL",int(st.session_state.raw.isna().sum().sum()));c.metric("Conflicts",len(st.session_state.conf));d.metric("Gate","BLOCKED" if st.session_state.blocked else "PASS")
  if not st.session_state.coverage.empty:st.dataframe(st.session_state.coverage,use_container_width=True)
  if st.session_state.conf:st.dataframe(pd.DataFrame(st.session_state.conf),use_container_width=True)
  else:st.success("Tidak ada konflik nilai antar-batch.")
elif p=="Candidates":
 x=st.session_state.x
 if x.empty:st.warning("Belum ada hasil.")
 else:st.dataframe(x,use_container_width=True,height=600)
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
  st.caption("RC1.1.1 belum membuat entry/target/stop dan belum menghubungkan AI/broker.")
