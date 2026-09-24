from io import StringIO
import csv
import re
import pandas as pd

HEADER_ALIASES = {
    "Volumesvg": "Volume",
    "Pricesvg": "Price",
    "Price Svg": "Price",
    "Volume Svg": "Volume",
    "Volume MA 20": "Volume MA20",
    "Price MA 20": "Price MA20",
    "Price MA 50": "Price MA50",
    "ADTV 30": "ADTV30",
    "ADTV 90": "ADTV90",
    "Price MA 100": "Price MA100",
    "Price MA 200": "Price MA200",
    "Open Price": "Open",
    "High Price": "High",
    "Low Price": "Low",
    "RSI (14)": "RSI14",
    "Previous RSI (14)": "Previous RSI14",
    "MACD (12,26)": "MACD",
    "Previous MACD (12,26)": "Previous MACD",
    "Average Directional Index 14": "ADX14",
    "Average Directional Index DI+ 14": "DI+",
    "Average Directional Index DI- 14": "DI-",
    "Average True Range 14": "ATR14",
    "Average Daily Range 14": "ADR14",
    "1 Week Price Returns": "Return 1W",
    "1 Month Price Returns": "Return 1M",
    "3 Month Price Returns": "Return 3M",
    "6 Month Price Returns": "Return 6M",
    "1 Year Price Returns": "Return 1Y",
    "Year to Date Price Returns": "Return YTD",
    "52 Week High": "52W High",
    "52 Week Low": "52W Low",
    "1 Month RS Line": "RS Line 1M",
    "3 Month RS Line": "RS Line 3M",
    "6 Month RS Line": "RS Line 6M",
    "9 Month RS Line": "RS Line 9M",
    "1 Year RS Line": "RS Line 1Y",
    "Beta (3 Year)": "Beta 3Y",
    "Standard Deviation (3 Year)": "StdDev 3Y",
    "Standard Deviation (5 Year)": "StdDev 5Y",
    "Standard Deviation (10 Year)": "StdDev 10Y",
    'Gross Profit Margin (TTM)(%)': 'Gross Margin TTM',
    'Operating Profit Margin (TTM)(%)': 'Operating Margin TTM',
    'Net Profit Margin (TTM)(%)': 'Net Profit Margin TTM',
    'Average (Net Profit Margin 5yr)': 'Avg Net Profit Margin 5Y',
    'Asset Turnover (TTM)': 'Asset Turnover',
    'Return on Assets (TTM)': 'ROA TTM',
    'Return on Equity (TTM)': 'ROE TTM',
    'Return on Capital Employed (TTM)': 'ROCE TTM',
    'Return On Invested Capital (TTM)': 'ROIC TTM',
    'Average (RoE 3 yr)': 'Avg ROE 3Y',
    'Piotroski F-Score': 'Piotroski Score',
    'Receivables Turnover (TTM)': 'Receivables Turnover',
    'Inventory Turnover (TTM)': 'Inventory Turnover',
    'Days Sales Outstanding (Annual)': 'DSO Annual',
    'Days Sales Outstanding (Quarter)': 'DSO Quarter',
    'Cash Conversion Cycle (Annual)': 'CCC Annual',
    'Cash Conversion Cycle (Quarter)': 'CCC Quarter',
    'Revenue (TTM)': 'Revenue TTM',
    'Revenue (Growth: Quarterly YoY)': 'Revenue Quarterly YoY',
    'Revenue (Growth: Annual YoY)': 'Revenue Annual YoY',
    'Revenue (Growth: 3 Year)': 'Revenue Growth 3Y',
    'Gross Profit (TTM)': 'Gross Profit TTM',
    'EBITDA (TTM)': 'EBITDA TTM',
    'Income From Operations (TTM)': 'Income From Operations TTM',
    'Finance Cost (TTM)': 'Finance Cost TTM',
    'Net Income (TTM)': 'Net Income TTM',
    'Net Income (Growth: Quarterly YoY)': 'Net Income Quarterly YoY',
    'Net Income (Growth: Annual YoY)': 'Net Income Annual YoY',
    'EPS (TTM)': 'EPS TTM',
    'EPS (Quarter YoY Growth)': 'EPS Quarter YoY',
    'EPS (Annual YoY Growth)': 'EPS Annual YoY',
    'EPS (3 Year CAGR)': 'EPS 3Y CAGR',
    'Cash and cash equivalents': 'Cash',
    'Short-term investments': 'Short Term Investments',
    'Total Current Assets': 'Current Assets',
    'Short-term Debt (Quarter)': 'Short Term Debt Quarter',
    'Long-term Debt (Quarter)': 'Long Term Debt Quarter',
    'Total Debt (Quarter)': 'Total Debt Quarter',
    'Total Current Liabilities': 'Current Liabilities',
    'Total Equity (Quarter)': 'Total Equity Quarter',
    'Book Value (Quarter)': 'Book Value Quarter',
    'Tangible Book Value': 'Tangible Book',
    'Operating Cash Flow (Quarter)': 'Operating Cash Flow Quarter',
    'Cash From Operations (TTM)': 'Cash From Operations TTM',
    'Cash From Financing (TTM)': 'Cash From Financing TTM',
    'Cash From Investing (TTM)': 'Cash From Investing TTM',
    'Capital expenditure (TTM)': 'CAPEX TTM',
    'Free cash flow (TTM)': 'Free Cash Flow TTM',
    'Interest Coverage (TTM)': 'Interest Coverage TTM',
    'Current Share Outstanding': 'Current Shares Outstanding',
    'Current PE Ratio (TTM)': 'PE TTM',
    'Current Price to Book Value': 'PBV',
    'Current Price to Sales (TTM)': 'P/S TTM',
    'EV to EBIT (TTM)': 'EV/EBIT TTM',
    'EV to EBITDA (TTM)': 'EV/EBITDA TTM',
    'Earnings Yield (TTM)': 'Earnings Yield TTM',
    'Forward PE Ratio': 'Forward PE',
    'PEG Ratio': 'PEG',
    'Average Dividend Yield (5 Year)': 'Avg Dividend Yield 5Y',
    '+1 PE Standard Deviation (5 Year)': 'PE +1SD 5Y',
    'Mean PE Standard Deviation (5 Year)': 'PE Mean 5Y',
    '-1 PE Standard Deviation (5 Year)': 'PE -1SD 5Y',
    '+1 PBV Standard Deviation (5 Year)': 'PBV +1SD 5Y',
    'Mean PBV Standard Deviation (5 Year)': 'PBV Mean 5Y',
    '-1 PBV Standard Deviation (5 Year)': 'PBV -1SD 5Y',
    'Net Interest Margin (NIM)': 'NIM',
    'NPL - Gross': 'NPL Gross',
    'NPF - Gross': 'NPF Gross',
    'NPL - Coverage': 'NPL Coverage',
    'NPF - Coverage': 'NPF Coverage',
    'Capital Adequacy Ratio': 'CAR',
    'Loan to Deposit Ratio': 'LDR',
    'Liabilitas kontrak asuransi': 'Insurance Contract Liabilities',
    'Land for development': 'Land for Development',
    'Investment properties': 'Investment Properties',
    'Deferred exploration and development costs': 'Deferred Exploration and Development Costs',
    'Exploration and evaluation Assets': 'Exploration and Evaluation Assets',
    'Deferred stripping cost': 'Deferred Stripping Cost',
    'Oil and gas assets': 'Oil and Gas Assets',
}

_MD_SYMBOL = re.compile(r"^\s*\[\*\*([^*\]]+)\*\*\]\([^)]*\)\s*$")
_MD_SEP = re.compile(r"^\s*:?-{3,}:?\s*$")


def _clean_md_cell(value):
    s = str(value).strip()
    # Remove common Markdown emphasis without touching ordinary metric text.
    if s.startswith("**") and s.endswith("**") and len(s) >= 4:
        s = s[2:-2].strip()
    return s


def _normalize_header(value):
    s = _clean_md_cell(value)
    return HEADER_ALIASES.get(s, s)


def _normalize_symbol(value):
    s = str(value).strip()
    m = _MD_SYMBOL.match(s)
    if m:
        return m.group(1).strip().upper()
    s = _clean_md_cell(s).upper()
    if re.fullmatch(r"[A-Z0-9.\-]+", s):
        return s
    return None


def _pipe_cells(line):
    s = line.strip()
    if not (s.startswith("|") and s.endswith("|")):
        return None
    return [x.strip() for x in s[1:-1].split("|")]


def _is_separator_row(cells):
    return bool(cells) and all(_MD_SEP.match(x or "") for x in cells)


def _finalize(header, data):
    header = [_normalize_header(x) for x in header]
    if not header or any(h == "" for h in header):
        return pd.DataFrame(), ["EMPTY_HEADER"]
    if len(set(header)) != len(header):
        return pd.DataFrame(), ["DUPLICATE_HEADER"]
    width = len(header)
    bad = [i + 1 for i, row in enumerate(data) if len(row) != width]
    if bad:
        return pd.DataFrame(), ["ROW_WIDTH_MISMATCH:" + ",".join(map(str, bad))]
    cleaned = []
    for idx, row in enumerate(data, start=1):
        row = [str(x).strip() for x in row]
        sym = _normalize_symbol(row[0])
        if not sym:
            return pd.DataFrame(), [f"INVALID_SYMBOL_ROW:{idx}"]
        row[0] = sym
        cleaned.append(row)
    if not cleaned:
        return pd.DataFrame(), ["NO_DATA_ROWS"]
    return pd.DataFrame(cleaned, columns=header), []


def _parse_tsv(raw):
    lines = [line for line in raw.split("\n") if line.strip()]
    if len(lines) < 2:
        return pd.DataFrame(), ["CLIPBOARD_REQUIRES_HEADER_AND_DATA"]
    reader = csv.reader(StringIO("\n".join(lines)), delimiter="\t")
    rows = list(reader)
    return _finalize(rows[0], rows[1:])


def _parse_stockbit_markdown(raw):
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    pipe_rows = []
    standalone = []
    for line in lines:
        cells = _pipe_cells(line)
        if cells is None:
            standalone.append(_clean_md_cell(line))
        elif not _is_separator_row(cells):
            pipe_rows.append(cells)

    if len(pipe_rows) < 2:
        return pd.DataFrame(), ["MARKDOWN_REQUIRES_HEADER_AND_DATA"]

    first = pipe_rows[0]
    # Data rows are identifiable by a Markdown-linked or plain ticker in col 1.
    data = pipe_rows[1:]
    if not data:
        return pd.DataFrame(), ["NO_DATA_ROWS"]
    widths = {len(r) for r in data}
    if len(widths) != 1:
        return pd.DataFrame(), ["INCONSISTENT_DATA_ROW_WIDTH"]
    width = next(iter(widths))

    # Stockbit copy can split the visible header: first 8 cells remain in the
    # Markdown table, while the remaining headers are emitted as standalone
    # lines before the first data row. Reconstruct only when width proves it.
    if len(first) < width:
        needed = width - len(first)
        if len(standalone) != needed:
            return pd.DataFrame(), [f"HEADER_RECONSTRUCTION_MISMATCH:EXPECTED_{needed}_GOT_{len(standalone)}"]
        header = first + standalone
    elif len(first) == width:
        if standalone:
            return pd.DataFrame(), ["UNEXPECTED_STANDALONE_HEADER_LINES"]
        header = first
    else:
        return pd.DataFrame(), ["HEADER_WIDER_THAN_DATA"]

    return _finalize(header, data)



# Legacy Stockbit vertical captures can omit the visible Volume header while
# retaining its value. Placement differs by B-layout. This map is a verified
# source-layout contract, not a numeric guess. It is used only when batch_id is
# supplied, Volume is absent, and every row is exactly one value wider.
_LEGACY_VOLUME_POSITION = {
    1: "END", 2: "BEFORE_VOLUME_MA20", 3: "END", 4: "END",
    5: "BEFORE_VOLUME_MA20", 6: "BEFORE_VOLUME_MA20",
    7: "BEFORE_VOLUME_MA20", 8: "END", 9: "BEFORE_VOLUME_MA20",
}

def _repair_legacy_vertical_header(header, value_width, batch_id):
    if batch_id not in _LEGACY_VOLUME_POSITION:
        return header, None
    normalized = [_normalize_header(x) for x in header]
    if "Volume" in normalized or value_width != len(header):
        return header, None
    if "Volume MA20" not in normalized:
        return header, "LEGACY_VOLUME_ANCHOR_MISSING"
    mode = _LEGACY_VOLUME_POSITION[batch_id]
    fixed = list(header)
    if mode == "END":
        fixed.append("Volume")
    else:
        idx = normalized.index("Volume MA20")
        fixed.insert(idx, "Volume")
    return fixed, "LEGACY_MISSING_VOLUME_HEADER_REPAIRED"

def _parse_stockbit_vertical(raw, batch_id=None):
    """Verified Stockbit shape: vertical headers, then ticker/value-row pairs."""
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if not lines or lines[0] != "Symbol":
        return pd.DataFrame(), ["VERTICAL_MISSING_SYMBOL_HEADER"]
    first = None
    for i in range(1, len(lines) - 1):
        if _normalize_symbol(lines[i]) and "\t" in lines[i + 1]:
            first = i
            break
    if first is None:
        return pd.DataFrame(), ["VERTICAL_NO_SYMBOL_VALUE_PAIR"]
    header = lines[:first]
    # Determine row width before validating the header. Legacy B1-B8 captures
    # may have one omitted Volume header; repair only from the verified batch
    # layout contract.
    first_values = [x.strip() for x in lines[first + 1].split("\t")]
    header, repair_note = _repair_legacy_vertical_header(header, len(first_values), batch_id)
    if repair_note == "LEGACY_VOLUME_ANCHOR_MISSING":
        return pd.DataFrame(), [repair_note]
    expected = len(header) - 1
    data = []
    pos = first
    while pos < len(lines):
        symbol = _normalize_symbol(lines[pos])
        if not symbol:
            return pd.DataFrame(), [f"INVALID_SYMBOL_ROW:{pos + 1}"]
        if pos + 1 >= len(lines):
            return pd.DataFrame(), [f"MISSING_VALUE_ROW:{symbol}"]
        values = [x.strip() for x in lines[pos + 1].split("\t")]
        if len(values) != expected:
            return pd.DataFrame(), [f"ROW_WIDTH_MISMATCH:{symbol}:EXPECTED_{expected}_GOT_{len(values)}"]
        data.append([symbol] + values)
        pos += 2
    return _finalize(header, data)


def parse_clipboard_text(text: str, batch_id=None):
    """Parse Stockbit browser clipboard data, fail-closed.

    Supported inputs:
      * TSV table copy
      * Stockbit Markdown/pipe copy, including split headers

    Returns (DataFrame, issues). Header aliases are normalized at the input
    boundary; malformed/ambiguous shapes are never guessed.
    """
    if text is None or not str(text).strip():
        return pd.DataFrame(), ["EMPTY_CLIPBOARD"]
    raw = str(text).replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    lines = [line for line in raw.split("\n") if line.strip()]
    if len(lines) < 2:
        return pd.DataFrame(), ["CLIPBOARD_REQUIRES_HEADER_AND_DATA"]
    if "\t" in lines[0]:
        return _parse_tsv(raw)
    if lines[0].strip() == "Symbol":
        return _parse_stockbit_vertical(raw, batch_id=batch_id)
    if any(line.strip().startswith("|") and line.strip().endswith("|") for line in lines):
        return _parse_stockbit_markdown(raw)
    return pd.DataFrame(), ["UNSUPPORTED_CLIPBOARD_DELIMITER_EXPECTED_TAB"]
