import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BINANCE_API_KEY = os.getenv("BINANCE_API_KEY", "")
    BINANCE_SECRET = os.getenv("BINANCE_SECRET", "")
    
    # Execution Mode: "BACKTEST", "PAPER", or "LIVE"
    MODE = os.getenv("MODE", "BACKTEST").upper()
    
    # Backtest specific settings
    BACKTEST_CANDLES = 1000            # Number of candles to download (1000, 5000, 10000, 50000)
    BACKTEST_START_DATE = "2023-01-01 00:00:00"
    BACKTEST_END_DATE = "2024-01-01 00:00:00"
    TEST_DURATION_PRESETS = {"1m": 30, "6m": 180, "1y": 365}
    MAX_TRADES = 0                     # 0 = unlimited trades, otherwise cap at this number
    
    # Live/Paper settings. For legacy code, USE_TESTNET maps to MODE == "PAPER"
    USE_TESTNET = MODE == "PAPER"
    
    # Trading pairs and settings
    TRADING_PAIR = "BTC/USDT"
    TIMEFRAME = "1m" # 1 minute for faster testing
    HIGHER_TIMEFRAME = "5m" # Higher timeframe for trend confirmation
    TRADE_AMOUNT_USDT = 10.0 # Legacy fixed amount
    INITIAL_BALANCE = 1000.0 # Mock balance for dynamic sizing if API fails/testnet
    
    # Risk Management & Limits
    STOP_LOSS_PCT = 0.01  # 1.0% stop loss
    TAKE_PROFIT_PCT = 0.03 # 3% take profit (1:2 RR) — legacy, see TP1/TP2
    MAX_DAILY_LOSS_USDT = 500.0 # Increased daily loss limit to allow high capital usage
    RISK_PERCENT_PER_TRADE = 0.95 # Maximize Capital Usage! Trade 95% of total balance for massive numerical profit vs 5% before
    COOLDOWN_WIN_MINUTES = 5 # Pause trading for X minutes after a trade win
    COOLDOWN_LOSS_MINUTES = 15 # Pause trading for X minutes after a trade loss

    # ── NEW: Improvement 1 — No-Trade Zone Filter ──────────────────────
    ATR_THRESHOLD_MULTIPLIER = 0.5      # ATR must be > ATR_SMA * this to allow trading
    MAX_SPREAD_PCT = 0.15               # Max bid-ask spread as % of price

    # ── NEW: Improvement 2 — Time-Based Session Filter ─────────────────
    # Each tuple is (start_hour_utc, end_hour_utc). Trading allowed inside ANY window.
    TRADING_SESSION_HOURS = [(7, 16), (13, 21)]  # London + US sessions
    REDUCE_SIZE_OUTSIDE_SESSION = True
    OFF_SESSION_SIZE_MULTIPLIER = 0.5   # Halve position outside active sessions

    # ── NEW: Improvement 3 — Partial Take Profit ──────────────────────
    TP1_PCT = 0.015             # +1.5% → close first tranche
    TP1_CLOSE_FRACTION = 1.0    # Close 100% of position at TP1
    # ATR Multipliers for high mathematical edge + frequent sizing
    SL_ATR_MULTIPLIER = 5.0     # Safe breathing room against wicks
    TP1_ATR_MULTIPLIER = 5.0    # 1:1 risk reward for 1.50+ Profit Factor edge
    TP2_ATR_MULTIPLIER = 15.0
    TRAIL_SL_ATR_MULTIPLIER = 50.0 # Effectively disable trailing stop

    # ── NEW: Improvement 4 — Loss Streak Kill Switch ──────────────────
    LOSS_STREAK_LIMIT = 3               # Consecutive losses before kill switch
    KILL_SWITCH_COOLDOWN_MINUTES = 60   # Minutes to pause after kill switch

    # ── NEW: Improvement 5 — Trade Quality / Confidence Score ─────────
    CONFIDENCE_THRESHOLD = 0.65         # Pristine Entry Only
    EMA_SLOPE_THRESHOLD = 0.0005        # Min EMA slope as fraction of price
    VOLUME_SPIKE_MULTIPLIER = 1.5       # Volume must be > SMA * this multiplier

    # ── NEW: Improvement 6 — Learning Agent Adaptive Sizing ───────────
    ADAPTIVE_SIZE_INCREASE_RATE = 0.1   # Max 10% step up per evaluation
    ADAPTIVE_SIZE_MAX_MULTIPLIER = 1.5  # Cap at 150% of base risk
    ADAPTIVE_SIZE_MIN_MULTIPLIER = 0.5  # Floor at 50% of base risk
