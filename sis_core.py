import pandas as pd, numpy as np, re
def num(x):
 s=str(x).strip()
 if s in ("","-","—","N/A","NA"): return np.nan
 neg=s.startswith("(") and s.endswith(")")
 if neg:s=s[1:-1]
 s=s.replace("Rp","").replace(",","").strip(); mult=1
 m=re.search(r"\s*([MBT])$",s,re.I)
 if m:mult={"M":1e6,"B":1e9,"T":1e12}[m.group(1).upper()];s=s[:m.start()].strip()
 if s.endswith("%"):s=s[:-1]
 try:v=float(s)*mult
 except:return np.nan
 return -v if neg else v
def parse(text):
 lines=[x.strip() for x in text.splitlines() if x.strip().startswith("|")]
 rows=[]
 for ln in lines:
  cells=[c.strip() for c in ln.strip("|").split("|")]
  if all(re.fullmatch(r"[-: ]+",c or "-") for c in cells):continue
  rows.append(cells)
 if len(rows)<2:return pd.DataFrame()
 w=len(rows[0]);return pd.DataFrame([r[:w]+[""]*max(0,w-len(r)) for r in rows[1:]],columns=rows[0])
def norm(d):
 d=d.copy();d.columns=[re.sub(r"\\*","",str(c)).strip().replace("ADTV 30svg","ADTV 30") for c in d]
 if "Symbol" not in d and len(d.columns):d=d.rename(columns={d.columns[0]:"Symbol"})
 d=d.drop(columns=["svg"],errors="ignore")
 if "Symbol" in d:
  d["Symbol"]=d["Symbol"].astype(str).str.extract(r"(?:\\*\\*|symbol/)([A-Za-z0-9]+)",expand=False).fillna(d["Symbol"]).str.replace(r"[^A-Za-z0-9]","",regex=True).str.upper()
 for c in d:
  if c!="Symbol":d[c]=d[c].map(num)
 return d
def merge(ds):
 ds=[d for d in ds if not d.empty and "Symbol" in d]
 if not ds:return pd.DataFrame(),[]
 x=ds[0];conf=[]
 for i,d in enumerate(ds[1:],2):
  for c in [q for q in d if q!="Symbol" and q in x]:
   q=x[["Symbol",c]].merge(d[["Symbol",c]],on="Symbol",suffixes=("_a","_b"))
   q=q[q[c+"_a"].notna()&q[c+"_b"].notna()&(~np.isclose(q[c+"_a"],q[c+"_b"],rtol=.001,atol=.001))]
   conf += [{"Symbol":r.Symbol,"Field":c,"Batch":i} for _,r in q.iterrows()]
  d=d.drop(columns=[q for q in d if q!="Symbol" and q in x],errors="ignore");x=x.merge(d,on="Symbol",how="outer")
 return x,conf
def eng(x):
 x=x.copy()
 def c(n):return x[n] if n in x else pd.Series(np.nan,index=x.index)
 x["RVOL"]=c("Volume")/c("Volume MA 20");x["RSI Delta"]=c("RSI (14)")-c("Previous RSI (14)");x["MACD Delta"]=c("MACD (12,26)")-c("Previous MACD (12,26)")
 def rs(r):
  a,b,z=r.get("Rank (RS 9m)"),r.get("Rank (RS 6m)"),r.get("Rank (RS 3m)")
  if pd.isna(a) or pd.isna(b) or pd.isna(z):return "INSUFFICIENT"
  if z>b>a:return "ACCELERATING"
  if z>=80 and b>=80:return "PERSISTENT LEADER"
  if z<b<a:return "DETERIORATING"
  return "MIXED"
 x["RS Trajectory"]=x.apply(rs,axis=1);return x
