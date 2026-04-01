"""Dashboard, Quotes, Portfolio pages — live auto-refresh, no filter: CSS."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QGridLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialog, QDialogButtonBox, QMessageBox, QAbstractItemView,
    QMenu, QCheckBox, QFrame, QDateEdit, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QPoint, QDate
from PyQt6.QtGui import QColor, QAction
from datetime import datetime, timedelta
import json, threading

from ui.widgets import StatCard, PageHeader, make_table, color_item, plain_item
from ui.order_dialog import OrderDialog
from ui.toast import notify
from api.schwab_client import SchwabAPI
from api.trade_store import trade_store

GREEN="#3fb950"; RED="#f85149"; BLUE="#58a6ff"; YELLOW="#d29922"; PURPLE="#8957e5"; DIM="#8b949e"; BG2="#161b22"; BG3="#21262d"


# ── THREADS ──────────────────────────────────────────────────────────────────

class LoadThread(QThread):
    done = pyqtSignal(dict, list)
    def __init__(self, api): super().__init__(); self.api=api
    def run(self):
        try:
            p=self.api.get_portfolio()
            from_d=(datetime.now()-timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")
            to_d=datetime.now().strftime("%Y-%m-%dT23:59:59Z")
            o=self.api.get_orders(from_date=from_d,to_date=to_d)
            self.done.emit(p,o)
        except: self.done.emit({}, [])

class QuoteThread(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api, syms): super().__init__(); self.api=api; self.symbols=syms
    def run(self):
        try: self.done.emit(self.api.get_quotes(self.symbols))
        except: self.done.emit({})

class PortfolioThread(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api): super().__init__(); self.api=api
    def run(self):
        try: self.done.emit(self.api.get_portfolio())
        except: self.done.emit({})

def _track(page, t):
    if not hasattr(page,"_threads"): page._threads=[]
    page._threads.append(t)
    t.finished.connect(lambda: page._threads.remove(t) if t in page._threads else None)


# ── DASHBOARD ────────────────────────────────────────────────────────────────

class DashboardPage(QWidget):
    def __init__(self, api):
        super().__init__(); self.api=api; self._threads=[]; self._all_orders=[]
        self._build()
        self._timer=QTimer(); self._timer.timeout.connect(self.on_show); self._timer.start(15000)

    def _build(self):
        vbox=QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)
        vbox.addWidget(PageHeader("📊  Dashboard", on_refresh=self.on_show))

        # Filter bar
        fbar=QWidget(); fbar.setFixedHeight(48)
        fbar.setStyleSheet(f"background:{BG3}; border-bottom:1px solid #30363d;")
        fb=QHBoxLayout(fbar); fb.setContentsMargins(16,0,16,0); fb.setSpacing(10)
        fb.addWidget(QLabel("Filter:"))

        self._filter_sym=QLineEdit(); self._filter_sym.setPlaceholderText("Symbol"); self._filter_sym.setFixedWidth(90)
        self._filter_sym.textChanged.connect(self._apply_filter); fb.addWidget(self._filter_sym)

        self._filter_side=QComboBox(); self._filter_side.addItems(["All Sides","BUY","SELL"])
        self._filter_side.setFixedWidth(100); self._filter_side.currentTextChanged.connect(self._apply_filter)
        fb.addWidget(self._filter_side)

        self._filter_status=QComboBox(); self._filter_status.addItems(["All Status","FILLED","WORKING","CANCELLED"])
        self._filter_status.setFixedWidth(120); self._filter_status.currentTextChanged.connect(self._apply_filter)
        fb.addWidget(self._filter_status)

        fb.addWidget(QLabel("From:"))
        self._date_from=QDateEdit(QDate.currentDate().addDays(-7))
        self._date_from.setDisplayFormat("MM/dd/yyyy"); self._date_from.setFixedWidth(110)
        self._date_from.dateChanged.connect(self.on_show); fb.addWidget(self._date_from)

        fb.addWidget(QLabel("To:"))
        self._date_to=QDateEdit(QDate.currentDate())
        self._date_to.setDisplayFormat("MM/dd/yyyy"); self._date_to.setFixedWidth(110)
        self._date_to.dateChanged.connect(self.on_show); fb.addWidget(self._date_to)

        clear_btn=QPushButton("Clear"); clear_btn.setFixedHeight(30)
        clear_btn.clicked.connect(self._clear_filters); fb.addWidget(clear_btn)
        fb.addStretch()
        vbox.addWidget(fbar)

        body=QWidget(); bl=QVBoxLayout(body); bl.setContentsMargins(24,16,24,16); bl.setSpacing(14)

        cards=QHBoxLayout(); cards.setSpacing(12); self._cards={}
        for lbl,col in [("Net Liquidation",BLUE),("Cash Balance",GREEN),("Option Buying Power",PURPLE if 'PURPLE' in dir() else "#8957e5"),("Day P&L",GREEN),("Open P&L",GREEN),("Positions",BLUE)]:
            c=StatCard(lbl,"—",col); cards.addWidget(c); self._cards[lbl]=c
        bl.addLayout(cards)

        lbl=QLabel("Orders"); lbl.setStyleSheet("color:#58a6ff; font-weight:bold; font-size:13px;")
        bl.addWidget(lbl)
        self._table=make_table(["Time","Symbol","Side","Qty","Type","Price","Status"],stretch_col=1)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().setDragEnabled(True)
        for i in range(7): self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        bl.addWidget(self._table,stretch=1)

        self._status=QLabel(""); self._status.setStyleSheet(f"color:{DIM}; font-size:10px;")
        bl.addWidget(self._status)
        vbox.addWidget(body,stretch=1)

    def on_show(self):
        from_d=self._date_from.date().toString("yyyy-MM-dd")+"T00:00:00Z"
        to_d=self._date_to.date().toString("yyyy-MM-dd")+"T23:59:59Z"
        t=LoadThread(self.api); t.done.connect(self._populate); _track(self,t); t.start()

    def _populate(self, portfolio, orders):
        self._all_orders=orders
        if portfolio:
            acct=portfolio.get("securitiesAccount",{}); bal=acct.get("currentBalances",{})
            pos=acct.get("positions",[]); nl=bal.get("liquidationValue",0); cash=bal.get("cashBalance",0)
            dp=sum(p.get("currentDayProfitLoss",0) for p in pos); op=sum(p.get("unrealizedProfitLoss",0) for p in pos)
            obp = bal.get("optionBuyingPower", bal.get("buyingPowerForTrade", 0))
            self._cards["Net Liquidation"].set_value(f"${nl:,.2f}",BLUE)
            self._cards["Cash Balance"].set_value(f"${cash:,.2f}",GREEN)
            self._cards["Option Buying Power"].set_value(f"${obp:,.2f}","#8957e5")
            self._cards["Day P&L"].set_value(f"{'+'if dp>=0 else''}${dp:,.2f}",GREEN if dp>=0 else RED)
            self._cards["Open P&L"].set_value(f"{'+'if op>=0 else''}${op:,.2f}",GREEN if op>=0 else RED)
            self._cards["Positions"].set_value(str(len(pos)),BLUE)
        self._apply_filter()

    def _apply_filter(self):
        sym_f   = self._filter_sym.text().strip().upper()
        side_f  = self._filter_side.currentText()
        stat_f  = self._filter_status.currentText()
        from_dt = self._date_from.date().toPyDate()
        to_dt   = self._date_to.date().toPyDate()

        self._table.setRowCount(0)
        for o in self._all_orders:
            legs   = o.get("orderLegCollection",[{}])
            inst   = legs[0].get("instrument",{}) if legs else {}
            sym    = inst.get("symbol","—")
            side   = legs[0].get("instruction","—") if legs else "—"
            status = o.get("status","—")
            # Date filter
            entered = o.get("enteredTime","")
            if entered:
                try:
                    from datetime import datetime as dt2
                    order_date = dt2.fromisoformat(entered.replace("Z","")).date()
                    if order_date < from_dt or order_date > to_dt: continue
                except: pass
            # Symbol filter
            if sym_f and sym_f not in sym.upper(): continue
            # Side filter
            if side_f not in ("All Sides","") and side_f not in side.upper(): continue
            # Status filter
            if stat_f not in ("All Status","") and stat_f != status: continue

            row = self._table.rowCount(); self._table.insertRow(row)
            for col,(val,clr) in enumerate([
                (entered[:16].replace("T"," ") if entered else "—", "#e6edf3"),
                (sym,BLUE),(side,GREEN if "BUY" in side else RED),
                (str(o.get("quantity","—")),"#e6edf3"),
                (o.get("orderType","—"),"#e6edf3"),
                (str(o.get("price","MKT")),"#e6edf3"),
                (status,GREEN if status=="FILLED" else YELLOW if status=="WORKING" else DIM),
            ]): self._table.setItem(row,col,color_item(val,clr))
        self._status.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}  |  {self._table.rowCount()} orders shown")

    def _clear_filters(self):
        self._filter_sym.clear(); self._filter_side.setCurrentIndex(0); self._filter_status.setCurrentIndex(0)


# ── QUOTES ───────────────────────────────────────────────────────────────────

DEFAULT_WATCHLIST=["SPY","QQQ","AAPL","MSFT","TSLA","NVDA","AMZN","META"]

class QuotesPage(QWidget):
    def __init__(self, api):
        super().__init__(); self.api=api; self._threads=[]; self.watchlist=list(DEFAULT_WATCHLIST)
        self._chart_nav=None
        self._build()
        self._timer=QTimer(); self._timer.timeout.connect(self.on_show); self._timer.start(1000)

    def _build(self):
        vbox=QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)
        vbox.addWidget(PageHeader("📈  Live Quotes", on_refresh=self.on_show))
        tb=QWidget(); tb.setFixedHeight(52); tb.setStyleSheet(f"background:{BG3}; border-bottom:1px solid #30363d;")
        tbox=QHBoxLayout(tb); tbox.setContentsMargins(16,0,16,0); tbox.setSpacing(8)
        tbox.addWidget(QLabel("Symbol:"))
        self._sym_input=QLineEdit(); self._sym_input.setPlaceholderText("e.g. GOOG"); self._sym_input.setFixedWidth(120)
        # Auto-capitalize as user types
        self._sym_input.textChanged.connect(self._auto_caps_input)
        self._sym_input.returnPressed.connect(self._add_symbol)
        tbox.addWidget(self._sym_input)
        ab=QPushButton("+ Add"); ab.setObjectName("blue_btn"); ab.setFixedHeight(32)
        ab.clicked.connect(self._add_symbol); tbox.addWidget(ab)
        rb=QPushButton("✕ Remove"); rb.setFixedHeight(32)
        rb.setStyleSheet("QPushButton{color:#f85149;border:1px solid #f85149;border-radius:4px;} QPushButton:hover{background:#da3633;color:white;}")
        rb.clicked.connect(self._remove_selected); tbox.addWidget(rb)
        tbox.addStretch()
        hint=QLabel("Double-click → Charts"); hint.setStyleSheet(f"color:{DIM}; font-size:10px;")
        tbox.addWidget(hint)
        vbox.addWidget(tb)
        self._table=make_table(["Symbol","Last","Bid","Ask","Change","Chg%","Volume","Open","High","Low"],stretch_col=0)
        # Make columns movable and resizable
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().setDragEnabled(True)
        for i in range(10): self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self._table.doubleClicked.connect(self._on_double_click)
        vbox.addWidget(self._table,stretch=1)
        self._status=QLabel(""); self._status.setStyleSheet(f"color:{DIM}; font-size:10px; padding:4px 16px;")
        vbox.addWidget(self._status)

    def set_chart_navigator(self, cb): self._chart_nav=cb

    def _on_double_click(self, index):
        item=self._table.item(index.row(),0)
        if item and self._chart_nav: self._chart_nav(item.text())

    def on_show(self):
        if not self.watchlist: return
        t=QuoteThread(self.api,list(self.watchlist)); t.done.connect(self._populate)
        _track(self,t); t.start()

    def _populate(self, data):
        # Save selected symbols before refresh
        selected_syms = set()
        for item in self._table.selectedItems():
            row_item = self._table.item(item.row(), 0)
            if row_item: selected_syms.add(row_item.text())

        self._table.setRowCount(0)
        for sym in self.watchlist:
            q=data.get(sym,{}).get("quote",{}); last=q.get("lastPrice",q.get("mark",0))
            bid=q.get("bidPrice",0); ask=q.get("askPrice",0); chg=q.get("netChange",0)
            chgp=q.get("netPercentChangeInDouble",0); vol=q.get("totalVolume",0)
            color=GREEN if chg>=0 else RED; sign="+" if chg>=0 else ""
            row=self._table.rowCount(); self._table.insertRow(row)
            for col,(val,clr) in enumerate([
                (sym,BLUE),(f"{last:.2f}",color),(f"{bid:.2f}","#e6edf3"),(f"{ask:.2f}","#e6edf3"),
                (f"{sign}{chg:.2f}",color),(f"{sign}{chgp:.2f}%",color),
                (f"{int(vol):,}","#e6edf3"),(f"{q.get('openPrice',0):.2f}","#e6edf3"),
                (f"{q.get('highPrice',0):.2f}","#e6edf3"),(f"{q.get('lowPrice',0):.2f}","#e6edf3"),
            ]): self._table.setItem(row,col,color_item(val,clr))
        # Restore selection
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.text() in selected_syms:
                self._table.selectRow(row)

        self._status.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}  |  {len(self.watchlist)} symbols")

    def _auto_caps_input(self, text):
        upper = text.upper()
        if upper != text:
            cur = self._sym_input.cursorPosition()
            self._sym_input.blockSignals(True)
            self._sym_input.setText(upper)
            self._sym_input.setCursorPosition(cur)
            self._sym_input.blockSignals(False)

    def _add_symbol(self):
        sym=self._sym_input.text().strip().upper()
        if not sym: return
        if sym in self.watchlist:
            self._sym_input.clear(); return
        # Validate ticker exists
        import threading
        def validate():
            q = self.api.get_quote(sym)
            quote = q.get("quote", {})
            if not quote or quote.get("lastPrice", 0) == 0:
                self._status.setText(f"❌ '{sym}' not found or invalid ticker")
                return
            self.watchlist.append(sym)
            self._sym_input.clear()
            self.on_show()
        threading.Thread(target=validate, daemon=True).start()

    def _remove_selected(self):
        rows=set(i.row() for i in self._table.selectedItems())
        for row in sorted(rows,reverse=True):
            item=self._table.item(row,0)
            if item and item.text() in self.watchlist: self.watchlist.remove(item.text())
        self.on_show()


# ── PORTFOLIO ─────────────────────────────────────────────────────────────────

class PortfolioPage(QWidget):
    def __init__(self, api):
        super().__init__(); self.api=api; self._threads=[]; self._build()
        self._timer=QTimer(); self._timer.timeout.connect(self.on_show); self._timer.start(10000)

    def _build(self):
        vbox=QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)
        vbox.addWidget(PageHeader("💼  Portfolio", on_refresh=self.on_show))
        body=QWidget(); bl=QVBoxLayout(body); bl.setContentsMargins(24,16,24,16); bl.setSpacing(14)
        cards=QHBoxLayout(); cards.setSpacing(12); self._cards={}
        for lbl,col in [("Net Liquidation",BLUE),("Cash",GREEN),("Option BP","#8957e5"),("Day P&L",GREEN),("Open P&L",GREEN),("Margin",YELLOW)]:
            c=StatCard(lbl,"—",col); cards.addWidget(c); self._cards[lbl]=c
        bl.addLayout(cards)
        hint=QLabel("Right-click to trade  |  Double-click → Charts")
        hint.setStyleSheet(f"color:{DIM}; font-size:10px;"); bl.addWidget(hint)
        self._table=make_table(["Symbol","Asset","Qty","Avg","Last","Mkt Val","Day P&L","Day%","Open P&L","Open%"],stretch_col=0)
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().setDragEnabled(True)
        for i in range(10): self._table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._ctx_menu)
        self._table.setSortingEnabled(True)
        bl.addWidget(self._table,stretch=1)
        self._status=QLabel(""); self._status.setStyleSheet(f"color:{DIM}; font-size:10px;"); bl.addWidget(self._status)
        vbox.addWidget(body,stretch=1)

    def _ctx_menu(self, pos):
        row=self._table.rowAt(pos.y())
        if row<0: return
        self._table.selectRow(row)
        sym=self._table.item(row,0).text(); asset=self._table.item(row,1).text()
        qty=self._table.item(row,2).text(); last=self._table.item(row,4).text().replace("$","")
        is_opt=asset=="OPTION"
        menu=QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{BG2};border:1px solid #30363d;color:#e6edf3;font-size:12px;}} QMenu::item{{padding:8px 24px;}} QMenu::item:selected{{background:#1f6feb;}} QMenu::separator{{background:#30363d;height:1px;margin:4px 0;}}")
        hdr=QAction(f"  {sym}  —  {qty}",self); hdr.setEnabled(False); menu.addAction(hdr); menu.addSeparator()
        if is_opt:
            for inst,label in [("BUY_TO_OPEN","🟢  Buy to Open"),("BUY_TO_CLOSE","🟢  Buy to Close"),("SELL_TO_OPEN","🔴  Sell to Open"),("SELL_TO_CLOSE","🔴  Sell to Close")]:
                a=QAction(label,self); a.triggered.connect(lambda _,i=inst,s=sym,p=last: OrderDialog(self,api=self.api,pre_fill={"symbol":s,"instruction":i,"price":float(p),"asset_type":"OPTION"},on_placed=self.on_show).exec()); menu.addAction(a)
            menu.addSeparator()
            ca=QAction(f"⚡  Close All ({qty})",self); ca.triggered.connect(lambda: self._market_close(sym,qty,"OPTION")); menu.addAction(ca)
        else:
            for inst,label in [("BUY","🟢  Buy More"),("SELL","🔴  Sell Shares")]:
                a=QAction(label,self); a.triggered.connect(lambda _,i=inst,s=sym,p=last: OrderDialog(self,api=self.api,pre_fill={"symbol":s,"instruction":i,"price":float(p),"asset_type":"EQUITY"},on_placed=self.on_show).exec()); menu.addAction(a)
            sa=QAction(f"🔴  Sell ALL {qty}",self); sa.triggered.connect(lambda: self._market_close(sym,qty,"EQUITY")); menu.addAction(sa)
            menu.addSeparator()
            stop=QAction("🛑  Stop Loss",self); stop.triggered.connect(lambda: OrderDialog(self,api=self.api,pre_fill={"symbol":sym,"instruction":"SELL","price":float(last),"asset_type":"EQUITY"},on_placed=self.on_show).exec()); menu.addAction(stop)
            qa=QAction("📊  Quick Quote",self); qa.triggered.connect(lambda: self._show_quote(sym)); menu.addAction(qa)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _market_close(self, sym, qty, asset):
        try: qty_i=int(qty)
        except: qty_i=1
        if asset=="OPTION": order=self.api.build_option_order(sym,qty_i,"SELL_TO_CLOSE","MARKET")
        else: order=self.api.build_stock_order(sym,qty_i,"SELL","MARKET")
        ok,msg=self.api.place_order(order)
        (QMessageBox.information if ok else QMessageBox.critical)(self,"Result",msg)
        if ok: self.on_show()

    def _show_quote(self, sym):
        def fetch():
            q=self.api.get_quote(sym).get("quote",{})
            last=q.get("lastPrice",0); bid=q.get("bidPrice",0); ask=q.get("askPrice",0)
            chg=q.get("netChange",0); chgp=q.get("netPercentChangeInDouble",0); vol=q.get("totalVolume",0)
            sign="+" if chg>=0 else ""
            QMessageBox.information(self,f"Quote — {sym}",f"Last: ${last:.2f}\nBid: ${bid:.2f}\nAsk: ${ask:.2f}\nChg: {sign}{chg:.2f} ({sign}{chgp:.2f}%)\nVol: {int(vol):,}")
        threading.Thread(target=fetch,daemon=True).start()

    def on_show(self):
        t=PortfolioThread(self.api); t.done.connect(self._populate); _track(self,t); t.start()

    def _populate(self, data):
        if not data: return
        acct=data.get("securitiesAccount",{}); bal=acct.get("currentBalances",{}); positions=acct.get("positions",[])
        nl=bal.get("liquidationValue",0); cash=bal.get("cashBalance",0); margin=bal.get("maintenanceRequirement",0)
        dp=sum(p.get("currentDayProfitLoss",0) for p in positions); op=sum(p.get("unrealizedProfitLoss",0) for p in positions)
        def fmt(v): return("+"if v>=0 else"")+f"${v:,.2f}"
        obp = bal.get("optionBuyingPower", bal.get("buyingPowerForTrade", 0))
        self._cards["Net Liquidation"].set_value(f"${nl:,.2f}",BLUE); self._cards["Cash"].set_value(f"${cash:,.2f}",GREEN)
        self._cards["Option BP"].set_value(f"${obp:,.2f}","#8957e5")
        self._cards["Day P&L"].set_value(fmt(dp),GREEN if dp>=0 else RED); self._cards["Open P&L"].set_value(fmt(op),GREEN if op>=0 else RED)
        self._cards["Margin"].set_value(f"${margin:,.2f}",YELLOW)
        self._table.setRowCount(0)
        for p in positions:
            inst=p.get("instrument",{}); sym=inst.get("symbol","—"); asset=inst.get("assetType","—")
            qty=p.get("longQuantity",p.get("shortQuantity",0)); avg=p.get("averagePrice",0)
            mkt=p.get("marketValue",0); last=mkt/qty if qty else 0
            dp2=p.get("currentDayProfitLoss",0); dp2p=p.get("currentDayProfitLossPercentage",0)
            op2=p.get("unrealizedProfitLoss",0); op2p=(op2/(avg*qty)*100) if avg and qty else 0
            row=self._table.rowCount(); self._table.insertRow(row)
            sd="+"if dp2>=0 else""; so="+"if op2>=0 else""
            for col,(val,clr) in enumerate([
                (sym,BLUE),(asset,"#e6edf3"),(str(int(qty)),"#e6edf3"),(f"${avg:.2f}","#e6edf3"),(f"${last:.2f}","#e6edf3"),
                (f"${mkt:,.2f}","#e6edf3"),(f"{sd}${dp2:,.2f}",GREEN if dp2>=0 else RED),(f"{sd}{dp2p:.2f}%",GREEN if dp2>=0 else RED),
                (f"{so}${op2:,.2f}",GREEN if op2>=0 else RED),(f"{so}{op2p:.2f}%",GREEN if op2>=0 else RED),
            ]): self._table.setItem(row,col,color_item(val,clr))
        self._status.setText(f"{len(positions)} positions  |  Updated {datetime.now().strftime('%H:%M:%S')}")
