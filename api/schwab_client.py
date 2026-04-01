"""
Schwab API Client v5
- OAuth 2.0 with auto token refresh
- Price history for charts
- Full order support including pre/after market sessions
- Paper trading account support
"""

import requests
import json
import os
import time
import base64
from datetime import datetime, timedelta
from urllib.parse import urlencode

SCHWAB_AUTH_URL   = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL  = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_BASE_URL   = "https://api.schwabapi.com/trader/v1"
SCHWAB_MARKET_URL = "https://api.schwabapi.com/marketdata/v1"
REDIRECT_URI      = "https://127.0.0.1"


class SchwabAPI:
    def __init__(self, app_key: str, app_secret: str,
                 token_path: str = "config/tokens.json"):
        self.app_key      = app_key
        self.app_secret   = app_secret
        self.token_path   = token_path
        self.access_token  = None
        self.refresh_token = None
        self.token_expiry  = 0
        self.account_hash  = None
        self._paper_hash   = None   # paper trading account hash
        self._use_paper    = False
        self._all_accounts = []
        self._load_tokens()

    # ── AUTH ─────────────────────────────────────────────────────────────────

    def _load_tokens(self):
        if os.path.exists(self.token_path):
            try:
                with open(self.token_path) as f:
                    data = json.load(f)
                self.access_token  = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                self.token_expiry  = data.get("expiry", 0)
                self.account_hash  = data.get("account_hash")
                self._paper_hash   = data.get("paper_hash")
            except Exception:
                pass

    def _save_tokens(self):
        os.makedirs(os.path.dirname(self.token_path), exist_ok=True)
        with open(self.token_path, "w") as f:
            json.dump({
                "access_token":  self.access_token,
                "refresh_token": self.refresh_token,
                "expiry":        self.token_expiry,
                "account_hash":  self.account_hash,
                "paper_hash":    self._paper_hash,
            }, f)

    def is_authenticated(self) -> bool:
        return bool(self.access_token)

    def needs_refresh(self) -> bool:
        return time.time() > self.token_expiry - 60

    def refresh_access_token(self) -> bool:
        if not self.refresh_token:
            return False
        try:
            creds = base64.b64encode(
                f"{self.app_key}:{self.app_secret}".encode()).decode()
            resp = requests.post(
                SCHWAB_TOKEN_URL,
                headers={
                    "Authorization": f"Basic {creds}",
                    "Content-Type":  "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type":    "refresh_token",
                    "refresh_token": self.refresh_token,
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.access_token  = data["access_token"]
                self.refresh_token = data.get("refresh_token", self.refresh_token)
                self.token_expiry  = time.time() + data.get("expires_in", 1800)
                self._save_tokens()
                return True
        except Exception:
            pass
        return False

    def _headers(self) -> dict:
        if self.needs_refresh():
            self.refresh_access_token()
        return {"Authorization": f"Bearer {self.access_token}"}

    def _active_hash(self) -> str:
        """Return paper hash if paper mode, else live hash."""
        if self._use_paper and self._paper_hash:
            return self._paper_hash
        return self.account_hash or ""

    # ── ACCOUNTS ─────────────────────────────────────────────────────────────

    def get_accounts(self) -> list:
        try:
            resp = requests.get(
                f"{SCHWAB_BASE_URL}/accounts/accountNumbers",
                headers=self._headers(), timeout=10,
            )
            if resp.status_code == 200:
                self._all_accounts = resp.json()
                return self._all_accounts
        except Exception:
            pass
        return []

    def set_account(self, account_hash: str):
        self.account_hash = account_hash
        self._save_tokens()

    def set_paper_account(self, paper_hash: str):
        self._paper_hash = paper_hash
        self._save_tokens()

    def set_paper_mode(self, enabled: bool):
        self._use_paper = enabled

    def get_paper_mode(self) -> bool:
        return self._use_paper

    # ── PORTFOLIO ─────────────────────────────────────────────────────────────

    def get_portfolio(self) -> dict:
        h = self._active_hash()
        if not h:
            return {}
        try:
            resp = requests.get(
                f"{SCHWAB_BASE_URL}/accounts/{h}",
                headers=self._headers(),
                params={"fields": "positions"},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}

    # ── QUOTES ────────────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> dict:
        try:
            resp = requests.get(
                f"{SCHWAB_MARKET_URL}/quotes",
                headers=self._headers(),
                params={"symbols": symbol.upper(), "fields": "quote,reference"},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get(symbol.upper(), {})
        except Exception:
            pass
        return {}

    def get_quotes(self, symbols: list) -> dict:
        try:
            resp = requests.get(
                f"{SCHWAB_MARKET_URL}/quotes",
                headers=self._headers(),
                params={"symbols": ",".join(s.upper() for s in symbols),
                        "fields": "quote"},
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}

    # ── PRICE HISTORY (CHARTS) ────────────────────────────────────────────────

    def get_price_history(self, symbol: str, period_type: str = "month",
                           period: int = 1, frequency_type: str = "minute",
                           frequency: int = 5) -> dict:
        try:
            resp = requests.get(
                f"{SCHWAB_MARKET_URL}/pricehistory",
                headers=self._headers(),
                params={
                    "symbol":               symbol.upper(),
                    "periodType":           period_type,
                    "period":               period,
                    "frequencyType":        frequency_type,
                    "frequency":            frequency,
                    "needExtendedHoursData": True,
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                candles = []
                for c in data.get("candles", []):
                    from datetime import timezone
                    dt = datetime.fromtimestamp(
                        c["datetime"] / 1000, tz=timezone.utc)
                    candles.append({
                        "datetime": dt.strftime("%Y-%m-%dT%H:%M:%S"),
                        "open":   round(c.get("open",  0), 4),
                        "high":   round(c.get("high",  0), 4),
                        "low":    round(c.get("low",   0), 4),
                        "close":  round(c.get("close", 0), 4),
                        "volume": c.get("volume", 0),
                    })
                return {"candles": candles, "symbol": symbol.upper()}
        except Exception as e:
            print(f"[PriceHistory] Error: {e}")
        return {}

    # ── OPTIONS ───────────────────────────────────────────────────────────────

    def get_options_chain(self, symbol: str, expiration_date: str = None,
                           strike_count: int = 20,
                           option_type: str = "ALL") -> dict:
        try:
            params = {
                "symbol":                symbol.upper(),
                "contractType":          option_type,
                "strikeCount":           strike_count,
                "includeUnderlyingQuote": True,
                "strategy":              "SINGLE",
            }
            if expiration_date:
                params["toDate"] = expiration_date
            resp = requests.get(
                f"{SCHWAB_MARKET_URL}/chains",
                headers=self._headers(),
                params=params,
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return {}

    def get_option_expirations(self, symbol: str) -> list:
        try:
            resp = requests.get(
                f"{SCHWAB_MARKET_URL}/expirationchain",
                headers=self._headers(),
                params={"symbol": symbol.upper()},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("expirationList", [])
        except Exception:
            pass
        return []

    # ── ORDERS ────────────────────────────────────────────────────────────────

    def place_order(self, order: dict) -> tuple:
        h = self._active_hash()
        if not h:
            return False, "No account selected"
        try:
            resp = requests.post(
                f"{SCHWAB_BASE_URL}/accounts/{h}/orders",
                headers={**self._headers(),
                         "Content-Type": "application/json"},
                json=order,
                timeout=10,
            )
            if resp.status_code in (200, 201):
                order_id = resp.headers.get("Location","").split("/")[-1]
                mode = " [PAPER]" if self._use_paper else ""
                return True, f"Order placed{mode}. ID: {order_id}"
            # Parse rejection reason
            try:
                err  = resp.json()
                msg  = err.get("message", "")
                errs = err.get("errors", [])
                if errs:
                    msg = "; ".join(
                        e.get("message", str(e)) for e in errs)
                if not msg:
                    msg = resp.text
            except Exception:
                msg = resp.text
            return False, f"Order rejected ({resp.status_code}): {msg}"
        except Exception as e:
            return False, f"Network error: {e}"

    def get_orders(self, from_date: str = None, to_date: str = None,
                   status: str = None) -> list:
        """
        Fetch orders using the all-accounts endpoint so orders from
        both accounts are always returned regardless of which is active.
        """
        try:
            params = {}
            if from_date: params["fromEnteredTime"] = from_date
            if to_date:   params["toEnteredTime"]   = to_date
            if status:    params["status"]           = status

            # Use /orders (all accounts) instead of /accounts/{hash}/orders
            resp = requests.get(
                f"{SCHWAB_BASE_URL}/orders",
                headers=self._headers(),
                params=params,
                timeout=10,
            )
            if resp.status_code == 200:
                result = resp.json()
                return result if isinstance(result, list) else []
            else:
                print(f"[API] get_orders error {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            print(f"[API] get_orders exception: {e}")
        return []

    def get_working_orders(self) -> list:
        """
        Fetch all active/working orders from Schwab.
        Uses all working status values per Schwab API docs.
        """
        h = self._active_hash()
        if not h: return []
        from datetime import datetime, timedelta
        from_d = (datetime.now()-timedelta(days=1)).strftime("%Y-%m-%dT00:00:00Z")
        to_d   = datetime.now().strftime("%Y-%m-%dT23:59:59Z")

        # All statuses that mean an order is active/working per Schwab docs
        working_statuses = [
            "WORKING", "QUEUED", "ACCEPTED", "PENDING_ACTIVATION",
            "AWAITING_PARENT_ORDER", "AWAITING_CONDITION",
            "AWAITING_STOP_CONDITION", "AWAITING_MANUAL_REVIEW",
            "AWAITING_UR_OUT", "NEW", "AWAITING_RELEASE_TIME",
            "PENDING_ACKNOWLEDGEMENT"
        ]

        all_working = []
        seen_ids = set()

        for status in working_statuses:
            try:
                params = {
                    "fromEnteredTime": from_d,
                    "toEnteredTime":   to_d,
                    "status":          status
                }
                # Use /orders (all accounts endpoint)
                resp = requests.get(
                    f"{SCHWAB_BASE_URL}/orders",
                    headers=self._headers(),
                    params=params,
                    timeout=10,
                )
                if resp.status_code == 200:
                    orders = resp.json()
                    if isinstance(orders, list):
                        for o in orders:
                            oid = str(o.get("orderId",""))
                            if oid not in seen_ids:
                                seen_ids.add(oid)
                                all_working.append(o)
            except Exception as e:
                print(f"[API] get_working_orders {status} error: {e}")

        print(f"[API] Working orders total: {len(all_working)}")
        # If still 0, try the /orders endpoint which gets ALL accounts
        if len(all_working) == 0:
            try:
                from datetime import datetime, timedelta
                from_d = (datetime.now()-timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z")
                to_d   = datetime.now().strftime("%Y-%m-%dT23:59:59Z")
                # Try all-accounts endpoint
                resp = requests.get(
                    f"{SCHWAB_BASE_URL}/orders",
                    headers=self._headers(),
                    params={"fromEnteredTime": from_d, "toEnteredTime": to_d, "status": "WORKING"},
                    timeout=10,
                )
                print(f"[API] All-accounts WORKING call: status={resp.status_code}")
                if resp.status_code == 200:
                    orders = resp.json()
                    print(f"[API] All-accounts WORKING orders: {len(orders) if isinstance(orders,list) else orders}")
                    if isinstance(orders, list) and orders:
                        all_working.extend(orders)
                else:
                    print(f"[API] All-accounts error: {resp.text[:300]}")
            except Exception as e:
                print(f"[API] All-accounts error: {e}")
        return all_working

    @staticmethod
    def build_bracket_order(symbol: str, qty: int, side: str,
                             entry_price: float,
                             take_profit: float,
                             stop_loss: float,
                             entry_type: str = "LIMIT",
                             session: str = "NORMAL",
                             duration: str = "DAY",
                             asset_type: str = "EQUITY") -> dict:
        """
        Bracket order: TRIGGER + OCO
        1. Entry order (Limit/Market)
        2. On fill, triggers OCO:
           - Take Profit (Limit)
           - Stop Loss (Stop_Limit)
        """
        close_side = "SELL" if side == "BUY" else "BUY"
        stop_limit_price = round(stop_loss - 0.03, 2) if side == "BUY"                            else round(stop_loss + 0.03, 2)

        def leg(instr, sym, atype, q):
            return [{"instruction": instr, "quantity": q,
                     "instrument": {"symbol": sym.upper(), "assetType": atype}}]

        entry = {
            "orderType":         entry_type,
            "session":           session,
            "duration":          duration,
            "orderStrategyType": "TRIGGER",
            "orderLegCollection": leg(side, symbol, asset_type, qty),
            "childOrderStrategies": [
                {
                    "orderStrategyType": "OCO",
                    "childOrderStrategies": [
                        {
                            "orderType":         "LIMIT",
                            "session":           session,
                            "duration":          duration,
                            "price":             str(round(take_profit, 2)),
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": leg(close_side, symbol, asset_type, qty),
                        },
                        {
                            "orderType":         "STOP_LIMIT",
                            "session":           session,
                            "duration":          duration,
                            "price":             str(stop_limit_price),
                            "stopPrice":         str(round(stop_loss, 2)),
                            "orderStrategyType": "SINGLE",
                            "orderLegCollection": leg(close_side, symbol, asset_type, qty),
                        },
                    ],
                }
            ],
        }
        if entry_type == "LIMIT":
            entry["price"] = str(round(entry_price, 2))
        elif entry_type == "MARKET":
            pass  # no price for market
        return entry

    def cancel_order(self, order_id: str) -> tuple:
        h = self._active_hash()
        if not h:
            return False, "No account selected"
        try:
            resp = requests.delete(
                f"{SCHWAB_BASE_URL}/accounts/{h}/orders/{order_id}",
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code in (200, 204):
                return True, "Order cancelled"
            return False, f"Cancel failed: {resp.status_code}"
        except Exception as e:
            return False, f"Error: {e}"

    # ── ORDER BUILDERS ────────────────────────────────────────────────────────

    @staticmethod
    def build_stock_order(symbol: str, qty: int, side: str,
                           order_type: str,
                           limit_price: float = None,
                           stop_price: float = None,
                           trailing_amount: float = None,
                           trailing_percent: float = None,
                           session: str = "NORMAL",
                           duration: str = "DAY") -> dict:
        """
        session: NORMAL | PRE_MARKET | AFTER_HOURS | SEAMLESS
        duration: DAY | GTC | GTD | FOK
        """
        order = {
            "orderType":         order_type,
            "session":           session,
            "duration":          duration,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": side,
                "quantity":    qty,
                "instrument":  {
                    "symbol":    symbol.upper(),
                    "assetType": "EQUITY",
                },
            }],
        }
        if order_type in ("LIMIT", "STOP_LIMIT") and limit_price:
            order["price"] = str(round(limit_price, 2))
        if order_type in ("STOP", "STOP_LIMIT", "TRAILING_STOP") and stop_price:
            order["stopPrice"] = str(round(stop_price, 2))
        if order_type == "TRAILING_STOP":
            if trailing_amount:
                order["trailingStopOffset"] = trailing_amount
                order["trailingStopOffsetIsAmount"] = True
            elif trailing_percent:
                order["trailingStopOffset"] = trailing_percent
                order["trailingStopOffsetIsAmount"] = False
        return order

    @staticmethod
    def build_option_order(option_symbol: str, qty: int,
                            instruction: str, order_type: str,
                            limit_price: float = None,
                            stop_price: float = None,
                            session: str = "NORMAL",
                            duration: str = "DAY") -> dict:
        order = {
            "orderType":         order_type,
            "session":           session,
            "duration":          duration,
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": instruction,
                "quantity":    qty,
                "instrument":  {
                    "symbol":    option_symbol,
                    "assetType": "OPTION",
                },
            }],
        }
        if order_type in ("LIMIT", "STOP_LIMIT") and limit_price:
            order["price"] = str(round(limit_price, 2))
        if stop_price:
            order["stopPrice"] = str(round(stop_price, 2))
        return order

    @staticmethod
    def build_oco_order(symbol: str, qty: int, side: str,
                         take_profit_price: float,
                         stop_loss_price: float,
                         stop_limit_offset: float = 0.03,
                         session: str = "NORMAL",
                         duration: str = "DAY",
                         asset_type: str = "EQUITY") -> dict:
        """
        Schwab OCO format per API docs:
        - Child 1: LIMIT at take_profit_price
        - Child 2: STOP_LIMIT at stop_loss_price (stop) + offset (limit)
        - Both children have session + duration
        - No price on parent
        """
        close_side = "SELL" if side == "BUY" else "BUY"
        stop_limit_price = round(stop_loss_price - stop_limit_offset, 2) if side == "BUY"                            else round(stop_loss_price + stop_limit_offset, 2)

        def leg(instr):
            return [{
                "instruction": instr,
                "quantity":    qty,
                "instrument":  {"symbol": symbol.upper(), "assetType": asset_type},
            }]

        return {
            "orderStrategyType": "OCO",
            "childOrderStrategies": [
                {
                    "orderType":         "LIMIT",
                    "session":           session,
                    "duration":          duration,
                    "price":             str(round(take_profit_price, 2)),
                    "orderStrategyType": "SINGLE",
                    "orderLegCollection": leg(close_side),
                },
                {
                    "orderType":         "STOP_LIMIT",
                    "session":           session,
                    "duration":          duration,
                    "price":             str(stop_limit_price),
                    "stopPrice":         str(round(stop_loss_price, 2)),
                    "orderStrategyType": "SINGLE",
                    "orderLegCollection": leg(close_side),
                },
            ],
        }
