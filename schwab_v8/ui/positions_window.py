"""Positions popout — floating window with today's trades and open positions."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QWidget, QHeaderView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QColor
from datetime import datetime, timedelta

from ui.widgets import make_table, color_item, plain_item

GREEN="#3fb950"; RED="#f85149"; BLUE="#58a6ff"; YELLOW="#d29922"; DIM="#8b949e"; BG2="#161b22"; BG3="#21262d"


class LoadThread(QThread):
    done = pyqtSignal(dict, list)
    def __init__(self, api): super().__init__(); self.api=api
    def run(self):
        try:
            p=self.api.get_portfolio()
            from_d=(datetime.now()-timedelta(hours=24)).strftime("%Y-%m-%dT00:00:00Z")
            to_d=datetime.now().strftime("%Y-%m-%dT23:59:59Z")
            o=self.api.get_orders(from_date=from_d,to_date=to_d)
            self.done.emit(p,o)
        except: self.done.emit({}, [])


class PositionsWindow(QDialog):
    def __init__(self, parent, api):
        super().__init__(parent)
        self.api=api; self._threads=[]
        self.setWindowTitle("Positions & Today's Trades")
        self.resize(900, 600)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet("background:#0d1117; color:#e6edf3; font-family:Consolas;")
        self._build()
        self._timer=QTimer(); self._timer.timeout.connect(self._load); self._timer.start(5000)
        self._load()

    def _build(self):
        vbox=QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0)

        # Header
        hdr=QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG2}; border-bottom:1px solid #30363d;")
        hh=QHBoxLayout(hdr); hh.setContentsMargins(20,0,20,0)
        title=QLabel("💼  Positions & Today's Trades")
        title.setStyleSheet("color:#58a6ff; font-size:15px; font-weight:bold;")
        hh.addWidget(title); hh.addStretch()
        ref=QPushButton("⟳ Refresh"); ref.setObjectName("blue_btn"); ref.setFixedHeight(32)
        ref.clicked.connect(self._load); hh.addWidget(ref)
        vbox.addWidget(hdr)

        # Summary cards
        cards_w=QWidget(); cards_w.setFixedHeight(70)
        cards_w.setStyleSheet(f"background:{BG3}; border-bottom:1px solid #30363d;")
        ch=QHBoxLayout(cards_w); ch.setContentsMargins(20,8,20,8); ch.setSpacing(20)
        self._sum_vars={}
        for key,label,color in [("nl","Net Liq",BLUE),("cash","Cash",GREEN),("day_pnl","Day P&L",GREEN),("open_pnl","Open P&L",GREEN),("trades","Today Trades",BLUE)]:
            f=QWidget(); fv=QVBoxLayout(f); fv.setContentsMargins(0,0,0,0); fv.setSpacing(2)
            lbl=QLabel(label); lbl.setStyleSheet(f"color:{DIM}; font-size:9px; background:transparent;")
            val=QLabel("—"); val.setStyleSheet(f"color:{color}; font-size:16px; font-weight:bold; background:transparent;")
            fv.addWidget(lbl); fv.addWidget(val); ch.addWidget(f); self._sum_vars[key]=val
        vbox.addWidget(cards_w)

        # Tabs
        tabs=QTabWidget(); tabs.setDocumentMode(True)

        # Open positions tab
        pos_w=QWidget(); pvbox=QVBoxLayout(pos_w); pvbox.setContentsMargins(12,12,12,12)
        self._pos_table=make_table(["Symbol","Asset","Qty","Avg Cost","Last","Mkt Value","Day P&L","Day %","Open P&L","Open %"],stretch_col=0)
        for i in range(10): self._pos_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        pvbox.addWidget(self._pos_table)
        tabs.addTab(pos_w,"  Open Positions  ")

        # Today's trades tab
        trades_w=QWidget(); tvbox=QVBoxLayout(trades_w); tvbox.setContentsMargins(12,12,12,12)
        self._trades_table=make_table(["Time","Symbol","Side","Qty","Type","Price","Status"],stretch_col=1)
        for i in range(7): self._trades_table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        tvbox.addWidget(self._trades_table)
        tabs.addTab(trades_w,"  Today's Trades  ")

        vbox.addWidget(tabs, stretch=1)

        self._status=QLabel("")
        self._status.setStyleSheet(f"color:{DIM}; font-size:10px; padding:4px 16px; background:{BG2};")
        vbox.addWidget(self._status)

    def _load(self):
        t=LoadThread(self.api); t.done.connect(self._populate)
        self._threads.append(t)
        t.finished.connect(lambda: self._threads.remove(t) if t in self._threads else None)
        t.start()

    def _populate(self, portfolio, orders):
        # Summary
        if portfolio:
            acct=portfolio.get("securitiesAccount",{}); bal=acct.get("currentBalances",{})
            pos=acct.get("positions",[]); nl=bal.get("liquidationValue",0); cash=bal.get("cashBalance",0)
            dp=sum(p.get("currentDayProfitLoss",0) for p in pos); op=sum(p.get("unrealizedProfitLoss",0) for p in pos)
            self._sum_vars["nl"].setText(f"${nl:,.2f}")
            self._sum_vars["cash"].setText(f"${cash:,.2f}")
            self._sum_vars["day_pnl"].setText(f"{'+'if dp>=0 else''}${dp:,.2f}")
            self._sum_vars["day_pnl"].setStyleSheet(f"color:{GREEN if dp>=0 else RED}; font-size:16px; font-weight:bold; background:transparent;")
            self._sum_vars["open_pnl"].setText(f"{'+'if op>=0 else''}${op:,.2f}")
            self._sum_vars["open_pnl"].setStyleSheet(f"color:{GREEN if op>=0 else RED}; font-size:16px; font-weight:bold; background:transparent;")

            # Positions table
            self._pos_table.setRowCount(0)
            for p in pos:
                inst=p.get("instrument",{}); sym=inst.get("symbol","—"); asset=inst.get("assetType","—")
                qty=p.get("longQuantity",p.get("shortQuantity",0)); avg=p.get("averagePrice",0)
                mkt=p.get("marketValue",0); last=mkt/qty if qty else 0
                dp2=p.get("currentDayProfitLoss",0); dp2p=p.get("currentDayProfitLossPercentage",0)
                op2=p.get("unrealizedProfitLoss",0); op2p=(op2/(avg*qty)*100) if avg and qty else 0
                row=self._pos_table.rowCount(); self._pos_table.insertRow(row)
                sd="+"if dp2>=0 else""; so="+"if op2>=0 else""
                for col,(val,clr) in enumerate([
                    (sym,BLUE),(asset,"#e6edf3"),(str(int(qty)),"#e6edf3"),(f"${avg:.2f}","#e6edf3"),(f"${last:.2f}","#e6edf3"),
                    (f"${mkt:,.2f}","#e6edf3"),(f"{sd}${dp2:,.2f}",GREEN if dp2>=0 else RED),(f"{sd}{dp2p:.2f}%",GREEN if dp2>=0 else RED),
                    (f"{so}${op2:,.2f}",GREEN if op2>=0 else RED),(f"{so}{op2p:.2f}%",GREEN if op2>=0 else RED),
                ]): self._pos_table.setItem(row,col,color_item(val,clr))

        # Today's trades
        self._trades_table.setRowCount(0)
        filled=[o for o in orders]
        self._sum_vars["trades"].setText(str(len(filled)))
        for o in filled:
            legs=o.get("orderLegCollection",[{}]); inst=legs[0].get("instrument",{}) if legs else {}
            sym=inst.get("symbol","—"); side=legs[0].get("instruction","—") if legs else "—"
            status=o.get("status","—")
            row=self._trades_table.rowCount(); self._trades_table.insertRow(row)
            for col,(val,clr) in enumerate([
                (o.get("enteredTime","")[:16].replace("T"," "),"#e6edf3"),(sym,BLUE),
                (side,GREEN if "BUY" in side else RED),(str(o.get("quantity","—")),"#e6edf3"),
                (o.get("orderType","—"),"#e6edf3"),(str(o.get("price","MKT")),"#e6edf3"),
                (status,GREEN if status=="FILLED" else YELLOW if status=="WORKING" else DIM),
            ]): self._trades_table.setItem(row,col,color_item(val,clr))

        self._status.setText(f"Auto-refreshing every 5s  |  Updated {datetime.now().strftime('%H:%M:%S')}")
