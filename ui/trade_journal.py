"""
Trade Journal v16
- Auto-logs fills from Schwab
- Manual notes, setup tags, grades
- Chart screenshot storage
- P&L tracking per trade
"""

import os
import json
import uuid
from datetime import datetime
from ui.table_utils import setup_table, format_option_symbol

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QDialog, QTextEdit, QComboBox, QLineEdit, QFileDialog,
    QSplitter, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap

GREEN  = "#3fb950"; RED = "#f85149"; BLUE = "#58a6ff"
YELLOW = "#d29922"; DIM = "#8b949e"; BG  = "#0d1117"
BG2    = "#161b22"; BG3 = "#21262d"; PURPLE = "#c792ea"


def to_mt(dt_str: str) -> str:
    """Convert ISO timestamp to Mountain Time."""
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(dt_str.replace("Z","+00:00"))
        mt = dt.astimezone(timezone(timedelta(hours=-7)))
        return mt.strftime("%m/%d/%Y %I:%M %p MST")
    except:
        return dt_str[:16].replace("T"," ")

def to_mt_date(dt_str: str) -> str:
    try:
        from datetime import datetime, timezone, timedelta
        dt = datetime.fromisoformat(dt_str.replace("Z","+00:00"))
        mt = dt.astimezone(timezone(timedelta(hours=-7)))
        return mt.strftime("%m/%d/%Y")
    except:
        return dt_str[:10]

JOURNAL_FILE = os.path.join(os.path.expanduser("~"), ".alphadesk_journal.json")

SETUP_TAGS = [
    "3-Candle FVG", "Opening Range Break", "VWAP Bounce",
    "Gap Fill", "Momentum", "Reversal", "Breakout",
    "Support/Resistance", "Other"
]

GRADES = ["A+", "A", "B", "C", "D", "F"]


def load_journal() -> list:
    try:
        if os.path.exists(JOURNAL_FILE):
            with open(JOURNAL_FILE, 'r') as f:
                return json.load(f)
    except: pass
    return []


def save_journal(entries: list):
    try:
        with open(JOURNAL_FILE, 'w') as f:
            json.dump(entries, f, indent=2)
    except Exception as e:
        print(f"[Journal] Save error: {e}")


def add_journal_entry(entry: dict):
    """Add or update a journal entry by trade_id."""
    entries = load_journal()
    tid = entry.get("trade_id","")
    for i, e in enumerate(entries):
        if e.get("trade_id") == tid:
            entries[i].update(entry)
            save_journal(entries)
            return
    entries.insert(0, entry)
    save_journal(entries)


def get_entry_by_id(trade_id: str) -> dict:
    for e in load_journal():
        if e.get("trade_id") == trade_id:
            return e
    return {}


TABLE_STYLE = f"""
    QTableWidget{{background:{BG2};border:none;gridline-color:#21262d;
                 color:#e6edf3;font-family:Consolas;font-size:12px;}}
    QTableWidget::item{{padding:4px 8px;}}
    QTableWidget::item:selected{{background:#1f6feb44;}}
    QHeaderView::section{{background:{BG3};padding:6px 8px;border:none;
                          border-right:1px solid #30363d;
                          border-bottom:2px solid #58a6ff;
                          font-weight:bold;font-size:11px;color:#e6edf3;}}
"""


class TradeDetailDialog(QDialog):
    """Dialog to view/edit a journal entry."""
    def __init__(self, parent, entry: dict):
        super().__init__(parent)
        self.entry = dict(entry)
        self.setWindowTitle(f"Trade Detail — {entry.get('symbol','')}")
        self.resize(700, 600)
        self.setStyleSheet(f"QDialog{{background:{BG2};color:#e6edf3;}}")
        self._build()

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(16,16,16,16); v.setSpacing(10)

        # Header
        sym   = self.entry.get("symbol","—")
        side  = self.entry.get("side","—")
        pnl   = self.entry.get("pnl", 0)
        pnl_p = self.entry.get("pnl_pct", 0)
        color = GREEN if pnl >= 0 else RED
        sign  = "+" if pnl >= 0 else ""

        hdr = QHBoxLayout()
        title = QLabel(f"{sym}  —  {side}")
        title.setStyleSheet(f"color:{BLUE};font-size:16px;font-weight:bold;")
        hdr.addWidget(title)
        hdr.addStretch()
        pnl_lbl = QLabel(f"{sign}${pnl:.2f} ({sign}{pnl_p:.1f}%)")
        pnl_lbl.setStyleSheet(f"color:{color};font-size:15px;font-weight:bold;")
        hdr.addWidget(pnl_lbl)
        v.addLayout(hdr)

        # Stats row
        stats = QHBoxLayout(); stats.setSpacing(16)
        for label, key, fmt in [
            ("Entry", "entry_price", "${:.2f}"),
            ("Exit",  "exit_price",  "${:.2f}"),
            ("Qty",   "qty",         "{}"),
            ("Entry Time", "entry_time", "{}"),
            ("Exit Time",  "exit_time",  "{}"),
        ]:
            col = QVBoxLayout(); col.setSpacing(2)
            lbl = QLabel(label); lbl.setStyleSheet(f"color:{DIM};font-size:10px;")
            val = QLabel(fmt.format(self.entry.get(key, "—")))
            val.setStyleSheet("color:#e6edf3;font-size:12px;font-weight:bold;")
            col.addWidget(lbl); col.addWidget(val)
            stats.addLayout(col)
        v.addLayout(stats)

        div = QFrame(); div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color:#30363d;"); v.addWidget(div)

        # Screenshot
        ss_path = self.entry.get("screenshot","")
        if ss_path and os.path.exists(ss_path):
            px = QPixmap(ss_path).scaledToWidth(660, Qt.TransformationMode.SmoothTransformation)
            img_lbl = QLabel(); img_lbl.setPixmap(px)
            img_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(img_lbl)
        else:
            no_img = QLabel("No screenshot")
            no_img.setStyleSheet(f"color:{DIM};font-size:11px;padding:8px;")
            no_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(no_img)

        # Setup tag
        tag_row = QHBoxLayout()
        tag_row.addWidget(QLabel("Setup:"))
        self._setup_cb = QComboBox()
        self._setup_cb.addItems(["— Select —"] + SETUP_TAGS)
        current_setup = self.entry.get("setup","")
        if current_setup in SETUP_TAGS:
            self._setup_cb.setCurrentText(current_setup)
        self._setup_cb.setStyleSheet(f"QComboBox{{background:{BG};color:#e6edf3;border:1px solid #30363d;border-radius:3px;padding:4px;}} QComboBox QAbstractItemView{{background:{BG2};color:#e6edf3;selection-background-color:#1f6feb;}}")
        tag_row.addWidget(self._setup_cb)

        tag_row.addWidget(QLabel("Grade:"))
        self._grade_cb = QComboBox()
        self._grade_cb.addItems(["—"] + GRADES)
        current_grade = self.entry.get("grade","")
        if current_grade in GRADES:
            self._grade_cb.setCurrentText(current_grade)
        self._grade_cb.setStyleSheet(self._setup_cb.styleSheet())
        tag_row.addWidget(self._grade_cb)
        tag_row.addStretch()
        v.addLayout(tag_row)

        # Notes
        v.addWidget(QLabel("Notes:"))
        self._notes = QTextEdit()
        self._notes.setPlaceholderText("What did you do well? What could be improved?")
        self._notes.setText(self.entry.get("notes",""))
        self._notes.setFixedHeight(100)
        self._notes.setStyleSheet(f"QTextEdit{{background:{BG};color:#e6edf3;border:1px solid #30363d;border-radius:3px;padding:6px;font-size:12px;}}")
        v.addWidget(self._notes)

        # Buttons
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(36)
        save_btn.setStyleSheet(f"QPushButton{{background:#238636;color:#fff;border:none;border-radius:4px;font-size:13px;font-weight:bold;padding:0 20px;}} QPushButton:hover{{background:#2ea043;}}")
        save_btn.clicked.connect(self._save)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(36)
        close_btn.setStyleSheet(f"QPushButton{{background:{BG3};color:{DIM};border:1px solid #30363d;border-radius:4px;font-size:13px;padding:0 20px;}} QPushButton:hover{{color:#e6edf3;}}")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        v.addLayout(btn_row)

    def _save(self):
        self.entry["setup"] = self._setup_cb.currentText()
        self.entry["grade"] = self._grade_cb.currentText()
        self.entry["notes"] = self._notes.toPlainText()
        add_journal_entry(self.entry)
        self.accept()


class TradeJournalPage(QWidget):
    """Main journal page shown as dashboard tab."""

    def __init__(self, api):
        super().__init__()
        self.api = api
        self._entries = []
        self._build()
        QTimer.singleShot(500, self._refresh)
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(10000)  # refresh every 10s

    def _build(self):
        v = QVBoxLayout(self); v.setContentsMargins(0,0,0,0); v.setSpacing(0)

        # Header
        hdr = QWidget(); hdr.setFixedHeight(52)
        hdr.setStyleSheet(f"background:{BG2};border-bottom:1px solid #30363d;")
        hh = QHBoxLayout(hdr); hh.setContentsMargins(16,0,16,0)
        title = QLabel("📓  Trade Journal")
        title.setStyleSheet(f"color:{BLUE};font-size:15px;font-weight:bold;")
        hh.addWidget(title); hh.addStretch()

        # Stats in header
        self._total_lbl  = QLabel(""); self._total_lbl.setStyleSheet(f"color:{DIM};font-size:11px;")
        self._winrate_lbl= QLabel(""); self._winrate_lbl.setStyleSheet(f"color:{DIM};font-size:11px;")
        self._pnl_lbl    = QLabel(""); self._pnl_lbl.setStyleSheet(f"color:{DIM};font-size:11px;")
        hh.addWidget(self._total_lbl)
        hh.addWidget(QLabel(" | "))
        hh.addWidget(self._winrate_lbl)
        hh.addWidget(QLabel(" | "))
        hh.addWidget(self._pnl_lbl)
        v.addWidget(hdr)

        # Filter bar
        fbar = QWidget(); fbar.setFixedHeight(44)
        fbar.setStyleSheet(f"background:{BG3};border-bottom:1px solid #30363d;")
        fh = QHBoxLayout(fbar); fh.setContentsMargins(12,6,12,6); fh.setSpacing(8)

        fh.addWidget(QLabel("Filter:"))
        self._filter_setup = QComboBox()
        self._filter_setup.addItems(["All Setups"] + SETUP_TAGS)
        self._filter_setup.setFixedHeight(30)
        self._filter_setup.setStyleSheet(f"QComboBox{{background:{BG};color:#e6edf3;border:1px solid #30363d;border-radius:3px;padding:3px 6px;font-size:11px;}} QComboBox QAbstractItemView{{background:{BG2};color:#e6edf3;selection-background-color:#1f6feb;}}")
        self._filter_setup.currentTextChanged.connect(self._apply_filter)
        fh.addWidget(self._filter_setup)

        self._filter_grade = QComboBox()
        self._filter_grade.addItems(["All Grades"] + GRADES)
        self._filter_grade.setFixedHeight(30)
        self._filter_grade.setStyleSheet(self._filter_setup.styleSheet())
        self._filter_grade.currentTextChanged.connect(self._apply_filter)
        fh.addWidget(self._filter_grade)

        self._filter_side = QComboBox()
        self._filter_side.addItems(["All", "LONG", "SHORT"])
        self._filter_side.setFixedHeight(30)
        self._filter_side.setStyleSheet(self._filter_setup.styleSheet())
        self._filter_side.currentTextChanged.connect(self._apply_filter)
        fh.addWidget(self._filter_side)

        fh.addWidget(QLabel("Period:"))
        self._date_filter = QComboBox()
        self._date_filter.addItems([
            "All Time", "Today", "Yesterday", "This Week",
            "Last 7 Days", "Last Week", "This Month", "Last Month", "Custom Date"
        ])
        self._date_filter.setCurrentText("Today")
        self._date_filter.setFixedHeight(30)
        self._date_filter.setFixedWidth(120)
        self._date_filter.setStyleSheet(f"QComboBox{{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:3px;padding:3px 6px;font-size:11px;}} QComboBox QAbstractItemView{{background:#161b22;color:#e6edf3;selection-background-color:#1f6feb;}}")
        self._date_filter.currentTextChanged.connect(self._apply_filter)
        fh.addWidget(self._date_filter)

        fh.addStretch()

        sync_btn = QPushButton("⟳  Sync Fills")
        sync_btn.setFixedHeight(30)
        sync_btn.setStyleSheet(f"QPushButton{{background:#1f6feb;color:#fff;border:none;border-radius:4px;font-size:11px;font-weight:bold;padding:0 12px;}} QPushButton:hover{{background:#388bfd;}}")
        sync_btn.clicked.connect(self._sync_fills)
        fh.addWidget(sync_btn)
        v.addWidget(fbar)

        # Table
        cols = ["Date","Symbol","Side","Qty","Entry $","Exit $","P&L","P&L %","Entry Time","Exit Time","Setup","Grade","Notes"]
        self._table = QTableWidget(0, len(cols))
        self._table.setHorizontalHeaderLabels(cols)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(True)
        self._table.setStyleSheet(TABLE_STYLE)
        hdr2 = self._table.horizontalHeader()
        for i in range(len(cols)):
            hdr2.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self._table.doubleClicked.connect(self._on_double_click)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_rclick)
        v.addWidget(self._table, stretch=1)

        # Status
        self._status = QLabel("  Loading…")
        self._status.setFixedHeight(22)
        self._status.setStyleSheet(f"color:{DIM};font-size:10px;background:{BG3};border-top:1px solid #30363d;padding:0 8px;")
        v.addWidget(self._status)

    def _refresh(self):
        self._entries = load_journal()
        self._apply_filter()

    def _sync_fills(self):
        """Pull fills from Schwab and add any new ones to journal."""
        import threading
        def fetch():
            try:
                from datetime import datetime, timedelta
                from_d = (datetime.now()-timedelta(days=364)).strftime("%Y-%m-%dT00:00:00Z")
                to_d   = datetime.now().strftime("%Y-%m-%dT23:59:59Z")
                orders = self.api.get_orders(from_date=from_d, to_date=to_d) or []
                fills = [o for o in orders if o.get("status") in ("FILLED","PART_FILLED")]

                # Sort fills by time so we can pair entries and exits
                def get_fill_time(o):
                    return o.get("enteredTime","")
                fills.sort(key=get_fill_time)

                def get_fill_price(o):
                    activities = o.get("orderActivityCollection",[])
                    if activities:
                        exec_legs = activities[0].get("executionLegs",[])
                        if exec_legs:
                            return float(exec_legs[0].get("price",0) or 0)
                    return float(o.get("price",0) or 0)

                # Group by symbol — match entries to exits
                # Entry instructions: BUY, BUY_TO_OPEN, BUY_TO_COVER
                # Exit instructions:  SELL, SELL_TO_CLOSE, SELL_SHORT
                ENTRY_INSTRS = {"BUY","BUY_TO_OPEN","BUY_TO_COVER"}
                EXIT_INSTRS  = {"SELL","SELL_TO_CLOSE","SELL_SHORT","BUY_TO_CLOSE"}

                # Build list of (sym, instr, price, qty, time, oid, asset)
                fill_records = []
                for o in fills:
                    legs  = o.get("orderLegCollection",[{}])
                    inst  = legs[0].get("instrument",{}) if legs else {}
                    sym   = inst.get("symbol","—")
                    instr = (legs[0].get("instruction","") if legs else "").upper()
                    qty   = int(float(o.get("filledQuantity") or o.get("quantity") or 0))
                    price = get_fill_price(o)
                    entered = o.get("enteredTime","")
                    oid   = str(o.get("orderId",""))
                    asset = inst.get("assetType","EQUITY")
                    fill_records.append({
                        "sym":sym,"instr":instr,"price":price,
                        "qty":qty,"time":entered,"oid":oid,"asset":asset
                    })

                # Pair entries with exits by symbol
                existing_ids = {e.get("trade_id","") for e in load_journal()}
                new_count = 0

                # Track open positions per symbol for pairing
                open_trades = {}  # sym -> list of entry records

                for rec in fill_records:
                    sym   = rec["sym"]
                    instr = rec["instr"]
                    oid   = rec["oid"]

                    if instr in ENTRY_INSTRS:
                        # Opening trade
                        if sym not in open_trades:
                            open_trades[sym] = []
                        open_trades[sym].append(rec)
                        # Add as open entry if not already in journal
                        if oid not in existing_ids:
                            entry = {
                                "trade_id":    oid,
                                "date":        to_mt_date(rec["time"]),
                                "symbol":      sym,
                                "side":        "LONG" if "BUY" in instr else "SHORT",
                                "instruction": instr,
                                "qty":         rec["qty"],
                                "entry_price": rec["price"],
                                "exit_price":  0,
                                "pnl":         0,
                                "pnl_pct":     0,
                                "entry_time":  to_mt(rec["time"]),
                                "exit_time":   "",
                                "setup":       "",
                                "grade":       "",
                                "notes":       "",
                                "screenshot":  "",
                                "asset_type":  rec["asset"],
                            }
                            add_journal_entry(entry)
                            existing_ids.add(oid)
                            new_count += 1

                    elif instr in EXIT_INSTRS:
                        # Closing trade — match to oldest open entry for this symbol
                        open_list = open_trades.get(sym, [])
                        if open_list:
                            matched = open_list.pop(0)
                            entry_price = matched["price"]
                            exit_price  = rec["price"]
                            qty         = matched["qty"]
                            is_long = "BUY" in matched["instr"]

                            # Calculate P&L safely
                            try:
                                if is_long:
                                    pnl = (exit_price - entry_price) * qty
                                else:
                                    pnl = (entry_price - exit_price) * qty
                                if matched["asset"] == "OPTION":
                                    pnl *= 100
                                denom = entry_price * max(qty, 1)
                                if matched["asset"] == "OPTION":
                                    denom *= 100
                                pnl_pct = (pnl / denom) * 100 if denom != 0 else 0
                            except:
                                pnl = 0.0
                                pnl_pct = 0.0

                            # Update the matched entry with exit info
                            existing = get_entry_by_id(matched["oid"])
                            if existing:
                                existing["exit_price"] = exit_price
                                existing["exit_time"]  = to_mt(rec["time"])
                                existing["pnl"]        = round(pnl, 2)
                                existing["pnl_pct"]    = round(pnl_pct, 2)
                                add_journal_entry(existing)
                        else:
                            # No matching open — log as standalone exit
                            if oid not in existing_ids:
                                entry = {
                                    "trade_id":    oid,
                                    "date":        to_mt_date(rec["time"]),
                                    "symbol":      sym,
                                    "side":        "SHORT" if "BUY" in instr else "LONG",
                                    "instruction": instr,
                                    "qty":         rec["qty"],
                                    "entry_price": 0,
                                    "exit_price":  rec["price"],
                                    "pnl":         0,
                                    "pnl_pct":     0,
                                    "entry_time":  "",
                                    "exit_time":   to_mt(rec["time"]),
                                    "setup":       "",
                                    "grade":       "",
                                    "notes":       "",
                                    "screenshot":  "",
                                    "asset_type":  rec["asset"],
                                }
                                add_journal_entry(entry)
                                existing_ids.add(oid)
                                new_count += 1

                self._status.setText(f"  Synced — {new_count} new trades  |  {len(fills)} total fills")
                self._refresh()
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                print(f"[Journal] Sync error:\n{tb}")
                self._status.setText(f"  Sync error: {e}")
        threading.Thread(target=fetch, daemon=True).start()

    def _apply_filter(self):
        from datetime import datetime, timedelta
        setup_f  = self._filter_setup.currentText()
        grade_f  = self._filter_grade.currentText()
        side_f   = self._filter_side.currentText()
        period_f = self._date_filter.currentText() if hasattr(self,'_date_filter') else "All Time"

        filtered = self._entries

        if setup_f != "All Setups":
            filtered = [e for e in filtered if e.get("setup") == setup_f]
        if grade_f != "All Grades":
            filtered = [e for e in filtered if e.get("grade") == grade_f]
        if side_f != "All":
            filtered = [e for e in filtered if e.get("side","").upper() == side_f]

        # Date filter
        if period_f != "All Time":
            now = datetime.now()
            today = now.replace(hour=0,minute=0,second=0,microsecond=0)
            if period_f == "Today":
                from_d = today
            elif period_f == "Yesterday":
                from_d = today - timedelta(days=1)
                now = today - timedelta(seconds=1)
            elif period_f == "This Week":
                from_d = today - timedelta(days=today.weekday())
            elif period_f == "Last 7 Days":
                from_d = today - timedelta(days=7)
            elif period_f == "Last Week":
                week_start = today - timedelta(days=today.weekday())
                from_d = week_start - timedelta(weeks=1)
                now = week_start - timedelta(seconds=1)
            elif period_f == "This Month":
                from_d = today.replace(day=1)
            elif period_f == "Last Month":
                first_this = today.replace(day=1)
                from_d = (first_this - timedelta(days=1)).replace(day=1)
                now = first_this - timedelta(seconds=1)
            else:
                from_d = today - timedelta(days=365)

            def in_range(e):
                date_str = e.get("date","")
                try:
                    d = datetime.strptime(date_str, "%m/%d/%Y")
                    return from_d <= d <= now
                except: return True

            filtered = [e for e in filtered if in_range(e)]

        # Only show opening trades — hide closing instructions
        CLOSE_INSTRS = {"SELL_TO_CLOSE","BUY_TO_CLOSE","SELL","SELL_SHORT"}
        filtered = [e for e in filtered
                    if e.get("instruction","").upper() not in CLOSE_INSTRS
                    and float(e.get("entry_price",0) or 0) > 0]
        self._populate(filtered)

    def _populate(self, entries: list):
        self._table.setRowCount(0)

        total_pnl = 0; wins = 0; losses = 0

        for e in entries:
            pnl   = float(e.get("pnl",0) or 0)
            pnl_p = float(e.get("pnl_pct",0) or 0)
            side  = e.get("side","—")
            total_pnl += pnl
            if pnl > 0: wins += 1
            elif pnl < 0: losses += 1

            row = self._table.rowCount(); self._table.insertRow(row)
            self._table.setRowHeight(row, 24)

            sc = GREEN if side == "LONG" else RED
            pc = GREEN if pnl >= 0 else RED
            sign = "+" if pnl >= 0 else ""

            def ci(text, color="#e6edf3"):
                item = QTableWidgetItem(str(text))
                item.setForeground(QColor(color))
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, e.get("trade_id",""))
                return item

            ep = e.get("entry_price",0)
            xp = e.get("exit_price",0)

            self._table.setItem(row,0,  ci(e.get("date","—"), DIM))
            raw_sym = e.get("symbol","—")
            disp_sym = format_option_symbol(raw_sym) if len(raw_sym) > 6 else raw_sym
            self._table.setItem(row,1,  ci(disp_sym, BLUE))
            self._table.setItem(row,2,  ci(side, sc))
            self._table.setItem(row,3,  ci(str(e.get("qty","—"))))
            self._table.setItem(row,4,  ci(f"${float(ep):.2f}" if ep else "—"))
            self._table.setItem(row,5,  ci(f"${float(xp):.2f}" if xp else "Open"))
            self._table.setItem(row,6,  ci(f"{sign}${abs(pnl):.2f}" if pnl else "—", pc))
            self._table.setItem(row,7,  ci(f"{sign}{abs(pnl_p):.1f}%" if pnl_p else "—", pc))
            self._table.setItem(row,8,  ci(e.get("entry_time","—"), DIM))
            self._table.setItem(row,9,  ci(e.get("exit_time","Open"), DIM))
            self._table.setItem(row,10, ci(e.get("setup","—"), DIM))
            self._table.setItem(row,11, ci(e.get("grade","—"), YELLOW))
            self._table.setItem(row,12, ci(e.get("notes","")[:40], DIM))

        total = len(entries)
        wr    = wins/total*100 if total > 0 else 0
        tsign = "+" if total_pnl >= 0 else ""
        tc    = GREEN if total_pnl >= 0 else RED

        self._total_lbl.setText(f"Trades: {total}")
        self._winrate_lbl.setText(f"Win Rate: {wr:.0f}%")
        self._pnl_lbl.setText(f"Total P&L: {tsign}${total_pnl:,.2f}")
        self._pnl_lbl.setStyleSheet(f"color:{tc};font-size:11px;font-weight:bold;")
        setup_table(self._table)
        self._status.setText(f"  {total} trades  |  {wins}W {losses}L  |  Updated {__import__('datetime').datetime.now().strftime('%H:%M:%S')}")

    def _on_double_click(self, index):
        row = index.row()
        item = self._table.item(row, 0)
        if not item: return
        trade_id = item.data(Qt.ItemDataRole.UserRole)
        entry = get_entry_by_id(trade_id)
        if entry:
            dlg = TradeDetailDialog(self, entry)
            dlg.exec()
            self._refresh()

    def _on_rclick(self, pos):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor
        row = self._table.rowAt(pos.y())
        if row < 0: return
        item = self._table.item(row, 0)
        if not item: return
        trade_id = item.data(Qt.ItemDataRole.UserRole)

        menu = QMenu(self)
        menu.setStyleSheet(f"QMenu{{background:{BG2};border:1px solid #30363d;color:#e6edf3;font-size:12px;padding:4px;}} QMenu::item{{padding:8px 20px;}} QMenu::item:selected{{background:#1f6feb;}}")
        edit_a   = menu.addAction("✏️  Edit / View")
        delete_a = menu.addAction("🗑️  Delete Entry")
        edit_a.triggered.connect(lambda: self._edit_entry(trade_id))
        delete_a.triggered.connect(lambda: self._delete_entry(trade_id))
        menu.exec(QCursor.pos())

    def _edit_entry(self, trade_id):
        entry = get_entry_by_id(trade_id)
        if entry:
            dlg = TradeDetailDialog(self, entry)
            dlg.exec()
            self._refresh()

    def _delete_entry(self, trade_id):
        entries = load_journal()
        entries = [e for e in entries if e.get("trade_id") != trade_id]
        save_journal(entries)
        self._refresh()

    def on_show(self):
        self._refresh()


def take_screenshot(webview_widget, trade_id: str, symbol: str) -> str:
    """
    Take a screenshot of the TradingView WebEngine widget.
    Returns path to saved screenshot.
    """
    try:
        ss_dir = os.path.join(os.path.expanduser("~"), ".alphadesk_screenshots")
        os.makedirs(ss_dir, exist_ok=True)
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(ss_dir, f"{symbol}_{ts}_{trade_id[:8]}.png")
        px = webview_widget.grab()
        px.save(path, "PNG")
        print(f"[Journal] Screenshot saved: {path}")
        return path
    except Exception as e:
        print(f"[Journal] Screenshot error: {e}")
        return ""