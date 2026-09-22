from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from stage1.clipboard import parse_clipboard_text
from stage1.history import get_snapshot_batch, list_snapshots, load_snapshot
from stage1.pipeline import run_stage1, validate_batch
from stage2.runner import run_stage2


def _select_snapshot(snapshot_id: str | None):
    history = list_snapshots()
    if not history:
        raise SystemExit("BLOCKED: no input-history snapshots found")
    sid = snapshot_id or history[0]["snapshot_id"]
    return load_snapshot(sid)


def main() -> int:
    ap = argparse.ArgumentParser(description="SIS S1 -> S2 integration runner")
    ap.add_argument("--snapshot", help="input-history snapshot id; default = latest")
    ap.add_argument("--output", help="output JSON path")
    args = ap.parse_args()

    snap = _select_snapshot(args.snapshot)
    metadata = snap.get("metadata") or {}
    batches = {}
    for b in range(1, 11):
        raw = get_snapshot_batch(snap, b)
        df, parse_issues = parse_clipboard_text(raw)
        if parse_issues:
            print(f"STATUS BLOCKED\nB{b} PARSE ISSUES {parse_issues}")
            return 2
        schema_issues = validate_batch(df, b)
        if schema_issues:
            print(f"STATUS BLOCKED\nB{b} SCHEMA ISSUES {schema_issues}")
            return 3
        batches[b] = df

    # Dynamic N: prefer captured S0 count, otherwise derive it from B1.
    expected = metadata.get("expected_total")
    if expected is None:
        expected = int(batches[1]["Symbol"].astype(str).str.upper().nunique())
    filter_fp = str(metadata.get("filter_fingerprint") or "S0-UNSPECIFIED")

    s1 = run_stage1(batches, expected_total=int(expected), filter_fingerprint=filter_fp)
    if s1["status"] != "PASS":
        print("STATUS BLOCKED")
        print("S1_ISSUES", s1["issues"])
        return 4

    s2 = run_stage2(s1["canonical"])
    if s2.status != "PASS":
        print("STATUS BLOCKED")
        print("S2_ISSUES", s2.issues)
        return 5

    payload = {
        "contract": "S1_TO_S2_RESEARCH_PACKAGE_V1",
        "created_at": datetime.now().astimezone().isoformat(),
        "source_snapshot_id": snap["snapshot_id"],
        "filter_fingerprint": filter_fp,
        "candidate_count": len(s1["canonical"]),
        "stage1_status": s1["status"],
        "stage2_status": s2.status,
        "research_packages": s2.packages,
    }
    out = Path(args.output) if args.output else Path("data") / "stage2_output" / f'{snap["snapshot_id"]}_S2.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print("STATUS PASS")
    print("SNAPSHOT", snap["snapshot_id"])
    print("CANDIDATES", payload["candidate_count"])
    print("S2_PACKAGES", len(s2.packages))
    print("HORIZON_THESES", len(s2.packages) * 2)
    print("OUTPUT", out.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
