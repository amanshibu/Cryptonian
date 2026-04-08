import time

class DecisionAgent:
    def __init__(self, config):
        self.config = config
        self.current_position = None  # None, 'LONG', 'SHORT'
        
        # Risk Management State
        self.entry_price = 0.0
        self.position_size_base = 0.0
        
        # Account/System constraints
        self.daily_pnl = 0.0
        self.last_trade_time = 0
        self.last_trade_was_win = True # Initialize with True

        # ── NEW: Improvement 3 — Partial TP & Trailing tracking ─────────
        self.tp1_hit = False
        self.trailing_sl_price = 0.0
        
        # ── NEW: Dynamic ATR tracking for current trade ──────────────────
        self.current_trade_sl_pct = 0.0
        self.current_trade_tp1_pct = 0.0
        self.current_trade_tp2_pct = 0.0
        self.current_trade_trail_pct = 0.0

        # ── NEW: Improvement 4 — Loss Streak Kill Switch ──────────────
        self.consecutive_losses = 0
        self.kill_switch_activated_at = 0.0  # timestamp when kill switch engaged

    def formulate_decision(self, strategy_output, current_price, current_balance, adaptive_params=None, current_ts=None):
        """
        Validates the strategy output against risk parameters and portfolio state.
        Returns an actionable decision dictionary.
        """
        if current_ts is None:
            current_ts = time.time()
        self._current_ts = current_ts
            
        if adaptive_params is None:
            adaptive_params = {}
            
        raw_signal = strategy_output.get("signal", "HOLD")
        reason = strategy_output.get("reason", "")
        
        print(f"[DecisionAgent] Processing signal: {raw_signal} at price {current_price}")
        
        decision = {
            "action": "HOLD",
            "amount_usdt": 0,
            "target_asset": self.config.TRADING_PAIR,
            "reason": ""
        }
        
        # 1. Check Max Daily Loss Protection
        if self.daily_pnl <= -self.config.MAX_DAILY_LOSS_USDT:
            decision["reason"] = f"Max daily loss reached ({self.daily_pnl:.2f}). Trading stopped."
            return decision

        # ── NEW: Improvement 4 — Kill Switch Check ────────────────────
        if self.consecutive_losses >= self.config.LOSS_STREAK_LIMIT:
            cooldown_sec = self.config.KILL_SWITCH_COOLDOWN_MINUTES * 60
            elapsed = current_ts - self.kill_switch_activated_at
            if elapsed < cooldown_sec:
                remaining = int(cooldown_sec - elapsed)
                decision["reason"] = (
                    f"Kill switch active — {self.consecutive_losses} consecutive losses. "
                    f"Resumes in {remaining // 60}m {remaining % 60}s."
                )
                print(f"[DecisionAgent] {decision['reason']}")
                return decision
            else:
                # Cooldown expired → reset
                print("[DecisionAgent] Kill switch cooldown expired. Resuming trading.")
                self.consecutive_losses = 0
                self.kill_switch_activated_at = 0
            
        # 2. Check Risk Management (SL / Partial TP) first if we have a position
        if self.current_position in ["LONG", "SHORT"]:
            is_long = self.current_position == "LONG"
            profit_pct = (current_price - self.entry_price) / self.entry_price if is_long else (self.entry_price - current_price) / self.entry_price
            
            # Use dynamic or config fallback percentages
            eff_sl_pct = self.current_trade_sl_pct if self.current_trade_sl_pct > 0 else getattr(self.config, 'STOP_LOSS_PCT', 0.02)
            eff_tp1_pct = self.current_trade_tp1_pct if self.current_trade_tp1_pct > 0 else getattr(self.config, 'TP1_PCT', 0.02)
            eff_tp2_pct = self.current_trade_tp2_pct if self.current_trade_tp2_pct > 0 else getattr(self.config, 'TP2_PCT', 0.04)
            eff_trail_pct = self.current_trade_trail_pct if self.current_trade_trail_pct > 0 else getattr(self.config, 'TRAILING_SL_PCT', 0.015)

            # SL hit → close ALL remaining
            if profit_pct <= -eff_sl_pct:
                sell_amount_base = self.position_size_base
                decision["action"] = "SELL" if is_long else "BUY"
                decision["amount_usdt"] = sell_amount_base * current_price
                decision["reason"] = f"Stop Loss Hit! ({profit_pct*100:.2f}%)"
                
                # Update PnL & state
                pnl = (decision["amount_usdt"] - (sell_amount_base * self.entry_price)) if is_long else ((sell_amount_base * self.entry_price) - decision["amount_usdt"])
                self.daily_pnl += pnl
                self.current_position = None
                self.tp1_hit = False
                self.last_trade_time = current_ts
                self._record_loss()
                return decision

            # ── NEW: Improvement 3 — Partial Take Profit (TP1) ────────
            if not self.tp1_hit and profit_pct >= eff_tp1_pct:
                close_fraction = getattr(self.config, 'TP1_CLOSE_FRACTION', 0.5)
                sell_amount_base = self.position_size_base * close_fraction
                
                decision["action"] = "PARTIAL_SELL" if is_long else "PARTIAL_BUY"
                decision["amount_usdt"] = sell_amount_base * current_price
                decision["reason"] = f"TP1 Hit! ({profit_pct*100:.2f}%) — closing {close_fraction*100:.0f}%"
                
                # Update PnL & reduce position
                pnl = (decision["amount_usdt"] - (sell_amount_base * self.entry_price)) if is_long else ((sell_amount_base * self.entry_price) - decision["amount_usdt"])
                self.daily_pnl += pnl
                self.position_size_base -= sell_amount_base
                self.tp1_hit = True
                self.last_trade_time = current_ts
                self._record_win()
                return decision
                
            # ── NEW: Improvement 3 — Trailing Stop Loss ───────────────
            if is_long:
                if current_price > self.trailing_sl_price:
                    self.trailing_sl_price = current_price
                hit_trailing = current_price <= self.trailing_sl_price * (1 - eff_trail_pct)
            else:
                if current_price < self.trailing_sl_price:
                    self.trailing_sl_price = current_price
                hit_trailing = current_price >= self.trailing_sl_price * (1 + eff_trail_pct)
            
            if hit_trailing:
                sell_amount_base = self.position_size_base
                decision["action"] = "SELL" if is_long else "BUY"
                decision["amount_usdt"] = sell_amount_base * current_price
                decision["reason"] = f"Trailing Stop Hit! (peaked at {self.trailing_sl_price:.2f})"
                
                # Update PnL & state
                pnl = (decision["amount_usdt"] - (sell_amount_base * self.entry_price)) if is_long else ((sell_amount_base * self.entry_price) - decision["amount_usdt"])
                self.daily_pnl += pnl
                self.current_position = None
                self.tp1_hit = False
                self.last_trade_time = current_ts
                
                if pnl > 0: self._record_win()
                else: self._record_loss()
                return decision

            # ── NEW: Improvement 3 — Full Take Profit (TP2) ──────────
            if profit_pct >= eff_tp2_pct:
                sell_amount_base = self.position_size_base
                decision["action"] = "SELL" if is_long else "BUY"
                decision["amount_usdt"] = sell_amount_base * current_price
                decision["reason"] = f"TP2 Hit! ({profit_pct*100:.2f}%) — closing remaining"
                
                # Update PnL & state
                pnl = (decision["amount_usdt"] - (sell_amount_base * self.entry_price)) if is_long else ((sell_amount_base * self.entry_price) - decision["amount_usdt"])
                self.daily_pnl += pnl
                self.current_position = None
                self.tp1_hit = False
                self.last_trade_time = current_ts

                self._record_win()
                return decision

        # 3. Check Cooldown
        cd_min = getattr(self.config, 'COOLDOWN_WIN_MINUTES', 5) if self.last_trade_was_win else getattr(self.config, 'COOLDOWN_LOSS_MINUTES', 15)
        if (current_ts - self.last_trade_time) < (cd_min * 60):
            decision["reason"] = f"In cooldown period ({cd_min}m)."
            return decision

        # 4. Process Signal
        # Wait for SL/TP to hit, ignore opposing signals during active trades!

        # Open new position if flat
        if (raw_signal in ["BUY", "SELL"]) and self.current_position is None:
            decision["action"] = raw_signal
            
            # Dynamic position sizing
            base_risk_amount = current_balance * self.config.RISK_PERCENT_PER_TRADE
            
            # Application of adaptive parameters from LearningAgent
            if adaptive_params.get("reduce_position_size", False):
                base_risk_amount *= 0.5
                reason += " (Position halved due to low WR)"

            # ── NEW: Improvement 6 — Adaptive size multiplier ─────────
            size_multiplier = adaptive_params.get("position_size_multiplier", 1.0)
            base_risk_amount *= size_multiplier
            if size_multiplier != 1.0:
                reason += f" (Size x{size_multiplier:.2f})"

            # ATR Based sizing: low volatility = larger size, high volatility = smaller size
            atr_ratio = strategy_output.get("atr_ratio", 1.0)
            if atr_ratio > 0:
                atr_scaler = min(max(1.0 / atr_ratio, 0.5), 1.5) # cap sizing between 0.5x and 1.5x
                base_risk_amount *= atr_scaler
                if abs(atr_scaler - 1.0) > 0.05:
                    reason += f" (ATR-Sized x{atr_scaler:.2f})"
                    
            # Set Dynamic Exits based on current ATR Value 
            atr_value = strategy_output.get("atr_value", 0.0)
            if atr_value > 0 and current_price > 0:
                self.current_trade_sl_pct = max((atr_value * getattr(self.config, 'SL_ATR_MULTIPLIER', 3.0)) / current_price, 0.003)
                self.current_trade_tp1_pct = max((atr_value * getattr(self.config, 'TP1_ATR_MULTIPLIER', 1.5)) / current_price, 0.002)
                self.current_trade_tp2_pct = max((atr_value * getattr(self.config, 'TP2_ATR_MULTIPLIER', 3.0)) / current_price, 0.004)
                self.current_trade_trail_pct = max((atr_value * getattr(self.config, 'TRAIL_SL_ATR_MULTIPLIER', 1.5)) / current_price, 0.002)
            else:
                self.current_trade_sl_pct = 0.0
                self.current_trade_tp1_pct = 0.0
                self.current_trade_tp2_pct = 0.0
                self.current_trade_trail_pct = 0.0

            # ── NEW: Improvement 2 — Off-session size reduction ───────
            off_session = strategy_output.get("off_session", False)
            if off_session and getattr(self.config, 'REDUCE_SIZE_OUTSIDE_SESSION', False):
                multiplier = getattr(self.config, 'OFF_SESSION_SIZE_MULTIPLIER', 0.5)
                base_risk_amount *= multiplier
                reason += f" (Off-session, size x{multiplier})"
                
            decision["amount_usdt"] = base_risk_amount
            decision["reason"] = f"Opening {'LONG' if raw_signal == 'BUY' else 'SHORT'}: {reason}"
            
            # Update state
            self.current_position = "LONG" if raw_signal == "BUY" else "SHORT"
            self.entry_price = current_price
            self.trailing_sl_price = current_price
            self.position_size_base = decision["amount_usdt"] / current_price
            self.tp1_hit = False
            self.last_trade_time = current_ts
            
        else:
            decision["reason"] = f"Signal {raw_signal} matched steady state or HOLD."

        # Add strategy/market state info for execution/learning agents
        decision["strategy_output"] = strategy_output

        return decision

    # ── NEW: Improvement 4 — Kill Switch Helpers ──────────────────────
    def _record_win(self):
        """Reset consecutive loss counter on a win."""
        self.consecutive_losses = 0
        self.last_trade_was_win = True

    def _record_loss(self):
        """Increment consecutive loss counter; activate kill switch if limit reached."""
        self.consecutive_losses += 1
        self.last_trade_was_win = False
        if self.consecutive_losses >= self.config.LOSS_STREAK_LIMIT:
            self.kill_switch_activated_at = getattr(self, '_current_ts', time.time())
            print(
                f"[DecisionAgent] [!] KILL SWITCH ACTIVATED - "
                f"{self.consecutive_losses} consecutive losses. "
                f"Pausing for {self.config.KILL_SWITCH_COOLDOWN_MINUTES} min."
            )
