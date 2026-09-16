import numpy as np,pandas as pd
from sis_core import *
assert num("(2.5 B)")==-2.5e9 and num("31.03%")==31.03 and np.isnan(num("-"))
d=norm(parse("| Symbol | Volume | Volume MA 20 | Price |\\n|---|---:|---:|---:|\\n| [**ANTM**](https://stockbit.com/symbol/ANTM) | 136,346,800 | 118,292,235 | 3,270 |"))
assert d.iloc[0].Symbol=="ANTM" and d.iloc[0].Volume==136346800
e=eng(d);assert e.iloc[0].RVOL>1
print("PASS")
