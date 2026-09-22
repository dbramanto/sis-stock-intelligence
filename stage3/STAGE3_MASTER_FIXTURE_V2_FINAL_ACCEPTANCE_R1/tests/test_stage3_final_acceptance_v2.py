import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT.parent
# Candidate is expected to be extracted directly under the active Dossier root OR copied there.
# Prefer active Dossier root when stage3_dossier.py is adjacent to this package.
if (PROJECT/"stage3_dossier.py").exists():
    sys.path.insert(0,str(PROJECT))
elif (ROOT/"stage3_dossier.py").exists():
    sys.path.insert(0,str(ROOT))
else:
    raise RuntimeError("ACTIVE_DOSSIER_ROOT_NOT_FOUND")
from stage3_dossier import build_dossier

fx=json.loads((ROOT/"fixtures"/"STAGE3_MASTER_FIXTURE_v2.json").read_text(encoding="utf-8"))
assert fx["version"]=="2.0"
assert len(fx["cases"])==16
ids=[x["id"] for x in fx["cases"]]
assert ids==[f"S3X{i:02d}" for i in range(1,17)]

def ck(name,cond):
    assert cond,name
def run_case(c):
    r=build_dossier(c["stock"],fx["analysis_date"]); e=c["expect"]
    if "status" in e: ck("status",r["stage3_status"]==e["status"])
    if "review_protected" in e: ck("review_protected",r.get("review_protected")==e["review_protected"])
    for d,st in e.get("states",{}).items(): ck(f"{d}.state",r["domains"][d]["state"]==st)
    for spec,st in e.get("components",{}).items():
        d,k=spec.split(".",1); ck(spec,r["domains"][d]["components"][k]["state"]==st)
    for d,vals in e.get("domain_contradictions",{}).items():
        for v in vals: ck(f"{d}:{v}",v in r["domains"][d]["contradictions"])
    for v in e.get("cross",[]): ck(f"cross:{v}",v in r["cross_engine_contradictions"])
    for d in e.get("stale",[]): ck(f"stale:{d}",d in r["data_quality"]["stale_or_future_domains"])
    if r["stage3_status"]!="BLOCKED":
        ck("seven_domains",set(r["domains"])=={"technical","business","cash_flow","valuation","sector","catalyst","risk"})
        ck("no_decision_leak",r["recommendation"] is None and r["ranking"] is None and r["horizon_score"] is None)
        ck("no_engine_failure",not r["data_quality"]["failed_domains"])
    return r

for c in fx["cases"]:
    run_case(c)
    print("PASS",c["id"],c["description"])
print("PASS 16/16 STAGE3 FINAL SYSTEM ACCEPTANCE")
print("PASS MASTER FIXTURE V2 CONTRACT")
print("PASS NO DECISION LEAK ALL CASES")
