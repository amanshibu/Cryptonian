import pandas_ta as ta
from datetime import datetime, timezone

class StrategyAgent:
    def __init__(self, config=None):
        self.config = config

    def add_indicators(self, df):
        """
        Calculates indicators needed for Breakout, Pullback and Scoring.
        """
        if self.config.MODE != "BACKTEST":
            print("[StrategyAgent] Calculating indicators (EMA, RSI, ATR, Vol SMA)...")
        if df is None or len(df) < 50:
            return df
            
        # Core EMAs
        df['ema_9'] = ta.ema(df['close'], length=9)
        df['ema_21'] = ta.ema(df['close'], length=21)
        df['ema_50'] = ta.ema(df['close'], length=50)
        
        # Volatility
        df['atr_14'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        df['atr_sma_14'] = ta.sma(df['atr_14'], length=14)
        
        # Momentum
        df['roc_14'] = ta.roc(df['close'], length=14)
        df['rsi_14'] = ta.rsi(df['close'], length=14)
        
        # Volume
        df['volume_sma_20'] = ta.sma(df['volume'], length=20)
        
        # Breakout Channels (Donchian-like)
        df['rolling_high_20'] = df['high'].rolling(window=20).max()
        df['rolling_low_20'] = df['low'].rolling(window=20).min()
        
        # Shift the rolling channels by 1 so we compare current price to PREVIOUS window high
        df['rolling_high_20'] = df['rolling_high_20'].shift(1)
        df['rolling_low_20'] = df['rolling_low_20'].shift(1)
        
        # Bollinger Bands (Mean Reversion)
        df['bb_mid'] = ta.sma(df['close'], length=20)
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_mid'] + (2.0 * df['bb_std'])
        df['bb_lower'] = df['bb_mid'] - (2.0 * df['bb_std'])
        
        return df

    # ── NEW: Improvement 2 — Time-Based Session Filter ─────────────────
    def _is_in_trading_session(self):
        """Check if current UTC hour falls within any configured trading session."""
        if self.config is None:
            return True, False  # No config → always in session
        
        sessions = getattr(self.config, 'TRADING_SESSION_HOURS', [])
        if not sessions:
            return True, False
        
        current_hour = datetime.now(timezone.utc).hour
        
        for start_h, end_h in sessions:
            if start_h <= current_hour < end_h:
                return True, False  # in_session=True, off_session=False
        
        return False, True  # in_session=False, off_session=True

    # ── UPDATED SCORING SYSTEM (SMOOTH, NOT BINARY) ──
    def _calculate_score(self, latest, previous, price):
        score = 0

        # Trend strength (0–30)
        trend_strength = abs(latest['ema_21'] - latest['ema_50']) / price
        score += min(trend_strength * 10000, 30)

        # Volume (0–25)
        vol_ratio = latest['volume'] / latest['volume_sma_20'] if latest['volume_sma_20'] > 0 else 1
        score += min(vol_ratio * 10, 25)

        # Volatility (0–20)
        atr_ratio = latest['atr_14'] / latest['atr_sma_14'] if latest['atr_sma_14'] > 0 else 1
        score += min(atr_ratio * 10, 20)

        # Momentum (0–25)
        roc = abs(latest['roc_14'])
        score += min(roc * 20, 25)

        return score

    def analyze(self, df, df_higher=None, spread_pct=0.0):
        """
        Analyzes the data and generates a raw signal dictionary.
        Implements Breakout and Pullback Trend Strategies based on a scoring system.
        """
        df = self.add_indicators(df)
        if df is None or len(df) < 55:
            return {"signal": "HOLD", "reason": "Not enough data", "confidence": 0.0, "atr_value": 0, "off_session": False}
            
        latest = df.iloc[-1]
        previous = df.iloc[-2]
        price = latest['close']

        max_spread = getattr(self.config, 'MAX_SPREAD_PCT', 0.15) if self.config else 0.15
        if spread_pct > max_spread:
            return {"signal": "HOLD", "reason": f"Spread too high ({spread_pct:.3f}% > {max_spread}%)", "confidence": 0.0, "atr_value": 0, "off_session": False}

        in_session, off_session = self._is_in_trading_session()
        
        score = self._calculate_score(latest, previous, price)
        # Convert score to an artificial confidence 0.0 - 1.0 for backwards compatibility
        confidence = score / 100.0

        atr_value = latest['atr_14']
        atr_ratio_val = atr_value / latest['atr_sma_14'] if latest['atr_sma_14'] > 0 else 1.0

        score_threshold = 30 # Minimum score required to trade
        
        signal = "HOLD"
        reason = "No valid setup found"
        strategy_name = ""

        # Higher Timeframe Confirmation Check (Optional but good)
        htf_bullish = True
        htf_bearish = True
        if df_higher is not None:
             df_higher = self.add_indicators(df_higher)
             if df_higher is not None and len(df_higher) > 0 and 'ema_50' in df_higher.columns:
                 htf_latest = df_higher.iloc[-1]
                 htf_bullish = htf_latest['close'] > htf_latest['ema_50']
                 htf_bearish = htf_latest['close'] < htf_latest['ema_50']

        if score >= score_threshold:
            # 1. Breakout Strategy
            is_breakout_up = price > latest['rolling_high_20'] and previous['close'] <= previous['rolling_high_20']
            is_breakout_down = price < latest['rolling_low_20'] and previous['close'] >= previous['rolling_low_20']
            
            # Volume confirmation for breakout
            vol_confirmed = latest['volume'] > latest['volume_sma_20']
            
            if is_breakout_up and vol_confirmed and htf_bullish:
                signal = "BUY"
                strategy_name = "Breakout UP"
                reason = f"{strategy_name} - Score: {score}"
            elif is_breakout_down and vol_confirmed and htf_bearish:
                signal = "SELL"
                strategy_name = "Breakout DOWN"
                reason = f"{strategy_name} - Score: {score}"
            
            # 2. Pullback Trend Strategy
            # Uptrend pullback
            in_uptrend = latest['ema_21'] > latest['ema_50']
            pulled_back = previous['low'] <= latest['ema_21'] or latest['low'] <= latest['ema_21']
            resuming_up = price > latest['ema_9'] and price > previous['high']
            
            if signal == "HOLD" and in_uptrend and pulled_back and resuming_up and htf_bullish:
                signal = "BUY"
                strategy_name = "Pullback UP"
                reason = f"{strategy_name} - Score: {score}"
                
            # Downtrend pullback
            in_downtrend = latest['ema_21'] < latest['ema_50']
            pulled_back_down = previous['high'] >= latest['ema_21'] or latest['high'] >= latest['ema_21']
            resuming_down = price < latest['ema_9'] and price < previous['low']
            
            if signal == "HOLD" and in_downtrend and pulled_back_down and resuming_down and htf_bearish:
                signal = "SELL"
                strategy_name = "Pullback DOWN"
                reason = f"{strategy_name} - Score: {score}"

        # Gate signals if confidence acts as a secondary block in DecisionAgent
        if signal != "HOLD" and confidence < (score_threshold/100.0):
             signal = "HOLD"

        if signal != "HOLD" and off_session:
            reason += " [OFF-SESSION]"

        market_state = "TREND" if latest['ema_21'] > latest['ema_50'] or latest['ema_21'] < latest['ema_50'] else "RANGE"

        return {
            "signal": signal,
            "market_state": market_state,
            "strategy": strategy_name,
            "reason": reason,
            "confidence": confidence,
            "off_session": off_session,
            "atr_ratio": atr_ratio_val,
            "atr_value": atr_value # Pass absolute ATR for dynamic TP/SL
        }

    # ── LIGHTNING FAST ANALYZE (For vectorized backtest engine) ────
    def analyze_fast(self, latest, previous, df_higher, current_ts, spread_pct=0.0):
        price = latest['close']
        
        max_spread = getattr(self.config, 'MAX_SPREAD_PCT', 0.15) if self.config else 0.15
        if spread_pct > max_spread:
            return {"signal": "HOLD", "reason": "Spread too high", "confidence": 0.0, "atr_value": 0, "off_session": False}

        in_session, off_session = self._is_in_trading_session()
        
        score = self._calculate_score(latest, previous, price)
        confidence = score / 100.0

        atr_value = latest['atr_14']
        atr_ratio_val = atr_value / latest['atr_sma_14'] if latest['atr_sma_14'] > 0 else 1.0

        score_threshold = getattr(self.config, 'CONFIDENCE_THRESHOLD', 0.5) * 100
        signal = "HOLD"
        reason = "No valid setup found"
        strategy_name = ""

        htf_bullish = True
        htf_bearish = True
        if df_higher is not None and not df_higher.empty:
            htf_past = df_higher[df_higher['timestamp'] <= current_ts]
            if not htf_past.empty:
                htf_latest = htf_past.iloc[-1]
                if 'ema_50' in htf_latest and 'close' in htf_latest:
                    htf_bullish = htf_latest['close'] > htf_latest['ema_50']
                    htf_bearish = htf_latest['close'] < htf_latest['ema_50']

        if score >= score_threshold:
            ema_slope = abs(latest['ema_21'] - previous['ema_21']) / price
            min_slope = getattr(self.config, 'EMA_SLOPE_THRESHOLD', 0.0005)
            
            # ROC Confirmation
            momentum_up = latest['roc_14'] > 0
            momentum_down = latest['roc_14'] < 0

            # 1. Breakout Strategy (DISABLED due to low win-rate)
            # buffer = 0.001  # 0.1% early entry
            # is_breakout_up = price > latest['rolling_high_20']* (1 - buffer) and previous['close'] < latest['rolling_high_20']* (1 - buffer) and ema_slope > min_slope
            # is_breakout_down = price < latest['rolling_low_20']* (1 + buffer) and previous['close'] > latest['rolling_low_20']* (1 + buffer) and ema_slope > min_slope
            # vol_confirmed = latest['volume'] > latest['volume_sma_20']* getattr(self.config, 'VOLUME_SPIKE_MULTIPLIER', 1.5)
            
            # if is_breakout_up and vol_confirmed and htf_bullish and momentum_up:
            #     signal, strategy_name = "BUY", "Breakout UP"
            #     reason = f"{strategy_name} - Score: {score}"
            # elif is_breakout_down and vol_confirmed and htf_bearish and momentum_down:
            #     signal, strategy_name = "SELL", "Breakout DOWN"
            #     reason = f"{strategy_name} - Score: {score}"
            
            # 2. Pullback Strategy (Primary Entry)
            in_uptrend = latest['ema_21'] > latest['ema_50'] and ema_slope > min_slope
            pulled_back = previous['low'] <= latest['ema_21'] or latest['low'] <= latest['ema_21']
            resuming_up = price > latest['ema_9'] and price > previous['high'] and latest['close'] > latest['open']
            
            if signal == "HOLD" and in_uptrend and pulled_back and resuming_up and htf_bullish and momentum_up:
                signal, strategy_name = "BUY", "Pullback UP"
                reason = f"{strategy_name} - Score: {score}"
                
            in_downtrend = latest['ema_21'] < latest['ema_50'] and ema_slope > min_slope
            pulled_back_down = previous['high'] >= latest['ema_21'] or latest['high'] >= latest['ema_21']
            resuming_down = price < latest['ema_9'] and price < previous['low'] and latest['close'] < latest['open']
            
            if signal == "HOLD" and in_downtrend and pulled_back_down and resuming_down and htf_bearish and momentum_down:
                signal, strategy_name = "SELL", "Pullback DOWN"
                reason = f"{strategy_name} - Score: {score}"

        market_state = "TREND" if abs(latest['ema_21'] - latest['ema_50']) / price > getattr(self.config, 'EMA_SLOPE_THRESHOLD', 0.0005) else "RANGE"

        return {
            "signal": signal,
            "market_state": market_state,
            "strategy": strategy_name,
            "reason": reason,
            "confidence": confidence,
            "off_session": off_session,
            "atr_ratio": atr_ratio_val,
            "atr_value": atr_value
        }
