#!/usr/bin/env python3
"""exp12: 时代年轮真实政策先验 + 信度学习

实验9/10的先验是我'事后拍的'(理想化)。
实验12:用'当时可得'的真实政策方向做先验——来自时代年轮调研的政策判断:
  十四五(2021-2025): 双碳/新能源扶持(+), 地产三道红线(-), 科技自主(+)
  十五五(2026): AI/算力/能源协同(+), 地产存量转型(-)
  -> 每只股票按'政策方向'给先验(不是事后涨跌,是当时政策就知道的)
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test

COST = 0.001

# 时代年轮政策先验(当时可得——十四五/十五五政策方向)
# 正=国家扶持(顺政策),负=国家调控(逆政策),0=中性
# 茅台(消费): 十四五促消费(+0.5) 长电(电力): 双碳/绿电(+1.0)
# 中远海控(航运): 非重点(0) 华夏幸福(地产): 三道红线(-1.0)
# 平安银行(银行): 中性偏稳(0) 中石油(石油): 双碳转型(-0.3)
# 中石化(石化): 双碳转型(-0.3) 沪深300: 综合(+0.3)
PLAN_PRIOR = {'600519': 0.5, '600900': 1.0, '601919': 0.0, '600340': -1.0,
              '000001': 0.0, '601857': -0.3, '600028': -0.3, '000300': 0.3}

class TraderPolicyTrust:
    """带政策先验信度学习的 R-STDP"""
    def __init__(self, seed=42, lr=0.05):
        random.seed(seed)
        self.lr = lr
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
        self.trust = 1.0  # 政策先验信度(可学习)
        self.trace_pre = [0.0, 0.0, 0.0]

    def step(self, rets, price, prices_hist, plan_prior, holding, cash, shares, bench, explore=True):
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        plan_sig = plan_prior * self.trust * 3.0
        feats = [ret1, trend, plan_sig]
        sense_spikes = [1.0 if f > 0.3 else 0.0 for f in feats]
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
            # 政策信度更新
            self.trust = max(0.0, min(2.0, self.trust + self.lr * reward * 0.5 * abs(plan_prior)))
        return action, holding, cash, shares

def run(code, initial=100.0, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderPolicyTrust(seed=seed)
    plan = PLAN_PRIOR.get(code, 0.0)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; hist=[]; h=False; c=initial; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-20:] if len(rets)>20 else rets
            hist.append(p); hist = hist[-40:] if len(hist)>40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s, initial*p/start_p, explore=True)
        else: hist.append(p)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    rets3=[]; hist3=[]; h3=False; c3=initial; s3=0.0; prev3=None
    for p in tp:
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-20:] if len(rets3)>20 else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3)>40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3, initial*p/start_t, explore=True)
        else: hist3.append(p)
        prev3 = p
    return c3 + s3*tp[-1], t.trust

if __name__ == '__main__':
    print('=== 实验12: 时代年轮真实政策先验 + 信度学习 ===')
    print('%-8s %12s %12s %12s %10s' % ('股票', '政策先验AI', '理想先验(10)', '纯数据(5)', '学到信度'))
    v10 = {'贵州茅台': 76.2, '长江电力': 169.9, '中远海控': 370.1, '华夏幸福': 26.3,
           '平安银行': 100.0, '中国石油': 135.0, '中国石化': 151.6, '沪深300指数': 101.6}
    v5 = {'贵州茅台': 70.8, '长江电力': 176.0, '中远海控': 278.9, '华夏幸福': 9.4,
          '平安银行': 65.8, '中国石油': 106.7, '中国石化': 100.0, '沪深300指数': 100.0}
    for code, name in POOL.items():
        final, trust = run(code)
        df = load_stock(code)
        train, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1]/test['close'].iloc[0]
        print('%-8s %12.1f %12.1f %12.1f %10.2f' % (name, final, v10.get(name,0), v5.get(name,0), trust))