
from __future__ import annotations
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional
import re

class EventState(str, Enum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    REJECTED = "REJECTED"

class EventDirection(str, Enum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    NEUTRAL = "NEUTRAL"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class DisclosureEvidence:
    symbol: str
    title: str
    text: str
    source_id: str
    source_reference: str
    published_at: str
    observed_at: str

@dataclass(frozen=True)
class EventExtraction:
    symbol: str
    state: EventState
    event_type: str
    direction: EventDirection
    materiality: str
    status: str
    event_date: Optional[str]
    amount: Optional[float]
    currency: Optional[str]
    confidence: float
    matched_rules: tuple[str, ...]
    source_id: str
    source_reference: str
    published_at: str
    reason: str

    def to_dict(self):
        d=asdict(self)
        d["state"]=self.state.value
        d["direction"]=self.direction.value
        return d

_RULES = (
    ("DIVIDEND", (r"\bdividen\b", r"\bdividend\b"), EventDirection.NEUTRAL),
    ("RIGHTS_ISSUE", (r"\bright[s ]*issue\b", r"\bhmetd\b"), EventDirection.NEUTRAL),
    ("BUYBACK", (r"\bbuyback\b", r"\bpembelian kembali saham\b"), EventDirection.NEUTRAL),
    ("STOCK_SPLIT", (r"\bstock split\b", r"\bpemecahan saham\b"), EventDirection.NEUTRAL),
    ("NEW_CONTRACT", (r"\bkontrak baru\b", r"\bnew contract\b", r"\bditunjuk sebagai penyedia\b"), EventDirection.POSITIVE),
    ("M_AND_A", (r"\bakuisisi\b", r"\bmerger\b", r"\bacquisition\b"), EventDirection.NEUTRAL),
    ("MANAGEMENT_CHANGE", (r"\bperubahan (?:direksi|dewan komisaris|manajemen)\b", r"\bmanagement change\b"), EventDirection.NEUTRAL),
    ("FINANCIAL_RESULT", (r"\blaporan keuangan\b", r"\bfinancial results?\b"), EventDirection.NEUTRAL),
    ("SUSPENSION", (r"\bsuspensi\b", r"\bsuspension\b"), EventDirection.NEGATIVE),
    ("LITIGATION", (r"\bgugatan\b", r"\blitigasi\b", r"\blawsuit\b"), EventDirection.NEGATIVE),
)

_AMOUNT = re.compile(r"\b(?:rp|idr)\s*([0-9][0-9\.,]*)\s*(triliun|miliar|juta)?\b", re.I)
_DATE = re.compile(r"\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b")

def _amount(text: str):
    m=_AMOUNT.search(text)
    if not m: return None, None
    raw=m.group(1).replace(".","").replace(",",".")
    try: v=float(raw)
    except ValueError: return None, None
    scale={"triliun":1e12,"miliar":1e9,"juta":1e6}.get((m.group(2) or "").lower(),1.0)
    return v*scale, "IDR"

def _date(text: str):
    m=_DATE.search(text)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None

def extract_event(e: DisclosureEvidence) -> EventExtraction:
    symbol=e.symbol.strip().upper()
    if not symbol or not e.source_id or not e.source_reference or not e.published_at:
        return EventExtraction(symbol,EventState.REJECTED,"UNKNOWN",EventDirection.UNKNOWN,
                               "UNKNOWN","UNKNOWN",None,None,None,0.0,(),e.source_id,
                               e.source_reference,e.published_at,"incomplete provenance")
    blob=f"{e.title}\n{e.text}".lower()
    hits=[]
    for typ, patterns, direction in _RULES:
        if any(re.search(p, blob, re.I) for p in patterns):
            hits.append((typ,direction))
    # Multiple materially different event types are not guessed.
    unique={x[0] for x in hits}
    if len(unique)!=1:
        return EventExtraction(symbol,EventState.UNRESOLVED,"UNKNOWN",EventDirection.UNKNOWN,
                               "UNKNOWN","UNKNOWN",_date(blob),*_amount(blob),0.0,
                               tuple(sorted(unique)),e.source_id,e.source_reference,e.published_at,
                               "no unique deterministic event classification")
    typ, direction=hits[0]
    amount,currency=_amount(blob)
    event_date=_date(blob)
    # Deterministic engine does not invent probability, priced-in, or unsupported materiality.
    materiality="UNKNOWN"
    status="DISCLOSED"
    confidence=1.0
    return EventExtraction(symbol,EventState.RESOLVED,typ,direction,materiality,status,
                           event_date,amount,currency,confidence,(typ,),e.source_id,
                           e.source_reference,e.published_at,"deterministic rule match")

def extract_many(items):
    return tuple(extract_event(x) for x in items)
