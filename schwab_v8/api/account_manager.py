"""
Account Manager
- Loads all accounts from Schwab
- Allows switching between accounts
- Syncs real positions from Schwab account
- Emits signals when account changes
"""

import threading
from PyQt6.QtCore import QObject, pyqtSignal, QTimer


class AccountManager(QObject):
    account_changed  = pyqtSignal(str, str)   # hash, name
    positions_updated = pyqtSignal(list)       # list of position dicts

    def __init__(self, api):
        super().__init__()
        self.api       = api
        self._accounts = []   # [{"hash": ..., "number": ..., "name": ...}]
        self._current  = None
        self._positions = []

        # Poll positions every 3 seconds
        self._pos_timer = QTimer()
        self._pos_timer.timeout.connect(self._refresh_positions)
        self._pos_timer.start(3000)

    def load_accounts(self):
        """Fetch all accounts from Schwab."""
        def fetch():
            accounts = self.api.get_accounts()
            self._accounts = []
            for i, acct in enumerate(accounts):
                num  = acct.get("accountNumber", f"Account {i+1}")
                hash_val = acct.get("hashValue", "")
                # Name heuristic — first account = Brokerage, others by type
                name = f"Account {num[-4:]}" if len(num) >= 4 else f"Account {i+1}"
                self._accounts.append({
                    "hash":   hash_val,
                    "number": num,
                    "name":   name,
                })
            # Set first account if none selected
            if self._accounts and not self._current:
                self.switch_account(self._accounts[0]["hash"])
        threading.Thread(target=fetch, daemon=True).start()

    def get_accounts(self) -> list:
        return self._accounts

    def current_hash(self) -> str:
        return self._current or ""

    def current_name(self) -> str:
        for a in self._accounts:
            if a["hash"] == self._current:
                return a["name"]
        return "Unknown"

    def switch_account(self, hash_val: str):
        self._current = hash_val
        self.api.set_account(hash_val)
        name = self.current_name()
        self.account_changed.emit(hash_val, name)
        self._refresh_positions()

    def _refresh_positions(self):
        if not self._current: return
        def fetch():
            portfolio = self.api.get_portfolio()
            acct      = portfolio.get("securitiesAccount", {})
            positions = acct.get("positions", [])
            self._positions = positions
            self.positions_updated.emit(positions)
        threading.Thread(target=fetch, daemon=True).start()

    def get_position(self, symbol: str) -> dict:
        """Get position for a specific symbol."""
        sym = symbol.upper().split()[0]
        for p in self._positions:
            inst = p.get("instrument", {})
            if inst.get("symbol", "").upper() == sym:
                return p
        return {}

    def get_net_position(self, symbol: str) -> tuple:
        """Returns (qty, avg_price) for symbol. qty negative = short."""
        p = self.get_position(symbol)
        if not p:
            return 0, 0.0
        long_qty  = p.get("longQuantity",  0)
        short_qty = p.get("shortQuantity", 0)
        avg_price = p.get("averagePrice",  0.0)
        qty = long_qty if long_qty > 0 else -short_qty
        return int(qty), float(avg_price)
