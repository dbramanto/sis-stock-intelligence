from pathlib import Path
import re,sys
sys.path.insert(0,str(Path(__file__).parent))
from stage1.clipboard import parse_clipboard_text
from stage1.pipeline import run_stage1,validate_batch
s=Path('/mnt/data/full batch(1).txt').read_text(encoding='utf-8')
pat=re.compile(r'(?im)^(?:batch|bach)\s*(\d+)\s*:\s*$')
ms=list(pat.finditer(s)); batches={}
for idx,m in enumerate(ms):
    b=int(m.group(1)); start=m.end(); end=ms[idx+1].start() if idx+1<len(ms) else len(s); raw=s[start:end].strip()
    df,issues=parse_clipboard_text(raw)
    print('PARSE',b,df.shape,issues[:3])
    if issues: raise SystemExit(2)
    vi=validate_batch(df,b); print('SCHEMA',b,vi)
    if vi: raise SystemExit(3)
    batches[b]=df
r=run_stage1(batches,expected_total=32,filter_fingerprint='S0-6FILTER-REAL-20260920')
print('STATUS',r['status']); print('ISSUES',r['issues']); print('CANONICAL',r['canonical'].shape); print('REC',r['reconciliation'].shape)
print('CONTROL_CONFLICTS',int(r['reconciliation']['conflict'].sum()))
print('B10_AVAILABLE_COUNTS',r['canonical']['B10 Specialized Available Count'].value_counts().sort_index().to_dict())
print('B9_PE_VALIDITY',r['canonical']['B9 PE Semantic Validity'].value_counts().to_dict())
print('B9_PBV_VALIDITY',r['canonical']['B9 PBV Semantic Validity'].value_counts().to_dict())
print(r['batch_summary'].to_string(index=False))
if r['status']!='PASS': raise SystemExit(4)
