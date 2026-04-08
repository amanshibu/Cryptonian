from abc import ABC, abstractmethod

class BaseExecution(ABC):
    @abstractmethod
    def place_order(self, symbol, side, amount):
        """Place an order. Returns a dictionary with status and order details."""
        pass

    @abstractmethod
    def get_balance(self):
        """Returns the available balance of the quote asset."""
        pass

    @abstractmethod
    def get_price(self, symbol):
        """Returns the current price of the asset."""
        pass

    @abstractmethod
    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        """Returns a Pandas DataFrame with historical OHLCV data."""
        pass

    @abstractmethod
    def get_spread_pct(self, symbol):
        """Returns the current bid/ask spread as a percentage."""
        pass
