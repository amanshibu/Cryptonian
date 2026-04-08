import time
from config import Config
from agents.data_agent import DataFetchAgent
from agents.strategy_agent import StrategyAgent
from agents.decision_agent import DecisionAgent
from agents.execution_agent import ExecutionAgent
from agents.learning_agent import LearningAgent
from execution.paper import PaperExecution
from execution.live import LiveExecution

def run_live(config: Config, testnet: bool = True):
    print("========================================")
    mode_name = "PAPER TRADING (TESTNET)" if testnet else "LIVE TRADING"
    print(f" Starting {mode_name}")
    print("========================================")
    
    # Initialize appropriate execution client
    if testnet:
        execution_client = PaperExecution(config)
    else:
        execution_client = LiveExecution(config)
        
    # Initialize Agents
    data_agent = DataFetchAgent(config, execution_client=execution_client)
    strategy_agent = StrategyAgent(config)
    decision_agent = DecisionAgent(config)
    execution_agent = ExecutionAgent(data_agent, execution_client=execution_client)
    learning_agent = LearningAgent(config)
    
    symbol = config.TRADING_PAIR
    timeframe = config.TIMEFRAME
    
    print(f"Target Asset: {symbol}")
    print(f"Timeframe: {timeframe}")
    print("System Running... Press Ctrl+C to stop.")
    
    try:
        while True:
            # 1. Fetch Data
            df = data_agent.fetch_ohlcv(symbol, timeframe)
            df_higher = data_agent.fetch_ohlcv(symbol, config.HIGHER_TIMEFRAME)
            current_price = data_agent.get_current_price(symbol)
            current_balance = data_agent.get_balance()

            spread_pct = execution_agent.get_spread_pct(symbol)
            
            # 2. Strategy Analysis
            strategy_output = strategy_agent.analyze(df, df_higher, spread_pct=spread_pct)
            
            if strategy_output['signal'] != "HOLD":
                print(
                    f"[Pipeline] Signal={strategy_output['signal']} | "
                    f"Confidence={strategy_output.get('confidence', 0):.2f} | "
                    f"Market={strategy_output.get('market_state', '?')} | "
                    f"Spread={spread_pct:.3f}% | "
                    f"Reason: {strategy_output.get('reason', '')}"
                )
            
            # 3. Decision Making
            adaptive_params = learning_agent.get_adaptive_parameters()
            decision = decision_agent.formulate_decision(strategy_output, current_price, current_balance, adaptive_params)
            
            # 4. Execution
            if decision["action"] != "HOLD":
                order_result = execution_agent.execute_trade(decision)
                
                # 5. Learning/Logging
                if order_result["status"] == "success":
                    learning_agent.log_trade(order_result)

            # Metrics Print
            metrics = adaptive_params.get("metrics", {})
            if metrics.get("trades", 0) > 0 and decision["action"] != "HOLD":
                print(
                    f"[Metrics] Trades={metrics['trades']} | "
                    f"WR={metrics['win_rate']:.1f}% | "
                    f"Streak W/L={metrics.get('consecutive_wins', 0)}/{metrics.get('consecutive_losses', 0)} | "
                    f"Size x{metrics.get('size_multiplier', 1.0):.2f} | "
                    f"Total PnL={decision_agent.daily_pnl:.2f}"
                )
            
            # Sleep for timeframe (e.g. 1m = 60s)
            time.sleep(60) 
            
    except KeyboardInterrupt:
        print(f"\nShutting down {mode_name} System.")
        if decision_agent.daily_pnl != 0:
            print(f"Final session PnL: {decision_agent.daily_pnl:.2f}")
