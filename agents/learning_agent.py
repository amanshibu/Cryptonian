import csv
from datetime import datetime
import os
import time as _time

class LearningAgent:
    def __init__(self, config=None, log_file="trade_logs.csv"):
        self.config = config
        self.log_file = log_file
        self._initialize_log()
        
        # Performance Tracking
        self.trades = 0
        self.wins = 0
        self.losses = 0
        self.total_profit = 0.0
        self.total_loss = 0.0
        self.max_drawdown = 0.0
        self.peak_pnl = 0.0
        self.current_pnl = 0.0
        
        # State for PNL calculation
        self.last_buy_price = 0.0
        self.last_buy_amount = 0.0

        # ── NEW: Improvement 6 — Enhanced Tracking ────────────────────
        self.consecutive_wins = 0
        self.consecutive_losses = 0
        self.trade_open_time = 0.0          # Timestamp when BUY logged
        self.profit_by_strategy = {}        # e.g. {"Trend Strategy": 0.0, "Range Strategy": 0.0}
        self.position_size_multiplier = 1.0 # Adaptive sizing output
        self._previous_win_rate = 100.0     # For trend detection

    def _initialize_log(self):
        if not os.path.exists(self.log_file):
            with open(self.log_file, mode='w', newline='') as file:
                writer = csv.writer(file)
                # NEW: added duration_seconds column
                writer.writerow([
                    "timestamp", "symbol", "action", "price", "amount",
                    "status", "strategy", "market_state", "pnl", "duration_seconds"
                ])

    def log_trade(self, order_result):
        """
        Logs the result of a trade execution for future learning and backtesting analysis.
        """
        if order_result.get("status") == "skipped" or order_result.get("status") == "error":
            return
            
        order = order_result.get("order", {})
        decision_context = order_result.get("decision_context", {})
        strategy_context = decision_context.get("strategy_output", {})
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        symbol = order.get("symbol", "UNKNOWN")
        side = order.get("side", "UNKNOWN")
        price = float(order.get("price", 0))
        amount = float(order.get("amount", 0))
        status = order.get("status", "UNKNOWN")
        is_partial = order.get("partial", False)
        
        strategy = strategy_context.get("reason", "UNKNOWN").split(":")[0] 
        market_state = strategy_context.get("market_state", "UNKNOWN")
        pnl = 0.0
        duration_seconds = 0
        
        if side.upper() == "BUY":
            self.last_buy_price = price
            self.last_buy_amount = amount
            self.trade_open_time = _time.time()  # NEW: record open time

        elif side.upper() == "SELL" and self.last_buy_price > 0:
            # For partial sells, compute PnL on the partial amount
            sell_amount = amount
            pnl = (price - self.last_buy_price) * sell_amount

            # ── NEW: Trade duration ───────────────────────────────────
            if self.trade_open_time > 0:
                duration_seconds = int(_time.time() - self.trade_open_time)

            self.trades += 1
            self.current_pnl += pnl
            
            if pnl > 0:
                self.wins += 1
                self.total_profit += pnl
                if self.current_pnl > self.peak_pnl:
                    self.peak_pnl = self.current_pnl
                # ── NEW: streak tracking ──────────────────────────────
                self.consecutive_wins += 1
                self.consecutive_losses = 0
            else:
                self.losses += 1
                self.total_loss += abs(pnl)
                drawdown = self.peak_pnl - self.current_pnl
                if drawdown > self.max_drawdown:
                    self.max_drawdown = drawdown
                # ── NEW: streak tracking ──────────────────────────────
                self.consecutive_losses += 1
                self.consecutive_wins = 0

            # ── NEW: Improvement 6 — Profit per strategy type ─────────
            strat_key = strategy.strip()
            self.profit_by_strategy[strat_key] = self.profit_by_strategy.get(strat_key, 0.0) + pnl

            # Only reset buy state if this is NOT a partial sell
            if not is_partial:
                self.last_buy_price = 0.0
                self.last_buy_amount = 0.0
                self.trade_open_time = 0.0
            else:
                # Partial sell: reduce tracked buy amount
                self.last_buy_amount -= sell_amount
                
            print(f"[LearningAgent] Trade closed with PNL: {pnl:.2f}. Win Rate: {self.get_win_rate():.2f}%")
        
        with open(self.log_file, mode='a', newline='') as file:
            writer = csv.writer(file)
            action_label = "PARTIAL_SELL" if is_partial else side
            writer.writerow([
                timestamp, symbol, action_label, price, amount,
                status, strategy, market_state, pnl, duration_seconds
            ])
            
        print(f"[LearningAgent] Trade logged: {side} {amount} {symbol} @ {price}")

    def get_win_rate(self):
        if self.trades == 0:
            return 100.0 # Default optimistic
        return (self.wins / self.trades) * 100

    def get_adaptive_parameters(self):
        """
        Provides dynamic adjustment suggestions for the Decision Agent.
        Now includes adaptive position size multiplier and enhanced metrics.
        """
        avg_profit = self.total_profit / self.wins if self.wins > 0 else 0.0
        avg_loss = self.total_loss / self.losses if self.losses > 0 else 0.0
        win_rate = self.get_win_rate()
        
        # ── NEW: Improvement 6 — Adaptive Position Sizing ─────────────
        self._update_size_multiplier(win_rate)
        
        params = {
            "reduce_position_size": False,
            "position_size_multiplier": self.position_size_multiplier,  # NEW
            "metrics": {
                "win_rate": win_rate,
                "avg_profit": avg_profit,
                "avg_loss": avg_loss,
                "max_drawdown": self.max_drawdown,
                "trades": self.trades,
                "consecutive_wins": self.consecutive_wins,       # NEW
                "consecutive_losses": self.consecutive_losses,   # NEW
                "profit_by_strategy": dict(self.profit_by_strategy),  # NEW
                "size_multiplier": self.position_size_multiplier # NEW
            }
        }
        
        # Adaptive behavior: reduce position size if system is underperforming
        if self.trades >= 30 and win_rate < 40.0:
            params["reduce_position_size"] = True
            
        return params

    # ── NEW: Improvement 6 — Adaptive Sizing Engine ───────────────────
    def _update_size_multiplier(self, win_rate):
        """
        Dynamically adjusts position_size_multiplier based on performance.
        - Drawdown increasing → reduce size (with floor)
        - Performance improving → increase size (with cap)
        """
        if self.config is None:
            return

        step = getattr(self.config, 'ADAPTIVE_SIZE_INCREASE_RATE', 0.1)
        cap = getattr(self.config, 'ADAPTIVE_SIZE_MAX_MULTIPLIER', 1.5)
        floor = getattr(self.config, 'ADAPTIVE_SIZE_MIN_MULTIPLIER', 0.5)

        current_drawdown = self.peak_pnl - self.current_pnl

        # Require a minimum number of trades before adapting
        if self.trades < 30:
            self._previous_win_rate = win_rate
            return

        # If drawdown is significant (> 10% of total running balance), reduce
        # Fixed logic: drawdown should be measured against peak_pnl logically, but effectively it should only fire on real capital loss.
        # So we check if current_drawdown > 150.0 (i.e. $150 loss from peak)
        if self.peak_pnl > 0 and current_drawdown > 150.0:
            self.position_size_multiplier = max(
                self.position_size_multiplier - step, floor
            )
            print(f"[LearningAgent] Drawdown > $150 — reducing size multiplier to {self.position_size_multiplier:.2f}")

        # If win rate is good and improving, cautiously increase
        elif win_rate > 55.0 and win_rate >= self._previous_win_rate:
            self.position_size_multiplier = min(
                self.position_size_multiplier + step, cap
            )
            print(f"[LearningAgent] Performance improving — size multiplier now {self.position_size_multiplier:.2f}")

        self._previous_win_rate = win_rate
