"""Dashboard, Quotes, Portfolio pages — live auto-refresh, no filter: CSS."""

from PyQt6.QtWidgets import (
    QDateEdit, QTabWidget, QTextEdit,
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QGridLayout, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
    QDialog, QDialogButtonBox, QMessageBox, QAbstractItemView,
    QMenu, QCheckBox, QFrame, QSplitter
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QDate, QPoint, QDate
from PyQt6.QtGui import QColor, QAction, QCursor
from datetime import datetime, timedelta
import json, threading

from ui.widgets import StatCard, PageHeader, make_table, color_item, plain_item
from ui.order_dialog import OrderDialog
from ui.toast import notify
from ui.table_utils import setup_table, format_option_symbol
from api.schwab_client import SchwabAPI
from api.trade_store import trade_store

GREEN="#3fb950"; RED="#f85149"; BLUE="#58a6ff"; YELLOW="#d29922"; PURPLE="#8957e5"; DIM="#8b949e"; BG2="#161b22"; BG3="#21262d"

def to_mt(dt_str: str) -> str:
    """Convert ISO timestamp to Mountain Time string."""
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(dt_str.replace("Z","+00:00"))
        mt = dt.astimezone(timezone(timedelta(hours=-7)))  # MST (UTC-6)
        return mt.strftime("%I:%M:%S %p  %m/%d/%Y MST")
    except:
        return dt_str[:16].replace("T"," ")

def now_mt() -> str:
    from datetime import datetime, timezone, timedelta
    mt = datetime.now(timezone(timedelta(hours=-7)))
    return mt.strftime("%H:%M:%S MST")


DEFAULT_WATCHLIST = ["SPY","QQQ","AAPL","TSLA","NVDA","AMD","META","MSFT","AMZN","GOOGL"]


# ── THREADS ──────────────────────────────────────────────────────────────────

class LoadThread(QThread):
    done = pyqtSignal(dict, list, list)  # portfolio, filtered_orders, ytd_orders
    def __init__(self, api, from_d=None, to_d=None):
        super().__init__(); self.api=api
        from datetime import datetime, timedelta
        self.from_d = from_d or (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        self.to_d   = to_d   or datetime.now().strftime("%Y-%m-%dT23:59:59Z")
    def run(self):
        try:
            p = self.api.get_portfolio()
            from datetime import datetime, timedelta
            # YTD always fixed — Jan 1 to now regardless of filter
            ytd_from = datetime.now().replace(month=1,day=1,hour=0,minute=0,second=0).strftime("%Y-%m-%dT00:00:00Z")
            ytd_to   = datetime.now().strftime("%Y-%m-%dT23:59:59Z")
            ytd_raw  = self.api.get_orders(from_date=ytd_from, to_date=ytd_to) or []
            ytd_orders = list(ytd_raw) if isinstance(ytd_raw, list) else []
            from_d, to_d = self.from_d, self.to_d

            all_orders = []
            seen_ids   = set()

            # 1. Get all orders (no filter)
            try:
                raw = self.api.get_orders(from_date=from_d, to_date=to_d)
                for o in (raw if isinstance(raw, list) else []):
                    oid = str(o.get("orderId",""))
                    if oid not in seen_ids:
                        seen_ids.add(oid); all_orders.append(o)
            except Exception as e:
                print(f"[Dashboard] get_orders error: {e}")

            # 2. Dedicated working orders call (catches any missed by #1)
            try:
                working = self.api.get_working_orders()
                print(f"[Dashboard] get_working_orders returned: {len(working) if isinstance(working,list) else working}")
                for o in (working if isinstance(working, list) else []):
                    oid = str(o.get("orderId",""))
                    status = o.get("status","?")
                    print(f"[Dashboard] Working order: {oid} status={status} sym={o.get('orderLegCollection',[{}])[0].get('instrument',{}).get('symbol','?')}")
                    if oid not in seen_ids:
                        seen_ids.add(oid); all_orders.append(o)
            except Exception as e:
                print(f"[Dashboard] get_working_orders error: {e}")

            statuses = set(str(o.get("status","?")) for o in all_orders)
            print(f"[Dashboard] {len(all_orders)} orders — statuses: {statuses}")
            self.done.emit(dict(p) if isinstance(p,dict) else {}, all_orders, ytd_orders)
        except Exception as e:
            import traceback; traceback.print_exc()
            self.done.emit({}, [], [])

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
        try:
            result = self.api.get_portfolio()
            self.done.emit(dict(result) if isinstance(result, dict) else {})
        except: self.done.emit({})

def _track(page, t):
    if not hasattr(page,"_threads"): page._threads=[]
    page._threads.append(t)
    t.finished.connect(lambda: page._threads.remove(t) if t in page._threads else None)


# ── DASHBOARD ────────────────────────────────────────────────────────────────

DATE_FILTERS = [
    "Today", "Yesterday", "This Week", "Last 7 Days",
    "Last Week", "This Month", "Last Month", "Custom Date"
]


def get_date_range(filter_text: str) -> tuple:
    """Return (from_date_str, to_date_str) for the given filter."""
    from datetime import datetime, timedelta
    now = datetime.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    if filter_text == "Today":
        from_d = today_start
        to_d   = now
    elif filter_text == "Yesterday":
        from_d = today_start - timedelta(days=1)
        to_d   = today_start - timedelta(seconds=1)
    elif filter_text == "This Week":
        from_d = today_start - timedelta(days=today_start.weekday())
        to_d   = now
    elif filter_text == "Last 7 Days":
        from_d = today_start - timedelta(days=7)
        to_d   = now
    elif filter_text == "Last Week":
        week_start = today_start - timedelta(days=today_start.weekday())
        from_d = week_start - timedelta(weeks=1)
        to_d   = week_start - timedelta(seconds=1)
    elif filter_text == "This Month":
        from_d = today_start.replace(day=1)
        to_d   = now
    elif filter_text == "Last Month":
        first_this = today_start.replace(day=1)
        from_d = (first_this - timedelta(days=1)).replace(day=1)
        to_d   = first_this - timedelta(seconds=1)
    else:  # All / Custom
        from_d = today_start - timedelta(days=364)
        to_d   = now

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return from_d.strftime(fmt), to_d.strftime(fmt)


class DashboardPage(QWidget):
    """
    Dashboard v12 — full trading hub
    - Account stat cards
    - Open Positions tab (right-click: flatten/buy limit/sell limit)
    - Pending Orders tab (right-click: cancel)
    - Today's Fills tab
    - Rejected Orders tab
    Auto-refreshes every 3s. Auto-fit columns.
    """

    def __init__(self, api):
        super().__init__()
        self.api = api
        self._threads = []
        self._all_orders = []
        self._positions  = []
        self._build()
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)

    def _build(self):
        vbox = QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG2};border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,0,16,0)
        title = QLabel("📊  Dashboard")
        title.setStyleSheet(f"color:{BLUE};font-size:16px;font-weight:bold;")
        hh.addWidget(title); hh.addStretch()
        self._updated_lbl = QLabel("")
        self._updated_lbl.setStyleSheet(f"color:{DIM};font-size:10px;")
        hh.addWidget(self._updated_lbl)

        # Date filter
        from PyQt6.QtWidgets import QComboBox as _CB
        self._date_filter = _CB()
        self._date_filter.addItems(DATE_FILTERS)
        self._date_filter.setCurrentText("Today")
        self._date_filter.setFixedHeight(28)
        self._date_filter.setFixedWidth(130)
        self._date_filter.setStyleSheet(f"QComboBox{{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;padding:2px 8px;font-size:11px;font-weight:bold;}} QComboBox QAbstractItemView{{background:{BG2};color:#e6edf3;selection-background-color:#1f6feb;}} QComboBox::drop-down{{border:none;}} QComboBox::down-arrow{{color:#58a6ff;}}")
        self._date_filter.currentTextChanged.connect(self._on_date_filter_changed)
        hh.addWidget(self._date_filter)
        vbox.addWidget(hdr)

        # Stat cards
        cards_w = QWidget(); cards_w.setFixedHeight(76)
        cards_w.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        ch = QHBoxLayout(cards_w); ch.setContentsMargins(12,8,12,8); ch.setSpacing(10)
        self._cards = {}
        for lbl,col in [("Net Liq",BLUE),("Cash",GREEN),
                         ("Day P&L",GREEN),("Open P&L",GREEN),
                         ("YTD P&L",GREEN),("Positions",BLUE)]:
            card = StatCard(lbl,"—",col); ch.addWidget(card); self._cards[lbl]=card
        vbox.addWidget(cards_w)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane{{border:none;background:{BG2};}}
            QTabBar::tab{{background:{BG3};color:{DIM};padding:8px 18px;border:none;
                         border-right:1px solid #30363d;font-size:12px;min-width:120px;}}
            QTabBar::tab:selected{{background:{BG2};color:#e6edf3;border-bottom:2px solid {BLUE};}}
            QTabBar::tab:hover{{color:#e6edf3;}}
        """)

        tbl_style = f"""
            QTableWidget{{background:{BG2};border:none;gridline-color:#21262d;
                         color:#e6edf3;font-family:Consolas;font-size:12px;}}
            QTableWidget::item{{padding:4px 10px;}}
            QTableWidget::item:selected{{background:#1f6feb44;color:#fff;}}
            QHeaderView::section{{background:{BG3};padding:6px 10px;border:none;
                                  border-right:1px solid #30363d;
                                  border-bottom:2px solid #58a6ff;
                                  font-weight:bold;font-size:11px;color:#e6edf3;}}
        """

        def mk_tbl(cols):
            t = QTableWidget(0,len(cols))
            t.setHorizontalHeaderLabels(cols)
            t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            t.setShowGrid(True); t.setAlternatingRowColors(False)
            t.horizontalHeader().setSectionsMovable(True)
            t.verticalHeader().setVisible(False)  # hide row numbers
            t.setStyleSheet(tbl_style)
            return t

        # Tab 0 — Trade Journal (first)
        from ui.trade_journal import TradeJournalPage
        self._journal_page = TradeJournalPage(self.api)
        self._tabs.addTab(self._journal_page, "📓  Journal")

        # Tab 1 — Open Positions
        self._pos_tbl = mk_tbl(["Symbol","Side","Qty","Avg Price","Last","Mkt Value","Day P&L","Open P&L","Asset"])
        self._pos_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._pos_tbl.customContextMenuRequested.connect(self._pos_rclick)
        self._tabs.addTab(self._pos_tbl, "📊  Open Positions")

        # Tab 2 — Pending Orders
        self._pend_tbl = mk_tbl(["Symbol","Side","Type","Qty","Price","Stop","Session","Duration","Status","Time"])
        self._pend_tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._pend_tbl.customContextMenuRequested.connect(self._pend_rclick)
        self._tabs.addTab(self._pend_tbl, "⏳  Working Orders")

        # Tab 3 — Today's Fills
        self._fill_tbl = mk_tbl(["Symbol","Side","Type","Qty","Price","Status","Time"])
        self._tabs.addTab(self._fill_tbl, "✅  Fills")

        # Tab 4 — Rejected Orders
        self._rej_tbl = mk_tbl(["Symbol","Side","Type","Qty","Price","Reason","Time"])
        self._tabs.addTab(self._rej_tbl, "❌  Rejected / Canceled")

        # Tab 5 — Automation / Webhook
        self._tabs.addTab(self._build_automation_tab(), "🤖  Automation")

        vbox.addWidget(self._tabs, stretch=1)

        # Status bar
        self._status = QLabel("  Loading…")
        self._status.setFixedHeight(22)
        self._status.setStyleSheet(f"color:{DIM};font-size:10px;background:{BG3};border-top:1px solid #30363d;padding:0 8px;")
        vbox.addWidget(self._status)

    def _ci(self, text, color="#e6edf3"):
        item = QTableWidgetItem(str(text))
        item.setForeground(QColor(color))
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _autofit(self, tbl):
        setup_table(tbl)

    def _refresh(self):
        filter_text = self._date_filter.currentText() if hasattr(self,'_date_filter') else "Today"
        if filter_text == "Custom Date" and hasattr(self,'_custom_from'):
            from_d = self._custom_from.date().toString("yyyy-MM-dd") + "T00:00:00Z"
            to_d   = self._custom_to.date().toString("yyyy-MM-dd") + "T23:59:59Z"
        else:
            from_d, to_d = get_date_range(filter_text)
        t = LoadThread(self.api, from_d, to_d)
        t.done.connect(self._populate)
        self._threads.append(t)
        t.finished.connect(lambda: self._threads.remove(t) if t in self._threads else None)
        t.start()

    def _populate(self, portfolio: dict, all_orders: list, ytd_orders: list = None):
        if ytd_orders is None: ytd_orders = all_orders
        self._all_orders = all_orders
        acct = portfolio.get("securitiesAccount",{})
        bal  = acct.get("currentBalances", acct.get("projectedBalances",{}))
        pos  = acct.get("positions",[])
        self._positions = pos

        # Cards
        nl   = bal.get("liquidationValue", bal.get("netLiquidation",0))
        cash = bal.get("cashBalance",0)
        # Day P&L from positions
        dp   = sum(float(p.get("currentDayProfitLoss",0) or 0) for p in pos)
        op   = sum(float(p.get("longOpenProfitLoss", p.get("shortOpenProfitLoss",0)) or 0) for p in pos)
        # YTD P&L — always from ytd_orders (Jan 1 to now, ignores date filter)
        ytd = sum(
            float(o.get("price",0) or 0) *
            float(o.get("filledQuantity", o.get("quantity",0)) or 0) *
            (-1 if o.get("orderLegCollection",[{}])[0].get("instruction","").upper() in
             ("BUY","BUY_TO_OPEN","BUY_TO_COVER") else 1)
            for o in ytd_orders
            if o.get("status") in ("FILLED","PART_FILLED")
        )
        def fmt(v): return f"{'+'if v>=0 else''}${v:,.2f}"
        self._cards["Net Liq"].set_value(f"${nl:,.2f}",BLUE)
        self._cards["Cash"].set_value(f"${cash:,.2f}",GREEN)
        self._cards["Day P&L"].set_value(fmt(dp),GREEN if dp>=0 else RED)
        self._cards["Open P&L"].set_value(fmt(op),GREEN if op>=0 else RED)
        self._cards["YTD P&L"].set_value(fmt(ytd),GREEN if ytd>=0 else RED)
        self._cards["Positions"].set_value(str(len(pos)),BLUE)

        ci = self._ci

        # Open Positions
        self._pos_tbl.setRowCount(0)
        for p in pos:
            inst      = p.get("instrument",{})
            sym       = inst.get("symbol","—")
            asset     = inst.get("assetType","EQUITY")
            long_qty  = p.get("longQuantity",0)
            short_qty = p.get("shortQuantity",0)
            qty       = long_qty if long_qty>0 else -short_qty
            side      = "LONG" if qty>0 else "SHORT"
            avg       = p.get("averagePrice",0)
            mkt_val   = p.get("marketValue",0)
            day_pnl   = p.get("currentDayProfitLoss",0)
            open_pnl  = p.get("longOpenProfitLoss",p.get("shortOpenProfitLoss",0))
            last_px   = mkt_val/abs(qty) if qty else 0
            sc = GREEN if side=="LONG" else RED
            dc = GREEN if day_pnl>=0 else RED
            oc = GREEN if open_pnl>=0 else RED
            row = self._pos_tbl.rowCount(); self._pos_tbl.insertRow(row)
            self._pos_tbl.setRowHeight(row,24)
            self._pos_tbl.setItem(row,0,ci(format_option_symbol(sym) if len(sym)>6 else sym,BLUE))
            self._pos_tbl.setItem(row,1,ci(side,sc))
            self._pos_tbl.setItem(row,2,ci(str(abs(int(qty)))))
            self._pos_tbl.setItem(row,3,ci(f"${avg:.2f}"))
            self._pos_tbl.setItem(row,4,ci(f"${last_px:.2f}"))
            self._pos_tbl.setItem(row,5,ci(f"${mkt_val:,.2f}"))
            self._pos_tbl.setItem(row,6,ci(fmt(day_pnl),dc))
            self._pos_tbl.setItem(row,7,ci(fmt(open_pnl),oc))
            self._pos_tbl.setItem(row,8,ci(asset,DIM))
        setup_table(self._pos_tbl)

        # Schwab API documented statuses
        WORKING_STATUSES = {
            "WORKING","QUEUED","ACCEPTED","PENDING_ACTIVATION",
            "AWAITING_PARENT_ORDER","AWAITING_CONDITION",
            "AWAITING_STOP_CONDITION","AWAITING_MANUAL_REVIEW",
            "AWAITING_UR_OUT","NEW","AWAITING_RELEASE_TIME",
            "PENDING_ACKNOWLEDGEMENT","PENDING_RECALL"
        }
        FILLED_STATUSES   = {"FILLED","PART_FILLED"}
        REJECTED_STATUSES = {"REJECTED","CANCELED","EXPIRED","REPLACED",
                             "PENDING_CANCEL","PENDING_REPLACE","UNKNOWN","CANCELLED"}

        def get_status(o):
            return (o.get("status") or "").upper().strip()

        working  = [o for o in all_orders if get_status(o) in WORKING_STATUSES]
        filled   = [o for o in all_orders if get_status(o) in FILLED_STATUSES]
        rejected = [o for o in all_orders if get_status(o) in REJECTED_STATUSES]
        print(f"[Dashboard] Sorted: {len(working)} working, {len(filled)} filled, {len(rejected)} rejected")

        def fmt_time(entered):
            try:
                from datetime import datetime, timezone, timedelta
                dt = datetime.fromisoformat(entered.replace("Z","+00:00"))
                mst = dt.astimezone(timezone(timedelta(hours=-7)))
                return mst.strftime("%I:%M:%S %p  %m/%d/%Y MST")
            except: return entered[:16].replace("T"," ")

        def order_base(o):
            legs  = o.get("orderLegCollection",[{}])
            inst  = legs[0].get("instrument",{}) if legs else {}
            sym   = inst.get("symbol","—")
            side  = legs[0].get("instruction","—") if legs else "—"
            otype = o.get("orderType","—")
            qty   = str(o.get("quantity","—"))
            price = f"${float(o.get('price',0) or 0):.2f}" if o.get("price") else "MKT"
            stop  = f"${float(o.get('stopPrice',0) or 0):.2f}" if o.get("stopPrice") else "—"
            time  = fmt_time(o.get("enteredTime",""))
            sc    = GREEN if "BUY" in side.upper() else RED
            return sym,side,otype,qty,price,stop,time,sc

        # Pending
        self._pend_tbl.setRowCount(0)
        for o in working:
            sym,side,otype,qty,price,stop,time,sc = order_base(o)
            row = self._pend_tbl.rowCount(); self._pend_tbl.insertRow(row)
            self._pend_tbl.setRowHeight(row,24)
            self._pend_tbl.setItem(row,0,ci(sym,BLUE))
            self._pend_tbl.setItem(row,1,ci(side,sc))
            self._pend_tbl.setItem(row,2,ci(otype))
            self._pend_tbl.setItem(row,3,ci(qty))
            self._pend_tbl.setItem(row,4,ci(price))
            self._pend_tbl.setItem(row,5,ci(stop))
            self._pend_tbl.setItem(row,6,ci(o.get("session","—"),DIM))
            self._pend_tbl.setItem(row,7,ci(o.get("duration","—"),DIM))
            self._pend_tbl.setItem(row,8,ci("WORKING",YELLOW))
            self._pend_tbl.setItem(row,9,ci(time,DIM))
            # Store order id for cancel
            self._pend_tbl.item(row,0).setData(Qt.ItemDataRole.UserRole, o.get("orderId",""))
        setup_table(self._pend_tbl)

        # Fills
        self._fill_tbl.setRowCount(0)
        for o in filled:
            try:
                sym,side,otype,qty,price,stop,time,sc = order_base(o)
                row = self._fill_tbl.rowCount(); self._fill_tbl.insertRow(row)
                self._fill_tbl.setRowHeight(row,24)
                self._fill_tbl.setItem(row,0,ci(sym,BLUE))
                self._fill_tbl.setItem(row,1,ci(side,sc))
                self._fill_tbl.setItem(row,2,ci(otype))
                self._fill_tbl.setItem(row,3,ci(str(o.get("filledQuantity",qty))))
                self._fill_tbl.setItem(row,4,ci(price))
                self._fill_tbl.setItem(row,5,ci(o.get("status",""),GREEN))
                self._fill_tbl.setItem(row,6,ci(time,DIM))
            except Exception as e:
                print(f"[Dashboard] fill row error: {e}")
        setup_table(self._fill_tbl)

        # Rejected
        self._rej_tbl.setRowCount(0)
        for o in rejected:
            try:
                sym,side,otype,qty,price,stop,time,sc = order_base(o)
                reason = str(o.get("statusDescription", o.get("cancelMessage", o.get("status","—"))))
                row = self._rej_tbl.rowCount(); self._rej_tbl.insertRow(row)
                self._rej_tbl.setRowHeight(row,24)
                self._rej_tbl.setItem(row,0,ci(sym,BLUE))
                self._rej_tbl.setItem(row,1,ci(side,sc))
                self._rej_tbl.setItem(row,2,ci(otype))
                self._rej_tbl.setItem(row,3,ci(qty))
                self._rej_tbl.setItem(row,4,ci(price))
                self._rej_tbl.setItem(row,5,ci(reason[:60],RED))
                self._rej_tbl.setItem(row,6,ci(time,DIM))
            except Exception as e:
                print(f"[Dashboard] rejected row error: {e} — {o}")
        setup_table(self._rej_tbl)
        print(f"[Dashboard] Rejected tab: {self._rej_tbl.rowCount()} rows displayed")

        now = now_mt()
        self._status.setText(
            f"  {len(pos)} positions  |  {len(working)} pending  |  "
            f"{len(filled)} fills  |  {len(rejected)} rejected  |  Updated {now}")
        self._updated_lbl.setText(f"Updated {now}")

    def _pos_rclick(self, pos):
        row = self._pos_tbl.rowAt(pos.y())
        if row < 0: return
        sym_item = self._pos_tbl.item(row,0)
        side_item = self._pos_tbl.item(row,1)
        qty_item  = self._pos_tbl.item(row,2)
        if not sym_item: return
        sym  = sym_item.text()
        side = side_item.text() if side_item else "LONG"
        qty  = int(qty_item.text()) if qty_item else 1

        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{BG2};border:1px solid #30363d;color:#e6edf3;font-size:12px;padding:4px;}} QMenu::item{{padding:8px 20px;}} QMenu::item:selected{{background:#1f6feb;}}")
        menu.addAction(f"  {sym}  —  {side}  {qty}").setEnabled(False)
        menu.addSeparator()
        flat_a  = menu.addAction("🔴  Flatten Position (Market)")
        buy_a   = menu.addAction("🟢  Buy at Limit…")
        sell_a  = menu.addAction("🔴  Sell at Limit…")

        flat_a.triggered.connect(lambda: self._flatten(sym, side, qty))
        buy_a.triggered.connect(lambda:  self._limit_order(sym, "BUY"))
        sell_a.triggered.connect(lambda: self._limit_order(sym, "SELL"))
        menu.exec(QCursor.pos())

    def _pend_rclick(self, pos):
        row = self._pend_tbl.rowAt(pos.y())
        if row < 0: return
        sym_item = self._pend_tbl.item(row,0)
        if not sym_item: return
        order_id = sym_item.data(Qt.ItemDataRole.UserRole)
        sym = sym_item.text()
        side_item = self._pend_tbl.item(row,1)
        price_item = self._pend_tbl.item(row,4)
        side  = side_item.text()  if side_item  else "—"
        price = price_item.text() if price_item else "—"

        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{BG2};border:1px solid #30363d;color:#e6edf3;font-size:12px;padding:4px;}} QMenu::item{{padding:8px 20px;}} QMenu::item:selected{{background:#1f6feb;}}")
        menu.addAction(f"  {sym}  {side}  {price}").setEnabled(False)
        menu.addSeparator()
        cancel_a = menu.addAction("❌  Cancel This Order")
        cancel_a.triggered.connect(lambda: self._cancel_order(order_id, sym))
        menu.exec(QCursor.pos())

    def _flatten(self, sym, side, qty):
        close_side = "SELL" if side=="LONG" else "BUY"
        order = self.api.build_stock_order(sym, qty, close_side, "MARKET")
        ok, msg = self.api.place_order(order)
        if ok:
            notify(f"{'🟢 BUY' if close_side=='BUY' else '🔴 SELL'}  {qty}× {sym}",
                   "fill", subtitle=f"MKT  |  Flatten", duration=5000)
        else:
            notify(f"❌ Order Rejected — {sym}", "reject",
                   subtitle=msg[:100] if msg else "Rejected", duration=7000)

    def _limit_order(self, sym, side):
        from ui.order_dialog import OrderDialog
        dlg = OrderDialog(self, api=self.api,
                          pre_fill={"symbol":sym,"instruction":side,"asset_type":"EQUITY"})
        dlg.exec()

    def _cancel_order(self, order_id, sym):
        try:
            self.api.cancel_order(order_id)
            notify(f"Order Cancelled","info",subtitle=sym,duration=3000)
        except Exception as e:
            notify("Cancel Failed","reject",subtitle=str(e)[:80],duration=5000)

    def _build_automation_tab(self):
        """Webhook automation tab — start/stop server, view alert log."""
        from PyQt6.QtWidgets import QTextEdit, QGroupBox
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(16,16,16,16); v.setSpacing(12)

        # Server control row
        ctrl_row = QHBoxLayout(); ctrl_row.setSpacing(10)

        self._wh_status = QLabel("⚫  Webhook Server: Stopped")
        self._wh_status.setStyleSheet(f"color:{DIM};font-size:13px;font-weight:bold;")
        ctrl_row.addWidget(self._wh_status)
        ctrl_row.addStretch()

        # Port selector
        from PyQt6.QtWidgets import QSpinBox
        ctrl_row.addWidget(QLabel("Port:"))
        self._wh_port = QSpinBox()
        self._wh_port.setRange(80, 65535); self._wh_port.setValue(80)
        self._wh_port.setFixedWidth(80); self._wh_port.setFixedHeight(32)
        self._wh_port.setStyleSheet("QSpinBox{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:3px;padding:4px;} QSpinBox::up-button,QSpinBox::down-button{background:#30363d;border:none;width:16px;}")
        ctrl_row.addWidget(self._wh_port)

        self._wh_start_btn = QPushButton("▶  Start Server")
        self._wh_start_btn.setFixedHeight(34)
        self._wh_start_btn.setStyleSheet(f"QPushButton{{background:#238636;color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:bold;padding:0 16px;}} QPushButton:hover{{background:#2ea043;}}")
        self._wh_start_btn.clicked.connect(self._start_webhook)
        ctrl_row.addWidget(self._wh_start_btn)

        self._wh_stop_btn = QPushButton("⏹  Stop")
        self._wh_stop_btn.setFixedHeight(34)
        self._wh_stop_btn.setEnabled(False)
        self._wh_stop_btn.setStyleSheet(f"QPushButton{{background:#da3633;color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:bold;padding:0 16px;}} QPushButton:hover{{background:#f85149;}} QPushButton:disabled{{background:#30363d;color:#8b949e;}}")
        self._wh_stop_btn.clicked.connect(self._stop_webhook)
        ctrl_row.addWidget(self._wh_stop_btn)

        v.addLayout(ctrl_row)

        # Instructions
        url_lbl = QLabel("📋  TradingView Webhook URL:")
        url_lbl.setStyleSheet(f"color:{DIM};font-size:11px;font-weight:bold;")
        v.addWidget(url_lbl)

        self._wh_url_lbl = QLabel("Start the server to see your webhook URL")
        self._wh_url_lbl.setStyleSheet(f"background:#0d1117;color:#58a6ff;font-family:Consolas;font-size:13px;padding:8px 12px;border:1px solid #30363d;border-radius:4px;")
        self._wh_url_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(self._wh_url_lbl)

        # Alert message template
        tmpl_lbl = QLabel("📝  TradingView Alert Message Template:")
        tmpl_lbl.setStyleSheet(f"color:{DIM};font-size:11px;font-weight:bold;")
        v.addWidget(tmpl_lbl)

        tmpl = QLabel(
            '{"symbol":"{{ticker}}","side":"BUY","qty":1,"type":"LIMIT",'
            '"price":{{close}},"stop_loss":{{low[1]}},"take_profit":0}'
        )
        tmpl.setStyleSheet(f"background:#0d1117;color:#d29922;font-family:Consolas;font-size:11px;padding:8px 12px;border:1px solid #30363d;border-radius:4px;")
        tmpl.setWordWrap(True)
        tmpl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(tmpl)

        # Alert log
        log_lbl = QLabel("📡  Alert Log:")
        log_lbl.setStyleSheet(f"color:{DIM};font-size:11px;font-weight:bold;")
        v.addWidget(log_lbl)

        self._wh_log = QTextEdit()
        self._wh_log.setReadOnly(True)
        self._wh_log.setStyleSheet(f"QTextEdit{{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:4px;font-family:Consolas;font-size:11px;padding:8px;}}")
        v.addWidget(self._wh_log, stretch=1)

        clear_btn = QPushButton("Clear Log")
        clear_btn.setFixedHeight(28)
        clear_btn.setStyleSheet(f"QPushButton{{background:{BG3};color:{DIM};border:1px solid #30363d;border-radius:3px;font-size:11px;}} QPushButton:hover{{color:#e6edf3;}}")
        clear_btn.clicked.connect(self._wh_log.clear)
        v.addWidget(clear_btn)

        # Wire webhook signals
        from ui.webhook_server import webhook_signals
        webhook_signals.alert_received.connect(self._on_alert_received)
        webhook_signals.order_placed.connect(self._on_order_placed)
        webhook_signals.error_occurred.connect(self._on_wh_error)
        webhook_signals.server_started.connect(self._on_server_started)
        webhook_signals.server_stopped.connect(self._on_server_stopped)

        return w

    def _start_webhook(self):
        from ui.webhook_server import webhook_server
        webhook_server.api = self.api
        port = self._wh_port.value()
        ok, msg = webhook_server.start(port)
        if not ok:
            self._wh_log.append(f"<span style='color:#f85149'>❌ {msg}</span>")

    def _stop_webhook(self):
        from ui.webhook_server import webhook_server
        webhook_server.stop()

    def _on_server_started(self, port):
        import socket
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except: ip = "YOUR_IP"
        url = f"http://{ip}:{port}/webhook"
        self._wh_status.setText(f"🟢  Webhook Server: Running on port {port}")
        self._wh_status.setStyleSheet("color:#3fb950;font-size:13px;font-weight:bold;")
        self._wh_url_lbl.setText(url)
        self._wh_start_btn.setEnabled(False)
        self._wh_stop_btn.setEnabled(True)
        self._wh_log.append(f"<span style='color:#3fb950'>✅ Server started — {url}</span>")
        self._wh_log.append(f"<span style='color:#8b949e'>Paste the URL above into TradingView → Alert → Webhook URL</span>")

    def _on_server_stopped(self):
        self._wh_status.setText("⚫  Webhook Server: Stopped")
        self._wh_status.setStyleSheet(f"color:{DIM};font-size:13px;font-weight:bold;")
        self._wh_url_lbl.setText("Start the server to see your webhook URL")
        self._wh_start_btn.setEnabled(True)
        self._wh_stop_btn.setEnabled(False)
        self._wh_log.append("<span style='color:#8b949e'>⏹ Server stopped</span>")

    def _on_alert_received(self, data: dict):
        ts = data.get("_received_at","")
        sym = data.get("symbol","?")
        side = data.get("side","?")
        qty = data.get("qty","?")
        self._wh_log.append(
            f"<span style='color:#58a6ff'>📡 [{ts}] Alert received: "
            f"{side} {qty}× {sym}</span>")

    def _on_order_placed(self, result: dict):
        sym  = result.get("symbol","?")
        side = result.get("side","?")
        qty  = result.get("qty","?")
        ok   = result.get("entry_ok", False)
        msg  = result.get("entry_msg","")
        sl   = result.get("stop_loss",0)
        tp   = result.get("take_profit",0)
        color = "#3fb950" if ok else "#f85149"
        icon  = "✅" if ok else "❌"
        self._wh_log.append(
            f"<span style='color:{color}'>{icon} Order: {side} {qty}× {sym} — {'Filled' if ok else msg}</span>")
        if sl and result.get("sl_ok"):
            self._wh_log.append(f"<span style='color:#d29922'>  🛑 Stop Loss @ ${sl:.2f} placed</span>")
        if tp and result.get("tp_ok"):
            self._wh_log.append(f"<span style='color:#3fb950'>  🎯 Take Profit @ ${tp:.2f} placed</span>")
        # Also show toast
        from ui.toast import notify
        notify(f"{'✅ AUTO TRADE' if ok else '❌ AUTO REJECTED'} — {sym}",
               "fill" if ok else "reject",
               subtitle=f"{side} {qty}× @ {result.get('price',0)}", duration=6000)

    def _on_wh_error(self, msg: str):
        self._wh_log.append(f"<span style='color:#f85149'>⚠️ {msg}</span>")

    def _on_date_filter_changed(self, filter_text):
        if filter_text == "Custom Date":
            self._show_custom_date_picker()
        else:
            self._refresh()

    def _show_custom_date_picker(self):
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QDateEdit, QDialogButtonBox
        from PyQt6.QtCore import QDate
        dlg = QDialog(self); dlg.setWindowTitle("Custom Date Range")
        dlg.setStyleSheet(f"QDialog{{background:{BG2};color:#e6edf3;}}")
        v = QVBoxLayout(dlg); v.setContentsMargins(16,16,16,16); v.setSpacing(10)
        from PyQt6.QtWidgets import QLabel as _QL
        v.addWidget(_QL("From:"))
        self._custom_from = QDateEdit(); self._custom_from.setCalendarPopup(True)
        self._custom_from.setDate(QDate.currentDate().addDays(-7))
        self._custom_from.setStyleSheet(f"QDateEdit{{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:3px;padding:4px;}}")
        v.addWidget(self._custom_from)
        v.addWidget(_QL("To:"))
        self._custom_to = QDateEdit(); self._custom_to.setCalendarPopup(True)
        self._custom_to.setDate(QDate.currentDate())
        self._custom_to.setStyleSheet(self._custom_from.styleSheet())
        v.addWidget(self._custom_to)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        v.addWidget(btns)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._refresh()

    def on_show(self):
        self._refresh()

class QuotesPage(QWidget):
    def __init__(self, api):
        super().__init__(); self.api=api; self._threads=[]; self.watchlist=list(DEFAULT_WATCHLIST)
        self._chart_nav=None
        self._build()
        self._timer=QTimer(); self._timer.timeout.connect(self.on_show); self._timer.start(1000)

    def _build(self):
        vbox=QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)
        vbox.addWidget(PageHeader("📈  Live Quotes"))
        tb=QWidget(); tb.setFixedHeight(52); tb.setStyleSheet(f"background:{BG3}; border-bottom:1px solid #30363d;")
        tbox=QHBoxLayout(tb); tbox.setContentsMargins(16,0,16,0); tbox.setSpacing(8)
        tbox.addWidget(QLabel("Symbol:"))
        self._sym_input=QLineEdit(); self._sym_input.setPlaceholderText("e.g. GOOG"); self._sym_input.setFixedWidth(120)
        # Auto-capitalize as user types
        self._sym_input.textChanged.connect(self._auto_caps_input)
        self._sym_input.returnPressed.connect(self._add_symbol)
        self._sym_input.editingFinished.connect(self._add_symbol)
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
        self._table.verticalHeader().setVisible(False)
        # Make columns movable and resizable
        self._table.horizontalHeader().setSectionsMovable(True)
        self._table.horizontalHeader().setDragEnabled(True)
        header = self._table.horizontalHeader()
        for i in range(10):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
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

        setup_table(self._table)
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
        vbox.addWidget(PageHeader("💼  Portfolio"))
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
        header = self._table.horizontalHeader()
        for i in range(10):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
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
