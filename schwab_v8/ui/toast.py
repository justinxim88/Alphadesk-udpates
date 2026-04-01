"""
Toast Notification — slides in, shows message, auto-dismisses after N seconds.
Used for order fills, rejections, and price alerts.
"""

from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect
from PyQt6.QtGui import QColor

GREEN  = "#3fb950"
RED    = "#f85149"
BLUE   = "#58a6ff"
YELLOW = "#d29922"
BG2    = "#161b22"


class ToastNotification(QWidget):
    """
    Floating toast that appears in the top-right corner of the parent
    and fades out after `duration` milliseconds.

    Usage:
        toast = ToastNotification(parent)
        toast.show_message("✓ Order Filled: BUY 10x AAPL @ $213.45", "success")
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self._queue = []
        self._showing = False
        self._build()

    def _build(self):
        self._container = QWidget(self)
        self._container.setStyleSheet(f"""
            QWidget {{
                background-color: {BG2};
                border: 1px solid #30363d;
                border-radius: 8px;
            }}
        """)
        layout = QVBoxLayout(self._container)
        layout.setContentsMargins(16, 12, 16, 12)

        self._icon_lbl = QLabel("")
        self._icon_lbl.setStyleSheet("font-size: 16px; background: transparent; border: none;")

        self._msg_lbl = QLabel("")
        self._msg_lbl.setWordWrap(True)
        self._msg_lbl.setStyleSheet("font-size: 12px; font-family: Consolas; background: transparent; border: none;")

        self._sub_lbl = QLabel("")
        self._sub_lbl.setStyleSheet(f"font-size: 10px; color: #8b949e; font-family: Consolas; background: transparent; border: none;")

        top_row = QHBoxLayout()
        top_row.setSpacing(8)
        top_row.addWidget(self._icon_lbl)
        top_row.addWidget(self._msg_lbl, stretch=1)

        layout.addLayout(top_row)
        layout.addWidget(self._sub_lbl)

        self._container.adjustSize()
        self.resize(self._container.size())

        self._dismiss_timer = QTimer()
        self._dismiss_timer.setSingleShot(True)
        self._dismiss_timer.timeout.connect(self._dismiss)

    def show_message(self, message: str, kind: str = "info",
                     subtitle: str = "", duration: int = 3500):
        """
        kind: "success" | "error" | "warning" | "info"
        """
        self._queue.append((message, kind, subtitle, duration))
        if not self._showing:
            self._show_next()

    def _show_next(self):
        if not self._queue:
            self._showing = False
            self.hide()
            return

        message, kind, subtitle, duration = self._queue.pop(0)
        self._showing = True

        colors = {
            "success": (GREEN,  "✓"),
            "error":   (RED,    "✗"),
            "warning": (YELLOW, "⚠"),
            "info":    (BLUE,   "ℹ"),
        }
        color, icon = colors.get(kind, (BLUE, "ℹ"))

        self._icon_lbl.setText(icon)
        self._icon_lbl.setStyleSheet(
            f"font-size:16px; color:{color}; background:transparent; border:none; font-weight:bold;")
        self._msg_lbl.setText(message)
        self._msg_lbl.setStyleSheet(
            f"font-size:12px; font-family:Consolas; color:{color}; background:transparent; border:none; font-weight:bold;")
        self._sub_lbl.setText(subtitle)
        self._sub_lbl.setVisible(bool(subtitle))

        # Left border color
        self._container.setStyleSheet(f"""
            QWidget {{
                background-color: {BG2};
                border: 1px solid #30363d;
                border-left: 4px solid {color};
                border-radius: 8px;
            }}
        """)

        self._container.adjustSize()
        self.resize(max(320, self._container.width()), self._container.height())
        self._container.resize(self.size())

        # Position top-right of parent
        if self.parent():
            parent = self.parent()
            pw = parent.width(); ph = parent.height()
            x = pw - self.width() - 20
            y = 80
            self.move(parent.mapToGlobal(
                __import__('PyQt6.QtCore', fromlist=['QPoint']).QPoint(x, y)))

        self.show()
        self.raise_()
        self._dismiss_timer.start(duration)

    def _dismiss(self):
        self.hide()
        self._showing = False
        # Show next queued message if any
        if self._queue:
            QTimer.singleShot(300, self._show_next)
        else:
            self._showing = False


# ── Global toast instance helper ─────────────────────────────────────────────

_global_toast = None

def get_toast(parent=None) -> ToastNotification:
    global _global_toast
    if _global_toast is None or not _global_toast.isVisible() and parent:
        _global_toast = ToastNotification(parent)
    return _global_toast

def notify(message: str, kind: str = "info",
           subtitle: str = "", duration: int = 3500, parent=None):
    """Convenience function — call from anywhere."""
    toast = get_toast(parent)
    toast.show_message(message, kind, subtitle, duration)
