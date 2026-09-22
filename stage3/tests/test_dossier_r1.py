import copy,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from stage3_dossier import build_dossier
x=json.loads((ROOT/"fixtures/dossier_all_domain.json").read_text())
def ck(n,c): assert c,n; print("PASS",n)
r=build_dossier(x)
ck("SEVEN DOMAIN CONTRACT",set(r["domains"])=={"technical","business","cash_flow","valuation","sector","catalyst","risk"})
ck("NO DECISION LEAK",r["recommendation"] is None and r["ranking"] is None and r["horizon_score"] is None)
ck("DOMAIN CONFIDENCE SEPARATE",set(r["confidence_by_domain"])==set(r["domains"]))
y=copy.deepcopy(x); y["stage2"]["eligibility"]="REVIEW"; rr=build_dossier(y)
ck("STAGE2 REVIEW PROTECTED",rr["stage3_status"]=="REVIEW_PROTECTED" and rr["review_protected"])
y=copy.deepcopy(x); y["upstream_gate"]="BLOCKED"; rr=build_dossier(y)
ck("UPSTREAM BLOCK STOPS STAGE3",rr["stage3_status"]=="BLOCKED" and not rr["domains"])
y=copy.deepcopy(x); y["fundamental_enrichment"]=[]
rr=build_dossier(y)
ck("DOMAIN ISOLATION",rr["domains"]["business"]["state"]=="NOT_EVALUATED" and len(rr["domains"])==7)
ck("MISSING NOT ZERO",rr["domains"]["business"]["state"]=="NOT_EVALUATED")
print("PASS STAGE3 DOSSIER R1")
