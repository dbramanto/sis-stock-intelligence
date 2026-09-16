import numpy as np
from sis_core import *
assert num("(2.5 B)")==-2.5e9 and num("31.03%")==31.03 and np.isnan(num("-"))
# Regression: markdown
m=norm(parse("| Symbol | Volume | Volume MA 20 | Price |\n|---|---:|---:|---:|\n| [**ANTM**](https://stockbit.com/symbol/ANTM) | 136,346,800 | 118,292,235 | 3,270 |"))
assert m.iloc[0].Symbol=="ANTM" and m.iloc[0].Volume==136346800 and eng(m).iloc[0].RVOL>1
# Laptop clipboard Batch 1: one value per line
b1='''Symbol\nVolumesvg\nVolume MA 20\nPrice MA 20\nPrice MA 50\nRSI (14)\nADTV 30\nPrice\nPrice MA 200\nSLIS\n684,854,000.00\n92,666,835.00\n91.00\n77.00\n59.22%\n16,325,007,803.00\n93.00\n82.00\nANTM\n142,697,700.00\n120,913,965.00\n3,154.00\n3,057.00\n56.15%\n365,732,495,500.00\n3,220.00\n3,388.00'''
d1=norm(parse(b1));assert list(d1.Symbol)==['SLIS','ANTM'] and d1.loc[0,'Volume']==684854000 and d1.loc[1,'Price']==3220
# Laptop clipboard Batch 2/3 style: ticker line + tab-separated values
b2='''Symbol\nVolume\nVolume MA 20\nPrice MA 20\nPrice MA 50\nRSI (14)\nADTV 30\nPrice\nNet Profit Margin (TTM)(%)\nReturn On Invested Capital (TTM)\nPiotroski F-Score\nEarnings Yield (TTM)\nDebt to Equity Ratio (Quarter)\nEPS (TTM YoY Growth)\nSLIS\n684,854,000.00\t92,666,835.00\t91.00\t77.00\t59.22%\t16,325,007,803.00\t93.00\t-10.06%\t-6.72%\t3\t-8.89%\t0.09\t-88.38%'''
d2=norm(parse(b2));assert d2.iloc[0].Symbol=='SLIS' and d2.iloc[0]['Net Profit Margin (TTM)(%)']==-10.06
b3='''Symbol\nVolume\nVolume MA 20\nPrice MA 20\nPrice MA 50\nRSI (14)\nADTV 30\nPrice\nOperating Cash Flow (Quarter)\nFree cash flow (TTM)\nFree cash flow (Quarter)\nNet Income (Quarter)\nNet Income (Annual)\nNet Income (TTM)\nNet Income (YTD)\nBRMS\n416,318,400.00\t364,829,925.00\t715.00\t631.00\t59.97%\t258,187,968,217.00\t730.00\t(921.81 B)\t(2,245.20 B)\t(1,614.06 B)\t(81.16 B)\t824.04 B\t672.92 B\t222.38 B'''
d3=norm(parse(b3));assert d3.iloc[0]['Operating Cash Flow (Quarter)']==-921.81e9 and d3.iloc[0]['Net Income (TTM)']==672.92e9
raw,conf=merge([d1,d2,d3]);assert len(raw)>=2
print('PASS RC1.1')
