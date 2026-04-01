"""
AlphaDesk Embedded OAuth Login v17
- Opens Schwab login inside WebEngine browser
- Auto-captures auth code from redirect URL
- No manual URL pasting required
- Token saved automatically
"""

import os
import sys
from urllib.parse import urlparse, parse_qs

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt6.QtGui import QColor

BG2 = "#161b22"; BG3 = "#21262d"; BLUE = "#58a6ff"
GREEN = "#3fb950"; DIM = "#8b949e"; RED = "#f85149"

HAS_WE = False
try:
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    from PyQt6.QtWebEngineCore import (
        QWebEngineProfile, QWebEnginePage, QWebEngineSettings
    )
    HAS_WE = True
except Exception as e:
    print(f"[OAuth] WebEngine not available: {e}")


class OAuthLoginDialog(QDialog):
    """
    Embedded Schwab OAuth login dialog.
    Opens login URL in WebEngine, watches for redirect,
    captures auth code automatically.
    """
    auth_complete = pyqtSignal(str)   # emits auth_code on success
    auth_failed   = pyqtSignal(str)   # emits error message

    def __init__(self, parent, auth_url: str, redirect_uri: str,
                 app_key: str, app_secret: str, api=None):
        super().__init__(None, Qt.WindowType.Window)
        self.auth_url    = auth_url
        self.redirect_uri = redirect_uri
        self.app_key     = app_key
        self.app_secret  = app_secret
        self.api         = api
        self._done       = False

        self.setWindowTitle("AlphaDesk — Sign in to Schwab")
        self.setMinimumSize(900, 650)
        self.setStyleSheet(f"QDialog{{background:{BG2};color:#e6edf3;}}")
        self._build()

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(48)
        hdr.setStyleSheet(f"background:{BG2};border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,0,16,0)
        title = QLabel("🔐  Sign in to Schwab")
        title.setStyleSheet(f"color:{BLUE};font-size:14px;font-weight:bold;")
        hh.addWidget(title); hh.addStretch()
        self._status_lbl = QLabel("Loading Schwab login…")
        self._status_lbl.setStyleSheet(f"color:{DIM};font-size:11px;")
        hh.addWidget(self._status_lbl)
        v.addWidget(hdr)

        # Progress bar
        self._progress = QProgressBar()
        self._progress.setFixedHeight(3)
        self._progress.setTextVisible(False)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setStyleSheet(f"QProgressBar{{background:#30363d;border:none;}} QProgressBar::chunk{{background:{BLUE};}}")
        v.addWidget(self._progress)

        if HAS_WE:
            # Use isolated profile for OAuth
            self._profile = QWebEngineProfile("alphadesk_oauth")
            self._profile.setPersistentCookiesPolicy(
                QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)

            self._page = QWebEnginePage(self._profile, self)
            self._page.urlChanged.connect(self._on_url_changed)
            self._page.loadProgress.connect(self._progress.setValue)
            self._page.loadFinished.connect(self._on_load_finished)

            self._view = QWebEngineView()
            self._view.setPage(self._page)

            s = self._profile.settings()
            s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)
            s.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)

            v.addWidget(self._view, stretch=1)
            self._view.setUrl(QUrl(self.auth_url))
        else:
            # Fallback if WebEngine not available
            import webbrowser
            webbrowser.open(self.auth_url)
            fallback = QLabel(
                "WebEngine not available.\n"
                "Please complete login in your browser\n"
                "and paste the redirect URL below."
            )
            fallback.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback.setStyleSheet(f"color:{DIM};font-size:13px;")
            v.addWidget(fallback, stretch=1)

    def _on_url_changed(self, url: QUrl):
        """Watch every URL change for the OAuth redirect."""
        url_str = url.toString()
        self._status_lbl.setText(f"Loading…")

        # Check if this is the redirect URL
        if self._is_redirect(url_str):
            self._capture_auth_code(url_str)

    def _on_load_finished(self, ok: bool):
        self._progress.setValue(100)
        url_str = self._view.url().toString() if HAS_WE else ""
        if self._is_redirect(url_str):
            self._capture_auth_code(url_str)
        else:
            self._status_lbl.setText("Sign in to your Schwab account")

    def _is_redirect(self, url: str) -> bool:
        """Check if URL is the OAuth callback."""
        redirect_base = self.redirect_uri.split("?")[0].rstrip("/")
        return (url.startswith(self.redirect_uri) or
                url.startswith(redirect_base) or
                "code=" in url)

    def _capture_auth_code(self, url: str):
        """Extract auth code from redirect URL and complete login."""
        if self._done: return
        self._done = True

        try:
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            code   = params.get("code", [None])[0]

            if not code:
                # Try fragment
                params2 = parse_qs(parsed.fragment)
                code = params2.get("code", [None])[0]

            if code:
                self._status_lbl.setText("✅ Login successful — completing setup…")
                self._progress.setValue(100)
                # Exchange code for tokens via API
                if self.api and hasattr(self.api, 'exchange_code_for_tokens'):
                    ok = self.api.exchange_code_for_tokens(code)
                    if ok:
                        self._status_lbl.setText("✅ Authenticated successfully!")
                        QTimer.singleShot(1000, self.accept)
                    else:
                        self._status_lbl.setText("❌ Token exchange failed")
                        self.auth_failed.emit("Token exchange failed")
                else:
                    self.auth_complete.emit(code)
                    QTimer.singleShot(500, self.accept)
            else:
                self._status_lbl.setText("❌ Could not capture auth code")
                self.auth_failed.emit("No auth code in redirect URL")
        except Exception as e:
            print(f"[OAuth] Capture error: {e}")
            self.auth_failed.emit(str(e))


def do_oauth_login(parent, api, app_key: str, app_secret: str) -> bool:
    """
    Main entry point for OAuth login.
    Opens embedded browser, completes login, saves tokens.
    Returns True if successful.
    """
    try:
        # Get the auth URL from the API
        if hasattr(api, 'get_auth_url'):
            auth_url, redirect_uri = api.get_auth_url()
        else:
            # Build default Schwab auth URL
            redirect_uri = "https://127.0.0.1"
            auth_url = (
                f"https://api.schwabapi.com/v1/oauth/authorize"
                f"?client_id={app_key}"
                f"&redirect_uri={redirect_uri}"
            )

        dlg = OAuthLoginDialog(
            parent, auth_url, redirect_uri,
            app_key, app_secret, api=api
        )
        result = dlg.exec()
        return result == QDialog.DialogCode.Accepted

    except Exception as e:
        print(f"[OAuth] Login error: {e}")
        return False
