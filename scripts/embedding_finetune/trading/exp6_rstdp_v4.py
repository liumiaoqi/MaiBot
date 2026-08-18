#!/usr/bin/env python3
"""exp6v2: R-STDP 三动作(买/卖/持有)——持有奖励真正落到权重

v3 问题:持有奖励发生时无 post_spike(没有买卖脉冲)→ 权重没更新
v4 修复:加第三个动作'持有'——持有奖励强化'持有'权重
  权重: 2 输入 -> 3 动作(买/卖/持有)
  持有奖励: reward=+1 时强化'持有'权重(拿住盈利被学习)
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001
HOLD_EVAL = 20

class RSTDPTraderV4:
    def __init__(self, seed=42, lr=0.05):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        # 2 输入(涨/跌) -> 3 动作(买/卖/持有)
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(2)]
        self.trace_pre = [0.0, 0.0]
        self.prev_value = 0.0
        self.hold_count = 0

    def step(self, rets, price, holding, cash, shares, explore=True):
        up = max(0.0, rets[-1] * 100) if len(rets) else 0.0
        down = max(0.0, -rets[-1] * 100) if len(rets) else 0.0
        sense_spikes = [1.0 if up > 0.5 else 0.0, 1.0 if down > 0.5 else 0.0]

        noise = random.uniform(-0.2, 0.2) if explore else 0.0
        act_buy = self.w[0][0] * up + self.w[1][0] * down + noise
        act_sell = self.w[0][1] * up + self.w[1][1] * down + noise
        act_hold = self.w[0][2] * up + self.w[1][2] * down + noise

        # 动作选择:三动作取最大(超过阈值才执行交易)
        action = 'hold'
        if act_buy > 0.1 and act_buy > act_sell and act_buy > act_hold and not holding:
            action = 'buy'
        elif act_sell > 0.1 and act_sell > act_buy and act_sell > act_hold and holding:
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
        # 奖励 + 动作脉冲(三动作都算)
        reward = 0.0
        if action == 'buy':
            reward = 1.0 if value >= self.prev_value else -1.0
        elif action == 'sell':
            reward = 1.0 if value >= self.prev_value else -1.0
        elif holding:
            self.hold_count += 1
            if self.hold_count >= HOLD_EVAL:
                self.hold_count = 0
                reward = 1.0 if value >= self.prev_value else -1.0
        self.prev_value = value

        if reward != 0.0:
            # 动作脉冲:买=0,卖=1,持有=2
            act_idx = {'buy': 0, 'sell': 1, 'hold': 2}[action]
            post = [0.0, 0.0, 0.0]
            post[act_idx] = 1.0
            for i in range(2):
                self.trace_pre[i] = self.trace_pre[i] * self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]

        return action, holding, cash, shares

def run_v4(code, initial=100, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    trader = RSTDPTraderV4(seed=seed)
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
    return cash3 + shares3 * test_prices[-1]

if __name__ == '__main__':
    print('=== 实验6v2: R-STDP 三动作(持有奖励真正生效) ===')
    print('%-8s %12s %12s %12s' % ('股票', 'v4终值', 'v2旧终值', '满仓对照'))
    old = {'贵州茅台': 76.3, '长江电力': 111.7, '中远海控': 123.6, '华夏幸福': 61.0,
           '平安银行': 72.9, '中国石油': 226.5, '中国石化': 90.2, '沪深300指数': 77.5}
    for code, name in POOL.items():
        final = run_v4(code)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        print('%-8s %12.1f %12.1f %12.1f' % (name, final, old.get(name, 0), full))