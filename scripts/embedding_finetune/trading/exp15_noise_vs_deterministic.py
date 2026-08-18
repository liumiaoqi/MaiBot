#!/usr/bin/env python3
"""exp15: 噪声注入 vs 确定性——输入噪声作为正则化资源

问题(用户洞察):"施加一些不确定因素要比试图掌控全局要好很多"
验证:训练阶段给输入特征加不同水平噪声(测试阶段干净),对 R-STDP 交易
    测试段收益的影响——噪声水平 0 = 确定性基线,>0 = 注入不确定。

设计:
- 噪声加在**输入特征**(ret1/trend/plan_sig),不是动作(explore 是动作噪声)
- 训练段加噪(像 dropout 的训练期),测试段不加(干净评估)
- 5 seeds 平均(RL 稳定性铁律)
- 对照:噪声 0.0/0.02/0.05/0.1/0.2 × 10 只股票(batch2)
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test

COST = 0.001

POOL2 = {
    '600036': '招商银行', '600887': '伊利股份', '601398': '工商银行',
    '600050': '中国联通', '601668': '中国建筑', '600276': '恒瑞医药',
    '002415': '海康威视', '600031': '三一重工', '601899': '紫金矿业',
    '000858': '五粮液',
}

PLAN_PRIOR = {'600036': 0.0, '600887': 0.5, '601398': 0.0, '600050': 0.3,
              '601668': 0.2, '600276': 0.5, '002415': 0.8, '600031': 0.5,
              '601899': 0.3, '000858': 0.5}

BEST_W = {'600036': 40, '600887': 20, '601398': 40, '600050': 20, '601668': 20,
          '600276': 20, '002415': 40, '600031': 40, '601899': 20, '000858': 20}


class TraderNoise:
    """R-STDP 交易员,支持训练期输入噪声注入。

    input_noise > 0 时:训练段每个特征加高斯噪声(探索特征空间)
    input_noise = 0 时:确定性基线(exp14 原样)
    探索率 explore 是动作噪声(选动作时扰动),与输入噪声独立。
    """

    def __init__(self, seed=42, lr=0.02, explore=0.1, input_noise=0.0):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.input_noise = input_noise
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
        self.trust = 1.0
        self.trace_pre = [0.0, 0.0, 0.0]

    def step(self, rets, price, prices_hist, plan, holding, cash, shares, bench,
             noisy=True):
        """noisy=True 训练段(加输入噪声);False 测试段(干净)。"""
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        plan_sig = plan * self.trust * 3.0
        feats = [ret1, trend, plan_sig]
        # 输入噪声注入(仅训练段)——高斯噪声,幅度 = input_noise * 特征量级
        if noisy and self.input_noise > 0.0:
            feats = [f + random.gauss(0.0, self.input_noise) for f in feats]
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


def run_noise(code, window, seed, input_noise):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderNoise(seed=seed, input_noise=input_noise)
    plan = PLAN_PRIOR.get(code, 0.0)

    # 训练段(加输入噪声)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-window:] if len(rets) > window else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s,
                                100.0 * p / prices[0], noisy=True)
        else:
            hist.append(p)
        prev = p

    # 测试段(干净,不加噪声)
    tp = test['close'].values
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-window:] if len(rets3) > window else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3,
                                   100.0 * p / tp[0], noisy=False)
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1]


if __name__ == '__main__':
    print('=== 实验15: 噪声注入 vs 确定性(输入噪声作为正则化资源) ===')
    print('噪声加在训练段输入特征(测试段干净);5 seeds 平均;batch2 10 只')
    NOISES = [0.0, 0.02, 0.05, 0.1, 0.2]
    header = '%-8s' % '股票'
    for n in NOISES:
        header += ' %10s' % ('noise=' + str(n))
    header += ' %10s' % '满仓'
    print(header)
    print('-' * len(header))

    agg = {n: [] for n in NOISES}
    for code, name in POOL2.items():
        row = '%-8s' % name
        df = load_stock(code)
        _, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        for n in NOISES:
            vals = [run_noise(code, BEST_W[code], seed=s, input_noise=n)
                    for s in range(5)]
            avg = sum(vals) / len(vals)
            agg[n].append(avg)
            row += ' %10.1f' % avg
        row += ' %10.1f' % full
        print(row)

    print('-' * len(header))
    # 汇总:每个噪声水平的平均终值 + 跑赢满仓数 + 相对基线的配对胜率
    print()
    print('=== 汇总 ===')
    base = agg[0.0]
    codes = list(POOL2.keys())
    fulls = {}
    for i, code in enumerate(codes):
        df = load_stock(code)
        _, test = split_train_test(df)
        fulls[code] = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
    for n in NOISES:
        mean = sum(agg[n]) / len(agg[n])
        wins = sum(1 for i, code in enumerate(codes) if agg[n][i] > fulls[code])
        beats = sum(1 for b, a in zip(base, agg[n], strict=True) if a > b)
        tag = ('  相对基线: %d/10 只跑赢' % beats) if n > 0.0 else ''
        print('noise=%5.2f  平均终值 %7.1f  跑赢满仓 %d/10%s' % (n, mean, wins, tag))
