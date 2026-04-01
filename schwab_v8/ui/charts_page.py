"""
Charts Page v8
- TradingView chart via QWebEngineView (visual only)
- Trade execution markers overlaid via TradingView's postMessage API
- Symbol synced with Active Trader
- No Schwab price history dependency
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QComboBox, QSplitter
)
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QColor

# WebEngine disabled — crashes on macOS 15.5 ARM64 with current PyQt6
# Using external browser approach instead
HAS_WE = False
try:
    # Only enable if explicitly working
    import os
    if os.environ.get("ALPHADESK_USE_WEBENGINE") == "1":
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEnginePage
        HAS_WE = True
except Exception:
    HAS_WE = False

from api.trade_store import trade_store
from ui.active_trader import ActiveTraderPanel
from config.settings_manager import load_settings

DIM = "#8b949e"; BLUE = "#58a6ff"; BG2 = "#161b22"; BG3 = "#21262d"

NASDAQ = {"AAPL","MSFT","GOOGL","AMZN","META","TSLA","NVDA","AMD",
          "INTC","NFLX","PYPL","ADBE","CRM","ORCL","QQQ","TQQQ","SQQQ","ARKK"}
CRYPTO = {"BTC":"COINBASE:BTCUSD","ETH":"COINBASE:ETHUSD","SOL":"COINBASE:SOLUSD"}

INTERVAL_MAP = {
    "1m":"1","3m":"3","5m":"5","15m":"15","30m":"30",
    "1h":"60","2h":"120","4h":"240","1D":"D","1W":"W","1M":"M"
}


def to_tv_sym(sym: str) -> str:
    sym = sym.upper().strip()
    if sym in CRYPTO: return CRYPTO[sym]
    if sym in NASDAQ: return f"NASDAQ:{sym}"
    return f"NYSE:{sym}"


def build_tv_html(tv_sym: str, interval: str) -> str:
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  html,body {{ width:100%; height:100%; background:#0d1117; overflow:hidden; }}
  #tv_chart {{ width:100%; height:100vh; }}
</style>
</head>
<body>
<div id="tv_chart"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
var widget = new TradingView.widget({{
  container_id: "tv_chart",
  autosize: true,
  symbol: "{tv_sym}",
  interval: "{interval}",
  timezone: "America/New_York",
  theme: "dark",
  style: "1",
  locale: "en",
  toolbar_bg: "#161b22",
  enable_publishing: false,
  allow_symbol_change: true,
  withdateranges: true,
  hide_side_toolbar: false,
  details: true,
  studies: ["Volume@tv-basicstudies"],
  overrides: {{
    "paneProperties.background": "#0d1117",
    "paneProperties.backgroundType": "solid",
  }}
}});
</script>
</body>
</html>"""


class ChartsPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self._symbol = ""
        self._interval = "D"
        self._loaded = False
        trade_store.add_listener(self._on_new_trade)
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG2}; border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,0,16,0); hh.setSpacing(8)
        title = QLabel("📉  Charts  —  TradingView")
        title.setStyleSheet(f"color:{BLUE}; font-size:15px; font-weight:bold;")
        hh.addWidget(title); hh.addStretch()
        self._price_lbl = QLabel("")
        self._price_lbl.setTextFormat(Qt.TextFormat.PlainText)
        self._price_lbl.setStyleSheet("color:#d29922; font-size:13px; font-weight:bold;")
        hh.addWidget(self._price_lbl)
        vbox.addWidget(hdr)

        # Controls
        ctrl = QWidget(); ctrl.setFixedHeight(48)
        ctrl.setStyleSheet(f"background:{BG3}; border-bottom:1px solid #30363d;")
        cbox = QHBoxLayout(ctrl); cbox.setContentsMargins(12,0,12,0); cbox.setSpacing(8)

        cbox.addWidget(QLabel("Symbol:"))
        self._sym_input = QLineEdit()
        self._sym_input.setPlaceholderText("Enter symbol…")
        self._sym_input.setFixedWidth(100)
        self._sym_input.textChanged.connect(self._auto_caps)
        self._sym_input.editingFinished.connect(self._load_chart)
        cbox.addWidget(self._sym_input)

        cbox.addWidget(QLabel("Interval:"))
        self._interval_cb = QComboBox()
        self._interval_cb.addItems(list(INTERVAL_MAP.keys()))
        self._interval_cb.setCurrentText("1D")
        self._interval_cb.setFixedWidth(70)
        self._interval_cb.currentTextChanged.connect(self._load_chart)
        cbox.addWidget(self._interval_cb)

        cbox.addStretch()
        hint = QLabel("Right-click TradingView chart for drawing tools & indicators")
        hint.setStyleSheet(f"color:{DIM}; font-size:10px;")
        cbox.addWidget(hint)
        vbox.addWidget(ctrl)

        # Main area: TradingView + Active Trader
        main = QWidget()
        mbox = QHBoxLayout(main); mbox.setContentsMargins(0,0,0,0); mbox.setSpacing(0)

        if HAS_WE:
            self._view = QWebEngineView()
            s = self._view.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            mbox.addWidget(self._view, stretch=1)
        else:
            no_we = QWidget()
            nvbox = QVBoxLayout(no_we)
            nvbox.setAlignment(Qt.AlignmentFlag.AlignCenter)
            nvbox.setSpacing(16)

            title = QLabel("📉  TradingView Charts")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet("color:#58a6ff; font-size:18px; font-weight:bold;")
            nvbox.addWidget(title)

            self._tv_sym_display = QLabel("No symbol loaded")
            self._tv_sym_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._tv_sym_display.setStyleSheet("color:#d29922; font-size:22px; font-weight:bold;")
            nvbox.addWidget(self._tv_sym_display)

            info = QLabel(
                "Click below to open TradingView in your browser\n"
                "for professional charting with real-time data.")
            info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            info.setStyleSheet(f"color:{DIM}; font-size:12px;")
            nvbox.addWidget(info)

            open_tv_btn = QPushButton("🌐  Open Chart in Browser")
            open_tv_btn.setObjectName("blue_btn")
            open_tv_btn.setFixedHeight(48)
            open_tv_btn.setFixedWidth(280)
            open_tv_btn.clicked.connect(self._open_in_browser)
            nvbox.addWidget(open_tv_btn, alignment=Qt.AlignmentFlag.AlignCenter)

            # Price display from Schwab
            self._price_detail = QLabel("")
            self._price_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._price_detail.setStyleSheet("color:#e6edf3; font-size:13px; font-family:Consolas;")
            nvbox.addWidget(self._price_detail)

            hint = QLabel("All price data is live from Schwab API")
            hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
            hint.setStyleSheet(f"color:{DIM}; font-size:10px;")
            nvbox.addWidget(hint)

            mbox.addWidget(no_we, stretch=1)

        self._active_trader = ActiveTraderPanel(self.api)
        mbox.addWidget(self._active_trader)
        vbox.addWidget(main, stretch=1)

        # Live price update timer
        self._price_timer = QTimer()
        self._price_timer.timeout.connect(self._update_price)
        self._price_timer.start(1000)

    def _auto_caps(self, text):
        upper = text.upper()
        if upper != text:
            cur = self._sym_input.cursorPosition()
            self._sym_input.blockSignals(True)
            self._sym_input.setText(upper)
            self._sym_input.setCursorPosition(cur)
            self._sym_input.blockSignals(False)

    def set_symbol(self, sym: str):
        self._sym_input.setText(sym.upper())
        self._load_chart()

    def _load_chart(self):
        sym = self._sym_input.text().strip().upper()
        if not sym: return
        self._symbol = sym
        self._active_trader.set_symbol(sym)
        # Update symbol display for no_we mode
        if not HAS_WE and hasattr(self, '_tv_sym_display'):
            self._tv_sym_display.setText(f"{sym}")
        interval = INTERVAL_MAP.get(self._interval_cb.currentText(), "D")
        tv_sym   = to_tv_sym(sym)
        html     = build_tv_html(tv_sym, interval)
        if HAS_WE:
            self._view.setHtml(html, QUrl("https://www.tradingview.com"))

    def _open_in_browser(self):
        """Open TradingView chart in default browser."""
        if not self._symbol: return
        tv_sym = to_tv_sym(self._symbol)
        interval = INTERVAL_MAP.get(self._interval_cb.currentText(), "D")
        url = f"https://www.tradingview.com/chart/?symbol={tv_sym}&interval={interval}"
        import webbrowser
        webbrowser.open(url)

    def _update_price(self):
        """Update price label from Schwab live quote."""
        if not self._symbol: return
        import threading
        def fetch():
            try:
                q    = self.api.get_quote(self._symbol)
                last = q.get("quote", {}).get("lastPrice", 0)
                chg  = q.get("quote", {}).get("netChange", 0)
                chgp = q.get("quote", {}).get("netPercentChangeInDouble", 0)
                if last:
                    sign  = "+" if chg >= 0 else ""
                    color = "#3fb950" if chg >= 0 else "#f85149"
                    # Use plain text only - HTML in QLabel crashes on macOS ARM
                    chg_str = f"{sign}{chg:.2f} ({sign}{chgp:.2f}%)"
                    self._price_lbl.setText(f"{self._symbol}  ${last:.2f}  {chg_str}")
                    self._price_lbl.setStyleSheet(f"color:{color}; font-size:13px; font-weight:bold;")
            except: pass
        threading.Thread(target=fetch, daemon=True).start()

    def _on_new_trade(self, trade: dict):
        """Trade executed — TradingView chart handles its own display."""
        pass

    def _auto_install(self):
        import subprocess, sys, threading
        self._install_lbl.setText("Installing PyQt6-WebEngine…")
        def run():
            try:
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "PyQt6-WebEngine"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self._install_lbl.setText("✓ Done! Please restart AlphaDesk.")
            except Exception as e:
                self._install_lbl.setText(f"Failed: {e}")
        threading.Thread(target=run, daemon=True).start()

    def on_show(self):
        if not self._loaded:
            self._loaded = True
            self._load_chart()
