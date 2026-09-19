from __future__ import annotations
from datetime import date, datetime
import math

UNKNOWN="UNKNOWN"
NOT_EVALUATED="NOT_EVALUATED"
VALID_CONFIDENCE={"INSUFFICIENT","LOW","MODERATE","HIGH"}

def missing(v):
    return v is None or (isinstance(v,float) and math.isnan(v))

def confidence_from_coverage(pct):
    if pct>=.90:return "HIGH"
    if pct>=.70:return "MODERATE"
    if pct>=.40:return "LOW"
    return "INSUFFICIENT"

def result(state=UNKNOWN,evidence=None,confidence="LOW",**extra):
    if confidence not in VALID_CONFIDENCE: confidence="LOW"
    out={"state":state,"evidence":list(evidence or []),"confidence":confidence}
    out.update(extra); return out

def parse_date(v):
    if not v:return None
    try:return datetime.strptime(str(v)[:10],"%Y-%m-%d").date()
    except ValueError:return None

def freshness(as_of, analysis_date="2026-09-17", max_age_days=7):
    a=parse_date(as_of); b=parse_date(analysis_date)
    if not a or not b:return {"state":"UNKNOWN","age_days":None}
    age=(b-a).days
    return {"state":"FRESH" if 0<=age<=max_age_days else "STALE","age_days":age}

def safe_ratio(a,b):
    if missing(a) or missing(b) or b==0:return None
    return a/b
