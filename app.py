import streamlit as st, pandas as pd
from sis_core import parse,norm,merge,eng
st.set_page_config(page_title="SIS MVP",layout="wide");st.title("SIS — Stock Intelligence System");st.caption("MVP RC1 • paste 3 tabel Stockbit langsung")
if "x" not in st.session_state:st.session_state.x=pd.DataFrame();st.session_state.conf=[]
p=st.sidebar.radio("Menu",["Import","Validation","Candidates","Stock Intelligence"])
if p=="Import":
 t=st.tabs(["Batch 1 Technical/RS","Batch 2 Fundamental","Batch 3 Cash Flow"]);v=[]
 for i,a in enumerate(t):
  with a:v.append(st.text_area("Paste tabel Stockbit",height=280,key=str(i)))
 if st.button("PROCESS SIS",type="primary",use_container_width=True):
  ds=[norm(parse(q)) for q in v]
  if any(d.empty for d in ds):st.error("Ada batch yang belum terbaca.")
  else:
   raw,cf=merge(ds);st.session_state.raw=raw;st.session_state.x=eng(raw);st.session_state.conf=cf;st.success(f"{len(raw)} saham berhasil diproses.")
elif p=="Validation":
 if st.session_state.x.empty:st.warning("Import dahulu.")
 else:
  a,b,c=st.columns(3);a.metric("Symbols",len(st.session_state.x));b.metric("NULL",int(st.session_state.raw.isna().sum().sum()));c.metric("Conflicts",len(st.session_state.conf))
  if st.session_state.conf:st.dataframe(pd.DataFrame(st.session_state.conf),use_container_width=True)
  else:st.success("Tidak ada konflik antar-batch.")
elif p=="Candidates":
 x=st.session_state.x
 if x.empty:st.warning("Belum ada hasil.")
 else:st.dataframe(x,use_container_width=True,height=600)
else:
 x=st.session_state.x
 if x.empty:st.warning("Belum ada hasil.")
 else:
  s=st.selectbox("Symbol",sorted(x.Symbol.unique()));r=x[x.Symbol==s].iloc[0];st.header(s)
  a,b,c=st.columns(3);a.metric("Price",r.get("Price","N/A"));b.metric("RVOL",round(r.RVOL,2) if pd.notna(r.RVOL) else "N/A");c.metric("RS",r["RS Trajectory"])
  st.subheader("WHY")
  if pd.notna(r.RVOL) and r.RVOL>1:st.write("• Volume > Volume MA20.")
  if r["RS Trajectory"]=="ACCELERATING":st.write("• RS9 → RS6 → RS3 accelerating.")
  if pd.notna(r["RSI Delta"]) and r["RSI Delta"]>0:st.write("• RSI membaik.")
  if st.session_state.conf and any(q["Symbol"]==s for q in st.session_state.conf):st.error("DATA CONFLICT — keputusan eksekusi diblokir.")
  st.caption("RC1 tidak membuat entry/target/stop dan belum menghubungkan AI/broker.")
