from .base import BaseExecution

class BacktestExecution(BaseExecution):
    def __init__(self, config):
        self.config = config
        self.balance = getattr(config, 'INITIAL_BALANCE', 1000.0)
        self.current_price = 0.0
        self.trades_history = []
        self._current_df_slice = None
        self._current_df_higher_slice = None

    def update_state(self, current_price, df_slice, df_higher_slice):
        self.current_price = current_price
        self._current_df_slice = df_slice
        self._current_df_higher_slice = df_higher_slice

    def fetch_ohlcv(self, symbol, timeframe, limit=100):
        if timeframe == self.config.HIGHER_TIMEFRAME:
            return self._current_df_higher_slice.tail(limit) if self._current_df_higher_slice is not None else None
        return self._current_df_slice.tail(limit) if self._current_df_slice is not None else None

    def get_price(self, symbol):
        return self.current_price

    def get_balance(self):
        return self.balance

    def get_spread_pct(self, symbol):
        # Backtest default simulated spread
        return 0.02 

    def place_order(self, symbol, side, amount):
        cost = amount * self.current_price
        fee_rate = 0.001  # 0.1%
        
        if side == "buy":
            self.balance -= cost * (1 + fee_rate)
        elif side == "sell":
            self.balance += cost * (1 - fee_rate)
        
        order = {
            "id": f"BT_ORDER_{len(self.trades_history)+1}",
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": self.current_price,
            "fee": cost * fee_rate,
            "status": "closed",
            "partial": False
        }
        self.trades_history.append(order)
        return {"status": "success", "order": order, "decision_context": {}}
