import argparse
from config import Config
from engine.backtest_engine import BacktestEngine
from engine.runner import run_live

def parse_args():
    parser = argparse.ArgumentParser(description="Cryptonian Multi-Mode Trading Engine")
    parser.add_argument("--mode", type=str, choices=["BACKTEST", "PAPER", "LIVE"],
                        default=None, help="Trading mode (overrides config)")
    parser.add_argument("--candles", type=int, default=None,
                        help="Number of candles to download for backtesting (e.g. 1000, 5000, 10000, 50000)")
    parser.add_argument("--timeframe", type=str, default=None,
                        help="Candle timeframe: 1m, 5m, 15m, 1h, 4h, 1d, 1w")
    parser.add_argument("--max-trades", type=int, default=None,
                        help="Max trades to execute (0 = unlimited)")
    parser.add_argument("--optimize", action="store_true",
                        help="Run backtest optimization loop")
    parser.add_argument("--balance", type=float, default=None,
                        help="Starting balance for backtest (default: 1000)")
    parser.add_argument("--pair", type=str, default=None,
                        help="Trading pair (e.g. BTC/USDT, ETH/USDT)")
    return parser.parse_args()

def main():
    args = parse_args()
    config = Config()
    
    # CLI overrides
    if args.mode:
        config.MODE = args.mode.upper()
    if args.candles:
        config.BACKTEST_CANDLES = args.candles
    if args.timeframe:
        config.TIMEFRAME = args.timeframe
    if args.max_trades is not None:
        config.MAX_TRADES = args.max_trades
    if args.balance:
        config.INITIAL_BALANCE = args.balance
    if args.pair:
        config.TRADING_PAIR = args.pair

    print("========================================")
    print(" Cryptonian Trading Engine")
    print("========================================")
    print(f" Mode:      {config.MODE}")
    print(f" Pair:      {config.TRADING_PAIR}")
    print(f" Timeframe: {config.TIMEFRAME}")
    if config.MODE == "BACKTEST":
        print(f" Candles:   {config.BACKTEST_CANDLES}")
        print(f" Max Trades:{config.MAX_TRADES if config.MAX_TRADES > 0 else 'Unlimited'}")
        print(f" Balance:   ${config.INITIAL_BALANCE:.2f}")
    print("========================================")

    if not config.BINANCE_API_KEY and config.MODE in ["PAPER", "LIVE"]:
        print("WARNING: BINANCE_API_KEY not set in .env. API calls will fail.")

    if config.MODE == "BACKTEST":
        if args.optimize:
            BacktestEngine.run_optimization(config)
        else:
            engine = BacktestEngine(config)
            engine.run()
        
    elif config.MODE == "PAPER":
        run_live(config, testnet=True)
        
    elif config.MODE == "LIVE":
        run_live(config, testnet=False)
        
    else:
        print(f"ERROR: Unknown MODE: {config.MODE}")
        print("Valid modes: BACKTEST, PAPER, LIVE")

if __name__ == "__main__":
    main()
