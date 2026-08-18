#!/usr/bin/env python3
"""exp10: 先验信度学习——AI 自己学'该信多少先验'

实验8/9问题:先验权重固定(×3.0)——中远海控先验错了,AI 被迫信错
实验10:加'先验信度'权重 w_trust——R-STDP 根据奖励自动调整
  先验信号 = prior × w_trust(信度可学)
  如果先验导致亏钱(reward=-1): w_trust 降低(少信它)
  如果先验导致赚钱(reward=+1): w_trust 提高(多信它)
  -> AI 学会'该信多少先验'——错的先验自动被忽略
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001

class TraderTrust:
    """带先验信度学习的 R-STDP:输入(涨跌+趋势+周期+计划)+ 信度可调"""
    def __init__(self, seed=42, lr=0.05):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        # 动作权重:4输入(涨跌/趋势/周期/计划)-> 3动作
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(4)]
        # 先验信度:2个先验(周期/计划)各一个可学习信度(初始 1.0=全信)
        self.trust = [1.0, 1.0]
        self.trace_pre = [0.0, 0.0, 0.0, 0.0]
        # 记录上次先验对奖励的贡献(用于更新信度)
        self.last_prior_vals = [0.0, 0.0]

    def step(self, rets, price, prices_hist, cycle_prior, plan_prior, holding, cash, shares, bench, explore=True):
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        # 先验信号 = 先验值 × 信度(可学习)
        cyc_sig = cycle_prior * self.trust[0] * 3.0
        plan_sig = plan_prior * self.trust[1] * 3.0
        feats = [ret1, trend, cyc_sig, plan_sig]
        sense_spikes = [1.0 if f > 0.3 else 0.0 for f in feats]
        noise = random.uniform(-0.2, 0.2) if explore else 0.0
        a_b = sum(self.w[i][0]*feats[i] for i in range(4)) + noise
        a_s = sum(self.w[i][1]*feats[i] for i in range(4)) + noise
        a_h = sum(self.w[i][2]*feats[i] for i in range(4)) + noise
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
            # 1. 更新动作权重(同前)
            act_idx = {'buy':0, 'sell':1, 'hold':2}[action]
            post = [0.0,0.0,0.0]; post[act_idx] = 1.0
            for i in range(4):
                self.trace_pre[i] = self.trace_pre[i]*self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
            # 2. 更新先验信度:交易时先验信号是否导致好结果
            #    reward>0: 信度微升; reward<0: 信度微降(错的先验被弱化)
            self.trust[0] = max(0.0, min(2.0, self.trust[0] + self.lr * reward * 0.5 * abs(cycle_prior)))
            self.trust[1] = max(0.0, min(2.0, self.trust[1] + self.lr * reward * 0.5 * abs(plan_prior)))
        return action, holding, cash, shares

def cycle_prior_at(prices_hist):
    if len(prices_hist) < 100: return 0.0
    lookback = min(750, len(prices_hist) - 1)
    ret_3y = (prices_hist[-1] - prices_hist[-1-lookback]) / prices_hist[-1-lookback]
    if ret_3y > 1.0: return -1.0
    elif ret_3y < -0.5: return 1.0
    return 0.0

PLAN_PRIOR = {'600519': 0.5, '600900': 0.5, '601919': -0.3, '600340': -1.0,
              '000001': 0.0, '601857': -0.3, '600028': -0.2, '000300': 0.5}

def run(code, initial=100.0, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderTrust(seed=seed)
    plan = PLAN_PRIOR.get(code, 0.0)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; hist=[]; h=False; c=initial; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-20:] if len(rets)>20 else rets
            hist.append(p); hist = hist[-800:] if len(hist)>800 else hist
            cp = cycle_prior_at(hist)
            _, h, c, s = t.step(rets, p, hist, cp, plan, h, c, s, initial*p/start_p, explore=True)
        else: hist.append(p)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    rets3=[]; hist3=[]; h3=False; c3=initial; s3=0.0; prev3=None
    for p in tp:
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-20:] if len(rets3)>20 else rets3
            hist3.append(p); hist3 = hist3[-800:] if len(hist3)>800 else hist3
            cp = cycle_prior_at(hist3)
            _, h3, c3, s3 = t.step(rets3, p, hist3, cp, plan, h3, c3, s3, initial*p/start_t, explore=True)
        else: hist3.append(p)
        prev3 = p
    return c3 + s3*tp[-1], t.trust

if __name__ == '__main__':
    print('=== 实验10: 先验信度学习(该信多少先验由AI自己学) ===')
    print('%-8s %12s %12s %12s %14s' % ('股票', '信度AI', '固定先验(9)', '纯数据(5)', '学到信度'))
    v9 = {'贵州茅台': 77.3, '长江电力': 164.9, '中远海控': 249.6, '华夏幸福': 36.9,
          '平安银行': 49.9, '中国石油': 137.2, '中国石化': 168.4, '沪深300指数': 95.0}
    v5 = {'贵州茅台': 70.8, '长江电力': 176.0, '中远海控': 278.9, '华夏幸福': 9.4,
          '平安银行': 65.8, '中国石油': 106.7, '中国石化': 100.0, '沪深300指数': 100.0}
    for code, name in POOL.items():
        final, trust = run(code)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1]/test['close'].iloc[0]
        print('%-8s %12.1f %12.1f %12.1f  周期%.2f 计划%.2f' % (name, final, v9.get(name,0), v5.get(name,0), trust[0], trust[1]))