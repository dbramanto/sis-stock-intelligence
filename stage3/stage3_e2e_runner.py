from __future__ import annotations
from stage3_dossier import build_dossier
from stage3h_synthesis import synthesize
from stage3i_swing import evaluate_swing
from stage3i_longterm import evaluate_longterm
from final_ranking_engine import rank_candidates

def run_stage3_candidate(stock, analysis_date="2026-09-17"):
    if not isinstance(stock,dict):
        return {"status":"INVALID","reason":"INVALID_STOCK_PAYLOAD"}
    dossier=build_dossier(stock,analysis_date)
    if dossier.get("stage3_status")=="BLOCKED":
        return {"status":"BLOCKED","symbol":stock.get("symbol"),"dossier":dossier}
    synthesis=synthesize(dossier)
    forward=stock.get("forward_enrichment",{})
    if not isinstance(forward,dict): forward={}
    swing=evaluate_swing(synthesis,dossier,stock)
    longterm=evaluate_longterm(synthesis,dossier,forward)
    return {"status":"COMPLETE","symbol":stock.get("symbol"),
            "dossier":dossier,"synthesis":synthesis,
            "swing_execution":swing,"longterm_outlook":longterm}

def run_stage3_universe(stocks, analysis_date="2026-09-17", top_n=3):
    if not isinstance(stocks,list):
        return {"status":"INVALID","reason":"INVALID_UNIVERSE"}
    candidates=[]; blocked=[]
    for stock in stocks:
        x=run_stage3_candidate(stock,analysis_date)
        if x.get("status")=="COMPLETE":
            candidates.append({"symbol":x.get("symbol"),
                               "dossier":x.get("dossier"),
                               "synthesis":x["synthesis"],
                               "swing_execution":x["swing_execution"],
                               "longterm_outlook":x["longterm_outlook"]})
        else: blocked.append({"symbol":x.get("symbol"),"status":x.get("status"),"reason":x.get("reason")})
    ranking=rank_candidates(candidates,top_n=top_n)
    return {"status":"COMPLETE","candidate_count":len(candidates),"blocked":blocked,
            "candidates":candidates,"ranking":ranking,"recommendation":None}
