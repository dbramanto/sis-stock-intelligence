CONTROL = ["Price","Volume","Volume MA20","Price MA20","Price MA50","RSI14","ADTV30"]
BATCHES = {
1: CONTROL + ["Previous Price","Open","High","Low","Previous Volume","Value","ADTV90","Price MA100","Price MA200","Previous RSI14","MACD","Previous MACD","ADX14","DI+","DI-","ATR14","ADR14","VWAP"],
2: CONTROL + ["Return 1W","Return 1M","Return 3M","Return 6M","Return 1Y","Return YTD","52W High","52W Low","RS Line 1M","RS Line 3M","RS Line 6M","RS Line 9M","RS Line 1Y","Beta 3Y","StdDev 3Y","StdDev 5Y","StdDev 10Y"],
3: CONTROL + ["Gross Margin TTM","Operating Margin TTM","Net Profit Margin TTM","Avg Net Profit Margin 5Y","Asset Turnover","ROA TTM","ROE TTM","ROCE TTM","ROIC TTM","Avg ROE 3Y","Piotroski Score","Receivables Turnover","Inventory Turnover","DSO Annual","DSO Quarter","CCC Annual","CCC Quarter"],
4: CONTROL + ["Revenue TTM","Revenue Quarterly YoY","Revenue Annual YoY","Revenue Growth 3Y","Gross Profit TTM","EBITDA TTM","Income From Operations TTM","Finance Cost TTM","Net Income TTM","Net Income Quarterly YoY","Net Income Annual YoY","EPS TTM","EPS Quarter YoY","EPS Annual YoY","EPS 3Y CAGR"],
5: CONTROL + ["Cash","Short Term Investments","Current Assets","Total Assets","Short Term Debt Quarter","Long Term Debt Quarter","Total Debt Quarter","Current Liabilities","Common Equity","Total Equity Quarter","Book Value Quarter","Tangible Book","Total Liabilities"],
6: CONTROL + ["Operating Cash Flow Quarter","Cash From Operations TTM","Cash From Financing TTM","Cash From Investing TTM","CAPEX TTM","Free Cash Flow TTM","Interest Coverage TTM"],
7: CONTROL + ["Market Cap","Enterprise Value","Current Shares Outstanding","Free Float","PE TTM","PBV","P/S TTM","EV/EBIT TTM","EV/EBITDA TTM","Earnings Yield TTM","Forward PE","PEG","Dividend Yield","Payout Ratio","Avg Dividend Yield 5Y"],
8: CONTROL + ["Foreign Flow","Net Foreign Buy / Sell","1 Month Net Foreign Flow","3 Month Net Foreign Flow","Bandar Value","Bandar Accum/Dist","Net Insider Buy / Sell (3M) (%)","Net Insider Buy / Sell (1Y) (%)"],
9: CONTROL + ["PE +1SD 5Y","PE Mean 5Y","PE -1SD 5Y","PBV +1SD 5Y","PBV Mean 5Y","PBV -1SD 5Y"],
10: CONTROL + ["NIM","CASA Ratio","Cost of Credit","NPL Gross","NPF Gross","NPL Coverage","NPF Coverage","CAR","LDR","Insurance Contract Liabilities","Land for Development","Investment Properties","Real Estate Assets","Plantations","Deferred Exploration and Development Costs","Exploration and Evaluation Assets","Mining Properties","Deferred Stripping Cost","Oil and Gas Assets"],
11: CONTROL + ["Expected Revenue (Growth: YoY)","Expected Revenue (Growth: 2Y CAGR)","Expected Op. Profit (Growth: YoY)","Expected Op. Profit (Growth: 2Y CAGR)","Expected Net Income (Growth: YoY)","Expected Net Income (Growth: 2Y CAGR)","Expected EPS (Growth: YoY)","Expected EPS (Growth: 2Y CAGR)","EPS (Forward)","PEG (Forward)"]
}
SEMANTIC_SPECIAL={"VWAP","RS Line 1M","RS Line 3M","RS Line 6M","RS Line 9M","RS Line 1Y","Revenue Growth 3Y","PEG"}
VENDOR_CHECK_ONLY={"Total Debt Quarter","Book Value Quarter","Free Cash Flow TTM","Earnings Yield TTM","PBV","P/S TTM","EV/EBITDA TTM"}
REQUIRED_BATCHES=set(range(1,12))
B9_FIELDS=BATCHES[9]
B10_SPECIAL_FIELDS=[c for c in BATCHES[10] if c not in CONTROL]
