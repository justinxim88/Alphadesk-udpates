"""
Settings Dialog
- Paper trading toggle with account selector
- Hotkey configuration
- Default session (pre-market, after-hours, etc)
- Default order quantity
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QLineEdit, QPushButton, QComboBox, QCheckBox,
    QGroupBox, QGridLayout, QSpinBox, QDialogButtonBox,
    QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeySequence

from config.settings_manager import load_settings, save_settings

GREEN  = "#3fb950"
RED    = "#f85149"
BLUE   = "#58a6ff"
YELLOW = "#d29922"
DIM    = "#8b949e"
BG     = "#0d1117"
BG2    = "#161b22"
BG3    = "#21262d"


class SettingsDialog(QDialog):
    settings_changed = pyqtSignal(dict)  # emitted when settings saved

    def __init__(self, parent, api):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("AlphaDesk — Settings")
        self.setMinimumSize(580, 520)
        self.setStyleSheet(f"background:{BG2}; color:#e6edf3; font-family:Consolas;")
        self._settings = load_settings()
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG3}; border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(20, 0, 20, 0)
        title = QLabel("⚙  Settings")
        title.setStyleSheet(f"color:{BLUE}; font-size:16px; font-weight:bold;")
        hh.addWidget(title)
        vbox.addWidget(hdr)

        # Tabs
        tabs = QTabWidget(); tabs.setDocumentMode(True)
        tabs.addTab(self._build_account_tab(),  "  Account  ")
        tabs.addTab(self._build_orders_tab(),   "  Orders  ")
        tabs.addTab(self._build_hotkeys_tab(),  "  Hotkeys  ")
        tabs.addTab(self._build_charts_tab(),   "  Charts  ")
        vbox.addWidget(tabs, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 8, 16, 16)
        save_btn = QPushButton("✓  Save Settings")
        save_btn.setObjectName("blue_btn")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        vbox.addLayout(btn_row)

    # ─────────────────────────────────────────────
    #  ACCOUNT TAB
    # ─────────────────────────────────────────────

    def _build_account_tab(self) -> QWidget:
        w = QWidget(); vbox = QVBoxLayout(w)
        vbox.setContentsMargins(20, 16, 20, 16); vbox.setSpacing(16)

        # Paper trading toggle
        paper_grp = QGroupBox("Paper Trading")
        pg = QVBoxLayout(paper_grp)

        self._paper_cb = QCheckBox(
            "Enable Paper Trading (practice account — no real money)")
        self._paper_cb.setChecked(self._settings.get("paper_mode", False))
        self._paper_cb.setStyleSheet(f"color:#e6edf3; font-size:12px;")
        self._paper_cb.toggled.connect(self._on_paper_toggle)
        pg.addWidget(self._paper_cb)

        paper_note = QLabel(
            "When enabled, all orders go to your Schwab paper trading account.\n"
            "Great for testing strategies without risking real money or triggering PDT.")
        paper_note.setStyleSheet(f"color:{DIM}; font-size:10px;")
        paper_note.setWordWrap(True)
        pg.addWidget(paper_note)

        # Account selector
        acct_row = QHBoxLayout()
        acct_row.addWidget(QLabel("Paper Account:"))
        self._paper_hash_combo = QComboBox()
        self._paper_hash_combo.setFixedWidth(280)
        acct_row.addWidget(self._paper_hash_combo)
        refresh_btn = QPushButton("⟳ Load Accounts")
        refresh_btn.setFixedHeight(30)
        refresh_btn.clicked.connect(self._load_accounts)
        acct_row.addWidget(refresh_btn)
        acct_row.addStretch()
        pg.addLayout(acct_row)

        self._paper_status = QLabel("")
        self._paper_status.setStyleSheet(f"color:{YELLOW}; font-size:10px;")
        pg.addWidget(self._paper_status)

        vbox.addWidget(paper_grp)

        # Live account info
        live_grp = QGroupBox("Live Account")
        lg = QVBoxLayout(live_grp)
        self._live_info = QLabel(
            f"Account Hash: {self.api.account_hash or 'Not set'}")
        self._live_info.setStyleSheet(f"color:{DIM}; font-size:10px;")
        lg.addWidget(self._live_info)
        vbox.addWidget(live_grp)

        vbox.addStretch()

        # Load accounts on open
        self._load_accounts()
        return w

    def _on_paper_toggle(self, checked: bool):
        status = "⚠  Paper mode ON — orders go to practice account" if checked else ""
        self._paper_status.setText(status)

    def _load_accounts(self):
        try:
            accounts = self.api.get_accounts()
            self._paper_hash_combo.clear()
            for acct in accounts:
                num  = acct.get("accountNumber", "Unknown")
                hash_val = acct.get("hashValue", "")
                self._paper_hash_combo.addItem(f"{num}  ({hash_val[:8]}…)", hash_val)

            # Select current paper hash
            paper_hash = self._settings.get("paper_hash", "")
            for i in range(self._paper_hash_combo.count()):
                if self._paper_hash_combo.itemData(i) == paper_hash:
                    self._paper_hash_combo.setCurrentIndex(i)
                    break
        except Exception as e:
            self._paper_status.setText(f"Could not load accounts: {e}")

    # ─────────────────────────────────────────────
    #  ORDERS TAB
    # ─────────────────────────────────────────────

    def _build_orders_tab(self) -> QWidget:
        w = QWidget(); vbox = QVBoxLayout(w)
        vbox.setContentsMargins(20, 16, 20, 16); vbox.setSpacing(16)

        order_grp = QGroupBox("Order Defaults")
        grid = QGridLayout(order_grp); grid.setSpacing(12)

        # Default session
        grid.addWidget(QLabel("Default Session:"), 0, 0)
        self._session_combo = QComboBox()
        self._session_combo.addItems([
            "NORMAL",
            "PRE_MARKET",
            "AFTER_HOURS",
            "SEAMLESS",
        ])
        self._session_combo.setCurrentText(
            self._settings.get("default_session", "NORMAL"))
        grid.addWidget(self._session_combo, 0, 1)

        session_note = QLabel(
            "NORMAL = market hours only\n"
            "PRE_MARKET = 7:00–9:30 AM ET\n"
            "AFTER_HOURS = 4:00–8:00 PM ET\n"
            "SEAMLESS = all sessions automatically"
        )
        session_note.setStyleSheet(f"color:{DIM}; font-size:10px;")
        grid.addWidget(session_note, 1, 0, 1, 2)

        # Default duration
        grid.addWidget(QLabel("Default Duration:"), 2, 0)
        self._duration_combo = QComboBox()
        self._duration_combo.addItems(["DAY", "GTC", "GTD", "FOK"])
        self._duration_combo.setCurrentText(
            self._settings.get("default_duration", "DAY"))
        grid.addWidget(self._duration_combo, 2, 1)

        # Default qty
        grid.addWidget(QLabel("Default Quantity:"), 3, 0)
        self._default_qty = QSpinBox()
        self._default_qty.setRange(1, 10000)
        self._default_qty.setValue(self._settings.get("default_qty", 1))
        grid.addWidget(self._default_qty, 3, 1)

        # Short selling guard
        self._short_guard = QCheckBox(
            "Warn before placing orders that would create a short position")
        self._short_guard.setChecked(
            self._settings.get("short_guard", True))
        grid.addWidget(self._short_guard, 4, 0, 1, 2)

        vbox.addWidget(order_grp)
        vbox.addStretch()
        return w

    # ─────────────────────────────────────────────
    #  HOTKEYS TAB
    # ─────────────────────────────────────────────

    def _build_hotkeys_tab(self) -> QWidget:
        w = QWidget(); vbox = QVBoxLayout(w)
        vbox.setContentsMargins(20, 16, 20, 16); vbox.setSpacing(12)

        note = QLabel(
            "Click a hotkey field and press your desired key combination.")
        note.setStyleSheet(f"color:{DIM}; font-size:10px;")
        vbox.addWidget(note)

        hotkeys_grp = QGroupBox("Keyboard Shortcuts")
        grid = QGridLayout(hotkeys_grp); grid.setSpacing(10)

        self._hotkey_inputs = {}
        saved_hotkeys = self._settings.get("hotkeys", {})

        hotkey_defs = [
            ("buy_market",     "Buy Market"),
            ("sell_market",    "Sell Market"),
            ("flatten",        "Flatten Position"),
            ("cancel_all",     "Cancel All Orders"),
            ("reverse",        "Reverse Position"),
            ("refresh",        "Refresh Data"),
            ("chart_zoom",     "Chart Auto Zoom"),
            ("chart_recenter", "Chart Recenter"),
        ]

        for row, (key, label) in enumerate(hotkey_defs):
            grid.addWidget(QLabel(label + ":"), row, 0)
            inp = QLineEdit(saved_hotkeys.get(key, ""))
            inp.setPlaceholderText("e.g. Ctrl+B")
            inp.setFixedWidth(160)
            inp.setReadOnly(True)
            inp.keyPressEvent = lambda e, i=inp: self._capture_hotkey(e, i)
            grid.addWidget(inp, row, 1)
            clear_btn = QPushButton("✕")
            clear_btn.setFixedSize(28, 28)
            clear_btn.clicked.connect(lambda _, i=inp: i.clear())
            grid.addWidget(clear_btn, row, 2)
            self._hotkey_inputs[key] = inp

        vbox.addWidget(hotkeys_grp)
        vbox.addStretch()
        return w

    def _capture_hotkey(self, event, input_widget):
        """Capture key press and display as shortcut string."""
        from PyQt6.QtCore import Qt
        key  = event.key()
        mods = event.modifiers()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift,
                   Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return
        combo = QKeySequence(int(mods) | key).toString()
        input_widget.setText(combo)

    # ─────────────────────────────────────────────
    #  CHARTS TAB
    # ─────────────────────────────────────────────

    def _build_charts_tab(self) -> QWidget:
        w = QWidget(); vbox = QVBoxLayout(w)
        vbox.setContentsMargins(20, 16, 20, 16); vbox.setSpacing(16)

        chart_grp = QGroupBox("Chart Defaults")
        grid = QGridLayout(chart_grp); grid.setSpacing(10)

        grid.addWidget(QLabel("Default Period:"), 0, 0)
        self._chart_period = QComboBox()
        self._chart_period.addItems(["1D","5D","1M","3M","1Y"])
        self._chart_period.setCurrentText(
            self._settings.get("default_period", "1M"))
        grid.addWidget(self._chart_period, 0, 1)

        vbox.addWidget(chart_grp)

        ind_grp = QGroupBox("Default Indicators")
        ig = QVBoxLayout(ind_grp)
        saved_inds = self._settings.get("default_indicators", ["Volume"])
        self._ind_checks = {}
        for ind in ["Volume", "EMA_9", "EMA_20", "EMA_50", "SMA_200",
                    "VWAP", "BB", "RSI", "MACD"]:
            cb = QCheckBox(ind)
            cb.setChecked(ind in saved_inds)
            cb.setStyleSheet("color:#e6edf3;")
            ig.addWidget(cb)
            self._ind_checks[ind] = cb

        vbox.addWidget(ind_grp)
        vbox.addStretch()
        return w

    # ─────────────────────────────────────────────
    #  SAVE
    # ─────────────────────────────────────────────

    def _save(self):
        s = load_settings()

        # Account
        paper_mode = self._paper_cb.isChecked()
        s["paper_mode"] = paper_mode
        if self._paper_hash_combo.count() > 0:
            s["paper_hash"] = self._paper_hash_combo.currentData() or ""

        # Apply paper mode to API immediately
        self.api.set_paper_mode(paper_mode)
        if paper_mode and s.get("paper_hash"):
            self.api.set_paper_account(s["paper_hash"])

        # Orders
        s["default_session"]  = self._session_combo.currentText()
        s["default_duration"] = self._duration_combo.currentText()
        s["default_qty"]      = self._default_qty.value()
        s["short_guard"]      = self._short_guard.isChecked()

        # Hotkeys
        s["hotkeys"] = {
            k: inp.text() for k, inp in self._hotkey_inputs.items()
        }

        # Charts
        s["default_period"] = self._chart_period.currentText()
        s["default_indicators"] = [
            ind for ind, cb in self._ind_checks.items() if cb.isChecked()
        ]

        save_settings(s)
        self.settings_changed.emit(s)
        QMessageBox.information(self, "Saved", "Settings saved successfully.")
        self.accept()
