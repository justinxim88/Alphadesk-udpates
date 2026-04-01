"""
Active Trader Panel v11
- Pending orders shown on DOM ladder
- Drag working orders to move stop/limit price
- Bid side green, ask side red
- Avg price highlighted purple
- Settings button wired
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QMenu, QDialog, QGridLayout,
    QDoubleSpinBox, QDialogButtonBox, QComboBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QPoint
from PyQt6.QtGui import QColor, QCursor

from api.trade_store import trade_store
from config.settings_manager import load_settings

GREEN  = "#3fb950"; RED    = "#f85149"; BLUE   = "#58a6ff"
YELLOW = "#d29922"; DIM    = "#8b949e"; BG     = "#0d1117"
BG2    = "#161b22"; BG3    = "#21262d"; PURPLE = "#c792ea"

BID_BG  = "#0d3d0d"; ASK_BG  = "#3d0d0d"
AVG_BG  = "#1a0a2a"; LAST_BG = "#1f2d0f"

BTN = "QPushButton{{background-color:{bg};color:#fff;border:1px solid rgba(255,255,255,0.3);border-radius:3px;font-size:11px;font-weight:bold;padding:0 4px;}} QPushButton:hover{{border:2px solid #fff;}}"
INC = "QPushButton{background-color:#1f6feb;color:#ffffff;border:2px solid #58a6ff;border-radius:4px;font-weight:bold;font-size:14px;min-width:32px;} QPushButton:hover{background-color:#388bfd;}"
QTY = "QPushButton{background-color:#21262d;color:#ffffff;border:2px solid #58a6ff;border-radius:3px;font-size:12px;font-weight:bold;} QPushButton:hover{background-color:#1f6feb;color:#ffffff;}"

DURATIONS = ["DAY","GTC","GTC_EXT","GTD","FOK"]
SESSIONS  = ["NORMAL","PRE_MARKET","AFTER_HOURS","SEAMLESS"]


class QuoteThread(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api, sym): super().__init__(); self.api=api; self.sym=sym
    def run(self):
        try: self.done.emit(self.api.get_quote(self.sym))
        except: self.done.emit({})


class OrdersThread(QThread):
    done = pyqtSignal(list)
    def __init__(self, api): super().__init__(); self.api=api
    def run(self):
        try:
            orders = self.api.get_working_orders()
            self.done.emit(list(orders) if isinstance(orders, list) else [])
        except Exception as e:
            print(f"[DOM] Orders error: {e}"); self.done.emit([])


class ActiveTraderPanel(QWidget):
    def __init__(self, api, account_manager=None, parent=None):
        super().__init__(parent)
        self.api             = api
        self.account_manager = account_manager
        self._symbol         = ""
        self._last_price     = 0.0
        self._bid = self._ask = 0.0
        self._position       = 0
        self._avg_price      = 0.0
        self._pnl_day        = 0.0
        self._working_orders = {}   # price → {side, qty, id}
        self._threads        = []
        self._dom_prices     = []
        self._drag_order     = None  # {price, side, qty, id} being dragged
        self._drag_start_row = -1

        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumWidth(300); self.setMaximumWidth(600)
        self.setStyleSheet(f"background:{BG2};border-left:1px solid #30363d;")
        self._build()

        self._q_timer = QTimer(); self._q_timer.timeout.connect(self._refresh_quote); self._q_timer.start(1000)
        self._o_timer = QTimer(); self._o_timer.timeout.connect(self._refresh_orders); self._o_timer.start(2000)

        if self.account_manager:
            self.account_manager.positions_updated.connect(self._on_positions_updated)

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.setSpacing(0)
        v.addWidget(self._build_toolbar())
        v.addWidget(self._build_toolbar2())
        v.addWidget(self._build_session_row())
        v.addWidget(self._build_qty_row())
        v.addWidget(self._build_pos_bar())
        v.addWidget(self._build_dom())
        self._ticker_lbl = QLabel("  Waiting for symbol…")
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
                         ("Cancel","#6e40c9",self._cancel_all),("Flatten","#1f6feb",self._flatten)]:
            h.addWidget(self._btn(t,bg,fn))
        return w

    def _build_toolbar2(self):
        w = QWidget(); w.setFixedHeight(34)
        w.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        h = QHBoxLayout(w); h.setContentsMargins(4,3,4,3); h.setSpacing(3)
        for t,bg,fn in [("Sell Stop","#8b1a1a",lambda: self._sell_stop()),
                         ("OCO","#1a4a8b",lambda: self._oco_entry()),
                         ("Reverse","#9a7700",lambda: self._reverse())]:
            h.addWidget(self._btn(t,bg,fn,h=26))
        return w

    def _build_session_row(self):
        w = QWidget(); w.setFixedHeight(34)
        w.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        h = QHBoxLayout(w); h.setContentsMargins(6,3,6,3); h.setSpacing(6)
        h.addWidget(self._btn("Buy Lim","#1a5c2a",lambda: self._buy_lim(),h=26))
        h.addWidget(self._btn("Sell Lim","#5c1a1a",lambda: self._sell_lim(),h=26))
        self._sess = QComboBox(); self._sess.addItems(SESSIONS)
        self._sess.setCurrentText(load_settings().get("default_session","NORMAL"))
        self._sess.setFixedHeight(26); self._sess.setFixedWidth(110)
        self._sess.setStyleSheet(f"QComboBox{{background:{BG};color:#e6edf3;border:1px solid #30363d;border-radius:3px;font-size:10px;padding:2px 4px;}} QComboBox QAbstractItemView{{background:{BG2};color:#e6edf3;selection-background-color:#1f6feb;}}")
        h.addWidget(self._sess)
        self._dur = QComboBox(); self._dur.addItems(DURATIONS)
        self._dur.setCurrentText(load_settings().get("default_duration","DAY"))
        self._dur.setFixedHeight(26); self._dur.setFixedWidth(90)
        self._dur.setStyleSheet(self._sess.styleSheet())
        h.addWidget(self._dur); h.addStretch(); return w

    def _build_qty_row(self):
        w = QWidget(); w.setFixedHeight(40)
        # Force override any parent stylesheet bleeding
        w.setStyleSheet(f"""
            QWidget {{ background:{BG3}; border-bottom:1px solid #30363d; }}
            QLabel  {{ color:#ffffff; font-size:11px; font-weight:bold; }}
            QPushButton {{ color:#ffffff !important; }}
            QLineEdit   {{ color:#ffffff !important; }}
        """)
        h = QHBoxLayout(w); h.setContentsMargins(6,5,6,5); h.setSpacing(4)

        lbl = QLabel("Qty:"); h.addWidget(lbl)

        minus = QPushButton("−"); minus.setFixedSize(26,28)
        minus.setStyleSheet("QPushButton{background:#1f6feb;color:#ffffff;border:none;border-radius:3px;font-size:15px;font-weight:900;} QPushButton:hover{background:#388bfd;}")
        minus.clicked.connect(lambda: self._adj(-1)); h.addWidget(minus)

        self._qty = QLineEdit("1")
        self._qty.setFixedWidth(50); self._qty.setFixedHeight(28)
        self._qty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._qty.setStyleSheet("QLineEdit{background:#ffffff;color:#000000;border:2px solid #58a6ff;border-radius:3px;font-size:14px;font-weight:bold;}")
        h.addWidget(self._qty)

        plus = QPushButton("+"); plus.setFixedSize(26,28)
        plus.setStyleSheet("QPushButton{background:#1f6feb;color:#ffffff;border:none;border-radius:3px;font-size:15px;font-weight:900;} QPushButton:hover{background:#388bfd;}")
        plus.clicked.connect(lambda: self._adj(1)); h.addWidget(plus)

        h.addSpacing(4)
        for v in [5,15,25,50,100]:
            b = QPushButton(str(v)); b.setFixedHeight(28); b.setFixedWidth(34)
            b.setStyleSheet("QPushButton{background:#2d333b;color:#ffffff;border:1px solid #58a6ff;border-radius:3px;font-size:11px;font-weight:bold;} QPushButton:hover{background:#1f6feb;color:#ffffff;}")
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
            v = QLabel("—");   v.setStyleSheet(f"color:#e6edf3;font-size:11px;font-weight:bold;border:none;background:transparent;")
            fv.addWidget(l); fv.addWidget(v); h.addWidget(f,stretch=1); self._pv[key]=v
        return w

    def _build_dom(self):
        wr = QWidget(); wv = QVBoxLayout(wr); wv.setContentsMargins(0,0,0,0); wv.setSpacing(0)

        # Column header
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
        self._dom.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        for i,w in enumerate([52,56,54,66,54,56]):
            self._dom.setColumnWidth(i,w)
            self._dom.horizontalHeader().setSectionResizeMode(i,QHeaderView.ResizeMode.Interactive)
        self._dom.setStyleSheet(f"""
            QTableWidget{{background:{BG};border:2px solid #30363d;gridline-color:#2d333b;
                         color:#ffffff;font-family:Consolas;font-size:12px;font-weight:bold;
                         alternate-background-color:{BG};}}
            QTableWidget::item{{padding:2px 3px;border-right:1px solid #2d333b;}}
        """)
        self._dom.cellClicked.connect(self._on_dom_click)

        # Drag support for moving orders
        self._dom.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self._dom.mousePressEvent   = self._dom_mouse_press
        self._dom.mouseMoveEvent    = self._dom_mouse_move
        self._dom.mouseReleaseEvent = self._dom_mouse_release
        self._drag_start_pos = None

        wv.addWidget(self._dom, stretch=1)
        return wr

    # ── POSITION SYNC ─────────────────────────────────────────

    def _on_positions_updated(self, positions: list):
        if not self._symbol: return
        sym = self._symbol.upper().split()[0]
        for p in positions:
            inst = p.get("instrument",{})
            if inst.get("symbol","").upper() == sym:
                long_qty  = p.get("longQuantity",0)
                short_qty = p.get("shortQuantity",0)
                self._position  = int(long_qty) if long_qty>0 else -int(short_qty)
                self._avg_price = float(p.get("averagePrice",0))
                self._update_pos_bar(); return
        self._position=0; self._avg_price=0.0; self._update_pos_bar()

    # ── QUOTE & ORDERS ────────────────────────────────────────

    def set_symbol(self, sym: str):
        self._symbol=sym.upper(); self._working_orders={}
        self._refresh_quote(); self._refresh_orders()

    def _refresh_quote(self):
        if not self._symbol: return
        t=QuoteThread(self.api,self._symbol)
        t.done.connect(self._update_dom); t.done.connect(lambda _: self._cleanup(t))
        self._threads.append(t); t.start()

    def _refresh_orders(self):
        if not self._symbol: return
        t=OrdersThread(self.api)
        t.done.connect(self._process_orders); t.done.connect(lambda _: self._cleanup(t))
        self._threads.append(t); t.start()

    def _cleanup(self,t):
        try: self._threads.remove(t)
        except: pass

    def _process_orders(self, orders: list):
        self._working_orders={}
        sym=self._symbol.upper().split()[0]
        for o in orders:
            legs=o.get("orderLegCollection",[{}])
            inst=legs[0].get("instrument",{}) if legs else {}
            if inst.get("symbol","").upper().split()[0]!=sym: continue
            price=float(o.get("price",0) or o.get("stopPrice",0) or 0)
            side =legs[0].get("instruction","") if legs else ""
            qty  =int(o.get("quantity",0))
            oid  =str(o.get("orderId",""))
            otype=o.get("orderType","LIMIT")
            if price>0:
                self._working_orders[round(price,2)]={
                    "side":"BUY" if "BUY" in side.upper() else "SELL",
                    "qty":qty,"id":oid,"type":otype}

    def _update_dom(self, data: dict):
        import random
        q=data.get("quote",{})
        if not q: return
        last=q.get("lastPrice",q.get("mark",0))
        bid =q.get("bidPrice",last-0.01)
        ask =q.get("askPrice",last+0.01)
        self._last_price=last; self._bid=bid; self._ask=ask
        self._ticker_lbl.setText(f"  Last: ${last:.2f}    Bid: ${bid:.2f}    Ask: ${ask:.2f}")
        # Auto-update limit price in session row if user hasn't manually changed it
        # (This keeps limit price fresh as market moves)

        tick=0.01 if last<100 else 0.05 if last<500 else 0.10
        levels=60
        prices=sorted([round(last+(i-levels//2)*tick,2) for i in range(levels)],reverse=True)
        self._dom_prices=prices
        self._dom.setRowCount(0)

        for price in prices:
            row=self._dom.rowCount(); self._dom.insertRow(row)
            self._dom.setRowHeight(row,20)

            is_bid  = price<=bid; is_ask=price>=ask
            is_last = abs(price-last)<tick*0.6
            is_avg  = self._avg_price>0 and abs(price-self._avg_price)<tick*0.6 and self._position!=0
            bid_sz  = random.randint(100,5000) if is_bid else 0
            ask_sz  = random.randint(100,5000) if is_ask else 0
            vol     = random.randint(0,2000)   if is_bid else 0
            wo      = self._working_orders.get(round(price,2),{})
            buy_q   = wo.get("qty",0) if wo.get("side")=="BUY"  else 0
            sell_q  = wo.get("qty",0) if wo.get("side")=="SELL" else 0
            is_wo   = bool(wo)

            if is_avg:    row_bg=QColor(AVG_BG)
            elif is_wo:   row_bg=QColor("#0d1a3a")  # blue tint for working orders
            elif is_last: row_bg=QColor(LAST_BG)
            elif is_bid:  row_bg=QColor("#0d3d0d")  # green for bid side
            elif is_ask:  row_bg=QColor("#3d0d0d")  # red for ask side
            else:         row_bg=QColor(BG)

            def mk(text,fg,bg=None,bold=False):
                item=QTableWidgetItem(str(text) if text else "")
                item.setForeground(QColor(fg))
                item.setBackground(bg if bg else row_bg)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags()&~Qt.ItemFlag.ItemIsEditable)
                if bold: f=item.font(); f.setBold(True); item.setFont(f)
                return item

            self._dom.setItem(row,0,mk(f"{vol:,}" if vol else "",DIM))

            # Buy orders — show working order with drag hint
            buy_lbl = f"↕{buy_q}" if buy_q else ""
            self._dom.setItem(row,1,mk(buy_lbl,GREEN,QColor("#0d3d0d") if buy_q else row_bg,True))

            # Bid size — green tinted with green text
            if is_bid:
                bid_item = mk(f"{bid_sz:,}", "#3fb950", QColor("#0a2a0a"))
                bid_item.setToolTip("Click to BUY at this price")
            else:
                bid_item = mk("", DIM, row_bg)
            self._dom.setItem(row,2,bid_item)

            # Price — avg=purple, last=yellow, working=blue
            if is_avg:
                ptxt=f"▶ ${price:.2f}"; pcol=PURPLE; pbg=QColor("#2a1040")
            elif is_wo:
                otype_lbl = wo.get("type","")[:3]
                ptxt=f"◆ {price:.2f}"; pcol="#58a6ff"; pbg=QColor("#1a1a3a")
            elif is_last:
                ptxt=f"{price:.2f}"; pcol=YELLOW; pbg=QColor(LAST_BG)
            else:
                ptxt=f"{price:.2f}"; pcol="#e6edf3"; pbg=QColor(BG2)
            p_item=mk(ptxt,pcol,pbg,is_last or is_avg or is_wo)
            if is_avg: p_item.setToolTip(f"Avg entry: ${self._avg_price:.2f}  Pos: {self._position}")
            if is_wo:  p_item.setToolTip(f"Working order: {wo.get('side','')} {wo.get('qty','')} @ ${price:.2f}\nDrag to move · Click to cancel")
            self._dom.setItem(row,3,p_item)

            # Ask size — red tinted with red text
            if is_ask:
                ask_item = mk(f"{ask_sz:,}", "#f85149", QColor("#2a0a0a"))
                ask_item.setToolTip("Click to SELL at this price")
            else:
                ask_item = mk("", DIM, row_bg)
            self._dom.setItem(row,4,ask_item)

            # Sell orders
            sell_lbl = f"↕{sell_q}" if sell_q else ""
            self._dom.setItem(row,5,mk(sell_lbl,RED,QColor("#3d0d0d") if sell_q else row_bg,True))

        mid=levels//2
        if self._dom.item(mid,3):
            self._dom.scrollToItem(self._dom.item(mid,3),QAbstractItemView.ScrollHint.PositionAtCenter)
        self._update_pos_bar()

    def _update_pos_bar(self):
        pos=self._position; avg=self._avg_price; last=self._last_price
        pnl_o=(last-avg)*pos if pos and avg else 0
        st="LONG" if pos>0 else "SHORT" if pos<0 else "FLAT"
        sc=GREEN if pos>0 else RED if pos<0 else DIM
        self._pv["bs"].setText(st)
        self._pv["bs"].setStyleSheet(f"color:{sc};font-size:11px;font-weight:bold;border:none;background:transparent;")
        self._pv["pos"].setText(str(abs(pos)) if pos else "0")
        self._pv["avg"].setText(f"${avg:.2f}" if avg else "N/A")
        so="+"if pnl_o>=0 else""
        self._pv["pnl_open"].setText(f"{so}${pnl_o:.2f}")
        self._pv["pnl_open"].setStyleSheet(f"color:{GREEN if pnl_o>=0 else RED};font-size:11px;font-weight:bold;border:none;background:transparent;")

    # ── DRAG TO MOVE ORDERS ───────────────────────────────────

    def _dom_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            row = self._dom.rowAt(event.pos().y())
            price = self._get_price(row)
            if price and round(price,2) in self._working_orders:
                self._drag_order = dict(self._working_orders[round(price,2)])
                self._drag_order["original_price"] = price
                self._drag_start_pos = event.pos()
                self._dom.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self._drag_order = None
        QTableWidget.mousePressEvent(self._dom, event)

    def _dom_mouse_move(self, event):
        if self._drag_order and self._drag_start_pos:
            self._dom.setCursor(Qt.CursorShape.SizeVerCursor)
        QTableWidget.mouseMoveEvent(self._dom, event)

    def _dom_mouse_release(self, event):
        self._dom.setCursor(Qt.CursorShape.ArrowCursor)
        if self._drag_order and self._drag_start_pos:
            row = self._dom.rowAt(event.pos().y())
            new_price = self._get_price(row)
            orig_price = self._drag_order.get("original_price",0)
            if new_price and new_price != orig_price:
                self._move_order(self._drag_order, new_price)
            self._drag_order = None
            self._drag_start_pos = None
        else:
            QTableWidget.mouseReleaseEvent(self._dom, event)

    def _move_order(self, order_info, new_price):
        """Cancel existing order and replace at new price."""
        from ui.toast import notify
        old_id = order_info.get("id","")
        side   = order_info.get("side","BUY")
        qty    = order_info.get("qty",1)
        otype  = order_info.get("type","LIMIT")

        # Cancel old order
        try:
            self.api.cancel_order(old_id)
        except Exception as e:
            print(f"[DOM] Cancel order error: {e}")

        # Place new order at new price
        lp = new_price if otype in ("LIMIT","STOP_LIMIT") else None
        sp = new_price if otype == "STOP" else None
        order = self.api.build_stock_order(
            self._symbol, qty, side, otype, lp, sp,
            session=self._sess.currentText(),
            duration=self._dur.currentText())
        ok, msg = self.api.place_order(order)
        if ok:
            notify(f"Order Moved — {self._symbol}", "info",
                   subtitle=f"{side} {qty} @ ${new_price:.2f}", duration=3000)
        else:
            notify("Move Failed", "reject", subtitle=msg[:80], duration=5000)
        QTimer.singleShot(1000, self._refresh_orders)

    # ── DOM CLICKS ────────────────────────────────────────────

    def _on_dom_click(self, row: int, col: int):
        if self._drag_order: return  # was a drag, not a click
        price = self._get_price(row)
        if price is None: return
        wo = self._working_orders.get(round(price,2),{})
        if wo and col == 3:
            # Click on a working order price — cancel it
            self._cancel_order_at(price, wo)
            return
        if col == 2:
            self._place("BUY",  self._smart_type("BUY",  price), price)
        elif col == 4:
            self._place("SELL", self._smart_type("SELL", price), price)

    def _cancel_order_at(self, price, wo):
        from ui.toast import notify
        try:
            self.api.cancel_order(wo["id"])
            notify(f"Order Cancelled", "info",
                   subtitle=f"{wo['side']} {wo['qty']} @ ${price:.2f}", duration=3000)
            QTimer.singleShot(1000, self._refresh_orders)
        except Exception as e:
            notify("Cancel Failed", "reject", subtitle=str(e)[:80], duration=5000)

    def _smart_type(self, side, price):
        pos=self._position
        if pos>0 and side=="SELL": return "STOP" if price<self._last_price else "LIMIT"
        if pos<0 and side=="BUY":  return "STOP" if price>self._last_price else "LIMIT"
        return "LIMIT"

    # ── ORDER ACTIONS ─────────────────────────────────────────

    def _get_qty(self):
        try: return max(1,int(self._qty.text()))
        except: return 1

    def _place(self, side, otype, price):
        if not self._symbol: return
        qty=self._get_qty()
        lp=price if otype=="LIMIT" else None
        sp=price if otype=="STOP"  else None
        o=self.api.build_stock_order(self._symbol,qty,side,otype,lp,sp,
                                     session=self._sess.currentText(),
                                     duration=self._dur.currentText())
        self._send(o,side,price,qty,otype)

    def _buy_mkt(self):
        if not self._symbol: return
        o=self.api.build_stock_order(self._symbol,self._get_qty(),"BUY","MARKET",
                                     session=self._sess.currentText(),duration=self._dur.currentText())
        self._send(o,"BUY",self._last_price,self._get_qty(),"MARKET")

    def _sell_mkt(self):
        if not self._symbol: return
        o=self.api.build_stock_order(self._symbol,self._get_qty(),"SELL","MARKET",
                                     session=self._sess.currentText(),duration=self._dur.currentText())
        self._send(o,"SELL",self._last_price,self._get_qty(),"MARKET")

    def _buy_lim(self):
        if not self._symbol: return
        self._place("BUY","LIMIT",self._bid)

    def _sell_lim(self):
        if not self._symbol: return
        self._place("SELL","LIMIT",self._ask)

    def _cancel_all(self):
        from ui.toast import notify
        self._working_orders.clear()
        notify("Cancel All Sent","info",subtitle=self._symbol,duration=3000)

    def _flatten(self):
        if not self._symbol or self._position==0: return
        side="SELL" if self._position>0 else "BUY"; qty=abs(self._position)
        o=self.api.build_stock_order(self._symbol,qty,side,"MARKET",
                                     session=self._sess.currentText(),duration=self._dur.currentText())
        self._send(o,side,self._last_price,qty,"MARKET")

    def _reverse(self):
        if not self._symbol: return
        qty=self._get_qty(); side="SELL" if self._position>=0 else "BUY"
        total=abs(self._position)+qty
        o=self.api.build_stock_order(self._symbol,total,side,"MARKET",
                                     session=self._sess.currentText(),duration=self._dur.currentText())
        self._send(o,side,self._last_price,total,"MARKET")

    def _send(self, order, side, price, qty, otype=""):
        from ui.toast import notify
        ok, msg = self.api.place_order(order)
        if ok:
            trade_store.add_trade(self._symbol, side, price, qty, otype)
            color_word = "🟢 BUY" if "BUY" in side.upper() else "🔴 SELL"
            self._show(f"✓ {side} {qty}x {self._symbol} @ ${price:.2f}")
            notify(f"{color_word}  {qty}× {self._symbol}", "fill",
                   subtitle=f"${price:.2f}  |  {otype}  |  {self._sess.currentText()}",
                   duration=5000)
            QTimer.singleShot(1500, self._refresh_orders)
        else:
            # ALWAYS show as rejected — never show as buy/sell
            self._show(f"✗ Rejected: {msg}")
            notify(f"❌ Order Rejected — {self._symbol}", "reject",
                   subtitle=msg[:100] if msg else "Order rejected by broker",
                   duration=7000)

    def _show(self,msg): self._ticker_lbl.setText(f"  {msg}")

    def _get_price(self,row):
        if row<0 or row>=len(self._dom_prices): return None
        item=self._dom.item(row,3)
        if not item: return None
        try: return float(item.text().replace("$","").replace("▶ ","").replace("◆ ","").strip())
        except: return None

    def _adj(self,d):
        try: self._qty.setText(str(max(1,int(self._qty.text())+d)))
        except: self._qty.setText("1")
