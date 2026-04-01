"""
Positions / Trades Window v11
- Auto-fit columns
- No refresh button
- Working/pending orders shown in separate tab
- Filled trades tab
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget,
    QAbstractItemView, QDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor

GREEN="#3fb950"; RED="#f85149"; BLUE="#58a6ff"; YELLOW="#d29922"
DIM="#8b949e"; BG="#0d1117"; BG2="#161b22"; BG3="#21262d"

TABLE_STYLE = f"""
    QTableWidget{{background:{BG2};border:none;gridline-color:#21262d;
                 color:#e6edf3;font-family:Consolas;font-size:12px;}}
    QTableWidget::item{{padding:4px 8px;}}
    QTableWidget::item:selected{{background:#1f6feb44;color:#fff;}}
    QHeaderView::section{{background:{BG3};padding:6px 8px;border:none;
                          border-right:1px solid #30363d;
                          border-bottom:2px solid #58a6ff;
                          font-weight:bold;font-size:11px;}}
"""


def ci(text, color="#e6edf3"):
    item = QTableWidgetItem(str(text))
    item.setForeground(QColor(color))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def autofit(table: QTableWidget):
    """Resize all columns to fit their content."""
    table.resizeColumnsToContents()
    table.horizontalHeader().setStretchLastSection(True)


class DataThread(QThread):
    done = pyqtSignal(dict, list, list)
    def __init__(self, api):
        super().__init__(); self.api = api
    def run(self):
        try:
            portfolio = self.api.get_portfolio()
            from datetime import datetime, timedelta
            from_d = (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
            to_d   = datetime.now().strftime("%Y-%m-%dT23:59:59Z")
            all_orders     = self.api.get_orders(from_date=from_d, to_date=to_d) or []
            working_orders = self.api.get_orders(from_date=from_d, to_date=to_d, status="WORKING") or []
            self.done.emit(portfolio, all_orders, working_orders)
        except Exception as e:
            print(f"[Positions] data error: {e}")
            self.done.emit({}, [], [])


class PositionsWindow(QDialog):
    def __init__(self, parent, api):
        super().__init__(parent)
        self.api = api
        self._threads = []
        self.setWindowTitle("Positions & Orders")
        self.resize(1100, 600)
        self.setStyleSheet(f"background:{BG};color:#e6edf3;")
        self._build()
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(3000)
        QTimer.singleShot(200, self._refresh)

    def _build(self):
        vbox = QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG2};border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,0,16,0)
        title = QLabel("💼  Positions & Orders")
        title.setStyleSheet(f"color:{BLUE};font-size:15px;font-weight:bold;")
        hh.addWidget(title); hh.addStretch()
        self._updated = QLabel("")
        self._updated.setStyleSheet(f"color:{DIM};font-size:10px;")
        hh.addWidget(self._updated)
        vbox.addWidget(hdr)

        # Tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane{{border:none;background:{BG2};}}
            QTabBar::tab{{background:{BG3};color:{DIM};padding:8px 20px;border:none;
                         border-right:1px solid #30363d;font-size:12px;}}
            QTabBar::tab:selected{{background:{BG2};color:#e6edf3;border-bottom:2px solid {BLUE};}}
            QTabBar::tab:hover{{color:#e6edf3;}}
        """)

        # Tab 1 — Open Positions
        self._pos_table = self._make_table([
            "Symbol","Side","Qty","Avg Price","Last","Mkt Value","Day P&L","Open P&L","Asset"
        ])
        self._tabs.addTab(self._pos_table, "📊  Open Positions")

        # Tab 2 — Working / Pending Orders
        self._work_table = self._make_table([
            "Symbol","Side","Type","Qty","Price","Stop","Session","Duration","Status","Time"
        ])
        self._tabs.addTab(self._work_table, "⏳  Pending Orders")

        # Tab 3 — Today's Fills
        self._fills_table = self._make_table([
            "Symbol","Side","Type","Qty","Price","Status","Time"
        ])
        self._tabs.addTab(self._fills_table, "✅  Today's Fills")

        vbox.addWidget(self._tabs, stretch=1)

        # Status
        self._status = QLabel("  Loading…")
        self._status.setFixedHeight(22)
        self._status.setStyleSheet(f"color:{DIM};font-size:10px;background:{BG3};border-top:1px solid #30363d;padding:0 8px;")
        vbox.addWidget(self._status)

    def _make_table(self, cols):
        t = QTableWidget(0, len(cols))
        t.setHorizontalHeaderLabels(cols)
        t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setShowGrid(True)
        t.setAlternatingRowColors(False)
        t.horizontalHeader().setSectionsMovable(True)
        t.setStyleSheet(TABLE_STYLE)
        return t

    def _refresh(self):
        t = DataThread(self.api)
        t.done.connect(self._populate)
        t.done.connect(lambda *_: self._cleanup(t))
        self._threads.append(t); t.start()

    def _cleanup(self, t):
        try: self._threads.remove(t)
        except: pass

    def _populate(self, portfolio: dict, all_orders: list, working_orders: list):
        from datetime import datetime
        now = datetime.now().strftime("%H:%M:%S")
        self._updated.setText(f"Updated {now}")

        # ── Open Positions ─────────────────────────────────────
        self._pos_table.setRowCount(0)
        acct = portfolio.get("securitiesAccount", {})
        positions = acct.get("positions", [])

        for p in positions:
            inst      = p.get("instrument", {})
            sym       = inst.get("symbol", "—")
            asset     = inst.get("assetType", "EQUITY")
            long_qty  = p.get("longQuantity", 0)
            short_qty = p.get("shortQuantity", 0)
            qty       = long_qty if long_qty > 0 else -short_qty
            side      = "LONG" if qty > 0 else "SHORT"
            avg       = p.get("averagePrice", 0)
            mkt_val   = p.get("marketValue", 0)
            day_pnl   = p.get("currentDayProfitLoss", 0)
            open_pnl  = p.get("longOpenProfitLoss", p.get("shortOpenProfitLoss", 0))
            last_px   = mkt_val / abs(qty) if qty else 0

            row = self._pos_table.rowCount()
            self._pos_table.insertRow(row)
            self._pos_table.setRowHeight(row, 24)

            sc = GREEN if side == "LONG" else RED
            dc = GREEN if day_pnl  >= 0 else RED
            oc = GREEN if open_pnl >= 0 else RED

            self._pos_table.setItem(row, 0, ci(sym, BLUE))
            self._pos_table.setItem(row, 1, ci(side, sc))
            self._pos_table.setItem(row, 2, ci(str(abs(int(qty)))))
            self._pos_table.setItem(row, 3, ci(f"${avg:.2f}"))
            self._pos_table.setItem(row, 4, ci(f"${last_px:.2f}"))
            self._pos_table.setItem(row, 5, ci(f"${mkt_val:,.2f}"))
            self._pos_table.setItem(row, 6, ci(f"{'+'if day_pnl>=0 else''}${day_pnl:,.2f}", dc))
            self._pos_table.setItem(row, 7, ci(f"{'+'if open_pnl>=0 else''}${open_pnl:,.2f}", oc))
            self._pos_table.setItem(row, 8, ci(asset, DIM))

        autofit(self._pos_table)

        # ── Working / Pending Orders ──────────────────────────
        self._work_table.setRowCount(0)
        for o in working_orders:
            self._add_order_row(self._work_table, o)
        autofit(self._work_table)

        # ── Today's Fills ─────────────────────────────────────
        self._fills_table.setRowCount(0)
        filled = [o for o in all_orders if o.get("status") in ("FILLED","PART_FILLED")]
        for o in filled:
            self._add_fill_row(self._fills_table, o)
        autofit(self._fills_table)

        self._status.setText(
            f"  {len(positions)} positions  |  "
            f"{len(working_orders)} pending  |  "
            f"{len(filled)} fills today  |  Updated {now}")

    def _add_order_row(self, table, o):
        from datetime import datetime
        legs   = o.get("orderLegCollection", [{}])
        inst   = legs[0].get("instrument", {}) if legs else {}
        sym    = inst.get("symbol", "—")
        side   = legs[0].get("instruction", "—") if legs else "—"
        otype  = o.get("orderType", "—")
        qty    = str(o.get("quantity", "—"))
        price  = f"${float(o.get('price',0) or 0):.2f}" if o.get("price") else "MKT"
        stop   = f"${float(o.get('stopPrice',0) or 0):.2f}" if o.get("stopPrice") else "—"
        sess   = o.get("session", "—")
        dur    = o.get("duration", "—")
        status = o.get("status", "—")
        entered = o.get("enteredTime", "")
        try:
            dt = datetime.fromisoformat(entered.replace("Z",""))
            time_str = dt.strftime("%I:%M:%S %p  %m/%d/%Y")
        except: time_str = entered[:16].replace("T"," ")

        row = table.rowCount(); table.insertRow(row)
        table.setRowHeight(row, 24)
        sc = GREEN if "BUY" in side.upper() else RED
        table.setItem(row, 0, ci(sym, BLUE))
        table.setItem(row, 1, ci(side, sc))
        table.setItem(row, 2, ci(otype))
        table.setItem(row, 3, ci(qty))
        table.setItem(row, 4, ci(price))
        table.setItem(row, 5, ci(stop))
        table.setItem(row, 6, ci(sess, DIM))
        table.setItem(row, 7, ci(dur, DIM))
        table.setItem(row, 8, ci(status, YELLOW))
        table.setItem(row, 9, ci(time_str, DIM))

    def _add_fill_row(self, table, o):
        from datetime import datetime
        legs   = o.get("orderLegCollection", [{}])
        inst   = legs[0].get("instrument", {}) if legs else {}
        sym    = inst.get("symbol", "—")
        side   = legs[0].get("instruction", "—") if legs else "—"
        otype  = o.get("orderType", "—")
        qty    = str(o.get("filledQuantity", o.get("quantity","—")))
        price  = f"${float(o.get('price',0) or 0):.2f}" if o.get("price") else "MKT"
        status = o.get("status","—")
        entered = o.get("enteredTime","")
        try:
            dt = datetime.fromisoformat(entered.replace("Z",""))
            time_str = dt.strftime("%I:%M:%S %p  %m/%d/%Y")
        except: time_str = entered[:16].replace("T"," ")

        row = table.rowCount(); table.insertRow(row)
        table.setRowHeight(row, 24)
        sc = GREEN if "BUY" in side.upper() else RED
        table.setItem(row, 0, ci(sym, BLUE))
        table.setItem(row, 1, ci(side, sc))
        table.setItem(row, 2, ci(otype))
        table.setItem(row, 3, ci(qty))
        table.setItem(row, 4, ci(price))
        table.setItem(row, 5, ci(status, GREEN if status=="FILLED" else YELLOW))
        table.setItem(row, 6, ci(time_str, DIM))

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)
