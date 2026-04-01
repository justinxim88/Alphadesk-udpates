"""Main Window v8 — account switcher, live account display, no paper toggle, no refresh buttons."""

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QStackedWidget, QFrame, QComboBox
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut

from ui.pages import DashboardPage, QuotesPage
from ui.options_page import OptionsPage
from ui.charts_page import ChartsPage
from ui.positions_window import PositionsWindow
from ui.settings_dialog import SettingsDialog
from api.account_manager import AccountManager
from ui.toast import init_toast_manager, notify
from config.settings_manager import load_settings


ACCOUNT_NICKNAMES = {
    "Individual": "Brokerage",
    "IRA": "Roth IRA",
    "ROTH": "Roth IRA",
    "MARGIN": "Margin",
}

def _get_account_nickname(acct):
    num  = acct.get("number","")
    name = acct.get("name","")
    # Use last 4 of account number with type hint
    suffix = f"...{num[-4:]}" if len(num)>=4 else num
    for key,nick in ACCOUNT_NICKNAMES.items():
        if key.upper() in name.upper():
            return f"{nick} ({suffix})"
    return suffix

NAV = [
    ("dashboard", "📊  Dashboard"),
    ("quotes",    "📈  Live Quotes"),
    ("options",   "🔗  Options Chain"),
    ("charts",    "📉  Charts"),
]


class MainWindow(QMainWindow):
    def __init__(self, api, demo_mode=False):
        super().__init__()
        self.api        = api
        self.demo_mode  = demo_mode
        self._settings  = load_settings()
        self._positions_win = None

        # Account manager
        self._acct_mgr = AccountManager(api)
        self._acct_mgr.account_changed.connect(self._on_account_changed)

        title = "AlphaDesk" + (" — DEMO" if demo_mode else "")
        self.setWindowTitle(title)
        self.resize(1500, 900); self.setMinimumSize(1100, 700)
        self._build()
        self._setup_hotkeys()
        self._select("dashboard")

        # Init toast notification system
        QTimer.singleShot(100, lambda: init_toast_manager(self))

        # Load accounts after UI is ready
        QTimer.singleShot(500, self._acct_mgr.load_accounts)
        QTimer.singleShot(1500, self._populate_account_switcher)

        # Check login status — show OAuth dialog if needed
        QTimer.singleShot(500, self._check_login)

        # Check for updates after 3 seconds (non-blocking)
        QTimer.singleShot(3000, self._check_for_updates)

    def _build(self):
        root = QWidget(); self.setCentralWidget(root)
        layout = QHBoxLayout(root); layout.setContentsMargins(0,0,0,0); layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_content(), stretch=1)
        mode = "DEMO" if self.demo_mode else "LIVE"
        color = "#d29922" if self.demo_mode else "#f85149"
        self.statusBar().showMessage(f"⚡ AlphaDesk  |  {mode} TRADING")
        self.statusBar().setStyleSheet(f"color:{color};")

    def _build_sidebar(self):
        sb = QFrame(); sb.setObjectName("sidebar"); sb.setFixedWidth(210)
        sb.setStyleSheet("QFrame#sidebar{background:#161b22;border-right:1px solid #30363d;}")
        vbox = QVBoxLayout(sb); vbox.setContentsMargins(0,0,0,0); vbox.setSpacing(0)

        # Logo
        logo = QLabel("⚡ ALPHA\nDESK")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("color:#58a6ff;font-size:16px;font-weight:bold;padding:18px 12px 6px;")
        vbox.addWidget(logo)

        # Mode badge
        self._mode_badge = QLabel("● LIVE" if not self.demo_mode else "● DEMO")
        self._mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mode_badge.setFixedHeight(18)
        color = "#f85149" if not self.demo_mode else "#d29922"
        self._mode_badge.setStyleSheet(f"color:{color};font-size:10px;font-weight:bold;")
        vbox.addWidget(self._mode_badge)

        # Account switcher
        acct_w = QWidget(); acct_w.setFixedHeight(54)
        acct_w.setStyleSheet("background:#0d1117;border-top:1px solid #30363d;border-bottom:1px solid #30363d;")
        av = QVBoxLayout(acct_w); av.setContentsMargins(8,4,8,4); av.setSpacing(2)
        acct_lbl = QLabel("Account:")
        acct_lbl.setStyleSheet("color:#8b949e;font-size:9px;background:transparent;")
        av.addWidget(acct_lbl)
        self._acct_combo = QComboBox()
        self._acct_combo.setFixedHeight(26)
        self._acct_combo.setStyleSheet("""
            QComboBox{background-color:#161b22;color:#e6edf3;border:1px solid #30363d;
                      border-radius:3px;font-size:11px;font-weight:bold;padding:2px 6px;}
            QComboBox QAbstractItemView{background-color:#161b22;color:#e6edf3;
                                         selection-background-color:#1f6feb;}
        """)
        self._acct_combo.currentIndexChanged.connect(self._on_acct_combo_changed)
        av.addWidget(self._acct_combo)
        vbox.addWidget(acct_w)

        # Current account display
        self._acct_display = QLabel("Loading accounts…")
        self._acct_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._acct_display.setWordWrap(True)
        self._acct_display.setFixedHeight(28)
        self._acct_display.setStyleSheet("color:#3fb950;font-size:10px;font-weight:bold;padding:2px 8px;background:#0a1a0a;border-bottom:1px solid #30363d;")
        vbox.addWidget(self._acct_display)

        vbox.addSpacing(4)

        # Nav buttons
        self._nav_btns = {}
        for key, label in NAV:
            btn = QPushButton(label); btn.setCheckable(True); btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet("""
                QPushButton{background:transparent;border:none;color:#c9d1d9;
                            font-size:12px;text-align:left;padding-left:20px;font-family:Consolas;}
                QPushButton:hover{background:#21262d;color:#e6edf3;}
                QPushButton:checked{background:#1f6feb;color:white;border-left:3px solid #58a6ff;}
            """)
            btn.clicked.connect(lambda _, k=key: self._select(k))
            vbox.addWidget(btn); self._nav_btns[key] = btn

        vbox.addSpacing(8)



        vbox.addStretch()

        # Trade button
        trade_btn = QPushButton("⚡  Trade")
        trade_btn.setFixedHeight(40); trade_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        trade_btn.setStyleSheet("QPushButton{background:#1f6feb;border:none;color:white;font-size:13px;font-weight:bold;text-align:left;padding-left:20px;} QPushButton:hover{background:#388bfd;}")
        trade_btn.clicked.connect(self._open_trade_window)
        vbox.addWidget(trade_btn)

        # Open P&L button
        pnl_btn = QPushButton("📈  Open P&L")
        pnl_btn.setFixedHeight(36); pnl_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        pnl_btn.setStyleSheet("QPushButton{background:#1a3a1a;border:none;color:#3fb950;font-size:12px;font-weight:bold;text-align:left;padding-left:20px;border-top:1px solid #30363d;} QPushButton:hover{background:#238636;color:#fff;}")
        pnl_btn.clicked.connect(self._open_pnl_popup)
        vbox.addWidget(pnl_btn)

        # Settings
        settings_btn = QPushButton("⚙  Settings")
        settings_btn.setFixedHeight(36); settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setStyleSheet("QPushButton{background:#21262d;border:none;color:#8b949e;font-size:11px;text-align:left;padding-left:20px;border-top:1px solid #30363d;} QPushButton:hover{color:#e6edf3;background:#30363d;}")
        settings_btn.clicked.connect(self._open_settings)
        vbox.addWidget(settings_btn)
        return sb

    def _build_content(self):
        self._stack = QStackedWidget()
        self._pages = {
            "dashboard": DashboardPage(api=self.api),
            "quotes":    QuotesPage(api=self.api),
            "options":   OptionsPage(api=self.api),
            "charts":    ChartsPage(api=self.api),
        }
        for page in self._pages.values():
            self._stack.addWidget(page)

        # Wire quotes → charts
        def nav_to_charts(sym):
            self._pages["charts"].set_symbol(sym)
            self._select("charts")
        self._pages["quotes"].set_chart_navigator(nav_to_charts)
        return self._stack

    def _populate_account_switcher(self):
        accounts = self._acct_mgr.get_accounts()
        self._acct_combo.blockSignals(True)
        self._acct_combo.clear()
        for i, acct in enumerate(accounts):
            num  = acct.get("number", "")
            # Try to get a friendly name from account details
            # Use index-based labels: first=Brokerage, second=Roth, etc.
            labels = ["Brokerage", "Roth IRA", "Traditional IRA", "Trust", "Margin"]
            label  = labels[i] if i < len(labels) else f"Account {i+1}"
            display = f"{label}  (…{num[-4:]})" if len(num) >= 4 else label
            self._acct_combo.addItem(display, acct["hash"])
        self._acct_combo.blockSignals(False)
        if accounts:
            self._acct_combo.setCurrentIndex(0)
            self._on_acct_combo_changed(0)

    def _on_acct_combo_changed(self, index):
        if index < 0: return
        hash_val = self._acct_combo.itemData(index)
        if hash_val:
            self._acct_mgr.switch_account(hash_val)

    def _on_account_changed(self, hash_val: str, name: str):
        label = self._acct_combo.currentText()
        self._acct_display.setText(f"Active: {label}")
        self.statusBar().showMessage(
            f"⚡ AlphaDesk  |  {'DEMO' if self.demo_mode else 'LIVE'}  |  {label}")

    def _select(self, key):
        for k, btn in self._nav_btns.items(): btn.setChecked(k==key)
        page = self._pages[key]; self._stack.setCurrentWidget(page)
        if hasattr(page, "on_show"): page.on_show()

    def _open_positions(self):
        pass  # replaced by dashboard tabs

    def _open_pnl_popup(self):
        from ui.pnl_popup import PnLPopup
        popup = PnLPopup(self, api=self.api)
        # Position near top-right of main window
        geo = self.geometry()
        popup.adjustSize()
        popup.move(geo.right() - popup.width() - 20, geo.top() + 80)
        popup.show()

    def _open_trade_window(self):
        from ui.trade_window import TradeWindow
        # Get current symbol from charts if available
        sym = ""
        charts = self._pages.get("charts")
        if charts and hasattr(charts, "_symbol"):
            sym = charts._symbol
        win = TradeWindow(self, api=self.api, symbol=sym)
        win.show()
        win.raise_()

    def _open_settings(self):
        try:
            from ui.settings_dialog import SettingsDialog
            dlg = SettingsDialog(self, api=self.api)
            if hasattr(dlg, "settings_changed"):
                dlg.settings_changed.connect(self._on_settings_changed)
            dlg.exec()
        except Exception as e:
            import traceback; traceback.print_exc()
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Settings Error", f"{type(e).__name__}: {e}")

    
    def _on_settings_changed(self, settings: dict):
        self._settings = settings
        self._setup_hotkeys()
        if hasattr(self._pages["charts"], "update_settings"):
            self._pages["charts"].update_settings(settings)

    def _setup_hotkeys(self):
        hotkeys = self._settings.get("hotkeys", {})
        charts  = self._pages.get("charts")
        at      = getattr(charts, "_active_trader", None) if charts else None

        def bind(key_str, handler):
            if not key_str: return
            try:
                sc = QShortcut(QKeySequence(key_str), self)
                sc.activated.connect(handler)
            except: pass

        if at:
            bind(hotkeys.get("buy_market"),  at._buy_mkt)
            bind(hotkeys.get("sell_market"), at._sell_mkt)
            bind(hotkeys.get("flatten"),     at._flatten)
            bind(hotkeys.get("cancel_all"),  at._cancel_all)
            bind(hotkeys.get("reverse"),     at._reverse)

    def _check_login(self):
        """Show OAuth login if not authenticated."""
        try:
            if hasattr(self.api, 'needs_login') and self.api.needs_login():
                from ui.oauth_login import do_oauth_login
                import os
                app_key    = getattr(self.api, '_app_key', '')
                app_secret = getattr(self.api, '_app_secret', '')
                ok = do_oauth_login(self, self.api, app_key, app_secret)
                if ok:
                    from ui.toast import notify
                    notify("✅ Logged in to Schwab", "fill",
                           subtitle="Authentication successful", duration=4000)
                    QTimer.singleShot(1000, self._acct_mgr.load_accounts)
                else:
                    from ui.toast import notify
                    notify("⚠️ Login Required", "warning",
                           subtitle="Please restart and log in", duration=8000)
        except Exception as e:
            print(f"[Login] Check error: {e}")

    def _check_for_updates(self):
        try:
            import os
            app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            from ui.updater import check_for_updates
            check_for_updates(self, app_dir)
        except Exception as e:
            print(f"[Updater] {e}")

    def _current_key(self):
        for k, p in self._pages.items():
            if p == self._stack.currentWidget(): return k
        return "dashboard"
