#!/usr/bin/env python3
"""
AlphaDesk
DEMO_MODE = True  → fake data, no API keys needed
DEMO_MODE = False → live Schwab API
"""

# ─────────────────────────────────────────
DEMO_MODE = False

# Your Schwab API credentials — hardcoded so you never have to type them again.
# Only your Schwab username/password will be asked on first launch.
APP_KEY    = "3i3Jo5RRicmdLxGUT4V51uzXGeCkmhqiE1JGKRfmj2s6X0KZ"
APP_SECRET = "V0TlhoZv8vyH7GBH3G3zjv3wG6jY9zK5ZaTGtnmS2ZvjbTJQAOfVSTYAFLqum3Nq"
# ─────────────────────────────────────────

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QMessageBox, QWidget
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPalette, QColor
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import threading
import base64
import requests as req_lib

if DEMO_MODE:
    from api.mock_client import MockSchwabAPI as API
else:
    from api.schwab_client import SchwabAPI as API

from config.settings_manager import get_credentials, set_credentials
from ui.main_window import MainWindow


# ── DARK STYLESHEET ───────────────────────────────────────────────────────────

STYLESHEET = """
    QWidget        { background:#0d1117; color:#e6edf3; font-family:Consolas; font-size:12px; }
    QMainWindow    { background:#0d1117; }
    QDialog        { background:#161b22; }
    QMessageBox    { background:#161b22; }
    QStatusBar     { background:#161b22; color:#8b949e; border-top:1px solid #30363d; }
    QTabWidget::pane { border:1px solid #30363d; background:#0d1117; }
    QTabBar::tab   { background:#21262d; color:#8b949e; padding:8px 18px;
                     border:1px solid #30363d; border-bottom:none; margin-right:2px; }
    QTabBar::tab:selected { background:#0d1117; color:#58a6ff; border-bottom:2px solid #1f6feb; }
    QTabBar::tab:hover    { background:#161b22; color:#e6edf3; }
    QLineEdit      { background:#21262d; border:1px solid #30363d; border-radius:4px;
                     padding:6px 10px; color:#e6edf3; selection-background-color:#1f6feb; }
    QLineEdit:focus { border:1px solid #58a6ff; }
    QComboBox      { background:#21262d; border:1px solid #30363d; border-radius:4px;
                     padding:5px 10px; color:#e6edf3; min-width:80px; }
    QComboBox::drop-down { border:none; width:20px; }
    QComboBox QAbstractItemView { background:#21262d; border:1px solid #30363d;
                                  selection-background-color:#1f6feb; color:#e6edf3; }
    QSpinBox, QDoubleSpinBox { background:#21262d; border:1px solid #30363d;
                     border-radius:4px; padding:5px 10px; color:#e6edf3; }
    QPushButton    { background:#21262d; border:1px solid #30363d; border-radius:4px;
                     padding:7px 16px; color:#e6edf3; font-weight:bold; }
    QPushButton:hover   { background:#30363d; border-color:#58a6ff; }
    QPushButton:pressed { background:#1f6feb; }
    QPushButton#buy_btn  { background:#238636; border-color:#2ea043; color:white; }
    QPushButton#buy_btn:hover  { background:#2ea043; }
    QPushButton#sell_btn { background:#da3633; border-color:#f85149; color:white; }
    QPushButton#sell_btn:hover { background:#f85149; }
    QPushButton#blue_btn { background:#1f6feb; border-color:#388bfd; color:white; }
    QPushButton#blue_btn:hover { background:#388bfd; }
    QPushButton#flat_btn { background:#6e40c9; border-color:#8957e5; color:white; }
    QPushButton#flat_btn:hover { background:#8957e5; }
    QTableWidget   { background:#161b22; border:1px solid #30363d; gridline-color:#21262d;
                     alternate-background-color:#0d1117; }
    QTableWidget::item { padding:4px 8px; }
    QTableWidget::item:selected { background:#1f6feb; color:white; }
    QHeaderView::section { background:#21262d; color:#58a6ff; font-weight:bold;
                           padding:6px 8px; border:none; border-right:1px solid #30363d; }
    QScrollBar:vertical   { background:#0d1117; width:8px; }
    QScrollBar::handle:vertical { background:#30363d; border-radius:4px; min-height:20px; }
    QScrollBar::handle:vertical:hover { background:#58a6ff; }
    QScrollBar:horizontal { background:#0d1117; height:8px; }
    QScrollBar::handle:horizontal { background:#30363d; border-radius:4px; }
    QGroupBox      { border:1px solid #30363d; border-radius:6px; margin-top:12px;
                     padding-top:8px; color:#58a6ff; font-weight:bold; }
    QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 6px; }
    QSplitter::handle { background:#30363d; }
    QMenu          { background:#161b22; border:1px solid #30363d; }
    QMenu::item    { padding:8px 24px; }
    QMenu::item:selected { background:#1f6feb; }
    QMenu::separator { background:#30363d; height:1px; margin:4px 0; }
    QDateEdit      { background:#21262d; border:1px solid #30363d; border-radius:4px;
                     padding:5px 10px; color:#e6edf3; }
"""


# ── LOGIN DIALOG ──────────────────────────────────────────────────────────────

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    auth_code = None
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200); self.end_headers()
            self.wfile.write(b"<h2 style='font-family:sans-serif;color:green'>Auth successful! You can close this window.</h2>")
        else:
            self.send_response(400); self.end_headers()
    def log_message(self, *args): pass


# AuthThread removed — using manual URL paste which is more reliable
# Port 443 requires admin rights on Mac/Windows so auto-capture is skipped


class LoginDialog(QDialog):
    def __init__(self, parent=None, app_key: str = "", app_secret: str = ""):
        super().__init__(parent)
        self.setWindowTitle("AlphaDesk — Login")
        self.setFixedSize(520, 480)
        self.setStyleSheet("background:#161b22; color:#e6edf3; font-family:Consolas;")
        self._api = None
        self._prefilled_key    = app_key
        self._prefilled_secret = app_secret
        self._build()

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(40, 32, 40, 32)
        vbox.setSpacing(16)

        # Title
        title = QLabel("⚡ ALPHADESK")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color:#58a6ff; font-size:18px; font-weight:bold; background:transparent;")
        vbox.addWidget(title)

        if self._prefilled_key:
            # Keys are hardcoded — just show Schwab login button
            sub = QLabel("Click below to authorize with your Schwab account.\nYou only need to do this once.")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet("color:#8b949e; font-size:11px; background:transparent;")
            vbox.addWidget(sub)

            key_info = QLabel(f"App Key: {self._prefilled_key[:12]}…")
            key_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_info.setStyleSheet("color:#30363d; font-size:10px; background:transparent;")
            vbox.addWidget(key_info)

            # Hidden inputs — still used internally
            self._key_input    = QLineEdit(self._prefilled_key)
            self._secret_input = QLineEdit(self._prefilled_secret)
            self._key_input.setVisible(False)
            self._secret_input.setVisible(False)
            vbox.addWidget(self._key_input)
            vbox.addWidget(self._secret_input)
        else:
            # No hardcoded keys — show input fields
            sub = QLabel("Enter your Schwab Developer credentials")
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet("color:#8b949e; font-size:11px; background:transparent;")
            vbox.addWidget(sub)

            vbox.addSpacing(8)

            key_lbl = QLabel("App Key")
            key_lbl.setStyleSheet("color:#c9d1d9; font-size:11px; font-weight:bold; background:transparent;")
            vbox.addWidget(key_lbl)
            self._key_input = QLineEdit()
            self._key_input.setPlaceholderText("Paste your App Key here")
            self._key_input.setFixedHeight(38)
            saved_key, saved_secret = get_credentials()
            if saved_key: self._key_input.setText(saved_key)
            vbox.addWidget(self._key_input)

            sec_lbl = QLabel("App Secret")
            sec_lbl.setStyleSheet("color:#c9d1d9; font-size:11px; font-weight:bold; background:transparent;")
            vbox.addWidget(sec_lbl)
            self._secret_input = QLineEdit()
            self._secret_input.setPlaceholderText("Paste your App Secret here")
            self._secret_input.setEchoMode(QLineEdit.EchoMode.Password)
            self._secret_input.setFixedHeight(38)
            if saved_secret: self._secret_input.setText(saved_secret)
            vbox.addWidget(self._secret_input)

        vbox.addSpacing(4)

        # Step 1 button
        self._connect_btn = QPushButton("Step 1:  Open Schwab Login →")
        self._connect_btn.setObjectName("blue_btn")
        self._connect_btn.setFixedHeight(44)
        self._connect_btn.clicked.connect(self._start_auth)
        vbox.addWidget(self._connect_btn)

        # Step 2 — always visible
        step2_lbl = QLabel("Step 2:  After logging in, copy the URL from your browser and paste it below:")
        step2_lbl.setWordWrap(True)
        step2_lbl.setStyleSheet("color:#c9d1d9; font-size:11px; background:transparent; padding-top:8px;")
        vbox.addWidget(step2_lbl)

        self._url_input = QLineEdit()
        self._url_input.setPlaceholderText("https://127.0.0.1/?code=C0.b3Blb...")
        self._url_input.setFixedHeight(38)
        self._url_input.returnPressed.connect(self._manual_submit)
        vbox.addWidget(self._url_input)

        submit_btn = QPushButton("Step 3:  Complete Login")
        submit_btn.setObjectName("blue_btn")
        submit_btn.setFixedHeight(44)
        submit_btn.clicked.connect(self._manual_submit)
        vbox.addWidget(submit_btn)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color:#8b949e; font-size:10px; background:transparent;")
        vbox.addWidget(self._status)

    def _set_status(self, msg, color="#8b949e"):
        self._status.setText(msg)
        self._status.setStyleSheet(f"color:{color}; font-size:10px; background:transparent;")

    def _start_auth(self):
        app_key    = self._key_input.text().strip()
        app_secret = self._secret_input.text().strip()

        if not app_key or not app_secret:
            QMessageBox.warning(self, "Missing credentials", "Please enter both App Key and App Secret.")
            return

        # Save credentials
        set_credentials(app_key, app_secret)

        self._connect_btn.setText("✓ Browser Opened — complete login there")
        self._set_status("Log in with your Schwab credentials, then copy the URL and paste it in Step 2 below.", "#d29922")

        # Build auth URL and open browser
        from urllib.parse import urlencode
        params = {
            "response_type": "code",
            "client_id":     app_key,
            "redirect_uri":  "https://127.0.0.1",
        }
        auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?{urlencode(params)}"
        webbrowser.open(auth_url)

    def _exchange_code(self, code: str):
        app_key    = self._key_input.text().strip()
        app_secret = self._secret_input.text().strip()
        self._set_status("Exchanging code for tokens…", "#d29922")

        # Exchange code for tokens
        try:
            creds = base64.b64encode(f"{app_key}:{app_secret}".encode()).decode()
            resp  = req_lib.post(
                "https://api.schwabapi.com/v1/oauth/token",
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type":  "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type":   "authorization_code",
                    "code":         code,
                    "redirect_uri": "https://127.0.0.1",
                }
            )
            if resp.status_code == 200:
                # Save tokens
                import json, time
                data = resp.json()
                os.makedirs("config", exist_ok=True)
                with open("config/tokens.json", "w") as f:
                    json.dump({
                        "access_token":  data["access_token"],
                        "refresh_token": data.get("refresh_token", ""),
                        "expiry":        time.time() + data.get("expires_in", 1800),
                        "account_hash":  "",
                    }, f)

                self._set_status("✓ Authenticated successfully!", "#3fb950")
                self._connect_btn.setText("✓ Connected")

                # Build API and load accounts
                self._api = API(
                    app_key=app_key,
                    app_secret=app_secret,
                    token_path="config/tokens.json"
                )
                accounts = self._api.get_accounts()
                if accounts:
                    self._api.set_account(accounts[0].get("hashValue", ""))

                # Small delay then close
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(800, self.accept)
            else:
                self._set_status(f"Token exchange failed ({resp.status_code}). Check your credentials.", "#f85149")
                self._connect_btn.setEnabled(True)
                self._connect_btn.setText("🔐  Connect & Authorize")
        except Exception as e:
            self._set_status(f"Error: {e}", "#f85149")
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("🔐  Connect & Authorize")

    def _on_auth_failed(self, reason: str):
        if reason == "PORT_ERROR":
            # Port 443 blocked — show manual URL entry
            self._set_status("Auto-capture failed. Paste the redirect URL below:", "#d29922")
            self._manual_frame.setVisible(True)
        else:
            self._set_status(f"Auth failed: {reason}", "#f85149")
            self._connect_btn.setEnabled(True)
            self._connect_btn.setText("🔐  Connect & Authorize")

    def _manual_submit(self):
        url = self._url_input.text().strip()
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        code   = params.get("code", [None])[0]
        if code:
            self._exchange_code(code)
        else:
            QMessageBox.warning(self, "Error", "Could not find auth code in URL.\nMake sure you pasted the full redirect URL.")

    def get_api(self):
        return self._api


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("AlphaDesk")
    app.setStyle("Fusion")

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor("#0d1117"))
    p.setColor(QPalette.ColorRole.WindowText,      QColor("#e6edf3"))
    p.setColor(QPalette.ColorRole.Base,            QColor("#161b22"))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor("#21262d"))
    p.setColor(QPalette.ColorRole.Text,            QColor("#e6edf3"))
    p.setColor(QPalette.ColorRole.Button,          QColor("#21262d"))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor("#e6edf3"))
    p.setColor(QPalette.ColorRole.Highlight,       QColor("#1f6feb"))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(p)
    app.setStyleSheet(STYLESHEET)

    if DEMO_MODE:
        from api.mock_client import MockSchwabAPI
        api = MockSchwabAPI()
        win = MainWindow(api=api, demo_mode=True)
        win.show()
    else:
        # Save hardcoded credentials so token refresh works automatically
        set_credentials(APP_KEY, APP_SECRET)

        live_api = API(
            app_key=APP_KEY,
            app_secret=APP_SECRET,
            token_path="config/tokens.json"
        )

        if live_api.is_authenticated():
            # Already have a valid token — go straight to app
            win = MainWindow(api=live_api, demo_mode=False)
            win.show()
        else:
            # First time — only need Schwab login, keys are already set
            login = LoginDialog(app_key=APP_KEY, app_secret=APP_SECRET)
            if login.exec() == QDialog.DialogCode.Accepted:
                api = login.get_api()
                if api:
                    win = MainWindow(api=api, demo_mode=False)
                    win.show()
                else:
                    sys.exit(0)
            else:
                sys.exit(0)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
