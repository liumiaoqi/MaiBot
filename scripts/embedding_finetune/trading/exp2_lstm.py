import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test, make_features

torch.manual_seed(42)

class LSTMPredictor(nn.Module):
    def __init__(self, input_size, hidden_size):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.fc = nn.Linear(hidden_size, 1)

    def forward(self, x):
        # x: (batch, seq, features) -> 每步一个特征(收益率)
        out, _ = self.lstm(x)
        out = self.fc(out[:, -1, :])
        return out.squeeze(-1)

def train_lstm(X_tr, y_tr, X_te, y_te, hidden, epochs=30, lr=0.001):
    # 数据形状: (N, seq) -> (N, seq, 1)
    X_tr_t = torch.tensor(X_tr, dtype=torch.float32).unsqueeze(-1)
    y_tr_t = torch.tensor(y_tr, dtype=torch.float32)
    X_te_t = torch.tensor(X_te, dtype=torch.float32).unsqueeze(-1)

    model = LSTMPredictor(input_size=1, hidden_size=hidden)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCEWithLogitsLoss()

    for epoch in range(epochs):
        model.train()
        opt.zero_grad()
        pred = model(X_tr_t)
        loss = loss_fn(pred, y_tr_t)
        loss.backward()
        opt.step()

    model.eval()
    with torch.no_grad():
        logits = model(X_te_t)
        pred_binary = (torch.sigmoid(logits) > 0.5).numpy().astype(int)
    acc = (pred_binary == y_te).mean()
    n_params = sum(p.numel() for p in model.parameters())
    return acc, n_params

print('=== 实验2: LSTM 非线性(小参数 vs 大参数) ===')
print('%-8s %12s %12s %10s %10s' % ('股票', '小LSTM准确率', '大LSTM准确率', '小参数量', '大参数量'))
results = []
for code, name in POOL.items():
    df = load_stock(code)
    train, test = split_train_test(df)
    X_tr, y_tr = make_features(train, 20)
    X_te, y_te = make_features(test, 20)
    if len(X_tr) < 100 or len(X_te) < 100: continue
    try:
        acc_small, params_small = train_lstm(X_tr, y_tr, X_te, y_te, hidden=16, epochs=20)
        acc_big, params_big = train_lstm(X_tr, y_tr, X_te, y_te, hidden=128, epochs=20)
        results.append((name, acc_small, acc_big, params_small, params_big))
        print('%-8s %12.3f %12.3f %10d %10d' % (name, acc_small, acc_big, params_small, params_big))
    except Exception as e:
        print(f'{name}: 失败 {str(e)[:60]}')

print('\n(对比:线性≈0.5;LSTM 若>0.55 说明非线性有效)')