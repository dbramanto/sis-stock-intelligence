from __future__ import annotations
import argparse, json
from stage3_production_runner import run_snapshot_stage3

DEFAULT_SNAPSHOT='20260921_160836_726178_3e39f1febf1b'
DEFAULT_ASOF='2026-09-21'

def main():
    ap=argparse.ArgumentParser(description='SIS Stage3 real-data target-machine gate')
    ap.add_argument('--snapshot', default=DEFAULT_SNAPSHOT)
    ap.add_argument('--as-of', default=DEFAULT_ASOF)
    args=ap.parse_args()
    r=run_snapshot_stage3(args.snapshot, analysis_as_of=args.as_of, top_n=3)
    print('SIS STAGE3 REAL-DATA GATE')
    print('snapshot:', args.snapshot)
    print('status:', r.get('status'))
    print('counts:', json.dumps(r.get('counts',{}), sort_keys=True))
    print('p10_state:', r.get('p10_state'))
    print('p10_diagnostics:', json.dumps(r.get('p10_diagnostics',[]), ensure_ascii=False))
    s3=r.get('stage3') or {}
    ranking=s3.get('ranking') or {}
    sw=(ranking.get('swing') or {}).get('top') or []
    lt=(ranking.get('long_term') or {}).get('top') or []
    print('swing_top:', json.dumps(sw, ensure_ascii=False, default=str))
    print('long_term_top:', json.dumps(lt, ensure_ascii=False, default=str))
    if r.get('status') != 'COMPLETE':
        raise SystemExit(2)

if __name__=='__main__':
    main()
