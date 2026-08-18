#!/usr/bin/env python3
"""exp5: R-STDP 交易(对齐 exp2b 觅食)——v2 修复:输入放大+阈值降低"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001

class RSTDPTrader:
    def __init__(self, seed=42, lr=0.05):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(2)] for _ in range(2)]
        self.trace_pre = [0.0, 0.0]
        self.prev_value = 0.0

    def step(self, rets, price, holding, cash, shares, explore=True):
        # 1. 感知(放大:单日收益率 x100,让信号能推动动作)
        up = max(0.0, rets[-1] * 100) if len(rets) else 0.0
        down = max(0.0, -rets[-1] * 100) if len(rets) else 0.0
        sense_spikes = [1.0 if up > 0.5 else 0.0, 1.0 if down > 0.5 else 0.0]

        # 2. 动作决策 + 探索噪声
        noise = random.uniform(-0.2, 0.2) if explore else 0.0
        buy_act = self.w[0][0] * up + self.w[1][0] * down + noise
        sell_act = self.w[0][1] * up + self.w[1][1] * down + noise

        action = 'hold'
        if buy_act > 0.1 and not holding:
            action = 'buy'
        elif sell_act > 0.1 and holding:
            action = 'sell'

        # 3. 执行
        if action == 'buy' and cash > 0:
            shares = cash / price * (1 - COST)
            cash = 0.0
            holding = True
        elif action == 'sell' and holding:
            cash = shares * price * (1 - COST)
            shares = 0.0
            holding = False

        # 4. 符号奖励
        value = cash + shares * price
        reward = 1.0 if value > self.prev_value else -1.0
        self.prev_value = value

        # 5. R-STDP 更新
        buy_spike = 1.0 if action == 'buy' else 0.0
        sell_spike = 1.0 if action == 'sell' else 0.0
        for i in range(2):
            self.trace_pre[i] = self.trace_pre[i] * self.decay + sense_spikes[i]
            self.w[i][0] += self.lr * reward * self.trace_pre[i] * buy_spike
            self.w[i][1] += self.lr * reward * self.trace_pre[i] * sell_spike

        return action, holding, cash, shares

def run_rstdp(code, initial=100, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    # 训练段:学权重(带探索)
    trader = RSTDPTrader(seed=seed)
    prices = train['close'].values
    rets = []; holding = False; cash = initial; shares = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            if len(rets) > 20: rets = rets[-20:]
            _, holding, cash, shares = trader.step(rets, p, holding, cash, shares, explore=True)
        prev = p
    # 测试段:用学到的权重(继续小额探索)
    test_prices = test['close'].values
    rets3 = []; holding3 = False; cash3 = initial; shares3 = 0.0; prev3 = None
    for p in test_prices:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            if len(rets3) > 20: rets3 = rets3[-20:]
            _, holding3, cash3, shares3 = trader.step(rets3, p, holding3, cash3, shares3, explore=True)
        prev3 = p
    final = cash3 + shares3 * test_prices[-1]
    return final, trader.w

if __name__ == '__main__':
    print('=== 实验5v2: R-STDP 交易(输入放大+阈值降低) ===')
    print('%-8s %12s %12s' % ('股票', 'RSTDP终值', '满仓对照'))
    for code, name in POOL.items():
        final, w = run_rstdp(code)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        print('%-8s %12.1f %12.1f' % (name, final, full))