"""
Options Chain v8
- Rows grouped by expiration date
- ATM row highlighted with arrow marker
- Columns aligned properly
- Real-time refresh from Schwab (3s)
- Auto-caps symbol input
- No load button
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QComboBox, QSpinBox, QSplitter, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont

GREEN="#3fb950"; RED="#f85149"; BLUE="#58a6ff"; YELLOW="#d29922"
DIM="#8b949e"; BG="#0d1117"; BG2="#161b22"; BG3="#21262d"
ATM_BG = "#1a2a1a"

CALL_COLS = ["Last","Chg","Vol","OI","IV%","Delta","Theta","Bid","Ask"]
PUT_COLS  = ["Bid","Ask","Delta","Theta","IV%","OI","Vol","Chg","Last"]
STRIKE_COL = ["Strike"]


class ChainThread(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api, sym, strike_count):
        super().__init__(); self.api=api; self.sym=sym; self.strike_count=strike_count
    def run(self):
        try: self.done.emit(self.api.get_options_chain(self.sym, strike_count=self.strike_count))
        except: self.done.emit({})


class ExpThread(QThread):
    done = pyqtSignal(list)
    def __init__(self, api, sym):
        super().__init__(); self.api=api; self.sym=sym
    def run(self):
        try: self.done.emit(self.api.get_option_expirations(self.sym))
        except: self.done.emit([])


class OptionsPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api=api; self._threads=[]; self._under_price=0.0
        self._chain_data={}; self._symbol=""
        self._build()
        self._timer = QTimer(); self._timer.timeout.connect(self._load_chain); self._timer.start(3000)

    def _build(self):
        vbox = QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG2};border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,0,16,0)
        title = QLabel("🔗  Options Chain")
        title.setStyleSheet(f"color:{BLUE};font-size:16px;font-weight:bold;")
        hh.addWidget(title); hh.addStretch()
        self._under_lbl = QLabel("")
        self._under_lbl.setStyleSheet(f"color:{YELLOW};font-size:13px;font-weight:bold;")
        hh.addWidget(self._under_lbl)
        vbox.addWidget(hdr)

        # Controls — no load button
        ctrl = QWidget(); ctrl.setFixedHeight(48)
        ctrl.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        cbox = QHBoxLayout(ctrl); cbox.setContentsMargins(12,0,12,0); cbox.setSpacing(10)

        cbox.addWidget(QLabel("Symbol:"))
        self._sym = QLineEdit(); self._sym.setFixedWidth(80)
        self._sym.setPlaceholderText("SPY")
        self._sym.textChanged.connect(self._auto_caps)
        self._sym.editingFinished.connect(self._on_sym_changed)
        cbox.addWidget(self._sym)

        cbox.addWidget(QLabel("Strikes:"))
        self._strikes = QSpinBox(); self._strikes.setRange(5,50); self._strikes.setValue(20)
        self._strikes.setFixedWidth(60)
        cbox.addWidget(self._strikes)

        cbox.addStretch()
        self._status = QLabel("Enter a symbol")
        self._status.setStyleSheet(f"color:{DIM};font-size:10px;")
        cbox.addWidget(self._status)
        vbox.addWidget(ctrl)

        # Chain table — single unified table with expiration headers
        self._table = QTableWidget(0, 19)  # 9 calls + 1 strike + 9 puts
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(False)
        self._table.setShowGrid(True)

        # Build headers: CALLS | STRIKE | PUTS
        headers = CALL_COLS + STRIKE_COL + PUT_COLS
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().setDragEnabled(True)

        # Set column widths
        call_w = [52,48,52,52,48,52,52,52,52]
        strike_w = [72]
        put_w  = [52,52,52,52,48,52,52,48,52]
        for i,w in enumerate(call_w+strike_w+put_w):
            self._table.setColumnWidth(i,w)
            self._table.horizontalHeader().setSectionResizeMode(i,QHeaderView.ResizeMode.Interactive)

        # Color headers
        hdr_font = QFont("Consolas",9,QFont.Weight.Bold)
        for i in range(9):
            item = QTableWidgetItem(headers[i])
            item.setForeground(QColor(GREEN)); item.setFont(hdr_font)
            self._table.setHorizontalHeaderItem(i,item)
        strike_item = QTableWidgetItem("STRIKE")
        strike_item.setForeground(QColor(YELLOW)); strike_item.setFont(hdr_font)
        self._table.setHorizontalHeaderItem(9, strike_item)
        for i in range(10,19):
            item = QTableWidgetItem(headers[i])
            item.setForeground(QColor(RED)); item.setFont(hdr_font)
            self._table.setHorizontalHeaderItem(i,item)

        self._table.setStyleSheet(f"""
            QTableWidget{{background-color:{BG};border:none;gridline-color:#21262d;color:#e6edf3;font-family:Consolas;font-size:11px;}}
            QTableWidget::item{{padding:2px 4px;}}
            QTableWidget::item:selected{{background-color:#1f6feb44;color:#ffffff;}}
            QHeaderView::section{{background-color:{BG3};padding:4px 6px;border:none;border-right:1px solid #30363d;border-bottom:1px solid #30363d;}}
        """)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        vbox.addWidget(self._table, stretch=1)

    def _auto_caps(self, text):
        upper = text.upper()
        if upper != text:
            cur = self._sym.cursorPosition()
            self._sym.blockSignals(True); self._sym.setText(upper); self._sym.blockSignals(False)
            self._sym.setCursorPosition(cur)

    def _on_sym_changed(self):
        sym = self._sym.text().strip().upper()
        if sym and sym != self._symbol:
            self._symbol = sym; self._table.setRowCount(0)
            self._load_chain()

    def _load_chain(self):
        sym = self._sym.text().strip().upper()
        if not sym: return
        self._symbol = sym
        t = ChainThread(self.api, sym, self._strikes.value())
        t.done.connect(self._populate); t.done.connect(lambda _: self._cleanup(t))
        self._threads.append(t); t.start()

    def _cleanup(self, t):
        try: self._threads.remove(t)
        except: pass

    def _populate(self, data: dict):
        if not data: return
        self._chain_data   = data
        self._under_price  = data.get("underlyingPrice", 0)
        sym = data.get("symbol","")
        self._under_lbl.setText(f"{sym}  ${self._under_price:.2f}")

        # Parse real Schwab format: date → strike → [contract]
        def parse_map(exp_map):
            """Returns {date_str: {strike_float: contract}}"""
            result = {}
            for outer, inner in exp_map.items():
                if not isinstance(inner, dict): continue
                is_date = ":" in outer or (len(outer)>4 and outer[4]=="-")
                if is_date:
                    date_key = outer.split(":")[0]
                    result.setdefault(date_key, {})
                    for strike_str, contracts in inner.items():
                        try:
                            strike = float(strike_str)
                            if contracts and isinstance(contracts, list):
                                result[date_key][strike] = contracts[0]
                        except: pass
                else:
                    # Mock format
                    try:
                        strike = float(outer)
                        for date_str, contracts in inner.items():
                            date_key = date_str.split(":")[0]
                            result.setdefault(date_key, {})
                            if contracts and isinstance(contracts, list):
                                result[date_key][strike] = contracts[0]
                    except: pass
            return result

        calls_by_date = parse_map(data.get("callExpDateMap", {}))
        puts_by_date  = parse_map(data.get("putExpDateMap",  {}))

        all_dates = sorted(set(list(calls_by_date.keys()) + list(puts_by_date.keys())))

        self._table.setRowCount(0)

        for date_str in all_dates:
            # ── Expiration header row ─────────────────────────────────────
            exp_row = self._table.rowCount()
            self._table.insertRow(exp_row)
            self._table.setRowHeight(exp_row, 26)
            exp_item = QTableWidgetItem(f"  📅  Expiration: {date_str}")
            exp_item.setBackground(QColor("#1c2333"))
            exp_item.setForeground(QColor(BLUE))
            exp_item.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            exp_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(exp_row, 0, exp_item)
            self._table.setSpan(exp_row, 0, 1, 19)

            calls = calls_by_date.get(date_str, {})
            puts  = puts_by_date.get(date_str, {})
            strikes = sorted(set(list(calls.keys()) + list(puts.keys())))

            for strike in strikes:
                c     = calls.get(strike, {})
                p     = puts.get(strike, {})
                is_atm = abs(strike - self._under_price) == min(
                    abs(s - self._under_price) for s in strikes)

                row = self._table.rowCount()
                self._table.insertRow(row)
                self._table.setRowHeight(row, 20)

                call_bg = QColor(ATM_BG) if is_atm else (QColor("#0a1a10") if strike <= self._under_price else QColor(BG))
                put_bg  = QColor(ATM_BG) if is_atm else (QColor("#1a0a0a") if strike >= self._under_price else QColor(BG))
                str_bg  = QColor("#1f2d0f") if is_atm else QColor(BG2)

                def cv(val, decimals=2):
                    if val is None or val == 0: return ""
                    return f"{val:.{decimals}f}"

                def cell(text, fg, bg, bold=False):
                    item = QTableWidgetItem(str(text))
                    item.setForeground(QColor(fg)); item.setBackground(bg)
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if bold: f=item.font(); f.setBold(True); item.setFont(f)
                    return item

                chg_c = GREEN if c.get("netChange",0)>=0 else RED
                chg_p = GREEN if p.get("netChange",0)>=0 else RED

                # Call columns (0-8)
                call_data = [
                    (cv(c.get("last")),         "#e6edf3"),
                    (cv(c.get("netChange")),     chg_c),
                    (f"{int(c.get('totalVolume',0)):,}" if c else "", "#e6edf3"),
                    (f"{int(c.get('openInterest',0)):,}" if c else "", DIM),
                    (f"{c.get('volatility',0):.1f}" if c else "", "#e6edf3"),
                    (cv(c.get("delta"),3),       "#e6edf3"),
                    (cv(c.get("theta"),4),       RED),
                    (cv(c.get("bid")),           GREEN),
                    (cv(c.get("ask")),           RED),
                ]
                for col,(text,fg) in enumerate(call_data):
                    self._table.setItem(row, col, cell(text, fg, call_bg))

                # Strike column (9) — ATM gets arrow marker
                atm_marker = " ◀" if is_atm else ""
                strike_item = cell(f"${strike:.2f}{atm_marker}", YELLOW if is_atm else "#e6edf3", str_bg, is_atm)
                self._table.setItem(row, 9, strike_item)

                # Put columns (10-18)
                put_data = [
                    (cv(p.get("bid")),           GREEN),
                    (cv(p.get("ask")),           RED),
                    (cv(p.get("delta"),3),       "#e6edf3"),
                    (cv(p.get("theta"),4),       RED),
                    (f"{p.get('volatility',0):.1f}" if p else "", "#e6edf3"),
                    (f"{int(p.get('openInterest',0)):,}" if p else "", DIM),
                    (f"{int(p.get('totalVolume',0)):,}" if p else "", "#e6edf3"),
                    (cv(p.get("netChange")),     chg_p),
                    (cv(p.get("last")),          "#e6edf3"),
                ]
                for i,(text,fg) in enumerate(put_data):
                    self._table.setItem(row, 10+i, cell(text, fg, put_bg))

        from datetime import datetime
        self._status.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}  |  {self._table.rowCount()} rows")

    def _on_double_click(self, row, col):
        # Get strike from col 9
        strike_item = self._table.item(row, 9)
        if not strike_item: return
        strike_text = strike_item.text().replace("$","").replace(" ◀","").strip()
        try: strike = float(strike_text)
        except: return

        is_call = col < 9
        from ui.order_dialog import OrderDialog
        # Find the option symbol
        sym = self._symbol
        exp_row = row - 1
        while exp_row >= 0:
            exp_item = self._table.item(exp_row, 0)
            if exp_item and "Expiration:" in exp_item.text():
                date = exp_item.text().split("Expiration:")[-1].strip()
                side = "CALL" if is_call else "PUT"
                option_sym = f"{sym}_{date}_{side}_{strike:.0f}"
                price_item = self._table.item(row, 8 if is_call else 10)
                price = float(price_item.text()) if price_item and price_item.text() else 0
                dlg = OrderDialog(self, api=self.api,
                    pre_fill={"symbol":option_sym,"instruction":"BUY_TO_OPEN",
                              "price":price,"asset_type":"OPTION"})
                dlg.exec()
                return
            exp_row -= 1

    def on_show(self):
        self._load_chain()
