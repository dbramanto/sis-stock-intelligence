from __future__ import annotations
import json, hashlib, math, os
from datetime import datetime
from pathlib import Path
from storage_adapter import JsonStore

HISTORY_VERSION=6
VALIDATED_STATUS="VALIDATED"
_NAMESPACE="input_history"

def _find_sis_root(here):
    for parent in Path(here).parents:
        if parent.name.upper()=="SIS":
            return parent
    return None

def _data_root():
    override=os.environ.get("SIS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    here=Path(__file__).resolve()
    sis_root=_find_sis_root(here)
    if sis_root is not None:
        return sis_root/"SIS_DATA"
    return here.parents[1]/"data"

def _default_history_root():
    return _data_root()/_NAMESPACE

def _store(base_dir=None):
    if base_dir is not None:
        return JsonStore(Path(base_dir).parent if Path(base_dir).name==_NAMESPACE else Path(base_dir))
    return JsonStore(_data_root())

def _clean_batches(raw_batches):return {str(i):str(raw_batches.get(i,raw_batches.get(str(i),""))) for i in range(1,12)}

def _json_scalar(v):
    if v is None:return None
    try:
        if hasattr(v,"item"):v=v.item()
    except Exception:pass
    if isinstance(v,float):
        if math.isnan(v):return "__NaN__"
        if math.isinf(v):return "__Inf__" if v>0 else "__-Inf__"
    if hasattr(v,"isoformat") and not isinstance(v,str):
        try:return v.isoformat()
        except Exception:pass
    if isinstance(v,(str,int,float,bool)):return v
    return str(v)

def _canonical_records(canonical):
    if hasattr(canonical,"to_dict"):
        try:return canonical.to_dict(orient="records")
        except TypeError:pass
    if isinstance(canonical,list):return canonical
    raise ValueError("HISTORY_INVALID_CANONICAL")

def _validate_canonical(canonical,metadata):
    records=_canonical_records(canonical)
    if not records:raise ValueError("HISTORY_EMPTY_CANONICAL")
    symbols=[]
    for row in records:
        if not isinstance(row,dict):raise ValueError("HISTORY_INVALID_CANONICAL")
        symbol=str(row.get("symbol","")).strip().upper()
        if not symbol:raise ValueError("HISTORY_CANONICAL_MISSING_SYMBOL")
        symbols.append(symbol)
    if len(symbols)!=len(set(symbols)):raise ValueError("HISTORY_CANONICAL_DUPLICATE_SYMBOL")
    expected=(metadata or{}).get("expected_total")
    if expected is None:raise ValueError("HISTORY_REQUIRES_EXPECTED_TOTAL")
    try:expected=int(expected)
    except (TypeError,ValueError):raise ValueError("HISTORY_INVALID_EXPECTED_TOTAL")
    if expected<=0 or expected!=len(records):raise ValueError("HISTORY_CANONICAL_COUNT_MISMATCH")
    return records

def _canonical_digest(canonical):
    rows=[{str(k):_json_scalar(v) for k,v in row.items()} for row in _canonical_records(canonical)]
    rows=sorted(rows,key=lambda x:str(x.get("symbol",x.get("ticker",""))).upper())
    body=json.dumps(rows,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=_json_scalar)
    return hashlib.sha256(body.encode()).hexdigest()

def _context_digest(metadata):
    m=metadata or{}
    identity={"filter_fingerprint":m.get("filter_fingerprint"),"expected_total":m.get("expected_total")}
    return hashlib.sha256(json.dumps(identity,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=_json_scalar).encode()).hexdigest()

def save_snapshot(raw_batches,status="INPUT_CAPTURED",base_dir=None,now=None,metadata=None):
    clean=_clean_batches(raw_batches)
    if not all(clean[str(i)].strip() for i in range(1,12)):raise ValueError("HISTORY_REQUIRES_B1_B11")
    ts=now or datetime.now().astimezone();core={"version":HISTORY_VERSION,"created_at":ts.isoformat(),"status":status,"raw_batches":clean,"metadata":metadata or{}}
    digest=hashlib.sha256(json.dumps(core,ensure_ascii=False,sort_keys=True,default=_json_scalar).encode()).hexdigest()[:12]
    sid=ts.strftime("%Y%m%d_%H%M%S_%f")+"_"+digest;payload={"snapshot_id":sid,**core}
    _store(base_dir).put(_NAMESPACE,sid,payload)
    return payload

def save_validated_snapshot(raw_batches,canonical,validation_status,base_dir=None,now=None,metadata=None):
    clean=_clean_batches(raw_batches)
    if not all(clean[str(i)].strip() for i in range(1,12)):raise ValueError("HISTORY_REQUIRES_B1_B11")
    if validation_status!="PASS" or canonical is None:raise ValueError("HISTORY_REQUIRES_VALIDATED_STAGE1")
    m=dict(metadata or{});m.setdefault("analysis_status","PENDING")
    records=_validate_canonical(canonical,m);digest=_canonical_digest(records);context_digest=_context_digest(m)
    store=_store(base_dir)
    for old in store.list(_NAMESPACE):
        if old.get("status")==VALIDATED_STATUS and old.get("canonical_digest")==digest and old.get("context_digest")==context_digest:return old
    ts=now or datetime.now().astimezone();core={"version":HISTORY_VERSION,"created_at":ts.isoformat(),"status":VALIDATED_STATUS,"canonical_digest":digest,"context_digest":context_digest,"raw_batches":clean,"metadata":m}
    sid=ts.strftime("%Y%m%d_%H%M%S_%f")+"_"+digest[:8]+context_digest[:4];payload={"snapshot_id":sid,**core}
    store.put(_NAMESPACE,sid,payload)
    return payload

def update_snapshot_analysis(snapshot_id,analysis_status,base_dir=None,metadata_updates=None):
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:raise ValueError("INVALID_SNAPSHOT_ID")
    store=_store(base_dir);x=store.get(_NAMESPACE,snapshot_id)
    if x.get("snapshot_id")!=snapshot_id or x.get("status")!=VALIDATED_STATUS:raise ValueError("INVALID_VALIDATED_SNAPSHOT")
    allowed={"PENDING","S2_BLOCKED","P10_BLOCKED","S3_BLOCKED","COMPLETE"}
    if analysis_status not in allowed:raise ValueError("INVALID_ANALYSIS_STATUS")
    m=dict(x.get("metadata") or {});m["analysis_status"]=analysis_status
    for k,v in dict(metadata_updates or {}).items():
        if k not in {"expected_total","filter_fingerprint"}:m[k]=v
    x["metadata"]=m;store.put(_NAMESPACE,snapshot_id,x);return x

def _valid_v6_record(x):
    if x.get("version")!=HISTORY_VERSION or x.get("status")!=VALIDATED_STATUS:return True
    return bool(x.get("canonical_digest") and x.get("context_digest") and (x.get("metadata")or{}).get("analysis_status") in {"PENDING","S2_BLOCKED","P10_BLOCKED","S3_BLOCKED","COMPLETE"})

def list_snapshots(base_dir=None,validated_only=False):
    out=[]
    for x in _store(base_dir).list(_NAMESPACE):
        try:
            if not _valid_v6_record(x):continue
            if validated_only and x.get("status")!=VALIDATED_STATUS:continue
            out.append({"snapshot_id":x["snapshot_id"],"created_at":x["created_at"],"status":x.get("status",""),"path":None})
        except Exception:continue
    return out

def load_snapshot(snapshot_id,base_dir=None):
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:raise ValueError("INVALID_SNAPSHOT_ID")
    x=_store(base_dir).get(_NAMESPACE,snapshot_id)
    if x.get("snapshot_id")!=snapshot_id or x.get("version") not in {1,2,3,4,5,HISTORY_VERSION}:raise ValueError("INVALID_SNAPSHOT")
    if not _valid_v6_record(x):raise ValueError("INVALID_VALIDATED_SNAPSHOT")
    return x

def get_snapshot_batch(snapshot,batch_id):
    try:bi=int(batch_id)
    except (TypeError,ValueError):raise ValueError("INVALID_BATCH_ID")
    if bi<1 or bi>11:raise ValueError("INVALID_BATCH_ID")
    raw=snapshot.get("raw_batches")
    if not isinstance(raw,dict):raise ValueError("INVALID_SNAPSHOT_RAW_BATCHES")
    v=raw.get(str(bi),"");return "" if v is None else str(v)
