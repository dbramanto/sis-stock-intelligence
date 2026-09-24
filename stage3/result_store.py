from __future__ import annotations
import hashlib, json, math, os, tempfile
from datetime import datetime
from pathlib import Path

RESULT_VERSION = 1

def _find_sis_root(here):
    for parent in Path(here).parents:
        if parent.name.upper() == "SIS":
            return parent
    return None

def _default_root():
    override = os.environ.get("SIS_DATA_DIR", "").strip()
    if override:
        return Path(override).expanduser() / "analysis_results"
    here = Path(__file__).resolve()
    sis_root = _find_sis_root(here)
    if sis_root is not None:
        return sis_root / "SIS_DATA" / "analysis_results"
    return here.parents[1] / "data" / "analysis_results"

def _root(base_dir=None):
    p = Path(base_dir) if base_dir else _default_root()
    p.mkdir(parents=True, exist_ok=True)
    return p

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

def _atomic_write(path, payload):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=path.name+".", suffix=".tmp", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, default=_json_scalar)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try: os.unlink(tmp)
        except OSError: pass
        raise

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
    path = _root(base_dir) / (sid + ".json")
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if old.get("snapshot_id") != sid: raise ValueError("RESULT_ID_CONFLICT")
        if old.get("stage3_digest") == payload["stage3_digest"]: return old
        raise ValueError("RESULT_CONTENT_CONFLICT")
    _atomic_write(path, payload)
    return payload

def load_analysis_result(snapshot_id, base_dir=None):
    sid = _safe_id(snapshot_id)
    x = json.loads((_root(base_dir)/(sid+".json")).read_text(encoding="utf-8"))
    if x.get("version") != RESULT_VERSION or x.get("snapshot_id") != sid or x.get("status") != "COMPLETE":
        raise ValueError("INVALID_ANALYSIS_RESULT")
    s3 = x.get("stage3")
    if not isinstance(s3, dict) or s3.get("status") != "COMPLETE" or _digest(s3) != x.get("stage3_digest"):
        raise ValueError("ANALYSIS_RESULT_INTEGRITY_FAILED")
    return x

def result_exists(snapshot_id, base_dir=None):
    try: return (_root(base_dir)/(_safe_id(snapshot_id)+".json")).is_file()
    except ValueError: return False
