import numpy as np
import torch
import torch.nn as nn
import snntorch as snn
from snntorch import surrogate, spikegen
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test, make_features

torch.manual_seed(42)
spike_grad = surrogate.fast_sigmoid(slope=25)

class SNNPredictor(nn.Module):
    """SNN: 输入收益率 -> 脉冲 -> Leaky 神经元 -> 读末态 -> 预测涨跌"""
    def __init__(self, input_size, hidden_size):
        super().__init__()
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.lif1 = snn.Leaky(beta=0.9, spike_grad=spike_grad)
        self.fc2 = nn.Linear(hidden_size, 1)

    def forward(self, x):
        # x: (batch, seq) -> 每个时间步喂一个收益率
        batch, seq = x.shape
        mem1 = self.lif1.init_leaky()
        for t in range(seq):
            cur1 = self.fc1(x[:, t:t+1])
            spk1, mem1 = self.lif1(cur1, mem1)
        out = self.fc2(mem1)  # 用末态膜电位预测
        return out.squeeze(-1)

def train_snn(X_tr, y_tr, X_te, y_te, hidden, epochs=30, lr=0.001):
    X_tr_t = torch.tensor(X_tr, dtype=torch.float32)
    y_tr_t = torch.tensor(y_tr, dtype=torch.float32)
    X_te_t = torch.tensor(X_te, dtype=torch.float32)

    model = SNNPredictor(input_size=1, hidden_size=hidden)
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

print('=== 实验3: SNN 监督式(和 LSTM 对比) ===')
print('%-8s %12s %10s %10s' % ('股票', 'SNN准确率', 'LSTM小', '线性'))
snn_results = {}
for code, name in POOL.items():
    df = load_stock(code)
    train, test = split_train_test(df)
    X_tr, y_tr = make_features(train, 20)
    X_te, y_te = make_features(test, 20)
    if len(X_tr) < 100 or len(X_te) < 100: continue
    try:
        acc, params = train_snn(X_tr, y_tr, X_te, y_te, hidden=16, epochs=20)
        snn_results[name] = acc
        print('%-8s %12.3f' % (name, acc))
    except Exception as e:
        print(f'{name}: 失败 {str(e)[:80]}')

# 对照表(从之前实验记录)
ref = {'贵州茅台': 0.539, '长江电力': 0.520, '中远海控': 0.485, '华夏幸福': 0.594,
       '平安银行': 0.554, '中国石油': 0.512, '中国石化': 0.470, '沪深300指数': 0.506}
print('\n=== SNN vs LSTM小 vs 线性 ===')
lin_ref = {'贵州茅台': 0.473, '长江电力': 0.520, '中远海控': 0.521, '华夏幸福': 0.482,
           '平安银行': 0.552, '中国石油': 0.512, '中国石化': 0.528, '沪深300指数': 0.495}
for name in POOL.values():
    if name in snn_results:
        print('%-8s SNN:%0.3f  LSTM:%0.3f  线性:%0.3f' % (name, snn_results[name], ref.get(name, 0), lin_ref.get(name, 0)))