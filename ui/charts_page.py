"""
Charts Page v17 - Clean rewrite
- Full width TradingView (no DOM panel)
- Persistent TradingView login profile
- Symbol sync from TradingView title polling
- Symbol input read/write (updates on tab-out)
- TradingView Login button
"""

import os, sys, re, threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QComboBox
)
from PyQt6.QtCore import Qt, QUrl, QTimer, QObject, pyqtSignal

if sys.platform == "win32":
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu-sandbox --no-sandbox")
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")

HAS_WE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import (
        QWebEngineProfile, QWebEnginePage, QWebEngineSettings
    )
    HAS_WE = True
    print("[Charts] WebEngine available — embedded TradingView enabled")
except Exception as e:
    print(f"[Charts] WebEngine not available: {e}")

DIM  = "#8b949e"; BLUE = "#58a6ff"; YELLOW = "#d29922"
BG2  = "#161b22"; BG3  = "#21262d"

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
<html><head><meta charset="utf-8">
<style>*{{margin:0;padding:0;box-sizing:border-box;}}
html,body{{width:100%;height:100%;background:#0d1117;overflow:hidden;}}
#tv{{width:100%;height:100vh;}}</style></head>
<body><div id="tv"></div>
<script src="https://s3.tradingview.com/tv.js"></script>
<script>
try{{
  new TradingView.widget({{
    container_id:"tv",autosize:true,
    symbol:"{tv_sym}",interval:"{interval}",
    timezone:"America/New_York",theme:"dark",style:"1",locale:"en",
    toolbar_bg:"#161b22",enable_publishing:false,
    allow_symbol_change:true,withdateranges:true,
    hide_side_toolbar:false,details:true,
    studies:["Volume@tv-basicstudies"],
    overrides:{{"paneProperties.background":"#0d1117","paneProperties.backgroundType":"solid"}}
  }});
}}catch(e){{
  document.body.innerHTML='<p style="color:#f85149;padding:20px;font-family:monospace">Chart error: '+e+'</p>';
}}
</script></body></html>"""


class PriceFetcher(QObject):
    price_ready = pyqtSignal(str, float, float, float, float, float, int)
    def __init__(self, api):
        super().__init__(); self.api = api
    def fetch(self, symbol: str):
        try:
            q   = self.api.get_quote(symbol)
            qd  = q.get("quote", {})
            last = float(qd.get("lastPrice", 0) or 0)
            chg  = float(qd.get("netChange", 0) or 0)
            chgp = float(qd.get("netPercentChangeInDouble", 0) or 0)
            bid  = float(qd.get("bidPrice", 0) or 0)
            ask  = float(qd.get("askPrice", 0) or 0)
            vol  = int(qd.get("totalVolume", 0) or 0)
            if last > 0:
                self.price_ready.emit(symbol, last, chg, chgp, bid, ask, vol)
        except Exception as e:
            print(f"[Charts] price fetch error: {e}")


class ChartsPage(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api      = api
        self._symbol  = ""
        self._load_pending = False
        self._fetcher = PriceFetcher(api)
        self._fetcher.price_ready.connect(self._on_price_ready)
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG2};border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,0,16,0); hh.setSpacing(8)
        title = QLabel("📉  Charts  —  TradingView")
        title.setStyleSheet(f"color:{BLUE};font-size:15px;font-weight:bold;")
        hh.addWidget(title); hh.addStretch()
        self._price_lbl = QLabel("")
        self._price_lbl.setStyleSheet("color:#d29922;font-size:13px;font-weight:bold;")
        hh.addWidget(self._price_lbl)
        vbox.addWidget(hdr)

        # Controls
        ctrl = QWidget(); ctrl.setFixedHeight(48)
        ctrl.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        cbox = QHBoxLayout(ctrl); cbox.setContentsMargins(12,0,12,0); cbox.setSpacing(8)
        # Current symbol display (read only - driven by TradingView)
        self._sym_lbl = QLabel("—")
        self._sym_lbl.setStyleSheet(f"color:{YELLOW};font-size:13px;font-weight:bold;min-width:60px;")
        cbox.addWidget(self._sym_lbl)

        cbox.addStretch()

        if HAS_WE:
            tv_login_btn = QPushButton("🔑 TradingView Login")
            tv_login_btn.setFixedHeight(30)
            tv_login_btn.setStyleSheet("QPushButton{background:#1e3a5f;color:#58a6ff;border:1px solid #30363d;border-radius:4px;font-size:11px;font-weight:bold;padding:0 10px;} QPushButton:hover{background:#1f6feb;color:#fff;}")
            tv_login_btn.clicked.connect(self._open_tv_login)
            cbox.addWidget(tv_login_btn)

        vbox.addWidget(ctrl)

        # Chart view — full width
        if HAS_WE:
            profile_path = os.path.join(os.path.expanduser("~"), ".alphadesk_tv_profile")
            self._profile = QWebEngineProfile("alphadesk_tv")
            self._profile.setPersistentStoragePath(profile_path)
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
            self._page = QWebEnginePage(self._profile, self)
            self._view = QWebEngineView()
            self._view.setPage(self._page)
            s = self._profile.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
            self._view.loadFinished.connect(self._on_load_finished)
            vbox.addWidget(self._view, stretch=1)
        else:
            vbox.addWidget(self._build_fallback(), stretch=1)

        # Price timer
        self._price_timer = QTimer()
        self._price_timer.timeout.connect(self._trigger_price_fetch)
        self._price_timer.start(1000)

        # Symbol poll timer
        self._sym_poll_timer = QTimer()
        self._sym_poll_timer.timeout.connect(self._poll_tv_symbol)
        self._sym_poll_timer.start(800)

    def _build_fallback(self):
        w = QWidget(); v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel("TradingView requires WebEngine\nInstall PyQt6-WebEngine")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet(f"color:{DIM};font-size:14px;")
        v.addWidget(lbl)
        return w



    def set_symbol(self, sym: str):
        self._sym_lbl.setText(sym.upper())
        self._symbol = sym.upper()
        QTimer.singleShot(100, self._load_chart)

    def _load_chart(self):
        try:
            sym = self._symbol
            if not sym or self._load_pending: return
            self._load_pending = True
            interval = "D"  # default daily
            tv_sym   = to_tv_sym(sym)
            if HAS_WE:
                html = build_tv_html(tv_sym, interval)
                self._view.setHtml(html, QUrl("https://www.tradingview.com"))
        except Exception as e:
            print(f"[Charts] _load_chart error: {e}")
        finally:
            self._load_pending = False

    def _on_load_finished(self, ok):
        if ok:
            QTimer.singleShot(1000, self._inject_symbol_watcher)
            try:
                from ui.chart_stamps import chart_stamp_manager
                chart_stamp_manager.set_webview(self._view)
            except: pass

    def _inject_symbol_watcher(self):
        if not HAS_WE: return
        if not hasattr(self, '_sym_poll_timer'):
            self._sym_poll_timer = QTimer()
            self._sym_poll_timer.timeout.connect(self._poll_tv_symbol)
            self._sym_poll_timer.start(800)

    def _poll_tv_symbol(self):
        if not HAS_WE or not hasattr(self, '_view'): return
        def handle(title):
            if not title or not isinstance(title, str): return
            try:
                if '•' in title:
                    raw = title.split('•')[0].strip()
                elif '—' in title:
                    raw = title.split('—')[0].strip()
                else: return
                sym = re.sub(r'[^A-Z]', '', raw.split(':')[-1].strip().upper())
                if not sym or len(sym) < 1 or len(sym) > 10: return
                if sym == self._symbol: return
                self._symbol = sym
                self._sym_lbl.setText(sym)
                print(f"[Charts] Symbol synced: {sym}")
            except: pass
        self._view.page().runJavaScript("document.title;", handle)

    def _open_tv_login(self):
        if HAS_WE:
            self._view.setUrl(QUrl("https://www.tradingview.com/accounts/signin/"))

    def _trigger_price_fetch(self):
        if not self._symbol: return
        threading.Thread(
            target=self._fetcher.fetch, args=(self._symbol,), daemon=True).start()

    def _on_price_ready(self, symbol, last, chg, chgp, bid, ask, vol):
        if symbol != self._symbol: return
        sign  = "+" if chg >= 0 else ""
        color = "#3fb950" if chg >= 0 else "#f85149"
        self._price_lbl.setText(
            f"{symbol}  ${last:.2f}  "
            f"<span style='color:{color}'>{sign}{chg:.2f} ({sign}{chgp:.2f}%)</span>")

    def on_show(self):
        pass
