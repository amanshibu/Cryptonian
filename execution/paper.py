import ccxt
import pandas as pd
from .base import BaseExecution

class PaperExecution(BaseExecution):
    def __init__(self, config):
        self.config = config
        self.exchange = ccxt.binance({
            'apiKey': self.config.BINANCE_API_KEY,
            'secret': self.config.BINANCE_SECRET,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot'
            }
        })
        self.exchange.set_sandbox_mode(True)
        print("[PaperExecution] Initialized Binance Testnet Sandbox.")

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"[PaperExecution] Error fetching data: {e}")
            return None

    def get_price(self, symbol):
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            print(f"[PaperExecution] Error fetching ticker: {e}")
            return None

    def get_balance(self):
        # In paper trading, CCXT testnet might reset or have weird balances.
        # Often it's safer to use the mock balance.
        return getattr(self.config, 'INITIAL_BALANCE', 1000.0)

    def get_spread_pct(self, symbol):
        try:
            ob = self.exchange.fetch_order_book(symbol, limit=1)
            best_bid = ob['bids'][0][0] if ob['bids'] else 0
            best_ask = ob['asks'][0][0] if ob['asks'] else 0
            if best_bid > 0 and best_ask > 0:
                mid = (best_bid + best_ask) / 2
                return ((best_ask - best_bid) / mid) * 100
        except Exception as e:
            print(f"[PaperExecution] Spread fetch failed: {e}")
        return 0.0

    def place_order(self, symbol, side, amount):
        # We will mock the order placement in paper to be extremely safe, 
        # or use real testnet orders. We'll use mock for safety as legacy did.
        # To actually execute testnet trades, uncomment create_market_order.
        print(f"[PaperExecution] Placing Paper Order: {side} {amount} {symbol}")
        try:
            price = self.get_price(symbol)
            # order = self.exchange.create_market_order(symbol, side, amount)
            order = {
                "id": "PAPER_ORDER_123",
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "price": price,
                "status": "closed",
                "partial": False
            }
            return {"status": "success", "order": order, "decision_context": {}}
        except Exception as e:
            return {"status": "error", "error": str(e)}
