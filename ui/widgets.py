"""Shared UI helpers."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QTableWidget, QTableWidgetItem, QHeaderView
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

GREEN  = "#3fb950"
RED    = "#f85149"
BLUE   = "#58a6ff"
YELLOW = "#d29922"
DIM    = "#8b949e"
BG2    = "#161b22"
BG3    = "#21262d"
TEXT   = "#e6edf3"
PURPLE = "#8957e5"


def color_item(text: str, color: str = TEXT) -> QTableWidgetItem:
    item = QTableWidgetItem(str(text))
    item.setForeground(QColor(color))
    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def plain_item(text: str) -> QTableWidgetItem:
    return color_item(str(text), TEXT)


def make_table(columns: list, stretch_col: int = 0) -> QTableWidget:
    t = QTableWidget(0, len(columns))
    t.setHorizontalHeaderLabels(columns)
    t.verticalHeader().setVisible(False)
    t.setAlternatingRowColors(True)
    t.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    t.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    t.horizontalHeader().setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
    t.setShowGrid(False)
    return t


class StatCard(QFrame):
    def __init__(self, label: str, value: str = "—", color: str = BLUE):
        super().__init__()
        self.setStyleSheet(f"QFrame {{ background:{BG2}; border:1px solid #30363d; border-radius:8px; }}")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(16, 12, 16, 12)
        vbox.setSpacing(4)
        lbl = QLabel(label)
        lbl.setStyleSheet(f"color:{DIM}; font-size:10px; background:transparent; border:none;")
        vbox.addWidget(lbl)
        self._val = QLabel(value)
        self._val.setStyleSheet(f"color:{color}; font-size:20px; font-weight:bold; background:transparent; border:none;")
        vbox.addWidget(self._val)

    def set_value(self, text: str, color: str = None):
        self._val.setText(text)
        if color:
            self._val.setStyleSheet(f"color:{color}; font-size:20px; font-weight:bold; background:transparent; border:none;")


class PageHeader(QWidget):
    def __init__(self, title: str, on_refresh=None):
        super().__init__()
        self.setFixedHeight(56)
        self.setStyleSheet("background:#161b22; border-bottom:1px solid #30363d;")
        hbox = QHBoxLayout(self)
        hbox.setContentsMargins(24, 0, 24, 0)
        lbl = QLabel(title)
        lbl.setStyleSheet("color:#58a6ff; font-size:16px; font-weight:bold; background:transparent;")
        hbox.addWidget(lbl)
        hbox.addStretch()
        if on_refresh:
            btn = QPushButton("⟳  Refresh")
            btn.setObjectName("blue_btn")
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(on_refresh)
            hbox.addWidget(btn)
