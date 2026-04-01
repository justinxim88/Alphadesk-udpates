"""
Toast Notification System v9
- In-app popup for fills, rejections, order updates
- Shows in top-right corner
- Auto-dismisses
- Color coded: green=fill, red=reject, yellow=warning, blue=info
"""

from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QColor


class ToastNotification(QWidget):
    closed = pyqtSignal()

    STYLES = {
        "success": {"bg": "#1a3a1a", "border": "#3fb950", "icon": "✅", "title_color": "#3fb950"},
        "error":   {"bg": "#3a1a1a", "border": "#f85149", "icon": "❌", "title_color": "#f85149"},
        "warning": {"bg": "#3a2a0a", "border": "#d29922", "icon": "⚠️", "title_color": "#d29922"},
        "info":    {"bg": "#1a2a3a", "border": "#58a6ff", "icon": "ℹ️", "title_color": "#58a6ff"},
        "fill":    {"bg": "#0a2a1a", "border": "#3fb950", "icon": "⚡", "title_color": "#3fb950"},
        "reject":  {"bg": "#3a0a0a", "border": "#f85149", "icon": "🚫", "title_color": "#f85149"},
    }

    def __init__(self, title, message, kind="info", duration=4000, parent=None):
        super().__init__(None, Qt.WindowType.Window |
                         Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.Tool)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMinimumWidth(320)
        self.setMaximumWidth(400)

        style = self.STYLES.get(kind, self.STYLES["info"])
        bg     = style["bg"]
        border = style["border"]
        icon   = style["icon"]
        tc     = style["title_color"]

        # Main container
        self.setStyleSheet(f"""
            QWidget#toast {{
                background-color: {bg};
                border: 2px solid {border};
                border-radius: 8px;
            }}
        """)

        container = QWidget(self)
        container.setObjectName("toast")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.addWidget(container)

        inner = QVBoxLayout(container)
        inner.setContentsMargins(14, 10, 14, 12)
        inner.setSpacing(4)

        # Header row
        hdr = QHBoxLayout()
        title_lbl = QLabel(f"{icon}  {title}")
        title_lbl.setStyleSheet(f"color: {tc}; font-size: 13px; font-weight: bold; background: transparent; border: none;")
        hdr.addWidget(title_lbl)
        hdr.addStretch()

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setStyleSheet("QPushButton { background: transparent; color: #8b949e; border: none; font-size: 12px; } QPushButton:hover { color: #e6edf3; }")
        close_btn.clicked.connect(self.close)
        hdr.addWidget(close_btn)
        inner.addLayout(hdr)

        # Message
        if message:
            msg_lbl = QLabel(message)
            msg_lbl.setStyleSheet("color: #e6edf3; font-size: 11px; background: transparent; border: none;")
            msg_lbl.setWordWrap(True)
            inner.addWidget(msg_lbl)

        # Progress bar
        self._progress = QWidget(container)
        self._progress.setFixedHeight(3)
        self._progress.setStyleSheet(f"background: {border}; border-radius: 1px;")
        inner.addWidget(self._progress)

        # Auto-dismiss timer
        self._duration = duration
        self._timer = QTimer()
        self._timer.timeout.connect(self.close)
        self._timer.setSingleShot(True)
        self._timer.start(duration)

        # Shrink progress bar
        self._prog_timer = QTimer()
        self._prog_timer.timeout.connect(self._shrink_progress)
        self._prog_timer.start(50)
        self._elapsed = 0

    def _shrink_progress(self):
        self._elapsed += 50
        ratio = max(0, 1 - self._elapsed / self._duration)
        full_w = self.width() - 28
        self._progress.setFixedWidth(max(0, int(full_w * ratio)))
        if self._elapsed >= self._duration:
            self._prog_timer.stop()

    def closeEvent(self, event):
        self._timer.stop()
        self._prog_timer.stop()
        self.closed.emit()
        super().closeEvent(event)


class ToastManager:
    """Manages multiple toast notifications stacked in top-right corner."""

    def __init__(self, parent_window):
        self._parent = parent_window
        self._toasts = []

    def show(self, title, message="", kind="info", duration=4000):
        toast = ToastNotification(title, message, kind, duration, None)
        toast.closed.connect(lambda: self._remove(toast))
        self._toasts.append(toast)
        self._reposition()
        toast.show()

    def _remove(self, toast):
        if toast in self._toasts:
            self._toasts.remove(toast)
        self._reposition()

    def _reposition(self):
        if not self._parent:
            return
        parent_geo = self._parent.geometry()
        right  = parent_geo.right()
        top    = parent_geo.top() + 60
        margin = 12
        y = top
        for toast in self._toasts:
            toast.adjustSize()
            w = toast.width()
            toast.move(right - w - margin, y)
            y += toast.height() + margin


# Global manager instance — set up in main_window.py
_manager = None

def init_toast_manager(parent_window):
    global _manager
    _manager = ToastManager(parent_window)

def notify(title, kind="info", subtitle="", duration=4000):
    global _manager
    if _manager:
        _manager.show(title, subtitle, kind, duration)
    else:
        print(f"[{kind.upper()}] {title}: {subtitle}")
