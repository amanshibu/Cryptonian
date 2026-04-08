import time
import pandas as pd
import ccxt

from config import Config
from agents.data_agent import DataFetchAgent
from agents.strategy_agent import StrategyAgent
from agents.decision_agent import DecisionAgent
from agents.execution_agent import ExecutionAgent
from agents.learning_agent import LearningAgent
from execution.backtest import BacktestExecution

class BacktestEngine:
    def __init__(self, config: Config):
        self.config = config
        self.execution = BacktestExecution(config)
        
        print("========================================")
        print(" Initializing Backtest Engine")
        print("========================================")
        
        # Initialize Agents with the new injected execution layer
        self.data_agent = DataFetchAgent(config, execution_client=self.execution)
        self.strategy_agent = StrategyAgent(config)
        self.decision_agent = DecisionAgent(config)
        self.execution_agent = ExecutionAgent(self.data_agent, execution_client=self.execution)
        self.learning_agent = LearningAgent(config)

    def fetch_historical_data(self, symbol, timeframe, total_candles=1000):
        """Downloads historical OHLCV data by paginating through CCXT in batches."""
        print(f"[BacktestEngine] Downloading {total_candles} candles for {symbol} at {timeframe}...")
        exchange = ccxt.binance({'enableRateLimit': True})
        
        all_ohlcv = []
        batch_size = 1000  # Binance max per request
        fetched = 0
        since = None  # Start from most recent and go backwards? No — CCXT fetches forward from 'since'.
        
        # If no 'since', CCXT returns the most recent candles.
        # To get MORE candles, we paginate forward from an older timestamp.
        # Strategy: first fetch without 'since' to get the latest batch,
        # then compute how far back we need to go.
        
        import time as _time
        
        # Calculate how far back to start based on timeframe
        tf_seconds = {
            '1m': 60, '3m': 180, '5m': 300, '15m': 900, '30m': 1800,
            '1h': 3600, '2h': 7200, '4h': 14400, '6h': 21600, '8h': 28800,
            '12h': 43200, '1d': 86400, '3d': 259200, '1w': 604800,
        }
        candle_duration = tf_seconds.get(timeframe, 60)
        now_ms = int(_time.time() * 1000)
        start_ms = now_ms - (total_candles * candle_duration * 1000)
        since = start_ms
        
        try:
            while fetched < total_candles:
                batch = min(batch_size, total_candles - fetched)
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=batch)
                if not ohlcv:
                    break
                all_ohlcv.extend(ohlcv)
                fetched += len(ohlcv)
                # Move 'since' forward to after the last candle
                since = ohlcv[-1][0] + (candle_duration * 1000)
                print(f"[BacktestEngine]   ...fetched {fetched}/{total_candles} candles")
                if len(ohlcv) < batch:
                    break  # No more data available
                    
            df = pd.DataFrame(all_ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.drop_duplicates(subset='timestamp').reset_index(drop=True)
            print(f"[BacktestEngine] Total candles loaded: {len(df)}")
            return df
        except Exception as e:
            print(f"[BacktestEngine] Data error: {e}")
            return None

    def run(self, df_main=None, df_higher=None):
        symbol = self.config.TRADING_PAIR
        timeframe = self.config.TIMEFRAME
        higher_tf = self.config.HIGHER_TIMEFRAME
        candle_count = getattr(self.config, 'BACKTEST_CANDLES', 1000)
        
        if df_main is None:
            df_main = self.fetch_historical_data(symbol, timeframe, total_candles=candle_count)
        if df_higher is None:
            higher_candle_count = max(candle_count // 5, 200)
            df_higher = self.fetch_historical_data(symbol, higher_tf, total_candles=higher_candle_count)

        if df_main is None or len(df_main) < 150:
            print("[BacktestEngine] Not enough data to backtest.")
            return

        print(f"[BacktestEngine] Loaded {len(df_main)} candles. Starting Simulation...")
        
        # PRE-CALCULATE INDICATORS (Vectorized for maximum speed)
        print("[BacktestEngine] Pre-calculating indicators...")
        df_main = self.strategy_agent.add_indicators(df_main)
        if df_higher is not None:
            df_higher = self.strategy_agent.add_indicators(df_higher)

        total_candles = len(df_main)
        
        # Metrics Tracking
        win_trades = 0
        loss_trades = 0
        total_pnl = 0.0
        max_balance = self.execution.get_balance()
        min_balance = max_balance
        start_balance = max_balance
        
        max_trades = getattr(self.config, 'MAX_TRADES', 0)
        trades_executed = 0
        
        # If MAX_TRADES is 0 or not set, iterate all candles
        end_index = total_candles
        if max_trades > 0:
            end_index = min(total_candles, 100 + max_trades)

        print("[BacktestEngine] Running lightning fast loop...")
        for i in range(100, end_index):
            # Pass only the 2 current required rows to StrategyAgent 
            # to avoid the overhead of copying and indicator calculations
            current_candle = df_main.iloc[i-1]
            previous_candle = df_main.iloc[i-2]
            current_price = current_candle['close']
            
            # For higher timeframe we just supply the most recently closed candle
            current_ts = current_candle['timestamp']
            
            # 1. Update Execution Layer State
            self.execution.update_state(current_price, None, None)

            # 2. Pipeline Execution simplified for backtest
            balance = self.execution.get_balance()
            spread_pct = self.execution.get_spread_pct(symbol)

            # Fast analyze path
            strategy_output = self.strategy_agent.analyze_fast(current_candle, previous_candle, df_higher, current_ts, spread_pct=spread_pct)
            
            # Print periodic logs (don't log HOLDs to avoid terminal spam)
            if strategy_output['signal'] != "HOLD":
                print(
                    f"[{current_ts}] [Strategy] Signal: {strategy_output['signal']} | "
                    f"Confidence: {strategy_output.get('confidence', 0):.2f}"
                )

            adaptive_params = self.learning_agent.get_adaptive_parameters()
            decision = self.decision_agent.formulate_decision(strategy_output, current_price, balance, adaptive_params)
            
            if decision['action'] != "HOLD":
                print(f"[{current_ts}] [Decision] Approved | Size: {decision.get('amount_usdt', 0):.2f} USDT")
                
                order_result = self.execution_agent.execute_trade(decision)
                
                if order_result['status'] == "success":
                    print(f"[{current_ts}] [Execution] Order placed - {decision['action']}")
                    trades_executed += 1
                    
                    self.learning_agent.log_trade(order_result)
                    
                    # Update metrics manually simulating PnL change directly in engine
                    pnl = self.decision_agent.daily_pnl
                    total_pnl = pnl
                    current_bal = start_balance + total_pnl
                    if current_bal > max_balance: max_balance = current_bal
                    if current_bal < min_balance: min_balance = current_bal

        # Post-Backtest Metrics
        print("\n========================================")
        print("[Backtest Complete]")
        print("========================================")
        
        params = self.learning_agent.get_adaptive_parameters()
        metrics = params.get("metrics", {})
        win_rate = metrics.get("win_rate", 0.0)
        
        total_profit = self.learning_agent.total_profit
        total_loss_abs = self.learning_agent.total_loss
        profit_factor = (total_profit / total_loss_abs) if total_loss_abs > 0 else float('inf')
        
        drawdown = ((max_balance - min_balance) / max_balance) * 100 if max_balance > 0 else 0
        return_pct = (total_pnl / start_balance) * 100 if start_balance > 0 else 0
        
        print(f"Trades: {trades_executed}")
        print(f"Win Rate: {win_rate:.1f}%")
        print(f"Profit Factor: {profit_factor:.2f}")
        print(f"Return: {return_pct:+.2f}%")
        print(f"Max Drawdown: {drawdown:.2f}%")
        print(f"Final Balance: ${start_balance + total_pnl:.2f}")
        print("========================================\n")

        return {
            "Trades": trades_executed,
            "Win Rate": win_rate,
            "Profit Factor": profit_factor,
            "Return": return_pct,
            "Max Drawdown": drawdown,
            "Final Balance": start_balance + total_pnl
        }

    @classmethod
    def run_optimization(cls, config: Config):
        print("\n========================================")
        print(" Starting Backtest Optimization Loop")
        print("========================================")
        
        temp_engine = cls(config)
        symbol = config.TRADING_PAIR
        timeframe = config.TIMEFRAME
        candle_count = getattr(config, 'BACKTEST_CANDLES', 1000)
        
        print("[Optimization] Fetching dataset once...")
        df_main = temp_engine.fetch_historical_data(symbol, timeframe, total_candles=candle_count)
        higher_candle_count = max(candle_count // 5, 200)
        df_higher = temp_engine.fetch_historical_data(symbol, config.HIGHER_TIMEFRAME, total_candles=higher_candle_count)
        
        if df_main is None or len(df_main) < 150:
            print("Not enough data to optimize.")
            return

        confidences = [0.5, 0.55, 0.6]
        atr_multipliers = [0.2, 0.5, 0.8]

        results = []
        import builtins
        import copy

        for conf in confidences:
            for atr_m in atr_multipliers:
                print(f"[Optimization] Testing config: CONF_THRESH={conf}, ATR_MULT={atr_m} ...")
                
                class OptConfig(Config):
                    CONFIDENCE_THRESHOLD = conf
                    ATR_THRESHOLD_MULTIPLIER = atr_m
                
                engine = cls(OptConfig())
                
                # Suppress trace prints during optimization
                original_print = builtins.print
                builtins.print = lambda *args, **kwargs: None
                try:
                    stats = engine.run(df_main=df_main.copy(), df_higher=df_higher.copy())
                finally:
                    builtins.print = original_print
                
                stats['CONFIDENCE_THRESHOLD'] = conf
                stats['ATR_THRESHOLD_MULTIPLIER'] = atr_m
                results.append(stats)
                print(f"   -> PF: {stats['Profit Factor']:.2f} | WR: {stats['Win Rate']:.1f}% | DD: {stats['Max Drawdown']:.2f}% | Trades: {stats['Trades']}")

        print("\n========================================")
        print(" Optimization Results")
        print("========================================")
        
        # Best config = PF > 1.3, DD < 15, Max Return
        valid = [r for r in results if r['Profit Factor'] >= 1.0 and r['Max Drawdown'] <= 15.0 and r['Trades'] >= 10]
        if not valid:
            print("No configuration met minimum viable criteria (PF>1, DD<15.0%, Trades>10).")
            valid = [r for r in results if r['Trades'] >= 10]

        best = None
        if valid:
            best = sorted(valid, key=lambda x: x['Return'], reverse=True)[0]
            print(f"🏆 BEST CONFIGURATION:")
            print(f"CONFIDENCE_THRESHOLD = {best['CONFIDENCE_THRESHOLD']}")
            print(f"ATR_THRESHOLD_MULTIPLIER = {best['ATR_THRESHOLD_MULTIPLIER']}")
            print(f"Produces -> Return: {best['Return']:+.2f}% | PF: {best['Profit Factor']:.2f} | DD: {best['Max Drawdown']:.2f}%")
        else:
            print("No profitable configurations found with decent trade volume.")
        
        return best

