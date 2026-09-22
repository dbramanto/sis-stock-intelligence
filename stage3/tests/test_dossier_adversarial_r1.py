import copy,json,math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from stage3_dossier import build_dossier
x=json.loads((ROOT/"fixtures/dossier_all_domain.json").read_text())
def ck(n,c): assert c,n; print("PASS",n)
ck("INVALID STOCK FAIL CLOSED",build_dossier([])["stage3_status"]=="BLOCKED")
y=copy.deepcopy(x); y["risk_enrichment"].update({"beta":1.9,"max_drawdown_pct":-50,"debt_equity":4,"interest_coverage":1,"cash_short_debt_coverage":.4})
r=build_dossier(y)
ck("HIGH RISK DOES NOT ERASE OTHER DOMAINS",r["domains"]["risk"]["state"]=="HIGH" and r["domains"]["business"]["state"]!="NOT_EVALUATED")
ck("CROSS RISK TENSION VISIBLE","FAVORABLE_EVIDENCE_COEXISTS_WITH_HIGH_RISK" in r["cross_engine_contradictions"])
y=copy.deepcopy(x); y["cash_enrichment"]={}
r=build_dossier(y)
ck("EMPTY DOMAIN NOT FALSE HEALTHY",r["domains"]["cash_flow"]["state"]=="NOT_EVALUATED")
y=copy.deepcopy(x); y["valuation_enrichment"]["metadata"]["as_of_date"]="2026-01-01"
r=build_dossier(y)
ck("STALE PROPAGATION","valuation" in r["data_quality"]["stale_or_future_domains"])
ck("NO UNIVERSAL SCORE","horizon_score" in r and r["horizon_score"] is None)

# ACC18 — frozen 3A uses BULL as favorable technical state.
from stage3_dossier import _cross
base_cross=lambda catalyst,sector:{"technical":{"state":"BULL"},"business":{"state":"MIXED"},"cash_flow":{"state":"MIXED"},"valuation":{"state":"MIXED_OR_FAIR"},"sector":{"state":sector},"catalyst":{"state":catalyst},"risk":{"state":"MODERATE"}}
ck("BULL TECHNICAL NEGATIVE CATALYST CONTRACT","STRONG_TECHNICAL_NEGATIVE_CATALYST" in _cross(base_cross("NEGATIVE","MIXED")))
ck("BULL TECHNICAL SECTOR HEADWIND CONTRACT","STRONG_TECHNICAL_SECTOR_HEADWIND" in _cross(base_cross("POSITIVE","HEADWIND")))

print("PASS STAGE3 DOSSIER ADVERSARIAL R1")
