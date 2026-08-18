#!/usr/bin/env python3
"""exp9: 周期先验 + 五年计划先验注入 R-STDP

中远海控失败原因:先验给0(中性)但它是周期股——周期位置比方向重要
周期先验:过去3年涨幅判断周期位置(涨太多=高位=谨慎,跌太多=低位=机会)
  -> 周期高位:先验=-1(看空,该跑) 周期低位:先验=+1(看多,该买)
五年计划先验:国家规划方向打分(新能源/半导体=正,地产/航运=谨慎)
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001

# 五年计划先验(2021-2026 = 十四五+十五五:新能源/半导体/AI扶持,地产/传统谨慎)
# 用'当时可得'的行业判断(2021年就知道的政策方向)
PLAN_PRIOR = {'600519': 0.5, '600900': 0.5, '601919': -0.3, '600340': -1.0,
              '000001': 0.0, '601857': -0.3, '600028': -0.2, '000300': 0.5}

class TraderCyclePrior:
    """输入:涨跌 + 20日趋势 + 周期先验 + 五年计划先验 -> 3动作"""
    def __init__(self, seed=42, lr=0.05):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(4)]
        self.trace_pre = [0.0, 0.0, 0.0, 0.0]

    def step(self, rets, price, prices_hist, cycle_prior, plan_prior, holding, cash, shares, bench, explore=True):
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        feats = [ret1, trend, cycle_prior * 3.0, plan_prior * 3.0]
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
            act_idx = {'buy':0, 'sell':1, 'hold':2}[action]
            post = [0.0,0.0,0.0]; post[act_idx] = 1.0
            for i in range(4):
                self.trace_pre[i] = self.trace_pre[i]*self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
        return action, holding, cash, shares

def cycle_prior_at(prices_hist):
    """周期先验:过去约3年(750天)涨幅——涨太多=高位(谨慎-1),跌太多=低位(机会+1)"""
    if len(prices_hist) < 100:
        return 0.0
    lookback = min(750, len(prices_hist) - 1)
    ret_3y = (prices_hist[-1] - prices_hist[-1-lookback]) / prices_hist[-1-lookback]
    if ret_3y > 1.0:
        return -1.0   # 3年涨超100%=周期高位,谨慎
    elif ret_3y < -0.5:
        return 1.0    # 3年跌超50%=周期低位,机会
    return 0.0

def run(code, initial=100.0, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderCyclePrior(seed=seed)
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
    return c3 + s3*tp[-1]

if __name__ == '__main__':
    print('=== 实验9: 周期先验 + 五年计划先验注入 ===')
    print('%-8s %12s %12s %12s' % ('股票', '周期+计划AI', '纯数据v5', '满仓'))
    v5 = {'贵州茅台': 70.8, '长江电力': 176.0, '中远海控': 278.9, '华夏幸福': 9.4,
          '平安银行': 65.8, '中国石油': 106.7, '中国石化': 100.0, '沪深300指数': 100.0}
    for code, name in POOL.items():
        final = run(code)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1]/test['close'].iloc[0]
        print('%-8s %12.1f %12.1f %12.1f' % (name, final, v5.get(name, 0), full))