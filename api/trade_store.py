"""
Trade execution store — singleton that holds all placed trades
so the chart can plot them as markers.
"""

from datetime import datetime


class TradeStore:
    """Singleton store of trade executions for chart markers."""
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._trades = []
            cls._instance._listeners = []
        return cls._instance

    def add_trade(self, symbol: str, side: str, price: float,
                   qty: int, order_type: str = "LIMIT"):
        """
        side: BUY or SELL (or BUY_TO_OPEN etc — normalized to BUY/SELL)
        """
        normalized = "BUY" if "BUY" in side.upper() else "SELL"
        # For options, extract underlying symbol
        underlying = symbol.split()[0].split("_")[0]

        trade = {
            "symbol":     symbol,
            "underlying": underlying,
            "side":       normalized,
            "price":      price,
            "qty":        qty,
            "order_type": order_type,
            "time":       datetime.now().isoformat(),
            "dt":         datetime.now(),
        }
        self._trades.append(trade)
        for cb in self._listeners:
            try: cb(trade)
            except: pass

    def get_trades(self, symbol: str) -> list:
        """Get all trades for a symbol or its underlying."""
        sym = symbol.upper().split()[0]
        return [t for t in self._trades
                if t["underlying"].upper() == sym or t["symbol"].upper() == sym]

    def add_listener(self, callback):
        self._listeners.append(callback)

    def remove_listener(self, callback):
        try: self._listeners.remove(callback)
        except: pass

    def clear(self):
        self._trades.clear()


# Global instance
trade_store = TradeStore()
