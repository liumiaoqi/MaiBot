#!/usr/bin/env python3
"""exp7: 趋势特征 R-STDP——让 AI 感知大趋势(解决中石油式踏空)

v5 问题:输入只有单日收益率——学不到'大趋势上涨/下跌'
  → 中石油 2021-2026 先大涨后大跌,AI 学会了'涨就跑'(错过主升浪)

v6 改进:感知层加趋势特征:
  输入1: 单日收益(短期信号)
  输入2: 20日均线斜率(中期趋势)
  输入3: 60日均线斜率(长期趋势)
  → AI 能看到'大环境在涨/在跌',趋势中敢持有,反转时敢跑
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001

class TraderTrend:
    """趋势感知 R-STDP:3输入(短期/中期/长期)-> 3动作(买/卖/持有)"""
    def __init__(self, seed=42, lr=0.05):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
        self.trace_pre = [0.0, 0.0, 0.0]

    def step(self, rets, price, prices_hist, holding, cash, shares, bench_value, explore=True):
        # 感知:3个特征
        # 1. 单日收益(短期)
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        # 2. 20日均线斜率(中期趋势)
        ma20_slope = 0.0
        if len(prices_hist) >= 21:
            ma20_now = sum(prices_hist[-20:]) / 20
            ma20_prev = sum(prices_hist[-21:-1]) / 20
            ma20_slope = (ma20_now - ma20_prev) / ma20_prev * 100
        # 3. 60日均线斜率(长期趋势)
        ma60_slope = 0.0
        if len(prices_hist) >= 61:
            ma60_now = sum(prices_hist[-60:]) / 60
            ma60_prev = sum(prices_hist[-61:-1]) / 60
            ma60_slope = (ma60_now - ma60_prev) / ma60_prev * 100

        feats = [ret1, ma20_slope, ma60_slope]
        # 脉冲化:特征>阈值发脉冲
        sense_spikes = [1.0 if abs(f) > 0.5 else 0.0 for f in feats]
        # 动作(用连续值算激活)
        noise = random.uniform(-0.2, 0.2) if explore else 0.0
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
        # 基准奖励(跑赢买入持有=+1)
        reward = 0.0
        if action in ('buy', 'sell'):
            reward = 1.0 if value >= bench_value else -1.0
        if reward != 0.0:
            act_idx = {'buy':0, 'sell':1, 'hold':2}[action]
            post = [0.0,0.0,0.0]; post[act_idx] = 1.0
            for i in range(3):
                self.trace_pre[i] = self.trace_pre[i]*self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
        return action, holding, cash, shares

def run_trend(code, initial=100.0, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderTrend(seed=seed)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; hist=[]; h=False; c=initial; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-20:] if len(rets)>20 else rets
            hist.append(p); hist = hist[-80:] if len(hist)>80 else hist
            _, h, c, s = t.step(rets, p, hist, h, c, s, initial*p/start_p, explore=True)
        else:
            hist.append(p)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    rets3=[]; hist3=[]; h3=False; c3=initial; s3=0.0; prev3=None
    for i, p in enumerate(tp):
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-20:] if len(rets3)>20 else rets3
            hist3.append(p); hist3 = hist3[-80:] if len(hist3)>80 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, h3, c3, s3, initial*p/start_t, explore=True)
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3*tp[-1]

if __name__ == '__main__':
    print('=== 实验7: 趋势特征 R-STDP(短期+中期+长期) ===')
    print('%-8s %12s %12s %12s' % ('股票', '趋势RSTDP', 'v5基准奖励', '满仓对照'))
    v5 = {'贵州茅台': 70.8, '长江电力': 176.0, '中远海控': 278.9, '华夏幸福': 9.4,
          '平安银行': 65.8, '中国石油': 106.7, '中国石化': 100.0, '沪深300指数': 100.0}
    for code, name in POOL.items():
        final = run_trend(code)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1]/test['close'].iloc[0]
        print('%-8s %12.1f %12.1f %12.1f' % (name, final, v5.get(name, 0), full))