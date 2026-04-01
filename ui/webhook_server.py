"""
AlphaDesk Webhook Server v14
- Listens on port 80 (HTTP) — TradingView compatible
- Receives alerts and places orders through Schwab
- Supports entry + stop loss + take profit
- Emits signals to UI for live logging
Run AlphaDesk as Administrator on Windows for port 80
"""

import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime

from PyQt6.QtCore import QObject, pyqtSignal


class WebhookSignals(QObject):
    """Signals to safely communicate from webhook thread to UI."""
    alert_received  = pyqtSignal(dict)   # raw alert data
    order_placed    = pyqtSignal(dict)   # order result
    error_occurred  = pyqtSignal(str)    # error message
    server_started  = pyqtSignal(int)    # port number
    server_stopped  = pyqtSignal()


# Global signals instance — shared between server and UI
webhook_signals = WebhookSignals()


class AlertHandler(BaseHTTPRequestHandler):
    """HTTP request handler for TradingView webhooks."""

    api = None  # set before starting server

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length).decode("utf-8")
            data   = json.loads(body)

            # Acknowledge to TradingView immediately
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')

            # Process in background so we don't block
            threading.Thread(
                target=self._process_alert,
                args=(data,),
                daemon=True
            ).start()

        except Exception as e:
            self.send_response(400)
            self.end_headers()
            webhook_signals.error_occurred.emit(f"Webhook parse error: {e}")

    def do_GET(self):
        """Health check endpoint."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"AlphaDesk Webhook Server Running")

    def _process_alert(self, data: dict):
        """Process incoming TradingView alert and place orders."""
        timestamp = datetime.now().strftime("%H:%M:%S %m/%d/%Y")
        data["_received_at"] = timestamp
        webhook_signals.alert_received.emit(data)

        if not self.api:
            webhook_signals.error_occurred.emit("No API connected")
            return

        try:
            symbol     = str(data.get("symbol", "")).upper().strip()
            side       = str(data.get("side", "BUY")).upper().strip()
            qty        = int(float(data.get("qty", 1)))
            order_type = str(data.get("type", "MARKET")).upper().strip()
            price      = float(data.get("price", 0) or 0)
            stop_loss  = float(data.get("stop_loss", 0) or 0)
            take_profit= float(data.get("take_profit", 0) or 0)
            session    = str(data.get("session", "NORMAL")).upper()
            duration   = str(data.get("duration", "DAY")).upper()
            asset_type = str(data.get("type", "EQUITY")).upper()

            if not symbol:
                webhook_signals.error_occurred.emit("Alert missing symbol")
                return

            # Handle option orders
            if asset_type == "OPTION" or data.get("call_put"):
                self._place_option_order(data, symbol, side, qty, price,
                                         stop_loss, session, duration)
                return

            # ── ENTRY ORDER ──────────────────────────────────
            lp = price if order_type in ("LIMIT","STOP_LIMIT") else None
            sp = price if order_type == "STOP" else None

            entry_order = self.api.build_stock_order(
                symbol, qty, side, order_type, lp, sp,
                session=session, duration=duration
            )
            ok, msg = self.api.place_order(entry_order)

            result = {
                "symbol":    symbol,
                "side":      side,
                "qty":       qty,
                "type":      order_type,
                "price":     price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "entry_ok":  ok,
                "entry_msg": msg,
                "timestamp": timestamp,
                "sl_ok":     None,
                "tp_ok":     None,
            }

            if not ok:
                result["error"] = msg
                webhook_signals.order_placed.emit(result)
                webhook_signals.error_occurred.emit(f"Entry rejected: {msg}")
                return

            # ── STOP LOSS ─────────────────────────────────────
            if stop_loss > 0:
                close_side = "SELL" if side == "BUY" else "BUY"
                sl_order = self.api.build_stock_order(
                    symbol, qty, close_side, "STOP",
                    None, stop_loss,
                    session=session, duration="GTC"
                )
                sl_ok, sl_msg = self.api.place_order(sl_order)
                result["sl_ok"]  = sl_ok
                result["sl_msg"] = sl_msg

            # ── TAKE PROFIT ───────────────────────────────────
            if take_profit > 0:
                close_side = "SELL" if side == "BUY" else "BUY"
                tp_order = self.api.build_stock_order(
                    symbol, qty, close_side, "LIMIT",
                    take_profit, None,
                    session=session, duration="GTC"
                )
                tp_ok, tp_msg = self.api.place_order(tp_order)
                result["tp_ok"]  = tp_ok
                result["tp_msg"] = tp_msg

            webhook_signals.order_placed.emit(result)

        except Exception as e:
            webhook_signals.error_occurred.emit(f"Alert processing error: {e}")

    def _place_option_order(self, data, symbol, side, qty, price,
                             stop_loss, session, duration):
        """Place an options order from webhook."""
        try:
            expiry   = str(data.get("expiry",""))
            strike   = float(data.get("strike", 0))
            call_put = str(data.get("call_put","CALL")).upper()
            instr    = str(data.get("instruction","BUY_TO_OPEN")).upper()

            # Build OCC symbol
            from datetime import datetime as dt
            d = dt.strptime(expiry, "%Y-%m-%d")
            date_part = d.strftime("%y%m%d")
            cp = "C" if call_put == "CALL" else "P"
            sym_padded = symbol.ljust(6)
            strike_int = int(round(strike * 1000))
            occ_sym = f"{sym_padded}{date_part}{cp}{strike_int:08d}"

            order = {
                "orderType": "LIMIT" if price > 0 else "MARKET",
                "session":   session,
                "duration":  duration,
                "orderStrategyType": "SINGLE",
                "orderLegCollection": [{
                    "instruction": instr,
                    "quantity": qty,
                    "instrument": {"symbol": occ_sym, "assetType": "OPTION"}
                }]
            }
            if price > 0:
                order["price"] = str(round(price, 2))

            ok, msg = self.api.place_order(order)
            result = {
                "symbol": occ_sym, "side": instr, "qty": qty,
                "type": "OPTION", "price": price,
                "stop_loss": stop_loss,
                "entry_ok": ok, "entry_msg": msg,
                "timestamp": data.get("_received_at",""),
            }

            # Option stop loss
            if stop_loss > 0 and ok:
                close_instr = "SELL_TO_CLOSE" if "BUY" in instr else "BUY_TO_CLOSE"
                sl_order = {
                    "orderType": "STOP",
                    "session": session, "duration": "GTC",
                    "orderStrategyType": "SINGLE",
                    "stopPrice": str(round(stop_loss, 2)),
                    "orderLegCollection": [{
                        "instruction": close_instr,
                        "quantity": qty,
                        "instrument": {"symbol": occ_sym, "assetType": "OPTION"}
                    }]
                }
                sl_ok, sl_msg = self.api.place_order(sl_order)
                result["sl_ok"] = sl_ok; result["sl_msg"] = sl_msg

            webhook_signals.order_placed.emit(result)

        except Exception as e:
            webhook_signals.error_occurred.emit(f"Option webhook error: {e}")

    def log_message(self, format, *args):
        pass  # suppress default HTTP server logging


class WebhookServer:
    """Manages the HTTP server lifecycle."""

    def __init__(self):
        self._server   = None
        self._thread   = None
        self._running  = False
        self._port     = 80
        self.api       = None

    def start(self, port: int = 80):
        if self._running:
            return True, f"Already running on port {port}"
        self._port = port
        AlertHandler.api = self.api
        try:
            self._server = HTTPServer(("", port), AlertHandler)
            self._thread = threading.Thread(
                target=self._server.serve_forever,
                daemon=True
            )
            self._thread.start()
            self._running = True
            webhook_signals.server_started.emit(port)
            return True, f"Webhook server started on port {port}"
        except PermissionError:
            return False, (f"Port {port} requires Administrator privileges.\n"
                           f"Right-click AlphaDesk and Run as Administrator,\n"
                           f"or use port 8080 (requires ngrok).")
        except OSError as e:
            return False, f"Port {port} error: {e}"

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._running = False
        webhook_signals.server_stopped.emit()

    def is_running(self):
        return self._running

    def get_port(self):
        return self._port


# Global server instance
webhook_server = WebhookServer()
