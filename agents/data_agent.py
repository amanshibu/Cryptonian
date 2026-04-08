import ccxt
import pandas as pd

class DataFetchAgent:
    def __init__(self, config, execution_client=None):
        self.config = config
        self.execution_client = execution_client
            
    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """
        Fetches historical Open, High, Low, Close, Volume data.
        Returns a Pandas DataFrame.
        """
        if self.config.MODE != "BACKTEST":
            print(f"[DataFetchAgent] Fetching {limit} candles for {symbol} at {timeframe}...")
        if self.execution_client:
            return self.execution_client.fetch_ohlcv(symbol, timeframe, limit=limit)
        return None
            
    def get_current_price(self, symbol):
        """Gets the most recent ticker price."""
        if self.execution_client:
            return self.execution_client.get_price(symbol)
        return None

    def get_balance(self):
        """Fetches available balance for the quote asset or returns mock balance."""
        if self.config.MODE != "BACKTEST":
            print("[DataFetchAgent] Fetching balance...")
        if self.execution_client:
            return self.execution_client.get_balance()
        return getattr(self.config, 'INITIAL_BALANCE', 1000.0)
