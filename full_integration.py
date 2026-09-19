from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import importlib, sys

@dataclass(frozen=True)
class FullIntegrationResult:
    state:str; analysis_as_of:str; stage2_integrity:Mapping[str,Any]
    pipeline_state:str|None; scope_symbols:tuple[str,...]; dossiers:tuple[dict,...]
    diagnostics:tuple[str,...]; rejected_evidence_ids:tuple[str,...]
    reconciliation_states:tuple[tuple[str,str,str],...]

def _prepend_once(p:Path):
    s=str(p.resolve()); sys.path[:]=[x for x in sys.path if str(Path(x or ".").resolve())!=s]; sys.path.insert(0,s)
def _assert_origin(m, expected:Path):
    a=Path(getattr(m,"__file__","")).resolve()
    try:a.relative_to(expected.resolve())
    except Exception as e: raise ImportError(f"MODULE_ORIGIN_MISMATCH:{m.__name__}") from e
def _load_runtime():
    root=Path(__file__).resolve().parent; p=root/"integration_pipeline"; s=root/"stage3"
    if not p.is_dir(): raise ImportError("MISSING_INTEGRATION_PIPELINE_DIR")
    if not s.is_dir(): raise ImportError("MISSING_STAGE3_DIR")
    _prepend_once(s); _prepend_once(p)
    p10=importlib.import_module("pipeline_p10_orchestrator"); _assert_origin(p10,p)
    d=importlib.import_module("stage3_dossier"); _assert_origin(d,s)
    return p10,d
def _sym(x): return str(x or "").strip().upper()

def run_full_integration(*,stage2_output:Mapping[str,Any],analysis_as_of:str,
 raw_evidence:Iterable[Any]=(),derivations:Sequence[Any]=(),ohlcv_by_symbol=None,
 business_context_by_symbol=None,sector_context_by_symbol=None,catalyst_events_by_symbol=None):
    if not isinstance(stage2_output,Mapping):
        return FullIntegrationResult("BLOCKED",analysis_as_of,{},None,(),(),("INVALID_STAGE2_OUTPUT",),(),())
    integ=stage2_output.get("integrity",{})
    if not isinstance(integ,Mapping): integ={}
    if str(integ.get("state","BLOCKED")).upper()=="BLOCKED":
        return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),None,(),(),("STAGE2_INTEGRITY_BLOCKED",),(),())
    rows=stage2_output.get("results",[])
    if not isinstance(rows,(list,tuple)) or any(not isinstance(x,Mapping) for x in rows):
        return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),None,(),(),("INVALID_STAGE2_RESULTS",),(),())
    rows=[dict(x) for x in rows]
    try:
        p10,dmod=_load_runtime()
        pr=p10.run_pipeline(stage2_records=rows,analysis_as_of=analysis_as_of,raw_evidence=raw_evidence,
          derivations=derivations,ohlcv_by_symbol=ohlcv_by_symbol,business_context_by_symbol=business_context_by_symbol,
          sector_context_by_symbol=sector_context_by_symbol,catalyst_events_by_symbol=catalyst_events_by_symbol)
    except Exception as e:
        return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),None,(),(),(f"RUNTIME_FAILURE:{type(e).__name__}",),(),())
    scope=tuple(_sym(x) for x in getattr(pr,"scope_symbols",()))
    payloads=tuple(getattr(pr,"payloads",()))
    ps=str(getattr(pr,"state","BLOCKED")).upper()
    diag=list(getattr(pr,"diagnostics",()))
    rej=tuple(getattr(pr,"rejected_evidence_ids",())); rec=tuple(getattr(pr,"reconciliation_states",()))
    if ps=="BLOCKED": return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),ps,scope,(),tuple(diag),rej,rec)
    syms=tuple(_sym(p.get("symbol")) for p in payloads if isinstance(p,Mapping))
    if len(syms)!=len(payloads) or syms!=scope:
        diag.append("CARDINALITY_OR_ORDER_MISMATCH:PIPELINE_SCOPE_TO_PAYLOAD")
        return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),ps,scope,(),tuple(diag),rej,rec)
    dossiers=[]
    for p in payloads:
        try:d=dmod.build_dossier(dict(p),analysis_date=analysis_as_of)
        except Exception as e:
            diag.append(f"STAGE3_DOSSIER_FAILURE:{_sym(p.get('symbol'))}:{type(e).__name__}")
            return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),ps,scope,tuple(dossiers),tuple(diag),rej,rec)
        if not isinstance(d,dict):
            diag.append("INVALID_DOSSIER_TYPE")
            return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),ps,scope,tuple(dossiers),tuple(diag),rej,rec)
        dossiers.append(d)
    if tuple(_sym(d.get("symbol")) for d in dossiers)!=scope:
        diag.append("CARDINALITY_OR_ORDER_MISMATCH:PAYLOAD_TO_DOSSIER")
        return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),ps,scope,tuple(dossiers),tuple(diag),rej,rec)
    for d in dossiers:
        if d.get("recommendation") is not None or d.get("ranking") is not None or d.get("horizon_score") is not None:
            diag.append(f"DECISION_LEAK:{_sym(d.get('symbol'))}")
            return FullIntegrationResult("BLOCKED",analysis_as_of,dict(integ),ps,scope,tuple(dossiers),tuple(diag),rej,rec)
    state="PARTIAL" if ps=="PARTIAL" or diag else "PASS"
    if any(str(d.get("stage3_status","")).upper()=="BLOCKED" for d in dossiers): state="BLOCKED"
    return FullIntegrationResult(state,analysis_as_of,dict(integ),ps,scope,tuple(dossiers),tuple(diag),rej,rec)
