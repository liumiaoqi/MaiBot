#!/usr/bin/env python3
"""exp14: 完整流程跑第二批——参数寻优 + 政策先验 + 信度学习

验证:第一批的完整方法论(安全默认参数 + 政策先验 + 信度学习)
在第二批 10 只上是否也有效(不是只对第一批有效)。
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test

COST = 0.001

# 第二批股票池
POOL2 = {
    '600036': '招商银行', '600887': '伊利股份', '601398': '工商银行',
    '600050': '中国联通', '601668': '中国建筑', '600276': '恒瑞医药',
    '002415': '海康威视', '600031': '三一重工', '601899': '紫金矿业',
    '000858': '五粮液',
}

# 政策先验(时代年轮:十四五/十五五方向——当时可得)
# 银行(稳)/消费(促)/基建(稳)/医药(扶持)/科技(扶持)/有色(双碳)/白酒(消费)
PLAN_PRIOR = {'600036': 0.0, '600887': 0.5, '601398': 0.0, '600050': 0.3,
              '601668': 0.2, '600276': 0.5, '002415': 0.8, '600031': 0.5,
              '601899': 0.3, '000858': 0.5}

class TraderFull:
    """完整版:安全默认参数 + 政策先验 + 信度学习"""
    def __init__(self, seed=42, lr=0.02, explore=0.1):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
        self.trust = 1.0
        self.trace_pre = [0.0, 0.0, 0.0]

    def step(self, rets, price, prices_hist, plan, holding, cash, shares, bench):
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        plan_sig = plan * self.trust * 3.0
        feats = [ret1, trend, plan_sig]
        sense_spikes = [1.0 if f > 0.3 else 0.0 for f in feats]
        noise = random.uniform(-self.explore, self.explore)
        a_b = sum(self.w[i][0]*feats[i] for i in range(3)) + noise
        a_s = sum(self.w[i][1]*feats[i] for i in range(3)) + noise
        a_h = sum(self.w[i][2]*feats[i] for i in range(3)) + noise
        action = 'hold'
        if a_b > 0.1 and a_b > a_s and a_b > a_h and not holding: action = 'buy'
        elif a_s > 0.1 and a_s > a_b and a_s > a_h and holding: action = 'sell'
        if action == 'buy' and cash > 0:
            shares = cash / price * (1 - COST); cash = 0.0; holding = True
        elif action == 'sell' and holding:
            cash = shares * price * (1 - COST); shares = 0.0; holding = False
        value = cash + shares * price
        reward = 0.0
        if action in ('buy', 'sell'):
            reward = 1.0 if value >= bench else -1.0
        if reward != 0.0:
            act_idx = {'buy':0, 'sell':1, 'hold':2}[action]
            post = [0.0,0.0,0.0]; post[act_idx] = 1.0
            for i in range(3):
                self.trace_pre[i] = self.trace_pre[i]*self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
            self.trust = max(0.0, min(2.0, self.trust + self.lr * reward * 0.5 * abs(plan)))
        return action, holding, cash, shares

def run_full(code, window, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderFull(seed=seed)
    plan = PLAN_PRIOR.get(code, 0.0)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; hist=[]; h=False; c=100.0; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-window:] if len(rets)>window else rets
            hist.append(p); hist = hist[-40:] if len(hist)>40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s, 100.0*p/start_p)
        else: hist.append(p)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    rets3=[]; hist3=[]; h3=False; c3=100.0; s3=0.0; prev3=None
    for p in tp:
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-window:] if len(rets3)>window else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3)>40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3, 100.0*p/start_t)
        else: hist3.append(p)
        prev3 = p
    return c3 + s3*tp[-1], t.trust

if __name__ == '__main__':
    print('=== 实验14: 完整流程跑第二批(安全默认+政策先验+信度) ===')
    print('%-8s %12s %12s %10s' % ('股票', '完整AI', '满仓', '信度'))
    # 每只用实验13的最优窗口(或安全默认20)
    best_w = {'600036': 40, '600887': 20, '601398': 40, '600050': 20, '601668': 20,
              '600276': 20, '002415': 40, '600031': 40, '601899': 20, '000858': 20}
    results = {}
    for code, name in POOL2.items():
        vals = [run_full(code, best_w[code], seed=s)[0] for s in range(5)]
        avg = sum(vals)/len(vals)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1]/test['close'].iloc[0]
        results[name] = (avg, full)
        print('%-8s %12.1f %12.1f' % (name, avg, full))
    wins = sum(1 for a, f in results.values() if a > f)
    print(f'\n跑赢满仓: {wins}/{len(results)} 只')