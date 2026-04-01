"""
Chart Stamps v16
- Draws horizontal arrows on TradingView chart at entry/exit times
- Green arrow for entry, Red arrow for exit
- Auto screenshot on exit (STC/BTC only)
- Works for equities and options (uses underlying ticker)
"""

import os
import json
import threading
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from PyQt6.QtWidgets import QWidget

GREEN_COLOR = "#00ff88"
RED_COLOR   = "#ff4444"


class ChartStampManager(QObject):
    """
    Manages entry/exit stamps on the embedded TradingView chart.
    Injects JavaScript arrows at the correct price/time.
    """
    screenshot_ready = pyqtSignal(str, str)  # trade_id, screenshot_path

    def __init__(self, webview=None):
        super().__init__()
        self._webview    = webview
        self._open_trades = {}  # trade_id -> {symbol, entry_time, entry_price, side}

    def set_webview(self, webview):
        self._webview = webview

    def _get_underlying(self, symbol: str) -> str:
        """Extract underlying ticker from OCC option symbol or return as-is."""
        sym = symbol.strip().upper()
        # OCC format: SPY   260326C00500000 (6 char padded symbol)
        if len(sym) > 6 and any(c.isdigit() for c in sym):
            return sym[:6].strip()
        return sym

    def on_entry_fill(self, trade_id: str, symbol: str, instruction: str,
                       price: float, qty: int):
        """Called when an entry order fills. Stamps green arrow on chart."""
        underlying = self._get_underlying(symbol)
        now = datetime.now()
        time_str = now.strftime("%H:%M")

        self._open_trades[trade_id] = {
            "symbol":      symbol,
            "underlying":  underlying,
            "entry_time":  now.isoformat(),
            "entry_price": price,
            "instruction": instruction,
            "qty":         qty,
        }

        self._stamp_arrow(
            price=price,
            time_str=time_str,
            color=GREEN_COLOR,
            label=f"▶ {instruction.replace('_',' ')} {qty}x @ ${price:.2f}",
            trade_id=trade_id
        )
        print(f"[ChartStamp] Entry stamp: {underlying} @ ${price:.2f} {time_str}")

    def on_exit_fill(self, trade_id: str, symbol: str, instruction: str,
                      price: float, qty: int):
        """
        Called when an exit order fills (STC or BTC only).
        Stamps red arrow and takes screenshot.
        """
        # Only screenshot on close instructions
        close_instrs = {"SELL_TO_CLOSE","BUY_TO_CLOSE","SELL","BUY_TO_COVER"}
        if instruction.upper() not in close_instrs:
            return

        underlying = self._get_underlying(symbol)
        now = datetime.now()
        time_str = now.strftime("%H:%M")

        self._stamp_arrow(
            price=price,
            time_str=time_str,
            color=RED_COLOR,
            label=f"◀ {instruction.replace('_',' ')} {qty}x @ ${price:.2f}",
            trade_id=trade_id
        )
        print(f"[ChartStamp] Exit stamp: {underlying} @ ${price:.2f} {time_str}")

        # Take screenshot after short delay so arrow renders
        QTimer.singleShot(800, lambda: self._take_screenshot(trade_id))

    def _stamp_arrow(self, price: float, time_str: str, color: str,
                      label: str, trade_id: str):
        """Inject JavaScript to draw a horizontal arrow on the TradingView chart."""
        if not self._webview: return

        js = f"""
        (function() {{
            try {{
                // Store stamp data for rendering
                if (!window._alphadeskStamps) window._alphadeskStamps = [];
                window._alphadeskStamps.push({{
                    price: {price},
                    time: '{time_str}',
                    color: '{color}',
                    label: '{label}',
                    id: '{trade_id}'
                }});

                // Create overlay div if not exists
                if (!document.getElementById('alphadesk-overlay')) {{
                    var overlay = document.createElement('div');
                    overlay.id = 'alphadesk-overlay';
                    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:9999;';
                    document.body.appendChild(overlay);
                }}

                // Draw arrow marker
                var overlay = document.getElementById('alphadesk-overlay');
                var marker = document.createElement('div');
                marker.style.cssText = `
                    position: absolute;
                    left: 10px;
                    top: 50%;
                    transform: translateY(-50%);
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    pointer-events: none;
                `;

                var arrow = document.createElement('div');
                arrow.style.cssText = `
                    width: 0;
                    height: 0;
                    border-top: 8px solid transparent;
                    border-bottom: 8px solid transparent;
                    border-left: 14px solid {color};
                `;

                var lbl = document.createElement('div');
                lbl.style.cssText = `
                    background: {color}22;
                    border: 1px solid {color};
                    color: {color};
                    font-family: Consolas, monospace;
                    font-size: 11px;
                    padding: 2px 8px;
                    border-radius: 3px;
                    white-space: nowrap;
                `;
                lbl.textContent = '{label}  {time_str}';

                marker.appendChild(arrow);
                marker.appendChild(lbl);
                overlay.appendChild(marker);

                // Auto-remove after 30 seconds
                setTimeout(function() {{
                    if (marker.parentNode) marker.parentNode.removeChild(marker);
                }}, 30000);

            }} catch(e) {{
                console.log('AlphaDesk stamp error:', e);
            }}
        }})();
        """
        self._webview.page().runJavaScript(js)

    def _take_screenshot(self, trade_id: str):
        """Take screenshot of the WebEngine view."""
        if not self._webview: return
        from ui.trade_journal import take_screenshot
        open_info = self._open_trades.get(trade_id, {})
        sym = open_info.get("underlying", "trade")
        path = take_screenshot(self._webview, trade_id, sym)
        if path:
            self.screenshot_ready.emit(trade_id, path)
            # Update journal entry with screenshot
            from ui.trade_journal import get_entry_by_id, add_journal_entry
            entry = get_entry_by_id(trade_id)
            if entry:
                entry["screenshot"] = path
                add_journal_entry(entry)
        # Clean up open trade
        self._open_trades.pop(trade_id, None)

    def clear_stamps(self):
        """Clear all stamps from the overlay."""
        if not self._webview: return
        js = """
        var overlay = document.getElementById('alphadesk-overlay');
        if (overlay) overlay.innerHTML = '';
        """
        self._webview.page().runJavaScript(js)


# Global instance
chart_stamp_manager = ChartStampManager()
