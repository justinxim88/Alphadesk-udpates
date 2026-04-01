"""
Table utilities v19
- Auto-fit columns to content
- Make all columns resizable
- Readable option symbol formatting
"""
from PyQt6.QtWidgets import QTableWidget, QHeaderView


def format_option_symbol(sym: str) -> str:
    """
    Convert OCC option symbol to readable format.
    Handles both padded (SPY   260330C00656000) and
    unpadded (SPY260330C00656000) formats.
    Output: SPY 656C 03/30/2026
    """
    import re
    try:
        sym = sym.strip()
        if len(sym) < 12:
            return sym  # too short to be an option

        # Try to parse using regex — works for both padded and unpadded
        # Pattern: letters (ticker) + 6 digits (YYMMDD) + C/P + 8 digits (strike)
        m = re.match(r'^([A-Z]+)\s*(\d{6})([CP])(\d+)$', sym.upper())
        if not m:
            return sym  # not a recognized option format

        ticker    = m.group(1).strip()
        date_part = m.group(2)   # YYMMDD
        cp        = m.group(3)   # C or P
        strike_raw = m.group(4)  # variable length digits

        yy = date_part[:2]
        mm = date_part[2:4]
        dd = date_part[4:6]
        year = f"20{yy}"

        # Pad strike_raw to 8 digits if needed
        strike_raw = strike_raw.zfill(8)
        strike = int(strike_raw) / 1000
        strike_str = str(int(strike)) if strike == int(strike) else f"{strike:.2f}"

        return f"{ticker} {strike_str}{cp} {mm}/{dd}/{year}"
    except:
        return sym


def setup_table(table: QTableWidget, stretch_last: bool = False):
    """
    Configure a table for auto-fit + resizable columns.
    Call after populating with data.
    """
    header = table.horizontalHeader()
    col_count = table.columnCount()

    # First fit to content
    table.resizeColumnsToContents()

    # Then make all columns interactive (resizable by user)
    for i in range(col_count):
        if stretch_last and i == col_count - 1:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

    # Hide row numbers
    table.verticalHeader().setVisible(False)