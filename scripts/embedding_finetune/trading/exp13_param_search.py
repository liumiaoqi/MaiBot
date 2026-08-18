#!/usr/bin/env python3
"""exp13: 参数寻优——不同股票的最优参数是否不同?有没有规律?

参数空间:
  窗口 window: 20 / 40 / 60(特征长度)
  学习率 lr: 0.02 / 0.05 / 0.1
  探索噪声 explore: 0.1 / 0.2
  -> 3x3x2 = 18 组合/股票
方法:每只股票训练段跑18组合,测试段测终值,找最优组合
问题:最优参数是否每只不同?和波动率/行业有关吗?
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001

# 第二批股票池(新建——第二批研究用)
POOL2 = {
    '600036': '招商银行', '600887': '伊利股份', '601398': '工商银行',
    '600050': '中国联通', '601668': '中国建筑', '600276': '恒瑞医药',
    '002415': '海康威视', '600031': '三一重工', '601899': '紫金矿业',
    '000858': '五粮液',
}

class TraderParam:
    """参数化 R-STDP(窗口/学习率/探索可调)"""
    def __init__(self, seed=42, lr=0.05, explore=0.2):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(2)]
        self.trace_pre = [0.0, 0.0]

    def step(self, rets, price, holding, cash, shares, bench):
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        feats = [ret1, 0.0]  # 简化:只用单日收益+趋势(保持简单)
        if len(rets) >= 21:
            feats[1] = (price - 0)  # 占位(趋势由外部算)
        sense_spikes = [1.0 if f > 0.3 else 0.0 for f in feats]
        noise = random.uniform(-self.explore, self.explore)
        a_b = self.w[0][0]*feats[0] + self.w[1][0]*feats[1] + noise
        a_s = self.w[0][1]*feats[0] + self.w[1][1]*feats[1] + noise
        a_h = self.w[0][2]*feats[0] + self.w[1][2]*feats[1] + noise
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
            for i in range(2):
                self.trace_pre[i] = self.trace_pre[i]*self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
        return action, holding, cash, shares

def run_params(code, window, lr, explore, initial=100.0, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderParam(seed=seed, lr=lr, explore=explore)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; h=False; c=initial; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-window:] if len(rets)>window else rets
            _, h, c, s = t.step(rets, p, h, c, s, initial*p/start_p)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    rets3=[]; h3=False; c3=initial; s3=0.0; prev3=None
    for p in tp:
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-window:] if len(rets3)>window else rets3
            _, h3, c3, s3 = t.step(rets3, p, h3, c3, s3, initial*p/start_t)
        prev3 = p
    return c3 + s3*tp[-1]

if __name__ == '__main__':
    windows = [20, 40, 60]
    lrs = [0.02, 0.05, 0.1]
    explores = [0.1, 0.2]
    print('=== 实验13: 参数寻优(窗口x学习率x探索=18组合/股票) ===')
    print('%-8s %20s %12s' % ('股票', '最优参数(w/lr/exp)', '最优终值'))
    results_all = {}
    for code, name in POOL2.items():
        best_val = -1; best_p = None
        for w in windows:
            for lr in lrs:
                for exp in explores:
                    val = run_params(code, w, lr, exp)
                    if val > best_val:
                        best_val = val; best_p = (w, lr, exp)
        results_all[code] = (best_p, best_val)
        print('%-8s   w=%d lr=%.2f exp=%.1f  %12.1f' % (name, best_p[0], best_p[1], best_p[2], best_val))
    # 统计最优参数分布
    from collections import Counter
    ws = Counter(p[0][0] for p in results_all.values())
    lrs_c = Counter(p[0][1] for p in results_all.values())
    exps = Counter(p[0][2] for p in results_all.values())
    print('\n最优窗口分布:', dict(ws))
    print('最优学习率分布:', dict(lrs_c))
    print('最优探索分布:', dict(exps))
    print('\n(若分布集中=通用参数存在;若分散=每只股票要单独调参)')