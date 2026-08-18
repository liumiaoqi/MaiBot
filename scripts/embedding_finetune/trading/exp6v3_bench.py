#!/usr/bin/env python3
"""exp6v3: 快速验证——长周期持有奖励 + 基准对照奖励"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test

COST = 0.001

class TraderV5:
    """奖励 = 资产变化 - 同期买入持有收益(超过基准才算好)"""
    def __init__(self, seed=42, lr=0.05, eval_period=60):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(2)]
        self.trace_pre = [0.0, 0.0]
        self.prev_value = 0.0
        self.prev_bench = 0.0
        self.count = 0
        self.eval_period = eval_period

    def step(self, rets, price, holding, cash, shares, bench_price, explore=True):
        up = max(0.0, rets[-1] * 100) if len(rets) else 0.0
        down = max(0.0, -rets[-1] * 100) if len(rets) else 0.0
        sense_spikes = [1.0 if up > 0.5 else 0.0, 1.0 if down > 0.5 else 0.0]
        noise = random.uniform(-0.2, 0.2) if explore else 0.0
        a_b = self.w[0][0]*up + self.w[1][0]*down + noise
        a_s = self.w[0][1]*up + self.w[1][1]*down + noise
        a_h = self.w[0][2]*up + self.w[1][2]*down + noise
        action = 'hold'
        if a_b > 0.1 and a_b > a_s and a_b > a_h and not holding: action = 'buy'
        elif a_s > 0.1 and a_s > a_b and a_s > a_h and holding: action = 'sell'
        if action == 'buy' and cash > 0:
            shares = cash / price * (1 - COST); cash = 0.0; holding = True
        elif action == 'sell' and holding:
            cash = shares * price * (1 - COST); shares = 0.0; holding = False
        value = cash + shares * price
        # 基准:买入持有(从训练开始假设满仓)
        self.count += 1
        reward = 0.0
        if action in ('buy', 'sell') or (holding and self.count % self.eval_period == 0):
            # 相对基准奖励:跑赢基准=+1,跑输=-1
            bench = 100.0 * bench_price / bench_price  # 简化:基准=初始资金持满仓
            reward = 1.0 if value >= self.prev_value else -1.0
            self.prev_value = value
        if reward != 0.0:
            act_idx = {'buy':0, 'sell':1, 'hold':2}[action]
            post = [0.0,0.0,0.0]; post[act_idx] = 1.0
            for i in range(2):
                self.trace_pre[i] = self.trace_pre[i]*self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
        return action, holding, cash, shares

def run(code):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderV5(seed=42)
    # 训练
    prices = train['close'].values
    rets=[]; h=False; c=100.0; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-20:] if len(rets)>20 else rets
            _, h, c, s = t.step(rets, p, h, c, s, p, explore=True)
        prev = p
    # 测试
    tp = test['close'].values
    rets3=[]; h3=False; c3=100.0; s3=0.0; prev3=None
    for p in tp:
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-20:] if len(rets3)>20 else rets3
            _, h3, c3, s3 = t.step(rets3, p, h3, c3, s3, p, explore=True)
        prev3 = p
    return c3 + s3*tp[-1]

for code, name in {'600900':'长江电力','600519':'贵州茅台','601919':'中远海控'}.items():
    df = load_stock(code)
    train, test = split_train_test(df)
    full = 100 * test['close'].iloc[-1]/test['close'].iloc[0]
    final = run(code)
    print(f'{name}: v5={final:.1f} 满仓={full:.1f}')