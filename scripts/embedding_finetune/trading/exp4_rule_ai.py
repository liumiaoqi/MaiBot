import numpy as np
import torch
import torch.nn as nn
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test, make_features

torch.manual_seed(42)
COST = 0.001

class LSTMPredictor(nn.Module):
    def __init__(self, input_size, hidden_size=16):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :]).squeeze(-1)

def train_lstm(X_tr, y_tr):
    X_tr_t = torch.tensor(X_tr, dtype=torch.float32).unsqueeze(-1)
    y_tr_t = torch.tensor(y_tr, dtype=torch.float32)
    model = LSTMPredictor(input_size=1)
    opt = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_fn = nn.BCEWithLogitsLoss()
    for epoch in range(20):
        opt.zero_grad()
        loss = loss_fn(model(X_tr_t), y_tr_t)
        loss.backward()
        opt.step()
    return model

def get_ai_signal(model, X_te):
    """AI 输出每个时间点的看涨概率(0-1)。"""
    model.eval()
    with torch.no_grad():
        X_t = torch.tensor(X_te, dtype=torch.float32).unsqueeze(-1)
        probs = torch.sigmoid(model(X_t)).numpy()
    return probs

def simulate_dca_ai(close, probs, initial=100, monthly=1.0, strength=0.5):
    """规则定投 + AI 调仓位:每月固定买,AI 信号高时多买/低时少买。
    strength=0: 纯规则(每月固定)  strength>0: AI 调整幅度"""
    cash = initial
    shares = 0
    n = len(close)
    for i in range(n):
        if i % 21 == 0:  # 每月定投点
            # AI 调整:prob>0.5 多买,<0.5 少买(strength 控制调整幅度)
            prob = probs[i] if i < len(probs) else 0.5
            adjust = 1.0 + strength * (prob - 0.5) * 2  # 0.5+strength*[-1,1]
            amt = monthly * adjust
            if cash >= amt:
                shares += amt / close[i] * (1 - COST)
                cash -= amt
    return cash + shares * close[-1]

if __name__ == '__main__':
    print('=== 实验4: 规则定投 + AI调仓(LSTM信号) ===')
    print('%-8s %10s %10s %10s %10s' % ('股票', '纯规则', 'AI弱(0.3)', 'AI中(0.7)', 'AI强(1.0)'))
    for code, name in POOL.items():
        df = load_stock(code)
        train, test = split_train_test(df)
        X_tr, y_tr = make_features(train, 20)
        X_te, y_te = make_features(test, 20)
        if len(X_tr) < 100 or len(X_te) < 100: continue
        # 注意:probs 对应 X_te 的行(从第20天开始),需对齐 close
        model = train_lstm(X_tr, y_tr)
        probs = get_ai_signal(model, X_te)
        close = test['close'].values[20:]  # 对齐特征起点
        r0 = simulate_dca_ai(close, probs, strength=0)
        r1 = simulate_dca_ai(close, probs, strength=0.3)
        r2 = simulate_dca_ai(close, probs, strength=0.7)
        r3 = simulate_dca_ai(close, probs, strength=1.0)
        print('%-8s %10.1f %10.1f %10.1f %10.1f' % (name, r0, r1, r2, r3))

    print('\n(若 AI 调仓 > 纯规则,说明 AI 信号有增量价值;否则规则就够)')