#!/usr/bin/env python3
"""exp34: QSNN——复振幅量子神经元 R-STDP(SNN 线 × 量子线收官)

量子神经元(学术真实方向):神经元状态 = 复平面单位圆上的点(用户熟悉的复平面!)
- 权重 = 相位旋转角 φ(酉变换=旋转,永远在圆上,天然防饱和)
- 激活:输入特征累加相位 phase = Σ φ_i·f_i,复振幅 e^{i·phase}
- 发放概率 = |振幅|² = sin²(phase)(量子测量语义)
- R-STDP 学习:奖励调制相位更新 Δφ_i = lr·reward·trace_i·f_i

三个量子神经元(buy/sell/hold)各 3 相位权重,动作 = 概率采样(量子测量风格)。
对比:经典 R-STDP(exp15 det 基线)vs QSNN——6 只代表股 × 5 seeds(大随机种子)。
"""

import math
import random
import sys
import os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test

COST = 0.001
WINDOW = 20
BIG_SEEDS = [254114614, 345602646, 133291536, 599850706, 909712711]

STOCKS = [('601088', '中国神华'), ('601919', '中远海控'), ('601899', '紫金矿业'),
          ('000858', '五粮液'), ('600276', '恒瑞医药'), ('600036', '招商银行')]


class QSNN:
    """复振幅量子脉冲网络:3 神经元(buy/sell/hold),相位权重,奖励调制。

    修复(初版 93.9 vs 经典 131.5 失败后):
    1. 相位 wrap 到 [-π, π]——保持"在圆上"语义,防 sin² 高频震荡
    2. 特征 tanh 归一化——总相位有界,不超 π
    3. 发放阈值——p>0.25 才动(量子测量 + 阈值混合,降交易频率)
    """

    def __init__(self, seed=42, lr=0.05, explore=0.1):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.decay = 0.9
        # 初始相位放大(±1.5):防止随机相位互相抵消导致死寂(exp5 v1 同款坑)
        self.phi = [[random.uniform(-1.5, 1.5) for _ in range(3)] for _ in range(3)]
        self.trace = [[0.0, 0.0, 0.0] for _ in range(3)]

    def fire_prob(self, action, feats):
        """发放概率 = sin²(总相位)——量子测量语义。"""
        phase = sum(self.phi[action][i] * feats[i] for i in range(3))
        return math.sin(phase) ** 2

    def act(self, feats):
        """量子测量:发放概率超阈值才动作,否则 hold;概率采样选动作。"""
        ps = [self.fire_prob(a, feats) for a in range(3)]
        # 加动作噪声(探索)
        ps = [p + random.uniform(-self.explore, self.explore) for p in ps]
        # 只有概率 > 阈值(0.25)的动作候选(量子测量 + 阈值混合)
        candidates = [a for a in range(3) if ps[a] > 0.1]
        if not candidates:
            return 2  # 全部低发放 → hold(量子"未坍缩到动作"语义)
        # 概率采样(softmax 化防负)——e 与 candidates 对齐
        e = [math.exp(ps[a]) for a in candidates]
        total = sum(e)
        r = random.random() * total
        acc = 0.0
        for a, ea in zip(candidates, e, strict=True):
            acc += ea
            if r <= acc:
                return a
        return candidates[-1]

    def learn(self, reward, action, feats):
        """R-STDP 相位学习:Δφ = lr·reward·trace·f,相位 wrap 回 [-π, π]。"""
        for i in range(3):
            self.trace[action][i] = (self.trace[action][i] * self.decay
                                     + feats[i])
            self.phi[action][i] += (self.lr * reward
                                    * self.trace[action][i] * feats[i])
            # wrap 到 [-π, π]:保持相位在圆上的语义(周期学习)
            if self.phi[action][i] > math.pi:
                self.phi[action][i] -= 2 * math.pi
            elif self.phi[action][i] < -math.pi:
                self.phi[action][i] += 2 * math.pi


def run_qsnn(code, seed):
    df = load_stock(code)
    train, test = split_train_test(df)
    net = QSNN(seed=seed)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-WINDOW:] if len(rets) > WINDOW else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            ret1 = math.tanh(rets[-1] * 50)
            trend = math.tanh((p - hist[-21]) / hist[-21] * 20) if len(hist) >= 21 else 0.0
            feats = [ret1, trend, 0.0]
            a = net.act(feats)
            if a == 0 and not h and c > 0:
                s = c / p * (1 - COST); c = 0.0; h = True
            elif a == 1 and h:
                c = s * p * (1 - COST); s = 0.0; h = False
            val = c + s * p
            reward = 0.0
            if a in (0, 1):
                reward = 1.0 if val >= 100.0 * p / prices[0] else -1.0
                net.learn(reward, a, feats)
        else:
            hist.append(p)
        prev = p
    # 测试段(冻结相位,不再学习)
    tp = test['close'].values
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-WINDOW:] if len(rets3) > WINDOW else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            ret1 = math.tanh(rets3[-1] * 50)
            trend = math.tanh((p - hist3[-21]) / hist3[-21] * 20) if len(hist3) >= 21 else 0.0
            feats = [ret1, trend, 0.0]
            a = net.act(feats)
            if a == 0 and not h3 and c3 > 0:
                s3 = c3 / p * (1 - COST); c3 = 0.0; h3 = True
            elif a == 1 and h3:
                c3 = s3 * p * (1 - COST); s3 = 0.0; h3 = False
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1]


def run_classic(code, seed):
    """经典 R-STDP 基线(exp15 TraderNoise det 逻辑,内联)。"""
    from exp19_quantum_noise import TraderQNoise
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderQNoise(seed=seed, noise_mode=None)
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
    print('=== exp34: QSNN 复振幅量子神经元 R-STDP vs 经典 R-STDP ===')
    print('6 只代表股 × 5 大随机种子;相位学习 = 复平面旋转(天然防饱和)\n')
    print('%-8s %12s %12s %12s' % ('股票', '经典R-STDP', 'QSNN', '满仓'))
    print('-' * 46)
    qs_vals = []
    cl_vals = []
    for code, name in STOCKS:
        df = load_stock(code)
        _, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        qs = [run_qsnn(code, seed) for seed in BIG_SEEDS]
        cl = [run_classic(code, seed) for seed in BIG_SEEDS]
        qm = sum(qs) / len(qs)
        cm = sum(cl) / len(cl)
        qs_vals.append(qm)
        cl_vals.append(cm)
        print('%-8s %12.1f %12.1f %12.1f' % (name, cm, qm, full))
    print('-' * 46)
    print('平均: 经典 %7.1f vs QSNN %7.1f' % (
        sum(cl_vals) / len(cl_vals), sum(qs_vals) / len(qs_vals)))
    beats = sum(1 for c, q in zip(cl_vals, qs_vals, strict=True) if q > c)
    print('QSNN 跑赢经典: %d/6 只' % beats)
