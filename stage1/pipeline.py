import math, re, hashlib
import pandas as pd
from .schema import BATCHES, CONTROL, VENDOR_CHECK_ONLY, REQUIRED_BATCHES, B10_SPECIAL_FIELDS

NULLS={"","-","—","n/a","na","null","none"}
SUFFIX={"k":1e3,"m":1e6,"b":1e9,"t":1e12}

def parse_number(v, field=None, source="STOCKBIT"):
    raw = None if v is None else str(v).strip()
    if source == "STOCKBIT" and field == "EPS Annual YoY" and raw and re.fullmatch(r"-,\d{1,3}(?:\.\d+)?%?", raw):
        repaired = "-" + raw[2:]
        if repaired.endswith("%"): repaired = repaired[:-1]
        try: return float(repaired), "NORMALIZED:STOCKBIT_NEGATIVE_LEADING_COMMA_REPAIR"
        except ValueError: pass
    if v is None or (isinstance(v,float) and math.isnan(v)): return None, None
    if isinstance(v,(int,float)): return float(v), None
    s=str(v).strip()
    if s.lower() in NULLS: return None, None
    neg=s.startswith('(') and s.endswith(')')
    if neg: s=s[1:-1].strip()
    pct=s.endswith('%'); s=s[:-1].strip() if pct else s
    if re.search(r'(^|[^0-9])-,\d',s): return None,"AMBIGUOUS_NUMERIC_FORMAT"
    s=s.replace('Rp','').replace('$','').replace(',','').strip(); mult=1
    if s and s[-1].lower() in SUFFIX: mult=SUFFIX[s[-1].lower()]; s=s[:-1]
    try: x=float(s)*mult
    except ValueError: return None,"INVALID_NUMERIC"
    if neg: x=-x
    return x, None

def _symbol_col(df):
    for c in df.columns:
        if str(c).strip().lower() in {"symbol","ticker","stock","code"}: return c
    return None

def validate_batch(df,b):
    issues=[]; sc=_symbol_col(df)
    if sc is None: return [f"B{b}:MISSING_SYMBOL_COLUMN"]
    syms=df[sc].astype(str).str.strip().str.upper()
    if syms.duplicated().any(): issues.append(f"B{b}:DUPLICATE_SYMBOL")
    missing=[c for c in BATCHES[b] if c not in df.columns]
    if missing: issues.append(f"B{b}:MISSING_COLUMNS:"+",".join(missing))
    return issues

def _set_hash(symbols):
    return hashlib.sha256("\n".join(sorted(symbols)).encode()).hexdigest()[:16]

def _b9_semantic(row):
    pe=[row.get("PE -1SD 5Y"),row.get("PE Mean 5Y"),row.get("PE +1SD 5Y")]
    pb=[row.get("PBV -1SD 5Y"),row.get("PBV Mean 5Y"),row.get("PBV +1SD 5Y")]
    def valid(vals, positive=False):
        if any(v is None or (isinstance(v,float) and math.isnan(v)) for v in vals): return "MISSING"
        if not (vals[0] <= vals[1] <= vals[2]): return "SPECIAL_TREATMENT"
        if positive and any(v <= 0 for v in vals): return "SPECIAL_TREATMENT"
        return "VALID_CONTEXT"
    return valid(pe, True), valid(pb, True)



def _control_sanity_issue(field, value):
    """Reject impossible controls; normal sequential market drift is valid."""
    if value is None or pd.isna(value):
        return None
    try:
        v=float(value)
    except Exception:
        return "INVALID_NUMERIC"
    if not math.isfinite(v):
        return "NONFINITE"
    if field == "RSI14" and not (0 <= v <= 100):
        return "RSI_OUT_OF_RANGE"
    if field in {"Price","Price MA20","Price MA50"} and v <= 0:
        return "NONPOSITIVE"
    if field in {"Volume","Volume MA20","ADTV30"} and v < 0:
        return "NEGATIVE"
    return None

def run_stage1(batches, expected_total=None, filter_fingerprint=None):
    result={"status":"PASS","issues":[],"canonical":pd.DataFrame(),"reconciliation":pd.DataFrame(),"universe_alignment":pd.DataFrame(),"batch_summary":pd.DataFrame(),"normalizations":[]}
    supplied=set(batches)
    if supplied != REQUIRED_BATCHES:
        result["status"]="BLOCKED"; result["issues"].append("MISSING_REQUIRED_BATCH:"+",".join(map(str,sorted(REQUIRED_BATCHES-supplied)))); return result
    for b,df in batches.items(): result["issues"] += validate_batch(df,b)
    if any("MISSING_" in x or "DUPLICATE_SYMBOL" in x for x in result["issues"]): result["status"]="BLOCKED"; return result
    parsed={}; raw_missing={}; parse_issues=[]
    for b,df in batches.items():
        sc=_symbol_col(df); z=df.copy(); z[sc]=z[sc].astype(str).str.strip().str.upper(); z=z.set_index(sc)
        raw_missing[b]={sym:{c:(str(v).strip().lower() in NULLS) for c,v in row.items()} for sym,row in z.iterrows()}
        for c in z.columns:
            vals=[]
            for sym,v in z[c].items():
                x,e=parse_number(v, field=c); vals.append(x)
                if e and not e.startswith("NORMALIZED:"): parse_issues.append(f"B{b}:{sym}:{c}:{e}")
                elif e: result["normalizations"].append({"batch":b,"symbol":sym,"field":c,"raw_value":str(v),"canonical_value":x,"normalization":e.split(":",1)[1]})
            z[c]=vals
        parsed[b]=z
    if parse_issues: result["status"]="BLOCKED"; result["issues"]+=parse_issues; return result
    sets={b:set(z.index) for b,z in parsed.items()}; ref=sets[1]
    summaries=[]
    for b in sorted(REQUIRED_BATCHES):
        s=sets[b]; summaries.append({"batch":b,"rows":len(parsed[b]),"unique_symbols":len(s),"symbol_set_hash":_set_hash(s),"missing_vs_b1":len(ref-s),"extra_vs_b1":len(s-ref)})
        if s != ref:
            result["status"]="BLOCKED"; result["issues"].append(f"B{b}:UNIVERSE_MISMATCH:MISSING={len(ref-s)}:EXTRA={len(s-ref)}")
    result["batch_summary"]=pd.DataFrame(summaries); result["universe_alignment"]=result["batch_summary"].copy()
    if any(s != ref for s in sets.values()):
        return result
    if expected_total is None:
        if result["status"]=="PASS": result["status"]="REVIEW"
        result["issues"].append("EXPECTED_UNIVERSE_TOTAL_NOT_PROVIDED")
    else:
        try: et=int(expected_total)
        except Exception: et=-1
        if et <= 0: result["status"]="BLOCKED"; result["issues"].append("INVALID_EXPECTED_UNIVERSE_TOTAL")
        for b,s in sets.items():
            if len(s)!=et: result["status"]="BLOCKED"; result["issues"].append(f"B{b}:UNIVERSE_INCOMPLETE:EXPECTED={et}:CAPTURED={len(s)}")
    # Fail closed only for impossible controls; ordinary B1-B11 drift is valid.
    for b in sorted(REQUIRED_BATCHES):
        for sym in sorted(ref):
            for c in CONTROL:
                v=parsed[b].loc[sym,c] if c in parsed[b].columns else None
                code=_control_sanity_issue(c,v)
                if code:
                    result["status"]="BLOCKED"
                    result["issues"].append(f"B{b}:{sym}:{c}:CONTROL_SANITY:{code}")
    if result["status"]=="BLOCKED":
        return result

    symbols=sorted(ref); rows=[]; rec=[]
    for sym in symbols:
        row={"symbol":sym}; control_review=False
        for c in CONTROL:
            vals=[]
            for b in sorted(REQUIRED_BATCHES):
                v=parsed[b].loc[sym,c] if c in parsed[b].columns else None
                if pd.notna(v):
                    vals.append((b,float(v)))
            if vals:
                # Sequential capture: market-derived controls may drift.
                # Keep universe strict; canonical uses freshest valid observation.
                row[c]=vals[-1][1]
            else:
                row[c]=None
        for b,z in parsed.items():
            for c in z.columns:
                if c in CONTROL or c in VENDOR_CHECK_ONLY: continue
                row[c]=z.at[sym,c]
        st,lt=row.get("Short Term Debt Quarter"),row.get("Long Term Debt Quarter")
        if st is not None and lt is not None: row["Derived Total Debt"]=st+lt
        cfo,capex=row.get("Cash From Operations TTM"),row.get("CAPEX TTM")
        if cfo is not None and capex is not None: row["Derived Free Cash Flow TTM"]=cfo+capex
        pe=row.get("PE TTM")
        if pe not in (None,0): row["Derived Earnings Yield TTM"]=100/pe
        mc,eq,rev,ev,ebitda=row.get("Market Cap"),row.get("Common Equity"),row.get("Revenue TTM"),row.get("Enterprise Value"),row.get("EBITDA TTM")
        if mc is not None and eq not in (None,0): row["Derived PBV"]=mc/eq
        if mc is not None and rev not in (None,0): row["Derived P/S TTM"]=mc/rev
        if ev is not None and ebitda not in (None,0): row["Derived EV/EBITDA TTM"]=ev/ebitda
        row["B9 PE Semantic Validity"],row["B9 PBV Semantic Validity"]=_b9_semantic(row)
        available=sum(v is not None and not (isinstance(v,float) and math.isnan(v)) for v in (row.get(c) for c in B10_SPECIAL_FIELDS))
        row["B10 Specialized Available Count"]=available
        row["B10 Applicability State"]="NOT_EVALUATED" if available==0 else "AVAILABLE_PARTIAL"
        if control_review and result["status"]=="PASS": result["status"]="REVIEW"
        rows.append(row)
    result["canonical"]=pd.DataFrame(rows); result["reconciliation"]=pd.DataFrame(rec)
    result["capture_metadata"]={"expected_total":expected_total,"captured_unique":len(ref),"filter_fingerprint":filter_fingerprint or "NOT_PROVIDED","reference_symbol_set_hash":_set_hash(ref)}
    return result
