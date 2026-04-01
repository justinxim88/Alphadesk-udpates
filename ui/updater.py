"""
AlphaDesk Auto-Updater v14
- Checks for updates on startup
- Downloads and applies updates automatically
- Never touches main.py (credentials safe)
- Shows update progress in a popup
"""

import os
import sys
import json
import shutil
import zipfile
import tempfile
import threading
import requests
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QProgressBar, QWidget
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QObject

# ── UPDATE SERVER CONFIG ──────────────────────────────────────
# This URL points to the update manifest JSON file
# I will provide you with this URL after setup
UPDATE_MANIFEST_URL = "https://raw.githubusercontent.com/alphadesk-updates/releases/main/manifest.json"

# Current version — increment this with each release
CURRENT_VERSION = "1.0.14"

# Files that should NEVER be updated (contain user credentials)
PROTECTED_FILES = {"main.py", "config/tokens.json", "config/settings.json"}

BG2 = "#161b22"; BG3 = "#21262d"; BLUE = "#58a6ff"
GREEN = "#3fb950"; DIM = "#8b949e"


class UpdateSignals(QObject):
    progress    = pyqtSignal(int, str)   # percent, message
    finished    = pyqtSignal(bool, str)  # success, message
    update_found = pyqtSignal(str, str)  # new_version, changelog


update_signals = UpdateSignals()


class UpdateChecker:
    """Checks for and applies updates."""

    def __init__(self, app_dir: str):
        self.app_dir = app_dir

    def check(self):
        """Check for updates in background thread."""
        threading.Thread(target=self._do_check, daemon=True).start()

    def _do_check(self):
        try:
            resp = requests.get(UPDATE_MANIFEST_URL, timeout=10)
            if resp.status_code != 200:
                return  # silently skip if can't reach server
            manifest = resp.json()
            latest   = manifest.get("version","")
            url      = manifest.get("download_url","")
            changelog= manifest.get("changelog","No changes listed")

            if not latest or not url:
                return
            if self._version_newer(latest, CURRENT_VERSION):
                update_signals.update_found.emit(latest, changelog)
                # Store for download
                self._pending_url     = url
                self._pending_version = latest
        except Exception as e:
            print(f"[Updater] Check failed: {e}")

    def download_and_apply(self, url: str):
        """Download update zip and apply it."""
        threading.Thread(
            target=self._do_update,
            args=(url,),
            daemon=True
        ).start()

    def _do_update(self, url: str):
        try:
            update_signals.progress.emit(5, "Downloading update…")
            resp = requests.get(url, stream=True, timeout=60)
            if resp.status_code != 200:
                update_signals.finished.emit(False, f"Download failed: {resp.status_code}")
                return

            # Save to temp file
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
            for chunk in resp.iter_content(chunk_size=8192):
                tmp.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    pct = int(downloaded / total * 60) + 5
                    update_signals.progress.emit(pct, f"Downloading… {downloaded//1024}KB")
            tmp.close()

            update_signals.progress.emit(70, "Applying update…")
            self._apply_update(tmp.name)
            os.unlink(tmp.name)

            update_signals.progress.emit(100, "Update complete!")
            update_signals.finished.emit(True, "Update applied. Please restart AlphaDesk.")

        except Exception as e:
            update_signals.finished.emit(False, f"Update error: {e}")

    def _apply_update(self, zip_path: str):
        """Extract update zip, skipping protected files."""
        with zipfile.ZipFile(zip_path, 'r') as zf:
            names = zf.namelist()
            total = len(names)
            for i, name in enumerate(names):
                # Skip protected files
                clean = name.split("/", 1)[-1] if "/" in name else name
                if any(clean == p or clean.endswith("/" + p) for p in PROTECTED_FILES):
                    continue
                # Skip main.py at any depth
                if os.path.basename(name) == "main.py":
                    continue
                # Extract
                try:
                    target = os.path.join(self.app_dir, clean)
                    if name.endswith("/"):
                        os.makedirs(target, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with zf.open(name) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                except Exception as e:
                    print(f"[Updater] Skip {name}: {e}")
                pct = 70 + int(i / total * 25)
                update_signals.progress.emit(pct, f"Applying… {i+1}/{total}")

    def _version_newer(self, latest: str, current: str) -> bool:
        """Compare version strings like '1.0.14' > '1.0.13'."""
        try:
            l = [int(x) for x in latest.split(".")]
            c = [int(x) for x in current.split(".")]
            return l > c
        except:
            return False


class UpdateDialog(QDialog):
    """Popup shown when an update is available."""

    def __init__(self, parent, new_version: str, changelog: str, checker):
        super().__init__(parent)
        self.checker  = checker
        self.setWindowTitle("AlphaDesk Update Available")
        self.setFixedWidth(420)
        self.setStyleSheet(f"QDialog{{background:{BG2};color:#e6edf3;}} QLabel{{color:#e6edf3;}}")
        self._build(new_version, changelog)

        update_signals.progress.connect(self._on_progress)
        update_signals.finished.connect(self._on_finished)

    def _build(self, version: str, changelog: str):
        v = QVBoxLayout(self); v.setContentsMargins(20,20,20,20); v.setSpacing(12)

        title = QLabel(f"⚡  AlphaDesk {version} Available")
        title.setStyleSheet(f"color:{BLUE};font-size:15px;font-weight:bold;")
        v.addWidget(title)

        current_lbl = QLabel(f"Current version: {CURRENT_VERSION}")
        current_lbl.setStyleSheet(f"color:{DIM};font-size:11px;")
        v.addWidget(current_lbl)

        # Changelog
        cl_lbl = QLabel("What's new:")
        cl_lbl.setStyleSheet(f"color:{DIM};font-size:11px;font-weight:bold;")
        v.addWidget(cl_lbl)

        cl = QLabel(changelog)
        cl.setWordWrap(True)
        cl.setStyleSheet(f"background:#0d1117;color:#e6edf3;padding:10px;border:1px solid #30363d;border-radius:4px;font-size:11px;")
        v.addWidget(cl)

        safe_lbl = QLabel("✅  Your credentials and settings will NOT be affected")
        safe_lbl.setStyleSheet(f"color:{GREEN};font-size:11px;")
        v.addWidget(safe_lbl)

        # Progress bar (hidden until update starts)
        self._progress = QProgressBar()
        self._progress.setFixedHeight(8)
        self._progress.setTextVisible(False)
        self._progress.setStyleSheet(f"QProgressBar{{background:#30363d;border:none;border-radius:4px;}} QProgressBar::chunk{{background:{BLUE};border-radius:4px;}}")
        self._progress.hide()
        v.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setStyleSheet(f"color:{DIM};font-size:10px;")
        self._status.hide()
        v.addWidget(self._status)

        # Buttons
        btns = QHBoxLayout(); btns.setSpacing(8)
        skip = QPushButton("Skip")
        skip.setFixedHeight(36)
        skip.setStyleSheet(f"QPushButton{{background:{BG3};color:{DIM};border:1px solid #30363d;border-radius:4px;font-size:12px;}} QPushButton:hover{{color:#e6edf3;}}")
        skip.clicked.connect(self.reject)
        btns.addWidget(skip)

        self._update_btn = QPushButton("⬇  Update Now")
        self._update_btn.setFixedHeight(36)
        self._update_btn.setStyleSheet(f"QPushButton{{background:{BLUE};color:#fff;border:none;border-radius:4px;font-size:12px;font-weight:bold;}} QPushButton:hover{{background:#388bfd;}}")
        self._update_btn.clicked.connect(self._start_update)
        btns.addWidget(self._update_btn)
        v.addLayout(btns)

    def _start_update(self):
        self._update_btn.setEnabled(False)
        self._update_btn.setText("Updating…")
        self._progress.show()
        self._status.show()
        url = getattr(self.checker, "_pending_url","")
        self.checker.download_and_apply(url)

    def _on_progress(self, pct: int, msg: str):
        self._progress.setValue(pct)
        self._status.setText(msg)

    def _on_finished(self, success: bool, msg: str):
        self._status.setText(msg)
        if success:
            self._progress.setValue(100)
            self._update_btn.setText("✅  Restart to Apply")
            self._update_btn.setEnabled(True)
            self._update_btn.clicked.disconnect()
            self._update_btn.clicked.connect(self._restart)
        else:
            self._update_btn.setText("❌  Failed — Retry")
            self._update_btn.setEnabled(True)

    def _restart(self):
        """Restart AlphaDesk after update."""
        self.accept()
        python = sys.executable
        os.execl(python, python, *sys.argv)


def check_for_updates(parent_window, app_dir: str):
    """
    Call this on app startup to check for updates.
    Shows a dialog if an update is available.
    """
    checker = UpdateChecker(app_dir)

    def on_update_found(new_version: str, changelog: str):
        dlg = UpdateDialog(parent_window, new_version, changelog, checker)
        dlg.exec()

    update_signals.update_found.connect(on_update_found)
    checker.check()
