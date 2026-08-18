#!/usr/bin/env python3
"""exp19: 量子信道式噪声 vs 高斯噪声——16 只新样本大规模验证

用户质疑:噪声不可自动化是否只是样本太少?量子式噪声(有结构)是否比高斯噪声更好?

量子真机噪声模型(Qiskit 内置 noise model 就是这三件)的经典模拟:
- depolar  退极化信道:以概率 p 把态变完全混合态 → 特征随机化为 uniform(-1,1)
- ampdamp  振幅阻尼信道:激发态以概率 p 衰减到基态 → 特征以概率 p 拉向 0
- bitflip  比特翻转信道:X 门噪声 → 特征以概率 p 翻转符号
对照:gauss 经典高斯噪声(exp15 用) + det 无噪声

16 只新样本(排除 batch1/2 共 18 只),统一 window=20/无先验(隔离变量)/5 seeds。
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test

COST = 0.001
WINDOW = 20

# 16 只新股票(行业多样,老股优先保证训练段数据足够)
POOL3 = {
    '000002': '万科A', '601318': '中国平安', '000333': '美的集团',
    '000651': '格力电器', '000568': '泸州老窖', '000538': '云南白药',
    '600019': '宝钢股份', '601088': '中国神华', '000725': '京东方A',
    '000063': '中兴通讯', '601012': '隆基绿能', '002594': '比亚迪',
    '600030': '中信证券', '601988': '中国银行', '600104': '上汽集团',
    '600585': '海螺水泥',
}


class TraderQNoise:
    """R-STDP + 可选量子信道式输入噪声(训练段,测试段干净)。"""

    def __init__(self, seed=42, lr=0.02, explore=0.1, noise_mode=None,
                 strength=0.02):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.noise_mode = noise_mode
        self.strength = strength
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
        self.trust = 1.0
        self.trace_pre = [0.0, 0.0, 0.0]

    def _noise(self, feats):
        p = self.strength
        mode = self.noise_mode
        if mode is None:
            return feats
        if mode == 'gauss':
            return [f + random.gauss(0.0, p) for f in feats]
        if mode == 'depolar':
            # 退极化:以概率 p 把每个特征随机化(完全混合态)
            return [random.uniform(-1.0, 1.0) if random.random() < p else f
                    for f in feats]
        if mode == 'ampdamp':
            # 振幅阻尼:以概率 p 把特征衰减到基态(0)
            return [0.0 if random.random() < p else f for f in feats]
        if mode == 'bitflip':
            # 比特翻转:以概率 p 翻转特征符号(X 门噪声)
            return [-f if random.random() < p else f for f in feats]
        return feats

    def step(self, rets, price, prices_hist, plan, holding, cash, shares, bench,
             noisy=True):
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        plan_sig = plan * self.trust * 3.0
        feats = [ret1, trend, plan_sig]
        if noisy:
            feats = self._noise(feats)
        sense_spikes = [1.0 if f > 0.3 else 0.0 for f in feats]
        noise = random.uniform(-self.explore, self.explore)
        a_b = sum(self.w[i][0] * feats[i] for i in range(3)) + noise
        a_s = sum(self.w[i][1] * feats[i] for i in range(3)) + noise
        a_h = sum(self.w[i][2] * feats[i] for i in range(3)) + noise
        action = 'hold'
        if a_b > 0.1 and a_b > a_s and a_b > a_h and not holding:
            action = 'buy'
        elif a_s > 0.1 and a_s > a_b and a_s > a_h and holding:
            action = 'sell'
        if action == 'buy' and cash > 0:
            shares = cash / price * (1 - COST); cash = 0.0; holding = True
        elif action == 'sell' and holding:
            cash = shares * price * (1 - COST); shares = 0.0; holding = False
        value = cash + shares * price
        reward = 0.0
        if action in ('buy', 'sell'):
            reward = 1.0 if value >= bench else -1.0
        if reward != 0.0:
            act_idx = {'buy': 0, 'sell': 1, 'hold': 2}[action]
            post = [0.0, 0.0, 0.0]
            post[act_idx] = 1.0
            for i in range(3):
                self.trace_pre[i] = self.trace_pre[i] * self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
            self.trust = max(0.0, min(2.0, self.trust + self.lr * reward * 0.5 * abs(plan)))
        return action, holding, cash, shares


def run_q(code, seed, mode, strength):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderQNoise(seed=seed, noise_mode=mode, strength=strength)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-WINDOW:] if len(rets) > WINDOW else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            _, h, c, s = t.step(rets, p, hist, 0.0, h, c, s,
                                100.0 * p / prices[0], noisy=True)
        else:
            hist.append(p)
        prev = p
    tp = test['close'].values
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-WINDOW:] if len(rets3) > WINDOW else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, 0.0, h3, c3, s3,
                                   100.0 * p / tp[0], noisy=False)
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1]


if __name__ == '__main__':
    print('=== exp19: 量子信道式噪声 vs 高斯噪声(16 只新样本) ===')
    print('模式: det(无) / gauss(高斯) / depolar(退极化) / ampdamp(振幅阻尼) / bitflip(比特翻转)')
    print('强度: 低=0.02 高=0.1;5 seeds 平均;window=20 无先验(隔离变量)\n')

    MODES = [('det', 0.0)] + [(m, s) for m in ['gauss', 'depolar', 'ampdamp', 'bitflip'] for s in [0.02, 0.1]]
    header = '%-8s' % '股票'
    for m, s in MODES:
        header += ' %10s' % (m if m == 'det' else m + str(s))
    header += ' %9s' % '满仓'
    print(header)
    print('-' * len(header))

    agg = {key: [] for key in [(m, s) for m, s in MODES]}
    fulls = {}
    for code, name in POOL3.items():
        df = load_stock(code)
        _, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        fulls[code] = full
        row = '%-8s' % name
        for m, s in MODES:
            vals = [run_q(code, seed=k, mode=m, strength=s) for k in range(5)]
            avg = sum(vals) / len(vals)
            agg[(m, s)].append(avg)
            row += ' %10.1f' % avg
        row += ' %9.1f' % full
        print(row)

    print('-' * len(header))
    print('\n=== 汇总(16 只) ===')
    base = agg[('det', 0.0)]
    for m, s in MODES:
        mean = sum(agg[(m, s)]) / len(agg[(m, s)])
        wins = sum(1 for i, code in enumerate(POOL3.keys()) if agg[(m, s)][i] > fulls[code])
        beats = sum(1 for b, a in zip(base, agg[(m, s)], strict=True) if a > b)
        gain = sum(a - b for b, a in zip(base, agg[(m, s)], strict=True)) / len(base)
        print('%-10s %5s 平均 %7.1f 跑赢满仓 %2d/16 跑赢基线 %2d/16 平均噪声收益 %+6.1f'
              % (m, ('-' if m == 'det' else s), mean, wins, beats, gain))
