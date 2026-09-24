from __future__ import annotations
import hashlib, json, math, os
from datetime import datetime
from pathlib import Path
from storage_adapter import JsonStore

RESULT_VERSION = 1
_NAMESPACE = "analysis_results"

def _find_sis_root(here):
    for parent in Path(here).parents:
        if parent.name.upper() == "SIS":
            return parent
    return None

def _data_root():
    override = os.environ.get("SIS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser()
    here = Path(__file__).resolve()
    sis_root = _find_sis_root(here)
    if sis_root is not None:
        return sis_root / "SIS_DATA"
    return here.parents[1] / "data"

def _default_root():
    return _data_root() / _NAMESPACE

def _store(base_dir=None):
    if base_dir is not None:
        p = Path(base_dir)
        return JsonStore(p.parent if p.name == _NAMESPACE else p)
    return JsonStore(_data_root())

def _safe_id(snapshot_id):
    sid = str(snapshot_id or "")
    if not sid or "/" in sid or "\\" in sid or ".." in sid:
        raise ValueError("INVALID_SNAPSHOT_ID")
    return sid

def _json_scalar(v):
    if v is None: return None
    try:
        if hasattr(v, "item"): v = v.item()
    except Exception: pass
    if isinstance(v, float):
        if math.isnan(v): return "__NaN__"
        if math.isinf(v): return "__Inf__" if v > 0 else "__-Inf__"
    if hasattr(v, "isoformat") and not isinstance(v, str):
        try: return v.isoformat()
        except Exception: pass
    if isinstance(v, (str, int, float, bool)): return v
    return str(v)

def _digest(stage3):
    body = json.dumps(stage3, ensure_ascii=False, sort_keys=True, separators=(",",":"), default=_json_scalar)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()

def save_analysis_result(snapshot_id, stage3, analysis_as_of, base_dir=None, now=None):
    sid = _safe_id(snapshot_id)
    if not isinstance(stage3, dict) or stage3.get("status") != "COMPLETE":
        raise ValueError("RESULT_REQUIRES_COMPLETE_STAGE3")
    if not isinstance(stage3.get("candidates"), list) or not isinstance(stage3.get("ranking"), dict):
        raise ValueError("RESULT_INVALID_STAGE3_CONTRACT")
    payload = {
        "version": RESULT_VERSION,
        "snapshot_id": sid,
        "created_at": (now or datetime.now().astimezone()).isoformat(),
        "analysis_as_of": str(analysis_as_of),
        "status": "COMPLETE",
        "stage3_digest": _digest(stage3),
        "stage3": stage3,
    }
    store = _store(base_dir)
    if store.exists(_NAMESPACE, sid):
        old = store.get(_NAMESPACE, sid)
        if old.get("snapshot_id") != sid: raise ValueError("RESULT_ID_CONFLICT")
        if old.get("stage3_digest") == payload["stage3_digest"]: return old
        raise ValueError("RESULT_CONTENT_CONFLICT")
    store.put(_NAMESPACE, sid, payload, overwrite=False)
    return payload

def load_analysis_result(snapshot_id, base_dir=None):
    sid = _safe_id(snapshot_id)
    x = _store(base_dir).get(_NAMESPACE, sid)
    if x.get("version") != RESULT_VERSION or x.get("snapshot_id") != sid or x.get("status") != "COMPLETE":
        raise ValueError("INVALID_ANALYSIS_RESULT")
    s3 = x.get("stage3")
    if not isinstance(s3, dict) or s3.get("status") != "COMPLETE" or _digest(s3) != x.get("stage3_digest"):
        raise ValueError("ANALYSIS_RESULT_INTEGRITY_FAILED")
    return x

def result_exists(snapshot_id, base_dir=None):
    try: return _store(base_dir).exists(_NAMESPACE, _safe_id(snapshot_id))
    except ValueError: return False
