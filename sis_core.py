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


def align_to_expected(d, expected, batch_no=None):
 """
 Align Stockbit clipboard values to the SIS canonical schema by position only when:
 - column count is exact,
 - header names are the same set as expected,
 - but DOM/header order differs.
 This addresses Stockbit clipboard header-order anomalies without guessing missing columns.
 Returns (aligned_df, diagnostic).
 """
 if d.empty or not expected:
  return d.copy(), {"state":"NO_DATA","batch":batch_no,"realigned":False}
 exp=[_clean_header(c) for c in expected]
 got=[_clean_header(c) for c in d.columns]
 if len(got)!=len(exp) or set(got)!=set(exp):
  return d.copy(), {"state":"SCHEMA_MISMATCH","batch":batch_no,"realigned":False,
                    "header_order":got,"expected_order":exp}
 if got==exp:
  return d.copy(), {"state":"ALIGNED","batch":batch_no,"realigned":False}
 x=d.copy()
 old=got[:]
 x.columns=exp
 return x, {"state":"REALIGNED","batch":batch_no,"realigned":True,
            "header_order":old,"expected_order":exp}

def conflict_details(ds, rtol=.001, atol=.001):
 """
 Compare common fields across all three batches and expose the actual value per batch.
 One row = one Symbol/Field, avoiding duplicated pairwise conflict messages.
 """
 if len(ds)!=3:return pd.DataFrame()
 clean=[dedupe_for_merge(d) for d in ds]
 common=set(clean[0].columns)
 for d in clean[1:]: common &= set(d.columns)
 common.discard("Symbol")
 syms=sorted(set().union(*(set(d["Symbol"]) for d in clean if "Symbol" in d)))
 rows=[]
 for sym in syms:
  for field in sorted(common):
   vals=[]
   for d in clean:
    q=d.loc[d["Symbol"]==sym,field]
    vals.append(np.nan if q.empty else q.iloc[0])
   known=[v for v in vals if pd.notna(v)]
   if len(known)<2:continue
   base=known[0]
   mismatch=any(not np.isclose(base,v,rtol=rtol,atol=atol) for v in known[1:])
   if not mismatch:continue
   b1,b2,b3=vals
   diag="MIXED"
   def eq(a,b):
    return pd.notna(a) and pd.notna(b) and np.isclose(a,b,rtol=rtol,atol=atol)
   if eq(b2,b3) and not eq(b1,b2):diag="BATCH 1 MISMATCH"
   elif eq(b1,b3) and not eq(b1,b2):diag="BATCH 2 MISMATCH"
   elif eq(b1,b2) and not eq(b1,b3):diag="BATCH 3 MISMATCH"
   rows.append({"Symbol":sym,"Field":field,"Batch 1":b1,"Batch 2":b2,"Batch 3":b3,
                "Diagnosis":diag,"Severity":"BLOCKED" if field=="Price" else "REVIEW"})
 return pd.DataFrame(rows)

def systematic_conflict_diagnosis(details, symbol_count):
 if details is None or details.empty:
  return {"state":"PASS","message":"Tidak ada konflik nilai antar-batch."}
 if symbol_count<=0:
  return {"state":"REVIEW","message":"Konflik ditemukan."}
 d=details
 common_fields=d["Field"].nunique()
 b1=(d["Diagnosis"]=="BATCH 1 MISMATCH").sum()
 total=len(d)
 # Strong systematic signature: almost all detailed conflicts point to the same batch.
 if total>=symbol_count*3 and b1/total>=.90:
  return {"state":"SCHEMA_ALIGNMENT_ERROR","suspected_batch":1,
          "message":f"Pola konflik sistematis terdeteksi: {b1}/{total} konflik menunjuk Batch 1. Periksa pemetaan/urutan kolom Batch 1."}
 return {"state":"VALUE_CONFLICT","message":f"{total} konflik nilai ditemukan. Periksa Conflict Details."}

def missing_value_details(raw_ds, norm_ds):
 """Expose source-level missing values with batch provenance for UI diagnostics."""
 rows=[]
 for i,(raw,normed) in enumerate(zip(raw_ds,norm_ds),1):
  if normed.empty or "Symbol" not in normed: continue
  raw_idx=raw.set_index("Symbol") if (not raw.empty and "Symbol" in raw) else pd.DataFrame()
  for _,r in normed.iterrows():
   sym=r["Symbol"]
   for field in [c for c in normed.columns if c!="Symbol"]:
    if pd.isna(r[field]):
     rv=""
     if not raw_idx.empty and sym in raw_idx.index and field in raw_idx.columns:
      q=raw_idx.loc[sym,field]
      if isinstance(q,pd.Series): q=q.iloc[0]
      rv=str(q).strip()
     rows.append({"Symbol":sym,"Field":field,"Source Batch":i,
                  "Source Value":rv or "(empty)","Status":"SOURCE MISSING",
                  "Reason":"Nilai sumber tidak tersedia; metric tidak diimputasi."})
 return pd.DataFrame(rows)

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

def align_batches_with_evidence(parsed_ds, expected_schemas, rtol=.001, atol=.001):
 """
 Evidence-based schema alignment across batches.
 Always returns one diagnostic slot per expected batch, including empty/malformed batches.
 Fail closed when any batch is unreadable or schema-invalid.
 """
 n=len(expected_schemas)
 diags=[]
 for i in range(n):
  d=parsed_ds[i] if i < len(parsed_ds) else pd.DataFrame()
  expected=expected_schemas[i]
  exp=[_clean_header(c) for c in expected]
  got=[_clean_header(c) for c in d.columns]
  state="PENDING"
  if d.empty: state="NO_DATA"
  elif len(got)!=len(exp) or set(got)!=set(exp): state="SCHEMA_MISMATCH"
  diags.append({"batch":i+1,"header_order":got,"expected_order":exp,"permuted":bool(got and got!=exp),"interpretation":None,"realigned":False,"state":state})

 if len(parsed_ds) != n:
  copies=[parsed_ds[i].copy() if i < len(parsed_ds) else pd.DataFrame() for i in range(n)]
  return copies,diags,{"blocked":True,"state":"SCHEMA_COUNT_MISMATCH","message":"Jumlah batch/schema tidak sesuai."}

 invalid=[d for d in diags if d["state"] in {"NO_DATA","SCHEMA_MISMATCH"}]
 if invalid:
  first=invalid[0]
  if first["state"]=="NO_DATA": msg=f"Batch {first['batch']} tidak terbaca."
  else: msg=f"Schema Batch {first['batch']} tidak cocok; normalisasi otomatis tidak dilakukan."
  return [d.copy() for d in parsed_ds],diags,{"blocked":True,"state":first["state"],"message":msg}

 options=[]
 for i,(d,expected) in enumerate(zip(parsed_ds,expected_schemas)):
  exp=diags[i]["expected_order"]; got=diags[i]["header_order"]
  semantic=d.copy(); semantic.columns=got
  if got==exp:
   options.append([("SEMANTIC",semantic)])
  else:
   positional=d.copy(); positional.columns=exp
   options.append([("SEMANTIC",semantic),("POSITIONAL",positional)])

 import itertools
 common_core={"Volume","Volume MA 20","Price MA 20","Price MA 50","RSI (14)","ADTV 30","Price"}
 def score(combo):
  nd=[norm(item[1]) for item in combo]
  details=conflict_details(nd,rtol=rtol,atol=atol)
  if details.empty:return 0
  return int(details[details["Field"].isin(common_core)].shape[0])
 combos=list(itertools.product(*options))
 scored=[(score(c),c) for c in combos]
 best_score=min(s for s,_ in scored)
 best=[c for s,c in scored if s==best_score]
 if len(best)>1:
  if any(d.get("permuted") for d in diags):
   return [d.copy() for d in parsed_ds],diags,{"blocked":True,"state":"AMBIGUOUS_SCHEMA_ALIGNMENT","message":"Urutan kolom ambigu; SIS tidak melakukan realignment otomatis tanpa bukti lintas-batch yang cukup.","best_conflicts":best_score}
  chosen=best[0]
 else:
  chosen=best[0]
 all_sem=[next(x for x in opts if x[0]=="SEMANTIC") for opts in options]
 baseline=score(tuple(all_sem))
 positional_used=any(mode=="POSITIONAL" for mode,_ in chosen)
 if positional_used and not (best_score < baseline and (baseline-best_score)>=max(3,int(.5*max(1,baseline)))):
  return [d.copy() for d in parsed_ds],diags,{"blocked":True,"state":"LOW_CONFIDENCE_ALIGNMENT","message":"Ada indikasi pergeseran kolom, tetapi bukti tidak cukup kuat untuk koreksi otomatis.","baseline_conflicts":baseline,"best_conflicts":best_score}
 aligned=[]
 for diag,(mode,d) in zip(diags,chosen):
  diag["interpretation"]=mode;diag["realigned"]=(mode=="POSITIONAL");diag["state"]="REALIGNED" if mode=="POSITIONAL" else "ALIGNED"
  aligned.append(d)
 return aligned,diags,{"blocked":False,"state":"PASS","message":"Schema alignment tervalidasi dengan bukti lintas-batch.","baseline_conflicts":baseline,"best_conflicts":best_score}
