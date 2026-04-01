"""
Open P&L Popup v14
- Floating window showing live Open P&L
- Updates every 2 seconds
- Shows per-position and total
"""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QWidget
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont

GREEN = "#3fb950"; RED = "#f85149"; BLUE = "#58a6ff"
DIM = "#8b949e"; BG = "#0d1117"; BG2 = "#161b22"; BG3 = "#21262d"


class PnLThread(QThread):
    done = pyqtSignal(dict)
    def __init__(self, api): super().__init__(); self.api = api
    def run(self):
        try: self.done.emit(self.api.get_portfolio())
        except: self.done.emit({})


class PnLPopup(QDialog):
    def __init__(self, parent, api):
        super().__init__(None, Qt.WindowType.Window |
                         Qt.WindowType.WindowStaysOnTopHint |
                         Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.Tool)
        self.api = api
        self._threads = []
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(280)
        self._build()
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(2000)
        QTimer.singleShot(100, self._refresh)
        # Allow dragging
        self._drag_pos = None

    def _build(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0,0,0,0)

        container = QWidget(self)
        container.setStyleSheet(f"""
            QWidget {{
                background: {BG2};
                border: 2px solid #30363d;
                border-radius: 8px;
            }}
        """)
        cv = QVBoxLayout(container)
        cv.setContentsMargins(14,10,14,12); cv.setSpacing(6)

        # Title bar
        hdr = QHBoxLayout()
        title = QLabel("📈  Open P&L")
        title.setStyleSheet(f"color:{BLUE};font-size:13px;font-weight:bold;background:transparent;border:none;")
        hdr.addWidget(title); hdr.addStretch()
        close_btn = QLabel("✕")
        close_btn.setStyleSheet(f"color:{DIM};font-size:13px;cursor:pointer;background:transparent;border:none;")
        close_btn.mousePressEvent = lambda _: self.close()
        hdr.addWidget(close_btn)
        cv.addLayout(hdr)

        # Total P&L — big display
        self._total_lbl = QLabel("$0.00")
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._total_lbl.setStyleSheet(f"color:{GREEN};font-size:28px;font-weight:bold;background:transparent;border:none;")
        cv.addWidget(self._total_lbl)

        self._pct_lbl = QLabel("0.00%")
        self._pct_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._pct_lbl.setStyleSheet(f"color:{DIM};font-size:13px;background:transparent;border:none;")
        cv.addWidget(self._pct_lbl)

        # Divider
        div = QWidget(); div.setFixedHeight(1)
        div.setStyleSheet("background:#30363d;border:none;")
        cv.addWidget(div)

        # Per-position list
        self._pos_container = QVBoxLayout()
        self._pos_container.setSpacing(3)
        cv.addLayout(self._pos_container)

        # Last updated
        self._updated = QLabel("")
        self._updated.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._updated.setStyleSheet(f"color:{DIM};font-size:9px;background:transparent;border:none;")
        cv.addWidget(self._updated)

        vbox.addWidget(container)

    def _refresh(self):
        t = PnLThread(self.api)
        t.done.connect(self._populate)
        t.done.connect(lambda _: self._cleanup(t))
        self._threads.append(t); t.start()

    def _cleanup(self, t):
        try: self._threads.remove(t)
        except: pass

    def _populate(self, data: dict):
        from datetime import datetime
        acct = data.get("securitiesAccount",{})
        pos  = acct.get("positions",[])

        total_open = sum(p.get("longOpenProfitLoss", p.get("shortOpenProfitLoss",0)) for p in pos)
        total_val  = sum(p.get("marketValue",0) for p in pos)
        pct = (total_open / (total_val - total_open) * 100) if (total_val - total_open) != 0 else 0

        color = GREEN if total_open >= 0 else RED
        sign  = "+" if total_open >= 0 else ""
        self._total_lbl.setText(f"{sign}${total_open:,.2f}")
        self._total_lbl.setStyleSheet(f"color:{color};font-size:28px;font-weight:bold;background:transparent;border:none;")
        self._pct_lbl.setText(f"{sign}{pct:.2f}%")
        self._pct_lbl.setStyleSheet(f"color:{color};font-size:13px;background:transparent;border:none;")

        # Clear and repopulate positions
        while self._pos_container.count():
            item = self._pos_container.takeAt(0)
            if item.widget(): item.widget().deleteLater()

        for p in pos[:8]:  # max 8 positions shown
            inst    = p.get("instrument",{})
            sym     = inst.get("symbol","—")
            pnl     = p.get("longOpenProfitLoss", p.get("shortOpenProfitLoss",0))
            sign_p  = "+" if pnl>=0 else ""
            color_p = GREEN if pnl>=0 else RED

            row = QHBoxLayout(); row.setSpacing(4)
            sym_lbl = QLabel(sym[:10])
            sym_lbl.setStyleSheet(f"color:{BLUE};font-size:11px;font-family:Consolas;font-weight:bold;background:transparent;border:none;")
            pnl_lbl = QLabel(f"{sign_p}${pnl:,.2f}")
            pnl_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            pnl_lbl.setStyleSheet(f"color:{color_p};font-size:11px;font-family:Consolas;font-weight:bold;background:transparent;border:none;")
            row.addWidget(sym_lbl); row.addStretch(); row.addWidget(pnl_lbl)
            w = QWidget(); w.setLayout(row)
            w.setStyleSheet("background:transparent;border:none;")
            self._pos_container.addWidget(w)

        self._updated.setText(f"Updated {datetime.now().strftime('%H:%M:%S')}")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def closeEvent(self, event):
        self._timer.stop()
        super().closeEvent(event)