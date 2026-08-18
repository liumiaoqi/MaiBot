def make_features(df, window=20):
    import numpy as np
    close = df['close'].values
    rets = pd.Series(close).pct_change().values
    X, y = [], []
    for i in range(window, len(rets) - 1):
        window_rets = rets[i-window:i]
        if np.isnan(window_rets).any() or np.isnan(rets[i+1]):
            continue
        X.append(window_rets)
        y.append(1 if rets[i+1] > 0 else 0)
    return np.array(X), np.array(y)