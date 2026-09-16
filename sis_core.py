import pandas as pd, numpy as np, re

NULLS={"","-","—","N/A","NA","NULL","NONE"}

def num(x):
 s=str(x).strip()
 if s.upper() in NULLS:return np.nan
 neg=s.startswith("(") and s.endswith(")")
 if neg:s=s[1:-1].strip()
 s=s.replace("Rp","").replace(",","").strip();mult=1
 m=re.search(r"\s*([MBT])$",s,re.I)
 if m:mult={"M":1e6,"B":1e9,"T":1e12}[m.group(1).upper()];s=s[:m.start()].strip()
 if s.endswith("%"):s=s[:-1].strip()
 try:v=float(s)*mult
 except (ValueError,TypeError):return np.nan
 return -v if neg else v

def _clean_header(c):
 c=re.sub(r"\*","",str(c)).strip()
 c=re.sub(r"\s+"," ",c)
 c=c.replace("ADTV 30svg","ADTV 30").replace("Volumesvg","Volume")
 return c

def _ticker(s):
 s=str(s).strip()
 m=re.search(r"stockbit\.com/symbol/([A-Za-z0-9]+)",s,re.I)
 if m:return m.group(1).upper()
 s=re.sub(r"[\[\]*()`_]","",s).strip()
 return s.upper() if re.fullmatch(r"[A-Z]{4,5}",s) else None

def _markdown(text):
 lines=[x.strip() for x in text.splitlines() if x.strip().startswith("|")]
 rows=[]
 for ln in lines:
  cells=[c.strip() for c in ln.strip("|").split("|")]
  if all(re.fullmatch(r"[-: ]+",c or "-") for c in cells):continue
  rows.append(cells)
 if len(rows)<2:return pd.DataFrame()
 w=len(rows[0]);return pd.DataFrame([r[:w]+[""]*max(0,w-len(r)) for r in rows[1:]],columns=rows[0])

def _clipboard(text):
 # Stockbit clipboard: headers are one-per-line; after first ticker, values may be
 # one-per-line (Batch 1) or tab-separated (Batch 2/3).
 raw=[x.strip() for x in text.replace("\r","").split("\n") if x.strip()]
 if not raw:return pd.DataFrame()
 first=None
 for i,s in enumerate(raw):
  if _ticker(s):first=i;break
 if first is None:return pd.DataFrame()
 headers=[]
 for h in raw[:first]:
  h=_clean_header(h)
  if h.lower()=="svg":continue
  headers.append(h)
 if not headers:return pd.DataFrame()
 if headers[0].lower()!="symbol":headers.insert(0,"Symbol")
 width=len(headers)-1
 tokens=[]
 for s in raw[first:]:
  # Tabs carry cells in laptop clipboard. Preserve parenthesized negatives.
  parts=[p.strip() for p in s.split("\t") if p.strip()]
  tokens.extend(parts if parts else [s])
 rows=[];i=0
 while i<len(tokens):
  sym=_ticker(tokens[i])
  if not sym:i+=1;continue
  vals=[];i+=1
  while i<len(tokens) and len(vals)<width and not _ticker(tokens[i]):
   vals.append(tokens[i]);i+=1
  if len(vals)<width:
   # incomplete final/garbled row: retain it padded so validation can report it
   vals += [""]*(width-len(vals))
  rows.append([sym]+vals[:width])
 return pd.DataFrame(rows,columns=headers)

def parse(text):
 if not str(text).strip():return pd.DataFrame()
 d=_markdown(text)
 if not d.empty:return d
 return _clipboard(text)

def norm(d):
 d=d.copy();d.columns=[_clean_header(c) for c in d]
 d=d.loc[:,~d.columns.duplicated()]
 if "Symbol" not in d and len(d.columns):d=d.rename(columns={d.columns[0]:"Symbol"})
 d=d.drop(columns=["svg"],errors="ignore")
 if "Symbol" in d:
  d["Symbol"]=d["Symbol"].map(lambda z:_ticker(z) or re.sub(r"[^A-Za-z0-9]","",str(z)).upper())
  d=d[d["Symbol"].astype(bool)].reset_index(drop=True)
 for c in d:
  if c!="Symbol":d[c]=d[c].map(num)
 return d

def duplicate_symbols(d):
 if d.empty or "Symbol" not in d:return []
 s=d["Symbol"].dropna().astype(str)
 return sorted(s[s.duplicated(keep=False)].unique().tolist())

def dedupe_for_merge(d):
 # Duplicates are a validation error. Keep one row only for safe diagnostics/preview;
 # execution must remain blocked by the caller until duplicates are corrected.
 if d.empty or "Symbol" not in d:return d.copy()
 return d.drop_duplicates("Symbol",keep="first").reset_index(drop=True)

def batch_coverage(ds):
 sets=[set(d.Symbol) if (not d.empty and "Symbol" in d) else set() for d in ds]
 union=set().union(*sets) if sets else set()
 rows=[]
 for s in sorted(union):
  present=[i+1 for i,z in enumerate(sets) if s in z]
  rows.append({"Symbol":s,"Batches Present":",".join(map(str,present)),"Batch Coverage":len(present),"Data Confidence":"COMPLETE" if len(present)==len(ds) else "PARTIAL"})
 return pd.DataFrame(rows)

def merge(ds):
 ds=[dedupe_for_merge(d) for d in ds if not d.empty and "Symbol" in d]
 if not ds:return pd.DataFrame(),[]
 x=ds[0].copy();conf=[]
 for i,d in enumerate(ds[1:],2):
  for c in [q for q in d if q!="Symbol" and q in x]:
   q=x[["Symbol",c]].merge(d[["Symbol",c]],on="Symbol",suffixes=("_a","_b"))
   q=q[q[c+"_a"].notna()&q[c+"_b"].notna()&(~np.isclose(q[c+"_a"],q[c+"_b"],rtol=.001,atol=.001))]
   conf += [{"Symbol":r.Symbol,"Field":c,"Batch":i,"Value A":r[c+"_a"],"Value B":r[c+"_b"],"Severity":"BLOCKED" if c=="Price" else "CONFLICT"} for _,r in q.iterrows()]
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
