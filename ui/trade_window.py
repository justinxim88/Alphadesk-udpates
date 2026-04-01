"""
Floating Trade Window v13
- Auto-updates bid/ask every second
- Option contract selector (expiration + strike picker)
- Equity and options support
- Stays on top while watching charts
- Fixed rejection notifications
"""

from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QObject
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox,
    QWidget, QFrame, QButtonGroup, QRadioButton, QTabWidget
)
from PyQt6.QtGui import QColor

from ui.toast import notify
from api.trade_store import trade_store

GREEN  = "#3fb950"; RED    = "#f85149"; BLUE   = "#58a6ff"
YELLOW = "#d29922"; DIM    = "#8b949e"; BG     = "#0d1117"
BG2    = "#161b22"; BG3    = "#21262d"; PURPLE = "#c792ea"

INPUT_STYLE = f"""
    QLineEdit, QDoubleSpinBox, QSpinBox, QComboBox {{
        background: {BG};
        color: #e6edf3;
        border: 1px solid #30363d;
        border-radius: 4px;
        padding: 6px 10px;
        font-size: 13px;
        font-family: Consolas;
    }}
    QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
        border: 2px solid {BLUE};
    }}
    QComboBox QAbstractItemView {{
        background: {BG2};
        color: #e6edf3;
        selection-background-color: #1f6feb;
    }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
    QSpinBox::up-button, QSpinBox::down-button {{
        background: #30363d; border: none; width: 20px;
    }}
"""
LBL = "color: #8b949e; font-size: 11px; font-weight: bold;"


class ChainFetcher(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api, sym): super().__init__(); self.api=api; self.sym=sym
    def run(self):
        try: self.done.emit(self.api.get_options_chain(self.sym, strike_count=20))
        except: self.done.emit({})


class PriceBridge(QObject):
    """Bridge to safely pass price data from background thread to UI."""
    price_ready          = pyqtSignal(float, float, float)
    opt_price_ready      = pyqtSignal(float, float, float)
    bracket_price_ready  = pyqtSignal(float, float, float)

class TradeWindow(QDialog):
    def __init__(self, parent, api, symbol=""):
        super().__init__(None, Qt.WindowType.Window |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)
        self.api = api
        self.setWindowTitle("⚡ Trade")
        self.setMinimumWidth(480)
        self.setMaximumWidth(560)
        self.setStyleSheet(f"QDialog{{background:{BG2};color:#e6edf3;}} QLabel{{color:#e6edf3;}}")
        self._symbol        = ""
        self._last_price    = 0.0
        self._bid           = 0.0
        self._ask           = 0.0
        self._chain_data    = {}
        self._chain_threads = []

        # Thread-safe price bridge
        self._bridge = PriceBridge()
        self._bridge.price_ready.connect(self._on_price_ready)
        self._bridge.opt_price_ready.connect(self._on_opt_price_ready)
        self._bridge.bracket_price_ready.connect(self._on_bracket_price_ready)

        self._build()

        # Auto-refresh price every second
        self._price_timer = QTimer()
        self._price_timer.timeout.connect(self._auto_refresh_price)
        self._price_timer.start(1000)

        if symbol:
            self._sym_input.setText(symbol.upper())
            self._symbol = symbol.upper()
            QTimer.singleShot(300, self._fetch_price)

    def _lbl(self, text):
        l = QLabel(text); l.setStyleSheet(LBL); return l

    def _radio(self, text, checked):
        r = QRadioButton(text); r.setChecked(checked)
        r.setStyleSheet(f"QRadioButton{{color:#e6edf3;font-size:12px;font-weight:bold;}} QRadioButton::indicator{{width:14px;height:14px;border-radius:7px;border:2px solid #30363d;background:{BG};}} QRadioButton::indicator:checked{{background:{BLUE};border:2px solid {BLUE};}}")
        return r

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(16,16,16,16); vbox.setSpacing(10)

        # Title
        title = QLabel("⚡  Quick Trade")
        title.setStyleSheet(f"color:{BLUE};font-size:15px;font-weight:bold;")
        vbox.addWidget(title)

        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color:#30363d;"); vbox.addWidget(div)

        # Tabs: Equity | Options
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane{{border:1px solid #30363d;background:{BG2};border-radius:4px;}}
            QTabBar::tab{{background:{BG3};color:{DIM};padding:7px 16px;border:none;font-size:12px;}}
            QTabBar::tab:selected{{background:{BG2};color:#e6edf3;border-bottom:2px solid {BLUE};}}
        """)
        self._tabs.addTab(self._build_equity_tab(), "📈  Equity")
        self._tabs.addTab(self._build_bracket_tab(), "⚡  Bracket")
        self._tabs.addTab(self._build_options_tab(), "🔗  Options")
        vbox.addWidget(self._tabs)

    def _build_bracket_tab(self):
        """Bracket order tab — Entry + Take Profit + Stop Loss as one linked order."""
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(12,12,12,12); v.setSpacing(8)

        # Symbol
        v.addWidget(self._lbl("Symbol"))
        br_sym_row = QHBoxLayout(); br_sym_row.setSpacing(8)
        self._br_sym = QLineEdit(); self._br_sym.setPlaceholderText("SPY")
        self._br_sym.setFixedHeight(36); self._br_sym.setStyleSheet(INPUT_STYLE)
        self._br_sym.textChanged.connect(self._auto_caps_br)
        self._br_sym.returnPressed.connect(self._fetch_bracket_price)
        self._br_sym.editingFinished.connect(self._fetch_bracket_price)
        br_sym_row.addWidget(self._br_sym)
        br_get = QPushButton("Go"); br_get.setFixedSize(50,36)
        br_get.setStyleSheet(f"QPushButton{{background:#30363d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;font-size:12px;font-weight:bold;}} QPushButton:hover{{background:{BLUE};color:#fff;}}")
        br_get.clicked.connect(self._fetch_bracket_price)
        br_sym_row.addWidget(br_get)
        v.addLayout(br_sym_row)

        # Live price
        self._br_price_lbl = QLabel("Last: —   Bid: —   Ask: —")
        self._br_price_lbl.setStyleSheet(f"color:{YELLOW};font-size:12px;font-weight:bold;padding:4px 0;")
        v.addWidget(self._br_price_lbl)

        # Side
        v.addWidget(self._lbl("Side"))
        self._br_side = QComboBox(); self._br_side.addItems(["BUY","SELL"])
        self._br_side.setFixedHeight(36); self._br_side.setStyleSheet(INPUT_STYLE)
        self._br_side.currentTextChanged.connect(self._update_br_btn)
        v.addWidget(self._br_side)

        # Entry type
        v.addWidget(self._lbl("Entry Type"))
        self._br_etype = QComboBox(); self._br_etype.addItems(["LIMIT","MARKET"])
        self._br_etype.setFixedHeight(36); self._br_etype.setStyleSheet(INPUT_STYLE)
        self._br_etype.currentTextChanged.connect(self._toggle_br_entry)
        v.addWidget(self._br_etype)

        # Entry Price
        self._br_entry_lbl = QLabel("Entry Price"); self._br_entry_lbl.setStyleSheet(LBL)
        v.addWidget(self._br_entry_lbl)
        self._br_entry = QDoubleSpinBox(); self._br_entry.setRange(0,999999)
        self._br_entry.setDecimals(2); self._br_entry.setFixedHeight(36)
        self._br_entry.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._br_entry)

        # Quantity
        v.addWidget(self._lbl("Quantity"))
        self._br_qty = QSpinBox(); self._br_qty.setRange(1,100000)
        self._br_qty.setValue(1); self._br_qty.setFixedHeight(36)
        self._br_qty.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._br_qty)

        qty_row = QHBoxLayout(); qty_row.setSpacing(4)
        for qv in [1,5,10,25,50,100]:
            b = QPushButton(str(qv)); b.setFixedHeight(28)
            b.setStyleSheet(f"QPushButton{{background:{BG3};color:#ffffff;border:1px solid #58a6ff;border-radius:3px;font-size:11px;font-weight:bold;}} QPushButton:hover{{background:#1f6feb;color:#fff;}}")
            b.clicked.connect(lambda _,vv=qv: self._br_qty.setValue(vv))
            qty_row.addWidget(b)
        v.addLayout(qty_row)

        # Take Profit
        v.addWidget(self._lbl("Take Profit Price"))
        self._br_tp = QDoubleSpinBox(); self._br_tp.setRange(0,999999)
        self._br_tp.setDecimals(2); self._br_tp.setFixedHeight(36)
        self._br_tp.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._br_tp)

        # Stop Loss
        v.addWidget(self._lbl("Stop Loss Price"))
        self._br_sl = QDoubleSpinBox(); self._br_sl.setRange(0,999999)
        self._br_sl.setDecimals(2); self._br_sl.setFixedHeight(36)
        self._br_sl.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._br_sl)

        # Session / Duration
        sd = QHBoxLayout(); sd.setSpacing(8)
        sc = QVBoxLayout(); sc.addWidget(self._lbl("Session"))
        self._br_sess = QComboBox(); self._br_sess.setFixedHeight(34)
        self._br_sess.addItems(["NORMAL","PRE_MARKET","AFTER_HOURS","SEAMLESS"])
        self._br_sess.setStyleSheet(INPUT_STYLE); sc.addWidget(self._br_sess)
        dc = QVBoxLayout(); dc.addWidget(self._lbl("Duration"))
        self._br_dur = QComboBox(); self._br_dur.setFixedHeight(34)
        self._br_dur.addItems(["DAY","GTC","GTC_EXT"])
        self._br_dur.setStyleSheet(INPUT_STYLE); dc.addWidget(self._br_dur)
        sd.addLayout(sc); sd.addLayout(dc); v.addLayout(sd)

        # Summary label
        self._br_summary = QLabel("")
        self._br_summary.setStyleSheet(f"color:{DIM};font-size:10px;")
        self._br_summary.setWordWrap(True)
        v.addWidget(self._br_summary)

        # Send button
        self._br_btn = QPushButton("SEND BRACKET ORDER")
        self._br_btn.setFixedHeight(46)
        self._br_btn.setStyleSheet(f"QPushButton{{background:#238636;color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:bold;}} QPushButton:hover{{background:#2ea043;}}")
        self._br_btn.clicked.connect(self._send_bracket)
        v.addWidget(self._br_btn)

        # Wire price updates
        self._br_entry.valueChanged.connect(self._update_br_summary)
        self._br_tp.valueChanged.connect(self._update_br_summary)
        self._br_sl.valueChanged.connect(self._update_br_summary)
        self._br_qty.valueChanged.connect(self._update_br_summary)

        return w

    def _auto_caps_br(self, t):
        u = t.upper()
        if u != t:
            cur = self._br_sym.cursorPosition()
            self._br_sym.blockSignals(True); self._br_sym.setText(u); self._br_sym.blockSignals(False)
            self._br_sym.setCursorPosition(cur)

    def _toggle_br_entry(self, etype):
        self._br_entry_lbl.setVisible(etype == "LIMIT")
        self._br_entry.setVisible(etype == "LIMIT")

    def _update_br_btn(self, side=None):
        side = side or self._br_side.currentText()
        is_buy = side == "BUY"
        color = "#238636" if is_buy else "#da3633"
        hover = "#2ea043" if is_buy else "#f85149"
        self._br_btn.setStyleSheet(f"QPushButton{{background:{color};color:#fff;border:none;border-radius:6px;font-size:13px;font-weight:bold;}} QPushButton:hover{{background:{hover};}}")

    def _fetch_bracket_price(self):
        sym = self._br_sym.text().strip().upper()
        if not sym or len(sym) > 10 or not sym.isalpha(): return
        import threading
        def fetch():
            try:
                q    = self.api.get_quote(sym)
                qd   = q.get("quote",{})
                last = float(qd.get("lastPrice",0) or 0)
                bid  = float(qd.get("bidPrice",0) or 0)
                ask  = float(qd.get("askPrice",0) or 0)
                # Emit signal — UI update happens on main thread
                self._bridge.bracket_price_ready.emit(last, bid, ask)
            except Exception as e:
                print(f"[Bracket] price fetch error: {e}")
        threading.Thread(target=fetch, daemon=True).start()

    def _update_br_summary(self):
        entry = self._br_entry.value()
        tp    = self._br_tp.value()
        sl    = self._br_sl.value()
        qty   = self._br_qty.value()
        side  = self._br_side.currentText()
        if entry > 0 and tp > 0 and sl > 0:
            risk   = abs(entry - sl) * qty
            reward = abs(tp - entry) * qty
            rr     = reward / risk if risk > 0 else 0
            self._br_summary.setText(
                f"Risk: ${risk:.2f}  |  Reward: ${reward:.2f}  |  R/R: 1:{rr:.1f}\n"
                f"Entry: ${entry:.2f}  |  TP: ${tp:.2f}  |  SL: ${sl:.2f}")

    def _send_bracket(self):
        sym = self._br_sym.text().strip().upper()
        if not sym:
            notify("No Symbol","warning",subtitle="Enter a symbol",duration=3000); return
        side   = self._br_side.currentText()
        etype  = self._br_etype.currentText()
        entry  = self._br_entry.value()
        tp     = self._br_tp.value()
        sl     = self._br_sl.value()
        qty    = self._br_qty.value()
        sess   = self._br_sess.currentText()
        dur    = self._br_dur.currentText()

        if tp <= 0 or sl <= 0:
            notify("Missing Prices","warning",
                   subtitle="Set Take Profit and Stop Loss",duration=3000); return
        if etype == "LIMIT" and entry <= 0:
            notify("Missing Entry","warning",
                   subtitle="Set Entry Price",duration=3000); return

        try:
            order = self.api.build_bracket_order(
                sym, qty, side, entry, tp, sl,
                entry_type=etype, session=sess, duration=dur)
            ok, msg = self.api.place_order(order)
            if ok:
                is_buy = side == "BUY"
                notify(f"{'🟢' if is_buy else '🔴'} Bracket Placed — {sym}", "fill",
                       subtitle=f"Entry: ${entry:.2f}  TP: ${tp:.2f}  SL: ${sl:.2f}",
                       duration=6000)
            else:
                notify(f"❌ Bracket Rejected — {sym}", "reject",
                       subtitle=msg[:100] if msg else "Rejected by broker",
                       duration=7000)
        except Exception as e:
            notify("Bracket Error","reject",subtitle=str(e)[:100],duration=7000)

    def _build_equity_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(12,12,12,12); v.setSpacing(8)

        # Symbol
        v.addWidget(self._lbl("Symbol"))
        sym_row = QHBoxLayout(); sym_row.setSpacing(8)
        self._sym_input = QLineEdit(); self._sym_input.setPlaceholderText("SPY")
        self._sym_input.setFixedHeight(36); self._sym_input.setStyleSheet(INPUT_STYLE)
        self._sym_input.textChanged.connect(self._auto_caps_eq)
        self._sym_input.returnPressed.connect(self._fetch_price)
        self._sym_input.editingFinished.connect(self._fetch_price)
        sym_row.addWidget(self._sym_input)
        get_btn = QPushButton("Go"); get_btn.setFixedSize(50,36)
        get_btn.setStyleSheet(f"QPushButton{{background:#30363d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;font-size:12px;font-weight:bold;}} QPushButton:hover{{background:{BLUE};color:#fff;}}")
        get_btn.clicked.connect(self._fetch_price)
        sym_row.addWidget(get_btn)
        v.addLayout(sym_row)

        # Live price display
        self._eq_price_lbl = QLabel("Last: —   Bid: —   Ask: —")
        self._eq_price_lbl.setStyleSheet(f"color:{YELLOW};font-size:12px;font-weight:bold;padding:4px 0;")
        v.addWidget(self._eq_price_lbl)

        # BUY / SELL toggle buttons
        bs_row = QHBoxLayout(); bs_row.setSpacing(8)
        self._eq_buy_btn = QPushButton("BUY")
        self._eq_buy_btn.setFixedHeight(44)
        self._eq_buy_btn.setStyleSheet("QPushButton{background:#238636;color:#fff;border:none;border-radius:6px;font-size:15px;font-weight:bold;} QPushButton:hover{background:#2ea043;} QPushButton:disabled{background:#1a3a1a;color:#3fb950;border:2px solid #3fb950;}")
        self._eq_buy_btn.clicked.connect(lambda: self._set_eq_side("BUY"))
        bs_row.addWidget(self._eq_buy_btn)

        self._eq_sell_btn = QPushButton("SELL")
        self._eq_sell_btn.setFixedHeight(44)
        self._eq_sell_btn.setStyleSheet("QPushButton{background:#21262d;color:#f85149;border:2px solid #f85149;border-radius:6px;font-size:15px;font-weight:bold;} QPushButton:hover{background:#da3633;color:#fff;border:2px solid #da3633;}")
        self._eq_sell_btn.clicked.connect(lambda: self._set_eq_side("SELL"))
        bs_row.addWidget(self._eq_sell_btn)
        v.addLayout(bs_row)

        self._eq_side = "BUY"  # track current side

        # Order type — Limit and Market only
        v.addWidget(self._lbl("Order Type"))
        otype_row = QHBoxLayout(); otype_row.setSpacing(8)
        self._eq_lim_type_btn = QPushButton("LIMIT")
        self._eq_lim_type_btn.setFixedHeight(36)
        self._eq_lim_type_btn.setStyleSheet("QPushButton{background:#1f6feb;color:#fff;border:none;border-radius:4px;font-size:13px;font-weight:bold;} QPushButton:hover{background:#388bfd;} QPushButton:disabled{background:#21262d;color:#58a6ff;border:2px solid #58a6ff;}")
        self._eq_lim_type_btn.clicked.connect(lambda: self._set_eq_otype("LIMIT"))
        otype_row.addWidget(self._eq_lim_type_btn)

        self._eq_mkt_type_btn = QPushButton("MARKET")
        self._eq_mkt_type_btn.setFixedHeight(36)
        self._eq_mkt_type_btn.setStyleSheet("QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;font-size:13px;font-weight:bold;} QPushButton:hover{background:#30363d;}")
        self._eq_mkt_type_btn.clicked.connect(lambda: self._set_eq_otype("MARKET"))
        otype_row.addWidget(self._eq_mkt_type_btn)
        v.addLayout(otype_row)

        self._eq_otype_val = "LIMIT"  # track current order type

        # Qty
        v.addWidget(self._lbl("Quantity"))
        self._eq_qty = QSpinBox(); self._eq_qty.setRange(1,100000)
        self._eq_qty.setValue(1); self._eq_qty.setFixedHeight(36)
        self._eq_qty.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._eq_qty)

        qty_row = QHBoxLayout(); qty_row.setSpacing(4)
        for qv in [1,5,10,25,50,100]:
            b = QPushButton(str(qv)); b.setFixedHeight(28)
            b.setStyleSheet(f"QPushButton{{background:{BG3};color:#ffffff;border:1px solid #58a6ff;border-radius:3px;font-size:11px;font-weight:bold;}} QPushButton:hover{{background:#1f6feb;color:#fff;}}")
            b.clicked.connect(lambda _,vv=qv: self._eq_qty.setValue(vv))
            qty_row.addWidget(b)
        v.addLayout(qty_row)

        # Limit price
        self._eq_lim_lbl = QLabel("Limit Price"); self._eq_lim_lbl.setStyleSheet(LBL)
        v.addWidget(self._eq_lim_lbl)
        self._eq_lim = QDoubleSpinBox(); self._eq_lim.setRange(0,999999)
        self._eq_lim.setDecimals(2); self._eq_lim.setFixedHeight(36)
        self._eq_lim.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._eq_lim)

        # Stop price
        self._eq_stop_lbl = QLabel("Stop Price"); self._eq_stop_lbl.setStyleSheet(LBL)
        v.addWidget(self._eq_stop_lbl)
        self._eq_stop = QDoubleSpinBox(); self._eq_stop.setRange(0,999999)
        self._eq_stop.setDecimals(2); self._eq_stop.setFixedHeight(36)
        self._eq_stop.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._eq_stop)

        # Session / Duration
        sd = QHBoxLayout(); sd.setSpacing(8)
        sc = QVBoxLayout(); sc.addWidget(self._lbl("Session"))
        self._eq_sess = QComboBox(); self._eq_sess.setFixedHeight(34)
        self._eq_sess.addItems(["NORMAL","PRE_MARKET","AFTER_HOURS","SEAMLESS"])
        self._eq_sess.setStyleSheet(INPUT_STYLE); sc.addWidget(self._eq_sess)
        dc = QVBoxLayout(); dc.addWidget(self._lbl("Duration"))
        self._eq_dur = QComboBox(); self._eq_dur.setFixedHeight(34)
        self._eq_dur.addItems(["DAY","GTC","GTC_EXT","GTD","FOK"])
        self._eq_dur.setStyleSheet(INPUT_STYLE); dc.addWidget(self._eq_dur)
        sd.addLayout(sc); sd.addLayout(dc); v.addLayout(sd)

        # Est value
        self._eq_est = QLabel("")
        self._eq_est.setStyleSheet(f"color:{DIM};font-size:11px;")
        v.addWidget(self._eq_est)
        self._eq_qty.valueChanged.connect(self._update_eq_est)
        self._eq_lim.valueChanged.connect(self._update_eq_est)

        # Send button
        self._eq_btn = QPushButton("BUY"); self._eq_btn.setFixedHeight(46)
        self._eq_btn.setStyleSheet(f"QPushButton{{background:#238636;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:bold;}} QPushButton:hover{{background:#2ea043;}}")
        self._eq_btn.clicked.connect(self._send_equity)
        v.addWidget(self._eq_btn)

        self._toggle_eq_prices("MARKET")
        return w

    def _build_options_tab(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setContentsMargins(12,12,12,12); v.setSpacing(8)

        # Symbol
        v.addWidget(self._lbl("Underlying Symbol"))
        opt_sym_row = QHBoxLayout(); opt_sym_row.setSpacing(8)
        self._opt_sym = QLineEdit(); self._opt_sym.setPlaceholderText("SPY")
        self._opt_sym.setFixedHeight(36); self._opt_sym.setStyleSheet(INPUT_STYLE)
        self._opt_sym.textChanged.connect(self._auto_caps_opt)
        self._opt_sym.returnPressed.connect(self._load_chain)
        self._opt_sym.editingFinished.connect(self._load_chain)
        opt_sym_row.addWidget(self._opt_sym)
        chain_btn = QPushButton("Load"); chain_btn.setFixedSize(60,36)
        chain_btn.setStyleSheet(f"QPushButton{{background:#1f6feb;color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:bold;}} QPushButton:hover{{background:#388bfd;}}")
        chain_btn.clicked.connect(self._load_chain)
        opt_sym_row.addWidget(chain_btn)
        v.addLayout(opt_sym_row)

        # Live price
        self._opt_price_lbl = QLabel("Last: —   Bid: —   Ask: —")
        self._opt_price_lbl.setStyleSheet(f"color:{YELLOW};font-size:12px;font-weight:bold;padding:4px 0;")
        v.addWidget(self._opt_price_lbl)

        # Expiration
        v.addWidget(self._lbl("Expiration"))
        self._opt_exp = QComboBox(); self._opt_exp.setFixedHeight(36)
        self._opt_exp.setStyleSheet(INPUT_STYLE)
        self._opt_exp.currentTextChanged.connect(self._on_exp_changed)
        v.addWidget(self._opt_exp)

        # Call/Put + Strike row
        cp_row = QHBoxLayout(); cp_row.setSpacing(12)
        cp_col = QVBoxLayout(); cp_col.addWidget(self._lbl("Type"))
        self._opt_cp = QComboBox(); self._opt_cp.addItems(["CALL","PUT"])
        self._opt_cp.setFixedHeight(36); self._opt_cp.setStyleSheet(INPUT_STYLE)
        self._opt_cp.currentTextChanged.connect(self._on_cp_changed)
        cp_col.addWidget(self._opt_cp)
        sk_col = QVBoxLayout(); sk_col.addWidget(self._lbl("Strike"))
        self._opt_strike = QComboBox(); self._opt_strike.setFixedHeight(36)
        self._opt_strike.setStyleSheet(INPUT_STYLE)
        self._opt_strike.currentTextChanged.connect(self._on_strike_changed)
        sk_col.addWidget(self._opt_strike)
        cp_row.addLayout(cp_col); cp_row.addLayout(sk_col)
        v.addLayout(cp_row)

        # Selected contract display
        self._opt_contract_lbl = QLabel("—")
        self._opt_contract_lbl.setStyleSheet(f"color:#c792ea;font-size:11px;font-family:Consolas;")
        v.addWidget(self._opt_contract_lbl)

        # Contract bid/ask
        self._opt_contract_price = QLabel("")
        self._opt_contract_price.setStyleSheet(f"color:{YELLOW};font-size:12px;font-weight:bold;")
        v.addWidget(self._opt_contract_price)

        # Instruction
        v.addWidget(self._lbl("Instruction"))
        self._opt_instr = QComboBox(); self._opt_instr.setFixedHeight(36)
        self._opt_instr.addItems(["BUY_TO_OPEN","SELL_TO_OPEN","BUY_TO_CLOSE","SELL_TO_CLOSE"])
        self._opt_instr.setStyleSheet(INPUT_STYLE)
        self._opt_instr.currentTextChanged.connect(self._update_opt_btn)
        v.addWidget(self._opt_instr)

        # Qty
        v.addWidget(self._lbl("Contracts"))
        self._opt_qty = QSpinBox(); self._opt_qty.setRange(1,1000)
        self._opt_qty.setValue(1); self._opt_qty.setFixedHeight(36)
        self._opt_qty.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._opt_qty)

        # Limit price
        v.addWidget(self._lbl("Limit Price"))
        self._opt_lim = QDoubleSpinBox(); self._opt_lim.setRange(0,99999)
        self._opt_lim.setDecimals(2); self._opt_lim.setFixedHeight(36)
        self._opt_lim.setStyleSheet(INPUT_STYLE)
        v.addWidget(self._opt_lim)

        # Session/Duration
        sd = QHBoxLayout(); sd.setSpacing(8)
        sc2 = QVBoxLayout(); sc2.addWidget(self._lbl("Session"))
        self._opt_sess = QComboBox(); self._opt_sess.setFixedHeight(34)
        self._opt_sess.addItems(["NORMAL","PRE_MARKET","AFTER_HOURS","SEAMLESS"])
        self._opt_sess.setStyleSheet(INPUT_STYLE); sc2.addWidget(self._opt_sess)
        dc2 = QVBoxLayout(); dc2.addWidget(self._lbl("Duration"))
        self._opt_dur = QComboBox(); self._opt_dur.setFixedHeight(34)
        self._opt_dur.addItems(["DAY","GTC","GTC_EXT"])
        self._opt_dur.setStyleSheet(INPUT_STYLE); dc2.addWidget(self._opt_dur)
        sd.addLayout(sc2); sd.addLayout(dc2); v.addLayout(sd)

        # Stop Loss / Take Profit (optional)
        div2 = QFrame(); div2.setFrameShape(QFrame.Shape.HLine)
        div2.setStyleSheet("color:#30363d;"); v.addWidget(div2)

        sl_tp_lbl = QLabel("Stop Loss & Take Profit (optional — creates OCO exit)")
        sl_tp_lbl.setStyleSheet(f"color:{DIM};font-size:10px;font-weight:bold;")
        v.addWidget(sl_tp_lbl)

        sl_tp_row = QHBoxLayout(); sl_tp_row.setSpacing(8)
        sl_col = QVBoxLayout()
        sl_col.addWidget(self._lbl("Stop Loss $"))
        self._opt_sl = QDoubleSpinBox(); self._opt_sl.setRange(0,99999)
        self._opt_sl.setDecimals(2); self._opt_sl.setFixedHeight(34)
        self._opt_sl.setStyleSheet(INPUT_STYLE)
        sl_col.addWidget(self._opt_sl)

        tp_col = QVBoxLayout()
        tp_col.addWidget(self._lbl("Take Profit $"))
        self._opt_tp = QDoubleSpinBox(); self._opt_tp.setRange(0,99999)
        self._opt_tp.setDecimals(2); self._opt_tp.setFixedHeight(34)
        self._opt_tp.setStyleSheet(INPUT_STYLE)
        tp_col.addWidget(self._opt_tp)

        sl_tp_row.addLayout(sl_col); sl_tp_row.addLayout(tp_col)
        v.addLayout(sl_tp_row)

        self._opt_oco_lbl = QLabel("")
        self._opt_oco_lbl.setStyleSheet(f"color:{DIM};font-size:10px;")
        v.addWidget(self._opt_oco_lbl)
        self._opt_sl.valueChanged.connect(self._update_opt_oco_summary)
        self._opt_tp.valueChanged.connect(self._update_opt_oco_summary)
        self._opt_lim.valueChanged.connect(self._update_opt_oco_summary)

        # Send
        self._opt_btn = QPushButton("SEND ORDER"); self._opt_btn.setFixedHeight(46)
        self._opt_btn.setStyleSheet(f"QPushButton{{background:#238636;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:bold;}} QPushButton:hover{{background:#2ea043;}}")
        self._opt_btn.clicked.connect(self._send_option)
        v.addWidget(self._opt_btn)
        return w

    def _update_opt_oco_summary(self):
        entry = self._opt_lim.value()
        sl    = self._opt_sl.value()
        tp    = self._opt_tp.value()
        if entry > 0 and sl > 0 and tp > 0:
            risk   = abs(entry - sl)
            reward = abs(tp - entry)
            rr     = reward/risk if risk > 0 else 0
            self._opt_oco_lbl.setText(
                f"OCO will be placed  |  Risk: ${risk:.2f}  Reward: ${reward:.2f}  R/R: 1:{rr:.1f}")
        elif sl > 0 or tp > 0:
            self._opt_oco_lbl.setText("Fill in both SL and TP to enable OCO exit")
        else:
            self._opt_oco_lbl.setText("Leave blank for simple order, or set both for OCO exit")

    # ── AUTO CAPS ────────────────────────────────────────────

    def _auto_caps_eq(self, t):
        u = t.upper()
        if u!=t:
            cur=self._sym_input.cursorPosition()
            self._sym_input.blockSignals(True); self._sym_input.setText(u); self._sym_input.blockSignals(False)
            self._sym_input.setCursorPosition(cur)

    def _auto_caps_opt(self, t):
        u = t.upper()
        if u!=t:
            cur=self._opt_sym.cursorPosition()
            self._opt_sym.blockSignals(True); self._opt_sym.setText(u); self._opt_sym.blockSignals(False)
            self._opt_sym.setCursorPosition(cur)

    # ── PRICE FETCH ──────────────────────────────────────────

    def _fetch_price(self):
        sym = self._sym_input.text().strip().upper()
        if not sym or len(sym) > 10 or not sym.isalpha(): return
        self._last_fetched_sym = sym
        self._symbol = sym
        import threading
        threading.Thread(target=self._do_fetch, args=(sym,), daemon=True).start()

    def _do_fetch(self, sym):
        """Run in background thread — emit signal to update UI safely."""
        try:
            q  = self.api.get_quote(sym)
            qd = q.get("quote",{})
            last = float(qd.get("lastPrice",0) or 0)
            bid  = float(qd.get("bidPrice",0) or 0)
            ask  = float(qd.get("askPrice",0) or 0)
            self._bridge.price_ready.emit(last, bid, ask)
        except Exception as e:
            print(f"[TradeWindow] fetch error: {e}")

    def _on_price_ready(self, last, bid, ask):
        """Called on main thread via signal — safe to update UI."""
        self._last_price = last
        self._bid = bid
        self._ask = ask
        self._eq_price_lbl.setText(
            f"Last: ${last:.2f}   "
            f"<span style='color:#3fb950'>Bid: ${bid:.2f}</span>   "
            f"<span style='color:#f85149'>Ask: ${ask:.2f}</span>")
        # Always auto-update limit price in real time
        side  = getattr(self, '_eq_side', 'BUY')
        price = ask if side == "BUY" else bid
        if price > 0:
            self._eq_lim.blockSignals(True)
            self._eq_lim.setValue(price)
            self._eq_lim.blockSignals(False)
        self._update_eq_est()

    def _auto_refresh_price(self):
        """Called every second — refresh price for active tab."""
        import threading
        if self._tabs.currentIndex() == 0:
            sym = self._sym_input.text().strip().upper()
            if sym and len(sym) <= 10 and sym.isalpha():
                threading.Thread(target=self._do_fetch, args=(sym,), daemon=True).start()
        else:
            sym = self._opt_sym.text().strip().upper()
            if sym and len(sym) <= 10 and sym.isalpha():
                threading.Thread(target=self._do_fetch_opt_price, args=(sym,), daemon=True).start()

    def _do_fetch_opt_price(self, sym):
        try:
            q = self.api.get_quote(sym)
            qd = q.get("quote",{})
            last = float(qd.get("lastPrice",0) or 0)
            bid  = float(qd.get("bidPrice",0) or 0)
            ask  = float(qd.get("askPrice",0) or 0)
            self._bridge.opt_price_ready.emit(last, bid, ask)
        except Exception as e:
            print(f"[TradeWindow] opt price fetch error: {e}")

    def _on_bracket_price_ready(self, last, bid, ask):
        """Called on main thread — safe to update bracket UI."""
        self._br_price_lbl.setText(
            f"Last: ${last:.2f}   "
            f"<span style='color:#3fb950'>Bid: ${bid:.2f}</span>   "
            f"<span style='color:#f85149'>Ask: ${ask:.2f}</span>")
        side = self._br_side.currentText()
        if last > 0:
            if side == "BUY":
                self._br_entry.setValue(round(ask, 2))
                self._br_tp.setValue(round(last * 1.02, 2))
                self._br_sl.setValue(round(last * 0.98, 2))
            else:
                self._br_entry.setValue(round(bid, 2))
                self._br_tp.setValue(round(last * 0.98, 2))
                self._br_sl.setValue(round(last * 1.02, 2))

    def _on_opt_price_ready(self, last, bid, ask):
        """Called on main thread — safe to update UI."""
        self._opt_price_lbl.setText(
            f"Last: ${last:.2f}   "
            f"<span style='color:#3fb950'>Bid: ${bid:.2f}</span>   "
            f"<span style='color:#f85149'>Ask: ${ask:.2f}</span>")

    # ── OPTIONS CHAIN ────────────────────────────────────────

    def _load_chain(self):
        sym = self._opt_sym.text().strip().upper()
        if not sym or len(sym) > 10: return
        if sym == getattr(self, '_last_chain_sym', ''):
            return  # avoid double fetch
        self._last_chain_sym = sym
        # Also fetch underlying price
        import threading
        threading.Thread(target=self._do_fetch_opt_price, args=(sym,), daemon=True).start()
        t = ChainFetcher(self.api, sym)
        t.done.connect(self._on_chain); t.done.connect(lambda _: self._chain_threads.remove(t) if t in self._chain_threads else None)
        self._chain_threads.append(t); t.start()

    def _on_chain(self, data: dict):
        if not data: return
        self._chain_data = data
        # Parse expirations
        calls = data.get("callExpDateMap",{}); puts = data.get("putExpDateMap",{})
        dates = sorted(set(
            [k.split(":")[0] for k in calls.keys()] +
            [k.split(":")[0] for k in puts.keys()]
        ))
        self._opt_exp.blockSignals(True)
        self._opt_exp.clear()
        self._opt_exp.addItems(dates)
        self._opt_exp.blockSignals(False)
        if dates:
            self._opt_exp.setCurrentIndex(0)
            self._on_exp_changed(dates[0])

    def _on_exp_changed(self, date_str):
        self._populate_strikes(date_str, self._opt_cp.currentText())

    def _on_cp_changed(self, cp):
        self._populate_strikes(self._opt_exp.currentText(), cp)

    def _populate_strikes(self, date_str, cp):
        if not self._chain_data: return
        exp_map = self._chain_data.get("callExpDateMap" if cp=="CALL" else "putExpDateMap",{})
        strikes = []
        for key, inner in exp_map.items():
            if key.split(":")[0] == date_str:
                for strike_str in inner.keys():
                    try: strikes.append(float(strike_str))
                    except: pass
        strikes.sort()
        self._opt_strike.blockSignals(True)
        self._opt_strike.clear()
        self._opt_strike.addItems([f"{s:.2f}" if s!=int(s) else f"{int(s)}" for s in strikes])
        self._opt_strike.blockSignals(False)
        # Find ATM
        under = self._chain_data.get("underlyingPrice",0)
        if under and strikes:
            atm = min(strikes, key=lambda s: abs(s-under))
            idx = strikes.index(atm)
            self._opt_strike.setCurrentIndex(idx)
        self._on_strike_changed(self._opt_strike.currentText())

    def _on_strike_changed(self, strike_str):
        if not strike_str: return
        date_str = self._opt_exp.currentText()
        cp       = self._opt_cp.currentText()
        sym      = self._opt_sym.text().strip().upper()
        # Build OCC symbol
        try:
            from datetime import datetime
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            date_part = dt.strftime("%y%m%d")
        except: date_part = "000000"
        c_p = "C" if cp=="CALL" else "P"
        try: strike = float(strike_str)
        except: return
        sym_padded = sym.ljust(6)
        strike_int = int(round(strike*1000))
        occ_sym = f"{sym_padded}{date_part}{c_p}{strike_int:08d}"
        self._opt_contract_lbl.setText(occ_sym)

        # Get bid/ask for this contract
        exp_map = self._chain_data.get("callExpDateMap" if cp=="CALL" else "putExpDateMap",{})
        for key, inner in exp_map.items():
            if key.split(":")[0] == date_str:
                for sk, contracts in inner.items():
                    try:
                        if abs(float(sk)-strike)<0.001 and contracts:
                            contract = contracts[0]
                            bid = float(contract.get("bid",0) or 0)
                            ask = float(contract.get("ask",0) or 0)
                            self._opt_contract_price.setText(
                                f"<span style='color:#3fb950'>Bid: ${bid:.2f}</span>   "
                                f"<span style='color:#f85149'>Ask: ${ask:.2f}</span>")
                            # Auto-set limit price
                            instr = self._opt_instr.currentText()
                            if "BUY" in instr:
                                self._opt_lim.setValue(ask)
                            else:
                                self._opt_lim.setValue(bid)
                            return
                    except: pass

    # ── UI HELPERS ───────────────────────────────────────────

    def _toggle_eq_prices(self, otype=None):
        # Simplified - only LIMIT and MARKET supported now
        pass

    def _set_eq_side(self, side):
        self._eq_side = side
        if side == "BUY":
            self._eq_buy_btn.setStyleSheet("QPushButton{background:#238636;color:#fff;border:none;border-radius:6px;font-size:15px;font-weight:bold;} QPushButton:hover{background:#2ea043;}")
            self._eq_sell_btn.setStyleSheet("QPushButton{background:#21262d;color:#f85149;border:2px solid #f85149;border-radius:6px;font-size:15px;font-weight:bold;} QPushButton:hover{background:#da3633;color:#fff;}")
            self._eq_btn.setStyleSheet("QPushButton{background:#238636;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:bold;} QPushButton:hover{background:#2ea043;}")
            self._eq_btn.setText("BUY")
            # Update limit price to ask
            if self._ask > 0:
                self._eq_lim.blockSignals(True)
                self._eq_lim.setValue(self._ask)
                self._eq_lim.blockSignals(False)
        else:
            self._eq_sell_btn.setStyleSheet("QPushButton{background:#da3633;color:#fff;border:none;border-radius:6px;font-size:15px;font-weight:bold;} QPushButton:hover{background:#f85149;}")
            self._eq_buy_btn.setStyleSheet("QPushButton{background:#21262d;color:#3fb950;border:2px solid #3fb950;border-radius:6px;font-size:15px;font-weight:bold;} QPushButton:hover{background:#238636;color:#fff;}")
            self._eq_btn.setStyleSheet("QPushButton{background:#da3633;color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:bold;} QPushButton:hover{background:#f85149;}")
            self._eq_btn.setText("SELL")
            # Update limit price to bid
            if self._bid > 0:
                self._eq_lim.blockSignals(True)
                self._eq_lim.setValue(self._bid)
                self._eq_lim.blockSignals(False)

    def _set_eq_otype(self, otype):
        self._eq_otype_val = otype
        if otype == "LIMIT":
            self._eq_lim_type_btn.setStyleSheet("QPushButton{background:#1f6feb;color:#fff;border:none;border-radius:4px;font-size:13px;font-weight:bold;} QPushButton:hover{background:#388bfd;}")
            self._eq_mkt_type_btn.setStyleSheet("QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;font-size:13px;font-weight:bold;} QPushButton:hover{background:#30363d;}")
            self._eq_lim_lbl.setVisible(True)
            self._eq_lim.setVisible(True)
        else:
            self._eq_mkt_type_btn.setStyleSheet("QPushButton{background:#1f6feb;color:#fff;border:none;border-radius:4px;font-size:13px;font-weight:bold;} QPushButton:hover{background:#388bfd;}")
            self._eq_lim_type_btn.setStyleSheet("QPushButton{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:4px;font-size:13px;font-weight:bold;} QPushButton:hover{background:#30363d;}")
            self._eq_lim_lbl.setVisible(False)
            self._eq_lim.setVisible(False)

    def _update_eq_btn(self, instr=None):
        pass  # replaced by _set_eq_side

    def _update_opt_btn(self, instr=None):
        instr = instr or self._opt_instr.currentText()
        is_buy = "BUY" in instr
        color = "#238636" if is_buy else "#da3633"
        hover = "#2ea043" if is_buy else "#f85149"
        self._opt_btn.setStyleSheet(f"QPushButton{{background:{color};color:#fff;border:none;border-radius:6px;font-size:14px;font-weight:bold;}} QPushButton:hover{{background:{hover};}}")

    def _update_eq_est(self):
        qty   = self._eq_qty.value()
        price = self._eq_lim.value() or self._last_price
        if price>0 and qty>0:
            self._eq_est.setText(f"Est. value: {qty} × ${price:.2f} = ${qty*price:,.2f}")

    # ── SEND ORDERS ──────────────────────────────────────────

    def _send_equity(self):
        sym  = self._sym_input.text().strip().upper()
        if not sym:
            notify("No Symbol","warning",subtitle="Enter a symbol",duration=3000); return
        side  = getattr(self, '_eq_side', 'BUY')
        otype = getattr(self, '_eq_otype_val', 'LIMIT')
        qty   = self._eq_qty.value()
        sess  = self._eq_sess.currentText()
        dur   = self._eq_dur.currentText()
        lp    = self._eq_lim.value() if otype == "LIMIT" else None
        try:
            order = self.api.build_stock_order(sym, qty, side, otype, lp, None,
                                               session=sess, duration=dur)
            ok, msg = self.api.place_order(order)
            if ok:
                is_buy = side == "BUY"
                fill_price = lp or self._last_price
                trade_store.add_trade(sym, side, fill_price, qty, otype)
                notify(f"{'🟢 BUY' if is_buy else '🔴 SELL'}  {qty}× {sym}",
                       "fill", subtitle=f"${fill_price:.2f}  |  {otype}",
                       duration=5000)
                # Chart stamp + journal
                try:
                    import uuid
                    from ui.chart_stamps import chart_stamp_manager
                    from ui.trade_journal import add_journal_entry
                    from datetime import datetime
                    tid = str(uuid.uuid4())[:8]
                    instr = side
                    chart_stamp_manager.on_entry_fill(tid, sym, instr, fill_price, qty)
                    add_journal_entry({
                        "trade_id":    tid,
                        "date":        datetime.now().strftime("%m/%d/%Y"),
                        "symbol":      sym,
                        "side":        "LONG" if is_buy else "SHORT",
                        "instruction": instr,
                        "qty":         qty,
                        "entry_price": fill_price,
                        "exit_price":  0,
                        "pnl":         0,
                        "pnl_pct":     0,
                        "entry_time":  datetime.now().strftime("%I:%M:%S %p"),
                        "exit_time":   "",
                        "setup":       "",
                        "grade":       "",
                        "notes":       "",
                        "screenshot":  "",
                        "asset_type":  "EQUITY",
                    })
                except Exception as e:
                    print(f"[Journal] entry error: {e}")
            else:
                notify(f"❌ Order Rejected — {sym}", "reject",
                       subtitle=msg[:100] if msg else "Rejected by broker",
                       duration=7000)
        except Exception as e:
            notify("Order Error","reject",subtitle=str(e)[:100],duration=7000)

    def _send_option(self):
        occ_sym = self._opt_contract_lbl.text().strip()
        if not occ_sym or occ_sym=="—":
            notify("No Contract","warning",subtitle="Load a chain and select a contract",duration=3000); return
        instr = self._opt_instr.currentText()
        qty   = self._opt_qty.value()
        lp    = self._opt_lim.value()
        sl    = self._opt_sl.value()
        tp    = self._opt_tp.value()
        sess  = self._opt_sess.currentText()
        dur   = self._opt_dur.currentText()
        otype = "LIMIT" if lp>0 else "MARKET"

        # If both SL and TP set — place entry then OCO exit
        has_oco = sl > 0 and tp > 0

        order = {
            "orderType": otype, "session": sess, "duration": dur,
            "orderStrategyType":"SINGLE",
            "orderLegCollection":[{
                "instruction":instr,"quantity":qty,
                "instrument":{"symbol":occ_sym,"assetType":"OPTION"}
            }]
        }
        if lp>0: order["price"] = str(round(lp,2))
        try:
            ok,msg = self.api.place_order(order)
            if ok and has_oco:
                # Place OCO exit order
                close_instr = "SELL_TO_CLOSE" if "BUY" in instr else "BUY_TO_CLOSE"
                sl_lp = round(sl - 0.03, 2) if "BUY" in instr else round(sl + 0.03, 2)
                oco = {
                    "orderStrategyType": "OCO",
                    "childOrderStrategies": [
                        {
                            "orderType": "LIMIT", "session": sess, "duration": dur,
                            "price": str(round(tp, 2)),
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": [{"instruction": close_instr, "quantity": qty,
                                "instrument": {"symbol": occ_sym, "assetType": "OPTION"}}]
                        },
                        {
                            "orderType": "STOP_LIMIT", "session": sess, "duration": dur,
                            "price": str(sl_lp), "stopPrice": str(round(sl, 2)),
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": [{"instruction": close_instr, "quantity": qty,
                                "instrument": {"symbol": occ_sym, "assetType": "OPTION"}}]
                        }
                    ]
                }
                oco_ok, oco_msg = self.api.place_order(oco)
                if oco_ok:
                    notify(f"⚡ OCO Exit Set — {occ_sym.strip()}", "info",
                           subtitle=f"TP: ${tp:.2f}  SL: ${sl:.2f}", duration=4000)
                else:
                    notify(f"⚠️ OCO Failed", "warning", subtitle=oco_msg[:80], duration=5000)
            if ok:
                is_buy = "BUY" in instr
                notify(f"{'🟢' if is_buy else '🔴'}  {instr.replace('_',' ')}  {qty}× {occ_sym.strip()}",
                       "fill",subtitle=f"${lp:.2f}  |  {otype}",duration=5000)
                # Chart stamp + journal
                try:
                    import uuid
                    from ui.chart_stamps import chart_stamp_manager
                    from ui.trade_journal import add_journal_entry
                    from datetime import datetime
                    tid = str(uuid.uuid4())[:8]
                    close_instrs = {"SELL_TO_CLOSE","BUY_TO_CLOSE"}
                    underlying = occ_sym.strip()[:6].strip()
                    if instr.upper() in close_instrs:
                        chart_stamp_manager.on_exit_fill(tid, occ_sym.strip(), instr, lp, qty)
                    else:
                        chart_stamp_manager.on_entry_fill(tid, occ_sym.strip(), instr, lp, qty)
                    add_journal_entry({
                        "trade_id":    tid,
                        "date":        datetime.now().strftime("%m/%d/%Y"),
                        "symbol":      occ_sym.strip(),
                        "side":        "LONG" if is_buy else "SHORT",
                        "instruction": instr,
                        "qty":         qty,
                        "entry_price": lp,
                        "exit_price":  0,
                        "pnl":         0,
                        "pnl_pct":     0,
                        "entry_time":  datetime.now().strftime("%I:%M:%S %p"),
                        "exit_time":   "",
                        "setup":       "",
                        "grade":       "",
                        "notes":       "",
                        "screenshot":  "",
                        "asset_type":  "OPTION",
                    })
                except Exception as e:
                    print(f"[Journal] option entry error: {e}")
            else:
                notify(f"❌ Order Rejected","reject",
                       subtitle=msg[:100] if msg else "Rejected by broker",duration=7000)
        except Exception as e:
            notify("Order Error","reject",subtitle=str(e)[:100],duration=7000)

    def closeEvent(self, event):
        self._price_timer.stop()
        super().closeEvent(event)