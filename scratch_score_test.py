import pandas as pd
import pandas_ta as ta
import ccxt

def test_score():
    exchange = ccxt.binance({'enableRateLimit': True})
    ohlcv = exchange.fetch_ohlcv('BTC/USDT', '5m', limit=1000)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    
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
    
    df = df.dropna()
    print(f"Total rows: {len(df)}")
    
    scores = []
    
    for i in range(1, len(df)):
        latest = df.iloc[i]
        price = latest['close']
        
        # Trend strength (0–30)
        trend_strength = abs(latest['ema_21'] - latest['ema_50']) / price
        score1 = min(trend_strength * 10000, 30) # Change multiplier from 1000 to 10000? Let's test 1000 first.
        score1_orig = min(trend_strength * 1000, 30)
        
        # Volume (0–25)
        vol_ratio = latest['volume'] / latest['volume_sma_20'] if latest['volume_sma_20'] > 0 else 1
        score2 = min(vol_ratio * 10, 25)
        
        # Volatility (0–20)
        atr_ratio = latest['atr_14'] / latest['atr_sma_14'] if latest['atr_sma_14'] > 0 else 1
        score3 = min(atr_ratio * 10, 20)
        
        # Momentum (0–25)
        roc = abs(latest['roc_14'])
        score4 = min(roc * 10, 25)
        
        scores.append((score1_orig, score2, score3, score4))
        
    df_scores = pd.DataFrame(scores, columns=['trend', 'vol', 'atr', 'roc'])
    print("Mean scores:")
    print(df_scores.mean())
    print("\nMax scores:")
    print(df_scores.max())
    print("\nTotal mean:", df_scores.sum(axis=1).mean())
    print("Total > 45:", (df_scores.sum(axis=1) > 45).sum())
    print("Total > 60:", (df_scores.sum(axis=1) > 60).sum())

if __name__ == '__main__':
    test_score()
