"""
Mock Schwab API — demo data including OHLCV price history for charts.
"""

import random
import time
import math
from datetime import datetime, timedelta

MOCK_PRICES = {
    "SPY":  {"last": 521.34, "bid": 521.30, "ask": 521.38, "open": 519.80, "high": 523.10, "low": 518.90, "volume": 48_230_000},
    "QQQ":  {"last": 441.22, "bid": 441.18, "ask": 441.26, "open": 439.50, "high": 443.00, "low": 438.80, "volume": 32_100_000},
    "AAPL": {"last": 213.45, "bid": 213.40, "ask": 213.50, "open": 211.80, "high": 214.20, "low": 211.00, "volume": 55_400_000},
    "MSFT": {"last": 415.78, "bid": 415.70, "ask": 415.85, "open": 413.20, "high": 417.00, "low": 412.50, "volume": 22_800_000},
    "TSLA": {"last": 248.90, "bid": 248.80, "ask": 249.00, "open": 245.00, "high": 251.30, "low": 244.50, "volume": 98_700_000},
    "NVDA": {"last": 875.22, "bid": 875.10, "ask": 875.35, "open": 868.00, "high": 880.50, "low": 866.20, "volume": 41_200_000},
    "AMZN": {"last": 191.34, "bid": 191.28, "ask": 191.40, "open": 189.80, "high": 192.50, "low": 189.20, "volume": 38_900_000},
    "META": {"last": 524.67, "bid": 524.60, "ask": 524.74, "open": 521.00, "high": 527.00, "low": 520.50, "volume": 18_600_000},
}

MOCK_POSITIONS = [
    {"symbol": "AAPL",  "assetType": "EQUITY", "qty": 50,  "avg": 195.20, "dayPnl": 87.50,  "openPnl": 911.25},
    {"symbol": "NVDA",  "assetType": "EQUITY", "qty": 10,  "avg": 820.00, "dayPnl": 52.20,  "openPnl": 552.20},
    {"symbol": "TSLA",  "assetType": "EQUITY", "qty": 30,  "avg": 262.10, "dayPnl": -98.10, "openPnl": -396.00},
    {"symbol": "SPY",   "assetType": "EQUITY", "qty": 20,  "avg": 505.00, "dayPnl": 32.80,  "openPnl": 326.80},
    {"symbol": "MSFT",  "assetType": "EQUITY", "qty": 15,  "avg": 398.50, "dayPnl": 34.20,  "openPnl": 259.20},
    {"symbol": "AAPL 250117C00220000", "assetType": "OPTION", "qty": 2, "avg": 4.50, "dayPnl": 60.00, "openPnl": 160.00},
    {"symbol": "TSLA 250117P00240000", "assetType": "OPTION", "qty": 3, "avg": 8.20, "dayPnl": -45.00, "openPnl": -120.00},
]

MOCK_ORDERS = [
    {"orderId": "1001", "symbol": "AAPL",  "instruction": "BUY",          "qty": 10, "type": "LIMIT",  "price": 210.00, "status": "FILLED",  "time": "2026-03-23T09:32:00"},
    {"orderId": "1002", "symbol": "TSLA",  "instruction": "SELL",         "qty": 5,  "type": "MARKET", "price": 248.90, "status": "FILLED",  "time": "2026-03-23T10:15:00"},
    {"orderId": "1003", "symbol": "NVDA",  "instruction": "BUY",          "qty": 2,  "type": "LIMIT",  "price": 870.00, "status": "WORKING", "time": "2026-03-23T11:02:00"},
    {"orderId": "1004", "symbol": "SPY",   "instruction": "BUY",          "qty": 5,  "type": "LIMIT",  "price": 519.00, "status": "CANCELLED","time": "2026-03-23T11:45:00"},
    {"orderId": "1005", "symbol": "AAPL 250117C00220000", "instruction": "BUY_TO_OPEN", "qty": 2, "type": "LIMIT", "price": 4.50, "status": "FILLED", "time": "2026-03-23T12:00:00"},
    {"orderId": "1006", "symbol": "MSFT",  "instruction": "BUY",          "qty": 5,  "type": "LIMIT",  "price": 413.00, "status": "WORKING", "time": "2026-03-23T13:10:00"},
]


def generate_ohlcv(symbol: str, days: int = 60, interval_minutes: int = 5) -> list:
    """Generate realistic OHLCV candlestick data."""
    base = MOCK_PRICES.get(symbol, {}).get("last", 200.0)
    candles = []
    now = datetime.now().replace(second=0, microsecond=0)

    # Start from `days` ago at market open
    start = now - timedelta(days=days)
    start = start.replace(hour=9, minute=30, second=0)

    price = base * random.uniform(0.85, 0.95)
    dt = start

    while dt <= now:
        # Skip weekends
        if dt.weekday() >= 5:
            dt += timedelta(days=1)
            continue
        # Skip outside market hours
        if dt.hour < 9 or (dt.hour == 9 and dt.minute < 30) or dt.hour >= 16:
            if dt.hour >= 16:
                dt += timedelta(hours=17, minutes=30)
                dt = dt.replace(hour=9, minute=30)
            else:
                dt += timedelta(minutes=interval_minutes)
            continue

        # Simulate price movement
        drift  = random.gauss(0.0001, 0.002)
        vol    = random.uniform(0.001, 0.004)
        change = price * (drift + random.gauss(0, vol))

        open_  = price
        close  = price + change
        high   = max(open_, close) * random.uniform(1.0, 1.003)
        low    = min(open_, close) * random.uniform(0.997, 1.0)
        volume = int(random.uniform(50_000, 500_000))

        candles.append({
            "datetime": dt.isoformat(),
            "open":   round(open_, 2),
            "high":   round(high, 2),
            "low":    round(low, 2),
            "close":  round(close, 2),
            "volume": volume,
        })
        price = close
        dt += timedelta(minutes=interval_minutes)

    return candles


class MockSchwabAPI:
    def __init__(self, *args, **kwargs):
        self.app_key     = "DEMO_KEY"
        self.app_secret  = "DEMO_SECRET"
        self.access_token  = "mock_token"
        self.refresh_token = "mock_refresh"
        self.token_expiry  = time.time() + 99999
        self.account_hash  = "DEMO_ACCOUNT"
        self._ohlcv_cache  = {}

    def is_authenticated(self): return True
    def needs_refresh(self):    return False
    def refresh_access_token(self): return True

    def get_accounts(self):
        return [{"hashValue": "DEMO_ACCOUNT", "accountNumber": "****1234"}]

    def set_account(self, account_hash): self.account_hash = account_hash
    def set_paper_account(self, h): self._paper_hash = h
    def set_paper_mode(self, e): self._use_paper = e
    def get_paper_mode(self): return getattr(self,'_use_paper',False)

    def get_portfolio(self):
        positions = []
        for p in MOCK_POSITIONS:
            sym  = p["symbol"].split()[0]
            last = MOCK_PRICES.get(sym, {}).get("last", p["avg"])
            qty  = p["qty"]
            mkt  = round(last * qty, 2)
            positions.append({
                "instrument": {"symbol": p["symbol"], "assetType": p["assetType"]},
                "longQuantity": qty,
                "averagePrice": p["avg"],
                "marketValue":  mkt,
                "currentDayProfitLoss": p["dayPnl"] + random.uniform(-5, 5),
                "currentDayProfitLossPercentage": round(p["dayPnl"] / (p["avg"] * qty) * 100, 2),
                "unrealizedProfitLoss": p["openPnl"],
            })
        total = sum(p["marketValue"] for p in positions)
        return {
            "securitiesAccount": {
                "currentBalances": {
                    "liquidationValue":        round(total + 24_850, 2),
                    "cashBalance":             24_850.00,
                    "maintenanceRequirement":  8_200.00,
                },
                "positions": positions,
            }
        }

    def get_quote(self, symbol: str) -> dict:
        sym  = symbol.upper().split()[0]
        base = MOCK_PRICES.get(sym, {"last":100,"bid":99.95,"ask":100.05,"open":99,"high":101,"low":98.5,"volume":1_000_000})
        last = round(base["last"] * random.uniform(0.998, 1.002), 2)
        chg  = round(last - base["open"], 2)
        chgp = round((chg / base["open"]) * 100, 2)
        return {"quote": {
            "lastPrice": last,
            "bidPrice":  round(last - 0.02, 2),
            "askPrice":  round(last + 0.02, 2),
            "netChange": chg,
            "netPercentChangeInDouble": chgp,
            "totalVolume": base["volume"] + random.randint(-500_000, 500_000),
            "openPrice": base["open"],
            "highPrice": base["high"],
            "lowPrice":  base["low"],
        }}

    def get_quotes(self, symbols: list) -> dict:
        return {s: self.get_quote(s) for s in symbols}

    def get_price_history(self, symbol: str, period_type: str = "month",
                           period: int = 1, frequency_type: str = "minute",
                           frequency: int = 5) -> dict:
        """Return OHLCV candle data for charting."""
        key = f"{symbol}_{period_type}_{period}_{frequency_type}_{frequency}"
        if key not in self._ohlcv_cache:
            # Map period to days
            days_map = {
                ("day",   1): (1,  1),
                ("day",   5): (5,  5),
                ("month", 1): (22, 5),
                ("month", 3): (66, 30),
                ("year",  1): (252, 60),
            }
            days, interval = days_map.get((period_type, period), (22, 5))
            self._ohlcv_cache[key] = generate_ohlcv(symbol.upper(), days=days, interval_minutes=interval)
        return {"candles": self._ohlcv_cache[key], "symbol": symbol.upper()}

    def get_options_chain(self, symbol: str, expiration_date=None,
                           strike_count=20, option_type="ALL") -> dict:
        sym        = symbol.upper()
        base_price = MOCK_PRICES.get(sym, {}).get("last", 200.0)
        strikes    = [round(base_price * (1 + (i - strike_count // 2) * 0.005), 1)
                      for i in range(strike_count)]
        exp_date   = expiration_date or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        exp_key    = f"{exp_date}:30"

        def make_contract(strike, is_call):
            itm       = (is_call and strike <= base_price) or (not is_call and strike >= base_price)
            intrinsic = max(0, (base_price - strike) if is_call else (strike - base_price))
            iv        = round(random.uniform(0.25, 0.55) * 100, 1)
            delta     = round(random.uniform(0.55, 0.85) if itm else random.uniform(0.15, 0.45), 3)
            if not is_call: delta = -delta
            last = round(intrinsic + random.uniform(0.5, 3.0), 2)
            bid  = round(last - 0.05, 2)
            ask  = round(last + 0.05, 2)
            dte  = (datetime.strptime(exp_date, "%Y-%m-%d") - datetime.now()).days
            return [{
                "strikePrice":  strike,
                "last": last, "bid": bid, "ask": ask,
                "netChange":    round(random.uniform(-1, 1), 2),
                "totalVolume":  random.randint(100, 5000),
                "openInterest": random.randint(500, 20000),
                "volatility":   iv,
                "delta":  delta,
                "gamma":  round(random.uniform(0.01, 0.05), 4),
                "theta":  round(random.uniform(-0.15, -0.01), 4),
                "vega":   round(random.uniform(0.05, 0.30), 4),
                "daysToExpiration": dte,
                "symbol": f"{sym}_{exp_date}_{'C' if is_call else 'P'}{int(strike*1000):08d}",
            }]

        call_map = {str(s): {exp_key: make_contract(s, True)}  for s in strikes}
        put_map  = {str(s): {exp_key: make_contract(s, False)} for s in strikes}
        return {
            "symbol":         sym,
            "underlyingPrice": base_price,
            "callExpDateMap":  call_map if option_type in ("ALL","CALL") else {},
            "putExpDateMap":   put_map  if option_type in ("ALL","PUT")  else {},
        }

    def get_option_expirations(self, symbol: str) -> list:
        today = datetime.now()
        sym   = symbol.upper()
        exps  = []
        DAILY = {"SPY","QQQ","SPX","SPXW"}
        if sym in DAILY:
            d = today; added = 0
            while added < 10:
                d += timedelta(days=1)
                if d.weekday() in (0, 2, 4):
                    exps.append({"expirationDate": d.strftime("%Y-%m-%d"),
                                 "daysToExpiration": (d-today).days})
                    added += 1
        for weeks in [1,2,3,4,5,6,8,10,12,16,20,26]:
            d = today + timedelta(weeks=weeks)
            d += timedelta(days=(4 - d.weekday()) % 7)
            ds = d.strftime("%Y-%m-%d")
            if not any(e["expirationDate"] == ds for e in exps):
                exps.append({"expirationDate": ds, "daysToExpiration": (d-today).days})
        exps.sort(key=lambda x: x["expirationDate"])
        return exps

    def get_orders(self, from_date=None, to_date=None, status=None) -> list:
        orders = []
        for o in MOCK_ORDERS:
            if status and o["status"] != status:
                continue
            orders.append({
                "orderId":   o["orderId"],
                "orderType": o["type"],
                "quantity":  o["qty"],
                "price":     o["price"],
                "status":    o["status"],
                "enteredTime": o["time"],
                "orderLegCollection": [{
                    "instruction": o["instruction"],
                    "instrument":  {"symbol": o["symbol"], "assetType": "EQUITY"},
                }],
            })
        return orders

    def place_order(self, order: dict):
        sym = "UNKNOWN"
        try: sym = order["orderLegCollection"][0]["instrument"]["symbol"]
        except: pass
        return True, f"[DEMO] Order for {sym} simulated. No real order placed."

    def cancel_order(self, order_id: str):
        return True, f"[DEMO] Order {order_id} cancelled (simulated)."

    @staticmethod
    def build_stock_order(symbol, qty, side, order_type, limit_price=None,
                           stop_price=None, trailing_amount=None, trailing_percent=None):
        order = {
            "orderType": order_type,
            "session":   "NORMAL",
            "duration":  "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": side,
                "quantity":    qty,
                "instrument":  {"symbol": symbol.upper(), "assetType": "EQUITY"},
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
    def build_option_order(option_symbol, qty, instruction, order_type,
                            limit_price=None, stop_price=None):
        order = {
            "orderType": order_type,
            "session":   "NORMAL",
            "duration":  "DAY",
            "orderStrategyType": "SINGLE",
            "orderLegCollection": [{
                "instruction": instruction,
                "quantity":    qty,
                "instrument":  {"symbol": option_symbol, "assetType": "OPTION"},
            }],
        }
        if order_type in ("LIMIT", "STOP_LIMIT") and limit_price:
            order["price"] = str(round(limit_price, 2))
        if stop_price:
            order["stopPrice"] = str(round(stop_price, 2))
        return order

    @staticmethod
    def build_oco_order(symbol, qty, side, take_profit_price, stop_loss_price,
                         asset_type="EQUITY"):
        """One-Cancels-Other: profit target + stop loss together."""
        instruction = side
        return {
            "orderStrategyType": "OCO",
            "childOrderStrategies": [
                {
                    "orderType": "LIMIT",
                    "session":   "NORMAL",
                    "duration":  "GTC",
                    "price":     str(round(take_profit_price, 2)),
                    "orderStrategyType": "SINGLE",
                    "orderLegCollection": [{
                        "instruction": "SELL" if side == "BUY" else "BUY",
                        "quantity":    qty,
                        "instrument":  {"symbol": symbol, "assetType": asset_type},
                    }],
                },
                {
                    "orderType": "STOP",
                    "session":   "NORMAL",
                    "duration":  "GTC",
                    "stopPrice": str(round(stop_loss_price, 2)),
                    "orderStrategyType": "SINGLE",
                    "orderLegCollection": [{
                        "instruction": "SELL" if side == "BUY" else "BUY",
                        "quantity":    qty,
                        "instrument":  {"symbol": symbol, "assetType": asset_type},
                    }],
                },
            ],
        }
