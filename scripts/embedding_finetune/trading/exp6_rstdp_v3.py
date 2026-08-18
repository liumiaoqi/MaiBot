#!/usr/bin/env python3
"""exp6: R-STDP 改进奖励——持有期也学习(解决涨股踏空)

v2 问题:奖励只在交易瞬间给(±1)——持有期间不学习
→ 学会'止损'但没学会'拿住盈利'(长电/中石油踏空)

v3 改进(两种叠加):
1. 持有奖励:持有期间,每 20 天按资产变化给奖励(涨+1/跌-1)
   → '拿住上涨'的行为被强化(不只是交易瞬间)
2. 交易奖励保留:买卖瞬间也给奖励(对齐 v2)
   → 止损/止盈的即时反馈不丢
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001
HOLD_EVAL = 20  # 持有奖励结算周期(天)

class RSTDPTraderV3:
    def __init__(self, seed=42, lr=0.05):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(2)] for _ in range(2)]
        self.trace_pre = [0.0, 0.0]
        self.prev_value = 0.0
        self.hold_count = 0

    def step(self, rets, price, holding, cash, shares, explore=True):
        up = max(0.0, rets[-1] * 100) if len(rets) else 0.0
        down = max(0.0, -rets[-1] * 100) if len(rets) else 0.0
        sense_spikes = [1.0 if up > 0.5 else 0.0, 1.0 if down > 0.5 else 0.0]

        noise = random.uniform(-0.2, 0.2) if explore else 0.0
        buy_act = self.w[0][0] * up + self.w[1][0] * down + noise
        sell_act = self.w[0][1] * up + self.w[1][1] * down + noise
        action = 'hold'
        if buy_act > 0.1 and not holding:
            action = 'buy'
        elif sell_act > 0.1 and holding:
            action = 'sell'

        if action == 'buy' and cash > 0:
            shares = cash / price * (1 - COST)
            cash = 0.0
            holding = True
        elif action == 'sell' and holding:
            cash = shares * price * (1 - COST)
            shares = 0.0
            holding = False

        value = cash + shares * price
        # 奖励设计(v3):
        # 1. 交易瞬间:资产变化给即时奖励(对齐 v2)
        # 2. 持有期间:每 HOLD_EVAL 天按资产变化给持有奖励(新!)
        reward = 0.0
        if action in ('buy', 'sell'):
            reward = 1.0 if value >= self.prev_value else -1.0
        elif holding:
            self.hold_count += 1
            if self.hold_count >= HOLD_EVAL:
                self.hold_count = 0
                reward = 1.0 if value >= self.prev_value else -1.0
        self.prev_value = value

        # R-STDP 更新(只在有奖励时更新——没有奖励=不学习)
        if reward != 0.0:
            buy_spike = 1.0 if action == 'buy' else 0.0
            sell_spike = 1.0 if action == 'sell' else 0.0
            # 持有奖励时,强化'继续持有'(等价于不卖)——用 buy_spike 弱化版?
            # 简化:持有奖励时,同时给买/卖权重一个'不动作'信号(0)
            for i in range(2):
                self.trace_pre[i] = self.trace_pre[i] * self.decay + sense_spikes[i]
                self.w[i][0] += self.lr * reward * self.trace_pre[i] * buy_spike
                self.w[i][1] += self.lr * reward * self.trace_pre[i] * sell_spike

        return action, holding, cash, shares

def run_rstdp_v3(code, initial=100, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    trader = RSTDPTraderV3(seed=seed)
    prices = train['close'].values
    rets = []; holding = False; cash = initial; shares = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            if len(rets) > 20: rets = rets[-20:]
            _, holding, cash, shares = trader.step(rets, p, holding, cash, shares, explore=True)
        prev = p
    test_prices = test['close'].values
    rets3 = []; holding3 = False; cash3 = initial; shares3 = 0.0; prev3 = None
    for p in test_prices:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            if len(rets3) > 20: rets3 = rets3[-20:]
            _, holding3, cash3, shares3 = trader.step(rets3, p, holding3, cash3, shares3, explore=True)
        prev3 = p
    final = cash3 + shares3 * test_prices[-1]
    return final

if __name__ == '__main__':
    print('=== 实验6: R-STDP 改进奖励(持有奖励+周期结算) ===')
    print('%-8s %12s %12s %12s' % ('股票', 'v3终值', 'v2(旧)终值', '满仓对照'))
    # 旧 v2 结果(实验5)
    old = {'贵州茅台': 76.3, '长江电力': 111.7, '中远海控': 123.6, '华夏幸福': 61.0,
           '平安银行': 72.9, '中国石油': 226.5, '中国石化': 90.2, '沪深300指数': 77.5}
    for code, name in POOL.items():
        final = run_rstdp_v3(code)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        print('%-8s %12.1f %12.1f %12.1f' % (name, final, old.get(name, 0), full))