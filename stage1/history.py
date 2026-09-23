from __future__ import annotations
import json, hashlib, os
from datetime import datetime
from pathlib import Path
HISTORY_VERSION=5
VALIDATED_STATUS="VALIDATED"

def _root(base_dir=None):
    p=Path(base_dir) if base_dir else Path(__file__).resolve().parents[1]/"data"/"input_history"
    p.mkdir(parents=True,exist_ok=True)
    return p

def _clean_batches(raw_batches):
    return {str(i):str(raw_batches.get(i,raw_batches.get(str(i),""))) for i in range(1,12)}

def _canonical_records(canonical):
    if hasattr(canonical,"to_dict"):
        return canonical.to_dict(orient="records")
    if isinstance(canonical,list):
        return canonical
    raise ValueError("HISTORY_INVALID_CANONICAL")

def _json_default(v):
    if hasattr(v,"item"):
        return v.item()
    if hasattr(v,"isoformat"):
        return v.isoformat()
    return str(v)

def _canonical_digest(canonical):
    records=_canonical_records(canonical)
    body=json.dumps(records,ensure_ascii=False,sort_keys=True,separators=(",",":"),default=_json_default)
    return hashlib.sha256(body.encode()).hexdigest()

def _validate_canonical(canonical,metadata):
    records=_canonical_records(canonical)
    if not records:
        raise ValueError("HISTORY_EMPTY_CANONICAL")
    symbols=[]
    for row in records:
        if not isinstance(row,dict):
            raise ValueError("HISTORY_INVALID_CANONICAL")
        symbol=str(row.get("symbol","")).strip().upper()
        if not symbol:
            raise ValueError("HISTORY_CANONICAL_MISSING_SYMBOL")
        symbols.append(symbol)
    if len(symbols)!=len(set(symbols)):
        raise ValueError("HISTORY_CANONICAL_DUPLICATE_SYMBOL")
    expected=(metadata or {}).get("expected_total")
    if expected is None:
        raise ValueError("HISTORY_REQUIRES_EXPECTED_TOTAL")
    try:
        expected=int(expected)
    except (TypeError,ValueError):
        raise ValueError("HISTORY_INVALID_EXPECTED_TOTAL")
    if expected<=0 or expected!=len(records):
        raise ValueError("HISTORY_CANONICAL_COUNT_MISMATCH")
    return records

def _atomic_write_json(path,payload):
    tmp=path.with_name(path.name+".tmp")
    data=json.dumps(payload,ensure_ascii=False,indent=2,default=_json_default)
    try:
        with tmp.open("w",encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if tmp.exists():
            try: tmp.unlink()
            except OSError: pass

def save_snapshot(raw_batches,status="INPUT_CAPTURED",base_dir=None,now=None,metadata=None):
    """Legacy v1 capture API retained only for regression compatibility.

    D1 v2 official validated history must use save_validated_snapshot().
    """
    clean=_clean_batches(raw_batches)
    if not all(clean[str(i)].strip() for i in range(1,12)):
        raise ValueError("HISTORY_REQUIRES_B1_B11")
    ts=now or datetime.now().astimezone()
    core={"version":HISTORY_VERSION,"created_at":ts.isoformat(),"status":status,"raw_batches":clean,"metadata":metadata or {}}
    digest=hashlib.sha256(json.dumps(core,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:12]
    sid=ts.strftime("%Y%m%d_%H%M%S_%f")+"_"+digest
    payload={"snapshot_id":sid,**core}
    _atomic_write_json(_root(base_dir)/(sid+".json"),payload)
    return payload

def save_validated_snapshot(raw_batches,canonical,validation_status,base_dir=None,now=None,metadata=None):
    """Persist an official D1 snapshot only after the Stage-1 gate passes."""
    clean=_clean_batches(raw_batches)
    if not all(clean[str(i)].strip() for i in range(1,12)):
        raise ValueError("HISTORY_REQUIRES_B1_B11")
    if validation_status!="PASS" or canonical is None:
        raise ValueError("HISTORY_REQUIRES_VALIDATED_STAGE1")
    records=_validate_canonical(canonical,metadata)
    digest=_canonical_digest(records)
    root=_root(base_dir)
    for p in root.glob("*.json"):
        try:
            old=json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if old.get("status")==VALIDATED_STATUS and old.get("canonical_digest")==digest:
            return old
    ts=now or datetime.now().astimezone()
    core={
        "version":HISTORY_VERSION,
        "created_at":ts.isoformat(),
        "status":VALIDATED_STATUS,
        "canonical_digest":digest,
        "raw_batches":clean,
        "metadata":metadata or {},
    }
    sid=ts.strftime("%Y%m%d_%H%M%S_%f")+"_"+digest[:12]
    payload={"snapshot_id":sid,**core}
    _atomic_write_json(root/(sid+".json"),payload)
    return payload

def list_snapshots(base_dir=None,validated_only=False):
    out=[]
    for p in sorted(_root(base_dir).glob("*.json"),reverse=True):
        try:
            x=json.loads(p.read_text(encoding="utf-8"))
            if validated_only and x.get("status")!=VALIDATED_STATUS:
                continue
            out.append({"snapshot_id":x["snapshot_id"],"created_at":x["created_at"],"status":x.get("status",""),"path":str(p)})
        except Exception:
            continue
    return out

def load_snapshot(snapshot_id,base_dir=None):
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id:
        raise ValueError("INVALID_SNAPSHOT_ID")
    x=json.loads((_root(base_dir)/(snapshot_id+".json")).read_text(encoding="utf-8"))
    if x.get("snapshot_id")!=snapshot_id or x.get("version") not in {1,2,3,4,HISTORY_VERSION}:
        raise ValueError("INVALID_SNAPSHOT")
    return x

def get_snapshot_batch(snapshot,batch_id):
    try:
        bi=int(batch_id)
    except (TypeError,ValueError):
        raise ValueError("INVALID_BATCH_ID")
    if bi<1 or bi>11:
        raise ValueError("INVALID_BATCH_ID")
    raw=snapshot.get("raw_batches")
    if not isinstance(raw,dict):
        raise ValueError("INVALID_SNAPSHOT_RAW_BATCHES")
    v=raw.get(str(bi),"")
    return "" if v is None else str(v)
