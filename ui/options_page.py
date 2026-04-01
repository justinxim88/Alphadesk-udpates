"""
Options Chain v10
- All expirations collapsed by default
- Sell to Open + Buy to Open on click
- Bid/Ask visible on both call and put sides
- Expand/collapse per expiration
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSpinBox, QMenu
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QFont

GREEN="#3fb950"; RED="#f85149"; BLUE="#58a6ff"; YELLOW="#d29922"
DIM="#8b949e"; BG="#0d1117"; BG2="#161b22"; BG3="#21262d"

# Columns: 9 calls + 1 strike + 9 puts
CALL_COLS = ["Last","Chg","Vol","OI","IV%","Delta","Theta","Bid","Ask"]
PUT_COLS  = ["Bid","Ask","Delta","Theta","IV%","OI","Vol","Chg","Last"]


class ChainThread(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api, sym, strike_count):
        super().__init__(); self.api=api; self.sym=sym; self.strike_count=strike_count
    def run(self):
        try: self.done.emit(self.api.get_options_chain(self.sym, strike_count=self.strike_count))
        except Exception as e:
            print(f"[Options] chain error: {e}")
            self.done.emit({})


class OptionsPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self._threads = []
        self._under_price = 0.0
        self._symbol = ""
        self._collapsed = set()
        self._parsed_calls = {}
        self._parsed_puts  = {}
        self._all_dates    = []
        self._build()
        self._timer = QTimer()
        self._timer.timeout.connect(self._load_chain)
        self._timer.start(3000)

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

        # Controls
        ctrl = QWidget(); ctrl.setFixedHeight(48)
        ctrl.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        cbox = QHBoxLayout(ctrl); cbox.setContentsMargins(12,0,12,0); cbox.setSpacing(10)
        cbox.addWidget(QLabel("Symbol:"))
        self._sym = QLineEdit(); self._sym.setFixedWidth(80); self._sym.setPlaceholderText("SPY")
        self._sym.textChanged.connect(self._auto_caps)
        self._sym.returnPressed.connect(self._on_sym_changed)
        self._sym.editingFinished.connect(self._on_sym_changed)
        cbox.addWidget(self._sym)
        cbox.addWidget(QLabel("Strikes:"))
        self._strikes = QSpinBox(); self._strikes.setRange(5,50); self._strikes.setValue(20)
        self._strikes.setFixedWidth(60)
        cbox.addWidget(self._strikes)

        btn_style = f"QPushButton{{background:{BG};color:{BLUE};border:1px solid #30363d;border-radius:3px;font-size:11px;padding:0 8px;height:28px;}} QPushButton:hover{{background:#1f6feb;color:#fff;}}"
        exp_btn = QPushButton("⊞ Expand All"); exp_btn.setFixedHeight(28)
        exp_btn.setStyleSheet(btn_style); exp_btn.clicked.connect(self._expand_all)
        cbox.addWidget(exp_btn)
        col_btn = QPushButton("⊟ Collapse All"); col_btn.setFixedHeight(28)
        col_btn.setStyleSheet(btn_style); col_btn.clicked.connect(self._collapse_all)
        cbox.addWidget(col_btn)
        cbox.addStretch()
        self._status = QLabel("Enter a symbol")
        self._status.setStyleSheet(f"color:{DIM};font-size:10px;")
        cbox.addWidget(self._status)
        vbox.addWidget(ctrl)

        # Table — 19 columns
        self._table = QTableWidget(0, 19)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setShowGrid(True)
        self._table.setAlternatingRowColors(False)

        headers = CALL_COLS + ["STRIKE"] + PUT_COLS
        self._table.setHorizontalHeaderLabels(headers)
        self._table.horizontalHeader().setSectionsMovable(True)

        bold9 = QFont("Consolas", 9, QFont.Weight.Bold)
        for i in range(9):
            it = QTableWidgetItem(headers[i])
            it.setForeground(QColor(GREEN)); it.setFont(bold9)
            self._table.setHorizontalHeaderItem(i, it)
        si = QTableWidgetItem("STRIKE")
        si.setForeground(QColor(YELLOW)); si.setFont(bold9)
        self._table.setHorizontalHeaderItem(9, si)
        for i in range(10,19):
            it = QTableWidgetItem(headers[i])
            it.setForeground(QColor(RED)); it.setFont(bold9)
            self._table.setHorizontalHeaderItem(i, it)

        for i,w in enumerate([52,48,52,52,48,52,52,52,52,72,52,52,52,52,48,52,52,48,52]):
            self._table.setColumnWidth(i, w)
            self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)

        self._table.setStyleSheet(f"""
            QTableWidget{{background:{BG};border:none;gridline-color:#21262d;
                         color:#e6edf3;font-family:Consolas;font-size:11px;}}
            QTableWidget::item{{padding:2px 4px;}}
            QTableWidget::item:selected{{background:#1f6feb44;color:#fff;}}
            QHeaderView::section{{background:{BG3};padding:4px 6px;border:none;
                                  border-right:1px solid #30363d;border-bottom:1px solid #30363d;}}
        """)
        self._table.cellClicked.connect(self._on_cell_click)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
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
            self._symbol = sym
            self._collapsed.clear()
            self._table.setRowCount(0)
            self._load_chain()

    def _load_chain(self):
        sym = self._sym.text().strip().upper()
        if not sym: return
        self._symbol = sym
        t = ChainThread(self.api, sym, self._strikes.value())
        t.done.connect(self._on_data)
        t.done.connect(lambda _: self._cleanup(t))
        self._threads.append(t); t.start()

    def _cleanup(self, t):
        try: self._threads.remove(t)
        except: pass

    def _on_data(self, data: dict):
        if not data: return
        self._under_price = data.get("underlyingPrice", 0)
        sym = data.get("symbol","")
        self._under_lbl.setText(f"{sym}  ${self._under_price:.2f}")

        def parse_map(exp_map):
            result = {}
            for outer, inner in exp_map.items():
                if not isinstance(inner, dict): continue
                is_date = ":" in outer or (len(outer)>4 and outer[4]=="-")
                if is_date:
                    dk = outer.split(":")[0]
                    result.setdefault(dk, {})
                    for sk, contracts in inner.items():
                        try:
                            s = float(sk)
                            if contracts and isinstance(contracts, list):
                                result[dk][s] = contracts[0]
                        except: pass
                else:
                    try:
                        s = float(outer)
                        for dk, contracts in inner.items():
                            dk = dk.split(":")[0]
                            result.setdefault(dk, {})
                            if contracts and isinstance(contracts, list):
                                result[dk][s] = contracts[0]
                    except: pass
            return result

        self._parsed_calls = parse_map(data.get("callExpDateMap",{}))
        self._parsed_puts  = parse_map(data.get("putExpDateMap",{}))
        all_dates = sorted(set(list(self._parsed_calls.keys())+list(self._parsed_puts.keys())))

        # Only collapse dates we haven't seen before
        # Dates already in _all_dates keep their current state
        existing = set(self._all_dates)
        for d in all_dates:
            if d not in existing:
                self._collapsed.add(d)   # new date — start collapsed
        self._all_dates = all_dates
        self._redraw()

    def _after_redraw(self):
        self._table.resizeColumnsToContents()
        from PyQt6.QtWidgets import QHeaderView
        for i in range(self._table.columnCount()):
            self._table.horizontalHeader().setSectionResizeMode(
                i, QHeaderView.ResizeMode.Interactive)

    def _redraw(self):
        self._table.setRowCount(0)
        total = 0
        for date_str in self._all_dates:
            is_collapsed = date_str in self._collapsed
            arrow = "▶" if is_collapsed else "▼"
            calls   = self._parsed_calls.get(date_str, {})
            puts    = self._parsed_puts.get(date_str, {})
            strikes = sorted(set(list(calls.keys())+list(puts.keys())))

            # Expiration header
            exp_row = self._table.rowCount()
            self._table.insertRow(exp_row)
            self._table.setRowHeight(exp_row, 28)
            txt = f"  {arrow}  📅  {date_str}  ({len(strikes)} strikes)"
            exp_item = QTableWidgetItem(txt)
            exp_item.setBackground(QColor("#1c2333"))
            exp_item.setForeground(QColor(BLUE))
            exp_item.setFont(QFont("Consolas",10,QFont.Weight.Bold))
            exp_item.setFlags(Qt.ItemFlag.ItemIsEnabled|Qt.ItemFlag.ItemIsSelectable)
            exp_item.setData(Qt.ItemDataRole.UserRole, ("expiry", date_str))
            self._table.setItem(exp_row, 0, exp_item)
            self._table.setSpan(exp_row, 0, 1, 19)
            total += 1

            if is_collapsed:
                continue

            for strike in strikes:
                c = calls.get(strike, {})
                p = puts.get(strike,  {})
                is_atm = len(strikes)>0 and abs(strike-self._under_price)==min(
                    abs(s-self._under_price) for s in strikes)

                row = self._table.rowCount()
                self._table.insertRow(row)
                self._table.setRowHeight(row, 20)

                call_bg = QColor("#1a2a1a") if is_atm else (QColor("#0a1a10") if strike<=self._under_price else QColor(BG))
                put_bg  = QColor("#1a2a1a") if is_atm else (QColor("#1a0a0a") if strike>=self._under_price else QColor(BG))
                str_bg  = QColor("#1f2d0f") if is_atm else QColor(BG2)

                def cv(val, d=2):
                    if val is None or val==0: return ""
                    return f"{val:.{d}f}"

                def cell(text, fg, bg, bold=False, ud=None):
                    it = QTableWidgetItem(str(text))
                    it.setForeground(QColor(fg)); it.setBackground(bg)
                    it.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if bold: f=it.font(); f.setBold(True); it.setFont(f)
                    if ud is not None: it.setData(Qt.ItemDataRole.UserRole, ud)
                    return it

                chg_c = GREEN if c.get("netChange",0)>=0 else RED
                chg_p = GREEN if p.get("netChange",0)>=0 else RED

                # Call columns — Bid (col 7) and Ask (col 8) clearly visible
                call_vals = [
                    (cv(c.get("last")),                          "#e6edf3", None),
                    (cv(c.get("netChange")),                     chg_c,     None),
                    (f"{int(c.get('totalVolume',0)):,}" if c else "", "#e6edf3", None),
                    (f"{int(c.get('openInterest',0)):,}" if c else "", DIM,   None),
                    (f"{c.get('volatility',0):.1f}" if c else "","#e6edf3", None),
                    (cv(c.get("delta"),3),                       "#e6edf3", None),
                    (cv(c.get("theta"),4),                       RED,       None),
                    (cv(c.get("bid")),                           "#58ffb0", ("call","bid",date_str,strike,c)),
                    (cv(c.get("ask")),                           "#ff8080", ("call","ask",date_str,strike,c)),
                ]
                for col,(text,fg,ud) in enumerate(call_vals):
                    bg = QColor("#0a2010") if col==7 else (QColor("#200a0a") if col==8 else call_bg)
                    self._table.setItem(row, col, cell(text, fg, bg, ud=ud))

                # Strike
                atm_txt = f"${strike:.2f} ◀" if is_atm else f"${strike:.2f}"
                self._table.setItem(row, 9, cell(atm_txt, YELLOW if is_atm else "#e6edf3",
                                                  str_bg, is_atm, ud=("strike",date_str,strike)))

                # Put columns — Bid (col 10) and Ask (col 11) clearly visible
                put_vals = [
                    (cv(p.get("bid")),                           "#58ffb0", ("put","bid",date_str,strike,p)),
                    (cv(p.get("ask")),                           "#ff8080", ("put","ask",date_str,strike,p)),
                    (cv(p.get("delta"),3),                       "#e6edf3", None),
                    (cv(p.get("theta"),4),                       RED,       None),
                    (f"{p.get('volatility',0):.1f}" if p else "","#e6edf3", None),
                    (f"{int(p.get('openInterest',0)):,}" if p else "", DIM, None),
                    (f"{int(p.get('totalVolume',0)):,}" if p else "", "#e6edf3", None),
                    (cv(p.get("netChange")),                     chg_p,     None),
                    (cv(p.get("last")),                          "#e6edf3", None),
                ]
                for i,(text,fg,ud) in enumerate(put_vals):
                    bg = QColor("#0a2010") if i==0 else (QColor("#200a0a") if i==1 else put_bg)
                    self._table.setItem(row, 10+i, cell(text, fg, bg, ud=ud))

                total += 1

        from datetime import datetime
        self._status.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}  |  {total} rows")

    def _on_cell_click(self, row, col):
        # Check if this row is an expiry header (spans all 19 cols)
        if self._table.columnSpan(row, 0) == 19:
            item0 = self._table.item(row, 0)
            if item0:
                ud0 = item0.data(Qt.ItemDataRole.UserRole)
                if ud0 and isinstance(ud0, tuple) and ud0[0] == "expiry":
                    ds = ud0[1]
                    if ds in self._collapsed:
                        self._collapsed.discard(ds)
                    else:
                        self._collapsed.add(ds)
                    self._redraw()
            return

        # Contract row — check clicked cell for bid/ask data
        item = self._table.item(row, col)
        if not item: return
        ud = item.data(Qt.ItemDataRole.UserRole)
        if not ud or not isinstance(ud, tuple): return

        if ud[0] in ("call", "put"):
            _, side_col, date_str, strike, contract = ud
            opt_type = "CALL" if ud[0] == "call" else "PUT"
            # bid col = Buy to Open, ask col = Sell to Open
            if side_col == "bid":
                instruction = "BUY_TO_OPEN"
                price = float(contract.get("ask", 0) or 0)
            else:
                instruction = "SELL_TO_OPEN"
                price = float(contract.get("bid", 0) or 0)
            self._place_option(date_str, strike, opt_type, contract, instruction, price)


    def _place_option(self, date_str, strike, opt_type, contract, instruction, price):
        """Open order dialog with pre-filled option details."""
        # Build OCC symbol
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            date_part = dt.strftime("%y%m%d")
        except:
            date_part = "000000"
        cp = "C" if opt_type == "CALL" else "P"
        sym_padded = self._symbol.ljust(6)
        strike_int = int(round(strike * 1000))
        opt_sym = f"{sym_padded}{date_part}{cp}{strike_int:08d}"

        from ui.order_dialog import OrderDialog
        dlg = OrderDialog(self, api=self.api,
                          pre_fill={"symbol": opt_sym,
                                    "instruction": instruction,
                                    "price": price,
                                    "asset_type": "OPTION"})
        dlg.exec()



    def _expand_all(self):
        self._collapsed.clear(); self._redraw()

    def _collapse_all(self):
        self._collapsed = set(self._all_dates); self._redraw()

    def on_show(self):
        self._load_chain()
