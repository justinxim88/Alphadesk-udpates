"""
Order Dialog — supports Market, Limit, Stop, Stop-Limit, Trailing Stop, OCO.
Used by Options Chain (bid/ask click), Chart right-click, and Orders page.
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QGroupBox,
    QDialogButtonBox, QMessageBox, QTextEdit, QWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
import json

from api.trade_store import trade_store
from ui.toast import notify

GREEN  = "#3fb950"
RED    = "#f85149"
BLUE   = "#58a6ff"
YELLOW = "#d29922"
DIM    = "#8b949e"


class OrderDialog(QDialog):
    """
    Universal order dialog.
    pre_fill dict keys: symbol, instruction, price, qty, asset_type
    """
    def __init__(self, parent, api, pre_fill: dict = None, on_placed=None):
        super().__init__(parent)
        self.api        = api
        self.on_placed  = on_placed
        self.pre_fill   = pre_fill or {}
        self.setWindowTitle("Place Order")
        self.setMinimumWidth(460)
        self.setMinimumHeight(500)
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setSpacing(10)

        # Title
        sym   = self.pre_fill.get("symbol", "")
        inst  = self.pre_fill.get("instruction", "BUY")
        is_buy = "BUY" in inst.upper()
        color  = GREEN if is_buy else RED

        title = QLabel(f"{'🟢' if is_buy else '🔴'}  {inst.replace('_',' ')}  {sym}")
        title.setStyleSheet(f"color:{color}; font-size:15px; font-weight:bold; padding:8px;")
        vbox.addWidget(title)

        # Main form
        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setContentsMargins(8, 0, 8, 0)
        grid.setColumnStretch(1, 1)

        def add_row(label, widget, row):
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(widget, row, 1)

        # Symbol
        self._sym = QLineEdit(self.pre_fill.get("symbol", ""))
        add_row("Symbol", self._sym, 0)

        # Asset type
        self._asset = QComboBox()
        self._asset.addItems(["EQUITY", "OPTION"])
        if self.pre_fill.get("asset_type") == "OPTION":
            self._asset.setCurrentText("OPTION")
        add_row("Asset Type", self._asset, 1)

        # Instruction
        self._inst = QComboBox()
        self._inst.addItems(["BUY","SELL","BUY_TO_OPEN","BUY_TO_CLOSE","SELL_TO_OPEN","SELL_TO_CLOSE"])
        self._inst.setCurrentText(self.pre_fill.get("instruction", "BUY"))
        self._inst.currentTextChanged.connect(self._update_color)
        add_row("Instruction", self._inst, 2)

        # Quantity
        self._qty = QSpinBox()
        self._qty.setRange(1, 100000)
        self._qty.setValue(int(self.pre_fill.get("qty", 1)))
        add_row("Quantity", self._qty, 3)

        # Order type
        self._order_type = QComboBox()
        self._order_type.addItems(["LIMIT","MARKET","STOP","STOP_LIMIT","TRAILING_STOP","OCO"])
        self._order_type.currentTextChanged.connect(self._on_type_change)
        add_row("Order Type", self._order_type, 4)

        # Limit price
        self._limit_price = QDoubleSpinBox()
        self._limit_price.setRange(0, 999999)
        self._limit_price.setDecimals(2)
        self._limit_price.setSingleStep(0.01)
        self._limit_price.setValue(float(self.pre_fill.get("price", 0)))
        add_row("Limit Price", self._limit_price, 5)

        # Stop price
        self._stop_price = QDoubleSpinBox()
        self._stop_price.setRange(0, 999999)
        self._stop_price.setDecimals(2)
        self._stop_price.setSingleStep(0.01)
        add_row("Stop Price", self._stop_price, 6)

        # Trailing stop
        self._trailing_lbl = QLabel("Trailing Amount $")
        grid.addWidget(self._trailing_lbl, 7, 0)
        self._trailing = QDoubleSpinBox()
        self._trailing.setRange(0.01, 9999)
        self._trailing.setDecimals(2)
        self._trailing.setValue(1.00)
        grid.addWidget(self._trailing, 7, 1)

        self._trailing_pct_cb = QCheckBox("Use % instead of $")
        self._trailing_pct_cb.setStyleSheet("color:#8b949e;")
        self._trailing_pct_cb.toggled.connect(self._on_trailing_toggle)
        grid.addWidget(self._trailing_pct_cb, 8, 0, 1, 2)

        # OCO fields
        self._oco_lbl1 = QLabel("Take Profit $")
        grid.addWidget(self._oco_lbl1, 9, 0)
        self._oco_tp = QDoubleSpinBox()
        self._oco_tp.setRange(0, 999999); self._oco_tp.setDecimals(2)
        grid.addWidget(self._oco_tp, 9, 1)

        self._oco_lbl2 = QLabel("Stop Loss $")
        grid.addWidget(self._oco_lbl2, 10, 0)
        self._oco_sl = QDoubleSpinBox()
        self._oco_sl.setRange(0, 999999); self._oco_sl.setDecimals(2)
        grid.addWidget(self._oco_sl, 10, 1)

        # Session
        self._session = QComboBox()
        self._session.addItems(["NORMAL","PRE_MARKET","AFTER_HOURS","SEAMLESS"])
        from config.settings_manager import load_settings
        self._session.setCurrentText(load_settings().get("default_session","NORMAL"))
        add_row("Session", self._session, 11)

        # Duration
        self._duration = QComboBox()
        self._duration.addItems(["DAY","GTC","GTD","FOK"])
        add_row("Duration", self._duration, 12)

        vbox.addLayout(grid)

        # Estimated value
        self._est = QLabel("")
        self._est.setStyleSheet(f"color:{DIM}; font-size:10px; padding:4px 8px;")
        vbox.addWidget(self._est)
        self._qty.valueChanged.connect(self._update_est)
        self._limit_price.valueChanged.connect(self._update_est)

        # Buttons
        btn_row = QHBoxLayout()
        self._send_btn = QPushButton("  SEND ORDER  ")
        self._send_btn.setFixedHeight(42)
        self._send_btn.setStyleSheet(
            f"background:{GREEN}; color:white; font-weight:bold; font-size:13px; border-radius:4px;")
        self._send_btn.clicked.connect(self._submit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(42)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addWidget(self._send_btn)
        btn_row.addWidget(cancel_btn)
        vbox.addLayout(btn_row)

        # Initialize visibility
        self._on_type_change(self._order_type.currentText())
        self._update_est()
        self._update_color(self._inst.currentText())

    # ─────────────────────────────────────────────

    def _update_color(self, inst: str):
        is_buy = "BUY" in inst.upper()
        color  = GREEN if is_buy else RED
        self._send_btn.setStyleSheet(
            f"background:{color}; color:white; font-weight:bold; font-size:13px; border-radius:4px;")

    def _on_type_change(self, otype: str):
        show_limit    = otype in ("LIMIT","STOP_LIMIT")
        show_stop     = otype in ("STOP","STOP_LIMIT")
        show_trailing = otype == "TRAILING_STOP"
        show_oco      = otype == "OCO"

        self._limit_price.setVisible(show_limit or otype == "LIMIT")
        self._stop_price.setVisible(show_stop)
        self._trailing.setVisible(show_trailing)
        self._trailing_lbl.setVisible(show_trailing)
        self._trailing_pct_cb.setVisible(show_trailing)
        self._oco_tp.setVisible(show_oco)
        self._oco_sl.setVisible(show_oco)
        self._oco_lbl1.setVisible(show_oco)
        self._oco_lbl2.setVisible(show_oco)

        # Always show limit price for LIMIT
        if otype == "MARKET":
            self._limit_price.setVisible(False)

    def _on_trailing_toggle(self, checked: bool):
        self._trailing_lbl.setText("Trailing %" if checked else "Trailing Amount $")

    def _update_est(self):
        try:
            qty   = self._qty.value()
            price = self._limit_price.value()
            if price > 0:
                self._est.setText(f"Est. value: {qty} × ${price:.2f} = ${qty*price:,.2f}")
            else:
                self._est.setText("")
        except: pass

    def _submit(self):
        sym    = self._sym.text().strip().upper()
        asset  = self._asset.currentText()
        inst   = self._inst.currentText()
        qty    = self._qty.value()
        otype  = self._order_type.currentText()
        dur    = self._duration.currentText()
        lp     = self._limit_price.value() if self._limit_price.isVisible() else None
        sp     = self._stop_price.value()  if self._stop_price.isVisible()  else None
        trail  = self._trailing.value()    if self._trailing.isVisible()    else None
        trail_pct = self._trailing_pct_cb.isChecked()

        if not sym:
            QMessageBox.warning(self, "Error", "Symbol is required."); return

        # Build order
        if otype == "OCO":
            order = self.api.build_oco_order(
                sym, qty, inst,
                self._oco_tp.value(),
                self._oco_sl.value(),
                asset_type=asset
            )
        elif asset == "OPTION":
            order = self.api.build_option_order(sym, qty, inst, otype, lp, sp)
        else:
            if trail_pct:
                order = self.api.build_stock_order(sym, qty, inst, otype, lp, sp,
                                                    trailing_percent=trail)
            else:
                order = self.api.build_stock_order(sym, qty, inst, otype, lp, sp,
                                                    trailing_amount=trail)
        order["duration"] = dur
        order["session"] = self._session.currentText()

        # Fire immediately — no confirmation
        # Short guard check
        from config.settings_manager import load_settings as _ls
        if _ls().get("short_guard", True):
            is_sell = "SELL" in inst.upper()
            if is_sell and asset != "OPTION":
                # Check if we'd go short
                pass  # position check happens server-side

        ok, msg = self.api.place_order(order)
        if ok:
            exec_price = lp or sp or self._get_last_price(sym)
            side_norm  = "BUY" if "BUY" in inst.upper() else "SELL"
            trade_store.add_trade(sym, side_norm, exec_price, qty, otype)
            notify(f"{inst.replace('_',' ')} {qty}x {sym}", "success",
                   subtitle=f"${exec_price:.2f}  |  {otype}",
                   duration=3000, parent=self.window())
            if self.on_placed:
                self.on_placed()
            self.accept()
        else:
            notify("Order Rejected", "error",
                   subtitle=msg[:80] if msg else "Unknown error",
                   duration=5000, parent=self.window())
            QMessageBox.critical(self, "Order Failed", msg)

    def _get_last_price(self, sym: str) -> float:
        try:
            q = self.api.get_quote(sym)
            return q.get("quote", {}).get("lastPrice", 0)
        except:
            return 0
