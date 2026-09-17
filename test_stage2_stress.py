from pathlib import Path
from copy import deepcopy
import tracemalloc

from sis_stage2 import parse_fixture, integrity_gate, evaluate_symbol, evaluate_universe

FIXTURE = Path(__file__).with_name("stage2_fixture_v1.txt")
text = FIXTURE.read_text(encoding="utf-8")
base = parse_fixture(text)

checks = []

def check(name, condition, detail=""):
    if not condition:
        raise AssertionError(f"{name} FAILED: {detail}")
    checks.append(name)
    print(f"PASS — {name}" + (f" — {detail}" if detail else ""))

# 1. Baseline normal: fixture itself must still work.
u = evaluate_universe(text)
check("BASELINE 24/24", u["integrity"]["state"] == "PASS" and len(u["results"]) == 24,
      f"{len(u['results'])} symbols; gate={u['integrity']['state']}")

# 2. Missing one symbol from one batch must not be silently treated as complete.
b = deepcopy(base)
b[3].pop("ITMG")
g = integrity_gate(b)
r = evaluate_symbol("ITMG", b)
check("PARTIAL BATCH PROTECTION",
      g["state"] == "REVIEW" and r["stage2_state"] == "NOT_EVALUATED",
      f"gate={g['state']}; ITMG={r['stage2_state']}")

# 3. Price conflict between batches must block.
b = deepcopy(base)
b[2]["ANTM"]["price"] = b[2]["ANTM"]["price"] + 10
g = integrity_gate(b)
check("PRICE CONFLICT BLOCKING", g["state"] == "BLOCKED", f"gate={g['state']}")

# 4. Missing fundamental metrics must reduce confidence, not be interpreted as good data.
b = deepcopy(base)
for key in ("npm_ttm", "roic_ttm", "piotroski", "earnings_yield_ttm", "de_quarter", "eps_yoy"):
    if key in b[2]["ANTM"]:
        b[2]["ANTM"][key] = None
r = evaluate_symbol("ANTM", b)
check("MISSING FUNDAMENTAL DATA",
      r["confidence"]["fundamental"] < 0.5,
      f"fundamental confidence={r['confidence']['fundamental']}")

# 5. Very strong technicals must not override severely damaged business/cash quality.
b = deepcopy(base)
sym = "ANTM"
for batch_no in (1, 2, 3):
    b[batch_no][sym]["price"] = 5000.0
b[1][sym].update({
    "price_ma20": 3000.0, "price_ma50": 2500.0, "price_ma200": 2000.0,
    "rsi14": 68.0, "adx14": 45.0, "di_plus14": 40.0, "di_minus14": 10.0,
    "volume": 500_000_000.0, "volume_ma20": 100_000_000.0
})
b[2][sym].update({"npm_ttm": -30.0, "roic_ttm": -20.0, "eps_yoy": -80.0})
b[3][sym].update({
    "ni_ttm": -1_000_000_000_000.0, "ni_q": -300_000_000_000.0,
    "fcf_ttm": -800_000_000_000.0, "fcf_q": -250_000_000_000.0,
    "ocf_q": -200_000_000_000.0
})
r = evaluate_symbol(sym, b)
check("STRONG TECHNICAL / BAD BUSINESS PROTECTION",
      r["eligibility"] == "REVIEW"
      and r["horizons"]["swing"]["effective_priority"] == "REVIEW",
      f"eligibility={r['eligibility']}; swing={r['horizons']['swing']['effective_priority']}")

# 6. Strong business with weak technicals should not be forced into the same horizon result.
b = deepcopy(base)
sym = "SLIS"
for batch_no in (1, 2, 3):
    b[batch_no][sym]["price"] = 60.0
b[1][sym].update({
    "price_ma20": 80.0, "price_ma50": 90.0, "price_ma200": 100.0,
    "rsi14": 30.0, "adx14": 15.0, "di_plus14": 10.0, "di_minus14": 30.0,
    "volume": 20_000_000.0, "volume_ma20": 100_000_000.0
})
b[2][sym].update({"npm_ttm": 20.0, "roic_ttm": 20.0, "eps_yoy": 30.0})
b[3][sym].update({
    "ni_ttm": 500_000_000_000.0, "ni_q": 150_000_000_000.0,
    "fcf_ttm": 400_000_000_000.0, "fcf_q": 100_000_000_000.0,
    "ocf_q": 180_000_000_000.0
})
r = evaluate_symbol(sym, b)
check("HORIZON INDEPENDENCE",
      r["horizons"]["swing"]["raw_score"] < r["horizons"]["long_term"]["raw_score"],
      f"swing={r['horizons']['swing']['raw_score']}; long={r['horizons']['long_term']['raw_score']}")

# 7. REVIEW protection across normal universe: REVIEW cannot become normal priority.
bad = []
for r in u["results"]:
    if r.get("eligibility") == "REVIEW":
        if (r["horizons"]["swing"]["effective_priority"] != "REVIEW"
                or r["horizons"]["long_term"]["effective_priority"] != "REVIEW"):
            bad.append(r["symbol"])
check("REVIEW STATUS PROTECTION", not bad, f"contradictions={bad}")

# 8. Repeat processing to expose accidental state/resource accumulation.
tracemalloc.start()
last = None
for _ in range(500):
    last = evaluate_universe(text)
current, peak = tracemalloc.get_traced_memory()
tracemalloc.stop()
check("500X REPEAT STABILITY",
      last["integrity"]["state"] == "PASS" and len(last["results"]) == 24
      and peak < 25 * 1024 * 1024,
      f"peak_memory={peak/1024/1024:.2f} MB")

print()
print(f"PASS STAGE 2 ADVERSARIAL/STRESS TEST — {len(checks)}/{len(checks)} checks")
