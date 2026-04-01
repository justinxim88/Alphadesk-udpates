"""
Active Trader Panel v8
- Position pulled from real Schwab account via AccountManager
- Only bid/ask clickable for order placement
- Buy/Sell order columns show actual working orders
- Average price line marked on ladder
- DOM rejection doesn't update position
- Session selector
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QDialog, QGridLayout,
    QDoubleSpinBox, QDialogButtonBox, QComboBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QAction

from api.trade_store import trade_store
from config.settings_manager import load_settings
from ui.toast import notify

GREEN="#3fb950"; RED="#f85149"; BLUE="#58a6ff"; YELLOW="#d29922"
DIM="#8b949e"; BG="#0d1117"; BG2="#161b22"; BG3="#21262d"

BTN = "QPushButton{{background-color:{bg};color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:3px;font-size:11px;font-weight:bold;padding:0 4px;}} QPushButton:hover{{border:2px solid #fff;}}"
INC = "QPushButton{background-color:#2d333b;color:#fff;border:2px solid #58a6ff;border-radius:4px;font-weight:bold;font-size:20px;} QPushButton:hover{background-color:#1f6feb;}"
QTY = "QPushButton{background-color:#21262d;color:#58a6ff;border:2px solid #30363d;border-radius:3px;font-size:11px;font-weight:bold;} QPushButton:hover{background-color:#1f6feb;color:#fff;border:2px solid #388bfd;}"


class QuoteThread(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api, sym): super().__init__(); self.api=api; self.sym=sym
    def run(self):
        try: self.done.emit(self.api.get_quote(self.sym))
        except: self.done.emit({})


class OrdersThread(QThread):
    done = pyqtSignal(list)
    def __init__(self, api):
        super().__init__(); self.api=api
    def run(self):
        try:
            from datetime import datetime, timedelta
            from_d = (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
            to_d   = datetime.now().strftime("%Y-%m-%dT23:59:59Z")
            self.done.emit(self.api.get_orders(from_date=from_d, to_date=to_d, status="WORKING"))
        except: self.done.emit([])


class ActiveTraderPanel(QWidget):
    def __init__(self, api, account_manager=None, parent=None):
        super().__init__(parent)
        self.api             = api
        self.account_manager = account_manager
        self._symbol         = ""
        self._last_price     = 0.0
        self._bid            = 0.0
        self._ask            = 0.0
        self._position       = 0        # from Schwab account
        self._avg_price      = 0.0      # from Schwab account
        self._pnl_day        = 0.0
        self._working_orders = {}       # price → {"side","qty","id"}
        self._threads        = []
        self._dom_prices     = []

        self.setFixedWidth(390)
        self.setStyleSheet(f"background:{BG2}; border-left:1px solid #30363d;")
        self._build()

        # Quote refresh
        self._q_timer = QTimer(); self._q_timer.timeout.connect(self._refresh_quote); self._q_timer.start(1000)
        # Orders refresh
        self._o_timer = QTimer(); self._o_timer.timeout.connect(self._refresh_orders); self._o_timer.start(3000)
        # Position refresh from account manager
        if self.account_manager:
            self.account_manager.positions_updated.connect(self._on_positions_updated)

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
        v.addWidget(self._build_toolbar())
        v.addWidget(self._build_session_row())
        v.addWidget(self._build_qty_row())
        v.addWidget(self._build_pos_bar())
        v.addWidget(self._build_dom())
        self._ticker_lbl = QLabel("  Last: —    Bid: —    Ask: —")
        self._ticker_lbl.setFixedHeight(22)
        self._ticker_lbl.setStyleSheet(f"color:{DIM};font-size:10px;padding:2px 8px;background:{BG3};border-top:1px solid #30363d;")
        v.addWidget(self._ticker_lbl)

    def _btn(self, text, bg, fn, h=34):
        b = QPushButton(text); b.setFixedHeight(h)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setStyleSheet(BTN.format(bg=bg)); b.clicked.connect(fn); return b

    def _build_toolbar(self):
        w = QWidget(); w.setFixedHeight(44)
        w.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        h = QHBoxLayout(w); h.setContentsMargins(4,4,4,4); h.setSpacing(3)
        for t,bg,fn in [("Buy MKT","#238636",self._buy_mkt),("Sell MKT","#da3633",self._sell_mkt),
                         ("Cancel","#6e40c9",self._cancel_all),("Reverse","#9a7700",self._reverse),
                         ("Flatten","#1f6feb",self._flatten)]:
            h.addWidget(self._btn(t,bg,fn))
        return w

    def _build_session_row(self):
        w = QWidget(); w.setFixedHeight(34)
        w.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        h = QHBoxLayout(w); h.setContentsMargins(6,3,6,3); h.setSpacing(6)
        h.addWidget(self._btn("Buy Limit","#1a5c2a",self._buy_lim,h=26))
        h.addWidget(self._btn("Sell Limit","#5c1a1a",self._sell_lim,h=26))
        h.addSpacing(4)
        self._sess = QComboBox()
        self._sess.addItems(["NORMAL","PRE_MARKET","AFTER_HOURS","SEAMLESS"])
        self._sess.setFixedHeight(26); self._sess.setFixedWidth(118)
        self._sess.setCurrentText(load_settings().get("default_session","NORMAL"))
        self._sess.setStyleSheet(f"QComboBox{{background-color:{BG};color:#e6edf3;border:1px solid #30363d;border-radius:3px;font-size:10px;padding:2px 4px;}} QComboBox QAbstractItemView{{background-color:{BG2};color:#e6edf3;selection-background-color:#1f6feb;}}")
        h.addWidget(self._sess); h.addStretch(); return w

    def _build_qty_row(self):
        w = QWidget(); w.setFixedHeight(42)
        w.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        h = QHBoxLayout(w); h.setContentsMargins(6,4,6,4); h.setSpacing(4)
        lbl = QLabel("Qty:"); lbl.setStyleSheet("color:#e6edf3;font-size:12px;font-weight:bold;"); h.addWidget(lbl)
        self._qty = QLineEdit("1"); self._qty.setFixedWidth(52); self._qty.setFixedHeight(30)
        self._qty.setStyleSheet(f"QLineEdit{{background-color:{BG};color:#fff;border:2px solid #58a6ff;border-radius:3px;padding:2px 6px;font-size:14px;font-weight:bold;}}")
        h.addWidget(self._qty)
        minus = QPushButton("−"); minus.setFixedSize(32,30); minus.setStyleSheet(INC); minus.clicked.connect(lambda: self._adj(-1)); h.addWidget(minus)
        plus  = QPushButton("+"); plus.setFixedSize(32,30);  plus.setStyleSheet(INC);  plus.clicked.connect(lambda: self._adj(1));  h.addWidget(plus)
        h.addSpacing(4)
        for v in [5,15,25,50,100]:
            b = QPushButton(str(v)); b.setFixedHeight(30); b.setFixedWidth(36); b.setStyleSheet(QTY)
            b.clicked.connect(lambda _,vv=v: self._qty.setText(str(vv))); h.addWidget(b)
        return w

    def _build_pos_bar(self):
        w = QWidget(); w.setFixedHeight(46)
        w.setStyleSheet(f"background:{BG};border-bottom:1px solid #30363d;")
        h = QHBoxLayout(w); h.setContentsMargins(4,0,4,0); h.setSpacing(0)
        self._pv = {}
        for key,label in [("bs","B/S"),("pos","Pos"),("avg","Avg"),("pnl_open","P/L Open"),("pnl_day","P/L Day")]:
            f = QWidget(); fv = QVBoxLayout(f); fv.setContentsMargins(4,2,4,2); fv.setSpacing(1)
            l = QLabel(label); l.setStyleSheet(f"color:{DIM};font-size:9px;border:none;background:transparent;")
            v = QLabel("—"); v.setStyleSheet(f"color:#e6edf3;font-size:11px;font-weight:bold;border:none;background:transparent;")
            fv.addWidget(l); fv.addWidget(v); h.addWidget(f,stretch=1); self._pv[key]=v
        return w

    def _build_dom(self):
        wr = QWidget(); wv = QVBoxLayout(wr); wv.setContentsMargins(0,0,0,0); wv.setSpacing(0)
        hdr = QWidget(); hdr.setFixedHeight(24)
        hdr.setStyleSheet(f"background:{BG3};border-bottom:2px solid #58a6ff;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(0,0,0,0); hh.setSpacing(0)
        for lbl,w,color in [("Vol",52,DIM),("Buy Ord",56,GREEN),("Bid Sz",54,GREEN),
                              ("Price",66,YELLOW),("Ask Sz",54,RED),("Sell Ord",56,RED)]:
            l = QLabel(lbl); l.setFixedWidth(w); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(f"color:{color};font-size:9px;font-weight:bold;background:transparent;border-right:1px solid #30363d;")
            hh.addWidget(l)
        wv.addWidget(hdr)

        self._dom = QTableWidget(0,6)
        self._dom.verticalHeader().setVisible(False)
        self._dom.horizontalHeader().setVisible(False)
        self._dom.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._dom.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._dom.setShowGrid(True)
        self._dom.horizontalHeader().setSectionsMovable(True)
        for i,w in enumerate([52,56,54,66,54,56]):
            self._dom.setColumnWidth(i,w)
            self._dom.horizontalHeader().setSectionResizeMode(i,QHeaderView.ResizeMode.Interactive)
        self._dom.setStyleSheet(f"""
            QTableWidget{{background-color:{BG};border:2px solid #30363d;gridline-color:#2d333b;color:#e6edf3;font-family:Consolas;font-size:11px;}}
            QTableWidget::item{{padding:2px 3px;border-right:1px solid #2d333b;color:#e6edf3;}}
            QTableWidget::item:hover{{background-color:#1c2b3a;}}
        """)
        # Only connect click on bid/ask columns (2 and 4)
        self._dom.cellClicked.connect(self._on_dom_click)
        self._dom.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._dom.customContextMenuRequested.connect(self._on_dom_rclick)
        wv.addWidget(self._dom, stretch=1)
        return wr

    # ── ACCOUNT POSITION SYNC ──────────────────────

    def _on_positions_updated(self, positions: list):
        """Called when Schwab positions refresh."""
        if not self._symbol: return
        sym = self._symbol.upper().split()[0]
        for p in positions:
            inst = p.get("instrument", {})
            if inst.get("symbol","").upper() == sym:
                long_qty  = p.get("longQuantity",  0)
                short_qty = p.get("shortQuantity", 0)
                self._position  = int(long_qty) if long_qty > 0 else -int(short_qty)
                self._avg_price = float(p.get("averagePrice", 0))
                self._update_pos_bar()
                return
        # Not found = flat
        self._position = 0; self._avg_price = 0.0
        self._update_pos_bar()

    # ── QUOTE & ORDERS REFRESH ─────────────────────

    def set_symbol(self, sym: str):
        self._symbol = sym.upper(); self._working_orders = {}
        self._refresh_quote(); self._refresh_orders()

    def _refresh_quote(self):
        if not self._symbol: return
        t = QuoteThread(self.api, self._symbol)
        t.done.connect(self._update_dom); t.done.connect(lambda _: self._cleanup(t))
        self._threads.append(t); t.start()

    def _refresh_orders(self):
        if not self._symbol: return
        t = OrdersThread(self.api)
        t.done.connect(self._update_working_orders); t.done.connect(lambda _: self._cleanup(t))
        self._threads.append(t); t.start()

    def _cleanup(self, t):
        try: self._threads.remove(t)
        except: pass

    def _update_working_orders(self, orders: list):
        """Update working orders map from Schwab."""
        self._working_orders = {}
        for o in orders:
            legs = o.get("orderLegCollection", [{}])
            inst = legs[0].get("instrument", {}) if legs else {}
            sym  = inst.get("symbol","").upper().split()[0]
            if sym != self._symbol.upper(): continue
            price = float(o.get("price", 0) or 0)
            side  = legs[0].get("instruction","") if legs else ""
            qty   = int(o.get("quantity", 0))
            oid   = str(o.get("orderId",""))
            if price > 0:
                self._working_orders[round(price,2)] = {
                    "side": "BUY" if "BUY" in side.upper() else "SELL",
                    "qty": qty, "id": oid
                }

    def _update_dom(self, data: dict):
        import random
        q = data.get("quote",{})
        if not q: return
        last = q.get("lastPrice", q.get("mark",0))
        bid  = q.get("bidPrice", last-0.01)
        ask  = q.get("askPrice", last+0.01)
        self._last_price=last; self._bid=bid; self._ask=ask
        self._ticker_lbl.setText(f"  Last: ${last:.2f}    Bid: ${bid:.2f}    Ask: ${ask:.2f}")

        tick   = 0.01 if last<100 else 0.05 if last<500 else 0.10
        levels = 30
        prices = sorted([round(last+(i-levels//2)*tick,2) for i in range(levels)],reverse=True)
        self._dom_prices = prices
        self._dom.setRowCount(0)

        for price in prices:
            row = self._dom.rowCount(); self._dom.insertRow(row); self._dom.setRowHeight(row,20)
            is_bid   = price <= bid
            is_ask   = price >= ask
            is_last  = abs(price-last) < tick*0.6
            is_avg   = self._avg_price>0 and abs(price-self._avg_price)<tick*0.6 and self._position!=0
            bid_sz   = random.randint(100,5000) if is_bid else 0
            ask_sz   = random.randint(100,5000) if is_ask else 0
            vol      = random.randint(0,2000)   if is_bid else 0
            wo       = self._working_orders.get(round(price,2), {})
            buy_q    = wo.get("qty",0) if wo.get("side")=="BUY"  else 0
            sell_q   = wo.get("qty",0) if wo.get("side")=="SELL" else 0

            # Row background
            if is_avg:    row_bg = QColor("#1a1a2e")   # purple tint = avg price
            elif is_last: row_bg = QColor("#1f2d0f")
            elif is_bid:  row_bg = QColor("#0a1a10")
            elif is_ask:  row_bg = QColor("#1a0a0a")
            else:         row_bg = QColor(BG)

            def mk(text, fg, bg=None, bold=False):
                item = QTableWidgetItem(str(text) if text else "")
                item.setForeground(QColor(fg))
                item.setBackground(bg if bg else row_bg)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if bold: f=item.font(); f.setBold(True); item.setFont(f)
                return item

            self._dom.setItem(row,0, mk(f"{vol:,}" if vol else "", DIM))
            # Buy orders from Schwab
            self._dom.setItem(row,1, mk(f"{buy_q}" if buy_q else "", GREEN,
                                         QColor("#0a2a0a") if buy_q else row_bg, True))
            # Bid size — clickable for BUY
            bid_item = mk(f"{bid_sz:,}" if bid_sz else "", GREEN)
            if is_bid:
                bid_item.setToolTip("Click to BUY at this price")
                bid_item.setForeground(QColor("#58ffb0"))  # brighter = clickable
            self._dom.setItem(row,2, bid_item)

            # Price — show avg marker
            price_txt  = f"${price:.2f}" if is_avg else f"{price:.2f}"
            price_color = "#c792ea" if is_avg else (YELLOW if is_last else "#e6edf3")
            price_bg    = QColor("#2a1a40") if is_avg else (QColor("#1f2d0f") if is_last else QColor(BG2))
            p_item = mk(price_txt, price_color, price_bg, is_last or is_avg)
            if is_avg:
                p_item.setToolTip(f"Your avg entry: ${self._avg_price:.2f}")
            self._dom.setItem(row,3, p_item)

            # Ask size — clickable for SELL
            ask_item = mk(f"{ask_sz:,}" if ask_sz else "", RED)
            if is_ask:
                ask_item.setToolTip("Click to SELL at this price")
                ask_item.setForeground(QColor("#ff8080"))  # brighter = clickable
            self._dom.setItem(row,4, ask_item)

            # Sell orders from Schwab
            self._dom.setItem(row,5, mk(f"{sell_q}" if sell_q else "", RED,
                                         QColor("#2a0a0a") if sell_q else row_bg, True))

        mid = levels//2
        if self._dom.item(mid,3):
            self._dom.scrollToItem(self._dom.item(mid,3), QAbstractItemView.ScrollHint.PositionAtCenter)
        self._update_pos_bar()

    def _update_pos_bar(self):
        pos   = self._position; avg = self._avg_price; last = self._last_price
        pnl_o = (last-avg)*pos if pos and avg else 0
        pnl_d = self._pnl_day
        st    = "LONG" if pos>0 else "SHORT" if pos<0 else "FLAT"
        sc    = GREEN if pos>0 else RED if pos<0 else DIM
        self._pv["bs"].setText(st)
        self._pv["bs"].setStyleSheet(f"color:{sc};font-size:11px;font-weight:bold;border:none;background:transparent;")
        self._pv["pos"].setText(str(abs(pos)) if pos else "0")
        self._pv["avg"].setText(f"${avg:.2f}" if avg else "N/A")
        so = "+"if pnl_o>=0 else""; sd = "+"if pnl_d>=0 else""
        self._pv["pnl_open"].setText(f"{so}${pnl_o:.2f}")
        self._pv["pnl_open"].setStyleSheet(f"color:{GREEN if pnl_o>=0 else RED};font-size:11px;font-weight:bold;border:none;background:transparent;")
        self._pv["pnl_day"].setText(f"{sd}${pnl_d:.2f}")
        self._pv["pnl_day"].setStyleSheet(f"color:{GREEN if pnl_d>=0 else RED};font-size:11px;font-weight:bold;border:none;background:transparent;")

    # ── DOM CLICKS — only bid/ask ──────────────────

    def _on_dom_click(self, row: int, col: int):
        price = self._get_price(row)
        if price is None: return
        # Only cols 2 (bid=buy) and 4 (ask=sell) are trade columns
        if col == 2:
            otype = self._smart_type("BUY", price)
            self._place("BUY", otype, price)
        elif col == 4:
            otype = self._smart_type("SELL", price)
            self._place("SELL", otype, price)
        # All other columns do nothing

    def _smart_type(self, side, price):
        pos = self._position
        if pos>0  and side=="SELL": return "STOP" if price<self._last_price else "LIMIT"
        if pos<0  and side=="BUY":  return "STOP" if price>self._last_price else "LIMIT"
        return "LIMIT"

    def _on_dom_rclick(self, pos):
        row = self._dom.rowAt(pos.y())
        if row < 0: return
        price = self._get_price(row)
        if price is None: return
        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{BG2};border:1px solid #30363d;color:#e6edf3;font-size:11px;}} QMenu::item{{padding:7px 20px;}} QMenu::item:selected{{background:#1f6feb;}}")
        hdr = menu.addAction(f"  ${price:.2f}"); hdr.setEnabled(False); menu.addSeparator()
        for label,side,ot in [(f"🟢  Buy Limit @ ${price:.2f}","BUY","LIMIT"),("🟢  Buy Market","BUY","MARKET"),
                               (f"🔴  Sell Limit @ ${price:.2f}","SELL","LIMIT"),("🔴  Sell Market","SELL","MARKET"),
                               (f"🛑  Stop @ ${price:.2f}","SELL","STOP")]:
            a = menu.addAction(label); a.triggered.connect(lambda _,s=side,o=ot,p=price: self._place(s,o,p))
        menu.addSeparator()
        oco_a = menu.addAction(f"⚡  OCO @ ${price:.2f}")
        oco_a.triggered.connect(lambda: self._oco_dialog(price))
        menu.exec(self._dom.viewport().mapToGlobal(pos))

    def _place(self, side, otype, price):
        if not self._symbol: return
        qty  = self._get_qty(); sess = self._sess.currentText()
        lp   = price if otype=="LIMIT" else None
        sp   = price if otype=="STOP"  else None
        order = self.api.build_stock_order(self._symbol, qty, side, otype, lp, sp, session=sess)
        self._send(order, side, price, qty)

    def _oco_dialog(self, price):
        dlg = OCODialog(self, price, self._last_price)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            tp, sl = dlg.get_values(); qty = self._get_qty()
            side = "BUY" if price <= self._last_price else "SELL"
            order = self.api.build_oco_order(self._symbol, qty, side, tp, sl)
            ok, msg = self.api.place_order(order)
            self._show(f"{'✓'if ok else '✗'} OCO: TP=${tp:.2f} SL=${sl:.2f}")

    # ── ORDER ACTIONS ──────────────────────────────

    def _get_qty(self):
        try: return max(1, int(self._qty.text()))
        except: return 1

    def _buy_mkt(self):
        if not self._symbol: return
        self._send(self.api.build_stock_order(self._symbol, self._get_qty(), "BUY", "MARKET",
                   session=self._sess.currentText()), "BUY", self._last_price, self._get_qty())

    def _sell_mkt(self):
        if not self._symbol: return
        self._send(self.api.build_stock_order(self._symbol, self._get_qty(), "SELL", "MARKET",
                   session=self._sess.currentText()), "SELL", self._last_price, self._get_qty())

    def _buy_lim(self):
        if not self._symbol: return
        self._place("BUY", "LIMIT", self._bid)

    def _sell_lim(self):
        if not self._symbol: return
        self._place("SELL", "LIMIT", self._ask)

    def _cancel_all(self):
        self._working_orders.clear()
        self._show("Cancel all sent (demo)")

    def _flatten(self):
        if not self._symbol or self._position==0: self._show("Already flat"); return
        side = "SELL" if self._position>0 else "BUY"; qty = abs(self._position)
        self._send(self.api.build_stock_order(self._symbol, qty, side, "MARKET"), side, self._last_price, qty)

    def _reverse(self):
        if not self._symbol: return
        qty  = self._get_qty(); side = "SELL" if self._position>=0 else "BUY"
        total = abs(self._position) + qty
        self._send(self.api.build_stock_order(self._symbol, total, side, "MARKET"), side, self._last_price, total)

    def _send(self, order, side, price, qty):
        ok, msg = self.api.place_order(order)
        if ok:
            trade_store.add_trade(self._symbol, side, price, qty, order.get("orderType",""))
            self._show(f"✓ {side} {qty}x {self._symbol} @ ${price:.2f}")
            notify(f"{side} {qty}x {self._symbol}", "success",
                   subtitle=f"${price:.2f}  |  {order.get('orderType','')}",
                   duration=3000, parent=self.window())
            # Refresh orders and positions after fill
            QTimer.singleShot(1000, self._refresh_orders)
        else:
            # DO NOT update position on rejection
            self._show(f"✗ Rejected: {msg}")
            notify("Order Rejected", "error", subtitle=msg[:80], duration=5000, parent=self.window())

    def _show(self, msg): self._ticker_lbl.setText(f"  {msg}")
    def _get_price(self, row):
        if row<0 or row>=len(self._dom_prices): return None
        item = self._dom.item(row,3)
        try: return float(item.text().replace("$","")) if item else None
        except: return None
    def _adj(self, d):
        try: self._qty.setText(str(max(1, int(self._qty.text())+d)))
        except: self._qty.setText("1")


class OCODialog(QDialog):
    def __init__(self, parent, price, last):
        super().__init__(parent)
        self.setWindowTitle("OCO Order"); self.setFixedWidth(300)
        self.setStyleSheet(f"background:{BG2};color:#e6edf3;")
        vbox = QVBoxLayout(self)
        vbox.addWidget(QLabel(f"Current: ${last:.2f}  |  Selected: ${price:.2f}"))
        grid = QGridLayout(); grid.setSpacing(10)
        grid.addWidget(QLabel("Take Profit $:"),0,0)
        self._tp = QDoubleSpinBox(); self._tp.setRange(0,999999); self._tp.setDecimals(2); self._tp.setValue(round(last*1.02,2))
        grid.addWidget(self._tp,0,1)
        grid.addWidget(QLabel("Stop Loss $:"),1,0)
        self._sl = QDoubleSpinBox(); self._sl.setRange(0,999999); self._sl.setDecimals(2); self._sl.setValue(round(last*0.98,2))
        grid.addWidget(self._sl,1,1)
        vbox.addLayout(grid)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); vbox.addWidget(btns)
    def get_values(self): return self._tp.value(), self._sl.value()
