import numpy as np, pandas as pd
from sis_core import num,norm,parse,merge,eng,duplicate_symbols,dedupe_for_merge,batch_coverage
# numeric adversarial
assert num('(921.81 B)') == -921.81e9
assert num('628.99 M') == 628.99e6
assert np.isnan(num('-'))
assert num('1,210.53%') == 1210.53
# duplicate must be visible, never silently erased
d=norm(pd.DataFrame({'Symbol':['ANTM','ANTM'],'Price':['3220','3220']}))
assert duplicate_symbols(d)==['ANTM'] and len(d)==2
# partial universe must survive outer merge and receive PARTIAL confidence
b1=norm(pd.DataFrame({'Symbol':['ANTM','BRMS'],'Price':['3220','730'],'Volume':['10','20'],'Volume MA 20':['5','10']}))
b2=norm(pd.DataFrame({'Symbol':['ANTM','BRMS'],'Price':['3220','730'],'Piotroski F-Score':['7','5']}))
b3=norm(pd.DataFrame({'Symbol':['ANTM'],'Price':['3220'],'Net Income (TTM)':['8.90 B']}))
cov=batch_coverage([b1,b2,b3]); assert cov.loc[cov.Symbol=='BRMS','Data Confidence'].iloc[0]=='PARTIAL'
raw,conf=merge([b1,b2,b3]); assert set(raw.Symbol)=={'ANTM','BRMS'}
# material price conflict must be explicit and BLOCKED
b2c=b2.copy();b2c.loc[b2c.Symbol=='ANTM','Price']=3300
raw,conf=merge([b1,b2c,b3]); pc=[x for x in conf if x['Symbol']=='ANTM' and x['Field']=='Price']
assert pc and pc[0]['Severity']=='BLOCKED' and pc[0]['Value A']==3220 and pc[0]['Value B']==3300
print('PASS RC1.1.1 HARDENING')
