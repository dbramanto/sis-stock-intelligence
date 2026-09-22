from __future__ import annotations
import json, hashlib
from datetime import datetime
from pathlib import Path
HISTORY_VERSION=4

def _root(base_dir=None):
    p=Path(base_dir) if base_dir else Path(__file__).resolve().parents[1]/"data"/"input_history"; p.mkdir(parents=True,exist_ok=True); return p

def save_snapshot(raw_batches,status="INPUT_CAPTURED",base_dir=None,now=None,metadata=None):
    clean={str(i):str(raw_batches.get(i,raw_batches.get(str(i),""))) for i in range(1,12)}
    if not all(clean[str(i)].strip() for i in range(1,12)): raise ValueError("HISTORY_REQUIRES_B1_B11")
    ts=now or datetime.now().astimezone(); core={"version":HISTORY_VERSION,"created_at":ts.isoformat(),"status":status,"raw_batches":clean,"metadata":metadata or {}}
    digest=hashlib.sha256(json.dumps(core,ensure_ascii=False,sort_keys=True).encode()).hexdigest()[:12]; sid=ts.strftime("%Y%m%d_%H%M%S_%f")+"_"+digest
    payload={"snapshot_id":sid,**core}; (_root(base_dir)/(sid+".json")).write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8"); return payload

def list_snapshots(base_dir=None):
    out=[]
    for p in sorted(_root(base_dir).glob("*.json"),reverse=True):
        try:
            x=json.loads(p.read_text(encoding="utf-8")); out.append({"snapshot_id":x["snapshot_id"],"created_at":x["created_at"],"status":x.get("status",""),"path":str(p)})
        except Exception: continue
    return out

def load_snapshot(snapshot_id,base_dir=None):
    if not snapshot_id or "/" in snapshot_id or "\\" in snapshot_id or ".." in snapshot_id: raise ValueError("INVALID_SNAPSHOT_ID")
    x=json.loads((_root(base_dir)/(snapshot_id+".json")).read_text(encoding="utf-8"))
    if x.get("snapshot_id")!=snapshot_id or x.get("version") not in {1,2,3,HISTORY_VERSION}: raise ValueError("INVALID_SNAPSHOT")
    return x

def get_snapshot_batch(snapshot,batch_id):
    try: bi=int(batch_id)
    except (TypeError,ValueError): raise ValueError("INVALID_BATCH_ID")
    if bi<1: raise ValueError("INVALID_BATCH_ID")
    raw=snapshot.get("raw_batches")
    if not isinstance(raw,dict): raise ValueError("INVALID_SNAPSHOT_RAW_BATCHES")
    v=raw.get(str(bi),""); return "" if v is None else str(v)
