#!/usr/bin/env python3
"""生成各策略测试段净值曲线数据(预测派 vs 决策派 vs 规则)"""

import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

OUT = r'E:\Users\lmq\Documents\finance\trading_curves'
os.makedirs(OUT, exist_ok=True)

# 1) 满仓基准净值(测试段)
# 2) 定投净值(规则)
# 3) R-STDP v5 净值(决策派)
# 4) LSTM 预测交易净值(预测派)

from sklearn.linear_model import LogisticRegression
import torch
import torch.nn as nn

class LSTMPredictor(nn.Module):
    def __init__(self, input_size, hidden_size=16):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :]).squeeze(-1)

def train_lstm(X_tr, y_tr):
    X_t = torch.tensor(X_tr, dtype=torch.float32).unsqueeze(-1)
    y_t = torch.tensor(y_tr, dtype=torch.float32)
    m = LSTMPredictor(1)
    opt = torch.optim.Adam(m.parameters(), lr=0.001)
    loss_fn = nn.BCEWithLogitsLoss()
    for _ in range(20):
        opt.zero_grad(); loss = loss_fn(m(X_t), y_t); loss.backward(); opt.step()
    return m

def make_features(df, window=20):
    close = df['close'].values
    rets = pd.Series(close).pct_change().values
    X, y = [], []
    for i in range(window, len(rets)-1):
        wr = rets[i-window:i]
        if np.isnan(wr).any() or np.isnan(rets[i+1]): continue
        X.append(wr); y.append(1 if rets[i+1] > 0 else 0)
    return np.array(X), np.array(y)

def simulate_pred(pred, close, initial=100.0):
    cash = initial; shares = 0.0; holding = False
    curve = np.zeros(len(close))
    for i, p in enumerate(close):
        if i < len(pred):
            if pred[i] == 1 and not holding and cash > 0:
                shares = cash/p*(1-0.001); cash = 0.0; holding = True
            elif pred[i] == 0 and holding:
                cash = shares*p*(1-0.001); shares = 0.0; holding = False
        curve[i] = cash + shares*p
    return curve

def lstm_curve(df):
    train, test = split_train_test(df)
    X_tr, y_tr = make_features(train)
    X_te, y_te = make_features(test)
    m = train_lstm(X_tr, y_tr)
    with torch.no_grad():
        X_t = torch.tensor(X_te, dtype=torch.float32).unsqueeze(-1)
        probs = torch.sigmoid(m(X_t)).numpy()
    pred = (probs > 0.5).astype(int).flatten()
    close = test['close'].values[20:]
    return simulate_pred(pred, close)

# R-STDP v5(从 exp6v5 import)
from exp6v5_bench import TraderBench
def rstdp_curve(df):
    train, test = split_train_test(df)
    t = TraderBench(seed=42)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; h=False; c=100.0; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-20:] if len(rets)>20 else rets
            _, h, c, s = t.step(rets, p, h, c, s, 100.0*p/start_p, explore=True)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    curve = np.zeros(len(tp))
    rets3=[]; h3=False; c3=100.0; s3=0.0; prev3=None
    for i, p in enumerate(tp):
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-20:] if len(rets3)>20 else rets3
            _, h3, c3, s3 = t.step(rets3, p, h3, c3, s3, 100.0*p/start_t, explore=True)
        else:
            c3 = 100.0; s3 = 0.0; h3 = False
        curve[i] = c3 + s3*p
        prev3 = p
    return curve

if __name__ == '__main__':
    print('生成净值曲线数据...')
    for code, name in POOL.items():
        df = load_stock(code)
        train, test = split_train_test(df)
        close = test['close'].values
        # 满仓
        full = 100.0 * close / close[0]
        # 定投(规则)
        n = len(close)
        dca = np.zeros(n); shares_d = 0.0; invested = 0.0
        for i in range(n):
            if i % 21 == 0:
                amt = 100.0/(n//21+1)
                shares_d += amt/close[i]*(1-0.001); invested += amt
            dca[i] = shares_d*close[i]
        # LSTM
        try:
            lstm_curve_val = lstm_curve(df)
            lstm_norm = lstm_curve_val / lstm_curve_val[0] * 100 if len(lstm_curve_val) > 0 else full
            # 对齐长度
            if len(lstm_norm) < n:
                lstm_norm = np.concatenate([np.full(n-len(lstm_norm), 100.0), lstm_norm])
        except Exception as e:
            print(f'{name} LSTM失败: {str(e)[:50]}')
            lstm_norm = full
        # R-STDP
        try:
            rst = rstdp_curve(df)
            rst_norm = rst / rst[0] * 100 if rst[0] > 0 else full
        except Exception as e:
            print(f'{name} RSTDP失败: {str(e)[:50]}')
            rst_norm = full
        # 存 CSV(date, full, dca, lstm, rstdp)
        out = pd.DataFrame({'date': test['date'].values[:n], 'full': full, 'dca': dca,
                            'lstm': lstm_norm[:n], 'rstdp': rst_norm[:n]})
        out.to_csv(os.path.join(OUT, code + '_curves.csv'), index=False)
        print(f'{name}: 已保存({n} 天)')
    print('\n完成! 数据在:', OUT)