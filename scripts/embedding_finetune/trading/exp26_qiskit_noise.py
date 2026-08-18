#!/usr/bin/env python3
"""exp26: 真·Qiskit 量子信道噪声——特征过量子电路(修正 exp19 的数学模拟)

用户指出:exp19-25 用 numpy 手写量子信道公式是"数学等价模拟",没真用 Qiskit。
本实验:真的用 qiskit_aer.noise 的量子信道对象(depolarizing/amplitude_damping/
pauli-X 翻转)构造噪声模型,让每个特征走一遍 1-qubit 量子电路:
  f --(tanh+缩放)--> theta --RY(theta)--> |psi> --量子信道--> 测量 P(1) --atanh--> f'

映射链:f ∈ R → θ=(tanh(f)+1)·π/2 ∈ [0,π] → 电路测量 → f'=atanh(2P(1)-1) ∈ R
查表优化:预计算网格 [-3,3] 步长 0.005 的噪声后特征,插值查表(O(1) 运行时)
对比:det / qiskit 三信道 / numpy 版(exp19 同参数)——一致性 + 效果
运行:uv run --project E:/Users/lmq/qiskit python exp26_qiskit_noise.py
"""

import math
import random
import sys
import os
import statistics
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator
from qiskit_aer.noise import (NoiseModel, depolarizing_error,
                              amplitude_damping_error, pauli_error)

COST = 0.001
WINDOW = 20
SHOTS = 1024
GRID = np.linspace(-3.0, 3.0, 1201)

# 6 只代表股(神华受益/海控修复/紫金受害/五粮液翻盘/恒瑞/招商)
STOCKS = [('601088', '中国神华'), ('601919', '中远海控'), ('601899', '紫金矿业'),
          ('000858', '五粮液'), ('600276', '恒瑞医药'), ('600036', '招商银行')]
BIG_SEEDS = [254114614, 345602646, 133291536, 599850706, 909712711,
             626987273, 82965397, 243151793, 119999097, 326006810]


def build_lookup(channel, p):
    """预计算量子信道噪声映射表:GRID -> 噪声后特征。"""
    nm = NoiseModel()
    if channel == 'depolar':
        err = depolarizing_error(p, 1)
    elif channel == 'ampdamp':
        err = amplitude_damping_error(p)
    elif channel == 'bitflip':
        err = pauli_error([('X', p), ('I', 1.0 - p)])
    else:
        raise ValueError(channel)
    nm.add_quantum_error(err, ['ry'], [0])
    sim = AerSimulator(noise_model=nm)
    out = np.zeros(len(GRID))
    for i, f in enumerate(GRID):
        theta = (math.tanh(float(f)) + 1.0) * math.pi / 2.0
        qc = QuantumCircuit(1, 1)
        qc.ry(theta, 0)
        qc.measure(0, 0)
        counts = sim.run(transpile(qc, sim), shots=SHOTS).result().get_counts()
        p1 = counts.get('1', 0) / SHOTS
        out[i] = math.atanh(max(-0.999, min(0.999, 2.0 * p1 - 1.0)))
    return out


class TraderQChannel:
    """R-STDP + Qiskit 量子信道噪声(训练段查表,测试段干净)。"""

    def __init__(self, seed, lookup=None, noise_mode=None, strength=0.02):
        random.seed(seed)
        self.lr = 0.02
        self.explore = 0.1
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
        self.trust = 1.0
        self.trace_pre = [0.0, 0.0, 0.0]
        self.lookup = lookup
        self.noise_mode = noise_mode
        self.strength = strength

    def _qnoise(self, f):
        """查表:特征 -> Qiskit 量子信道输出。"""
        idx = int(np.searchsorted(GRID, f))
        idx = max(0, min(len(GRID) - 1, idx))
        return float(self.lookup[idx])

    def step(self, rets, price, prices_hist, plan, holding, cash, shares, bench,
             noisy=True):
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        plan_sig = plan * self.trust * 3.0
        feats = [ret1, trend, plan_sig]
        if noisy and self.noise_mode is not None:
            # 量子信道:特征 -> 量子态 -> 信道 -> 测量 -> 特征
            feats = [self._qnoise(f) for f in feats]
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


def run_qchannel(code, seed, lookup, mode, strength):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderQChannel(seed=seed, lookup=lookup, noise_mode=mode, strength=strength)
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
    print('=== exp26: 真·Qiskit 量子信道噪声(特征过量子电路) ===')
    print('构建查表(1201 点 × 3 信道,shots=1024)...')
    lookups = {}
    for ch, p in [('depolar', 0.1), ('ampdamp', 0.02), ('bitflip', 0.02)]:
        print('  信道 %s p=%s ...' % (ch, p))
        lookups[ch] = build_lookup(ch, p)
    print('查表完成\n')

    MODES = [('det', None, 0.0)] + [(ch, ch, p) for ch, p in
                                    [('depolar', 0.1), ('ampdamp', 0.02), ('bitflip', 0.02)]]
    header = '%-8s' % '股票'
    for m, _, _ in MODES:
        header += ' %12s' % m
    header += ' %9s' % '满仓'
    print(header)
    print('-' * len(header))

    agg = {m: [] for m, _, _ in MODES}
    fulls = {}
    for code, name in STOCKS:
        df = load_stock(code)
        _, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        fulls[code] = full
        row = '%-8s' % name
        for m, ch, p in MODES:
            vals = []
            for seed in BIG_SEEDS[:5]:  # 5 seeds 足够本验证
                if ch is None:
                    random.seed(seed)
                    from exp19_quantum_noise import TraderQNoise
                    t = TraderQNoise(seed=seed, noise_mode=None)
                    df2 = load_stock(code)
                    train2, test2 = split_train_test(df2)
                    prices = train2['close'].values
                    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
                    for p2 in prices:
                        if prev is not None:
                            rets.append(p2 / prev - 1)
                            rets = rets[-WINDOW:] if len(rets) > WINDOW else rets
                            hist.append(p2); hist = hist[-40:] if len(hist) > 40 else hist
                            _, h, c, s = t.step(rets, p2, hist, 0.0, h, c, s,
                                                100.0 * p2 / prices[0], noisy=True)
                        else:
                            hist.append(p2)
                        prev = p2
                    tp = test2['close'].values
                    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
                    for p2 in tp:
                        if prev3 is not None:
                            rets3.append(p2 / prev3 - 1)
                            rets3 = rets3[-WINDOW:] if len(rets3) > WINDOW else rets3
                            hist3.append(p2); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
                            _, h3, c3, s3 = t.step(rets3, p2, hist3, 0.0, h3, c3, s3,
                                                   100.0 * p2 / tp[0], noisy=False)
                        else:
                            hist3.append(p2)
                        prev3 = p2
                    vals.append(c3 + s3 * tp[-1])
                else:
                    vals.append(run_qchannel(code, seed, lookups[ch], ch, p))
            avg = sum(vals) / len(vals)
            agg[m].append(avg)
            row += ' %12.1f' % avg
        row += ' %9.1f' % full
        print(row)

    print('-' * len(header))
    base = agg['det']
    for m, ch, p in MODES[1:]:
        gain = sum(a - b for b, a in zip(base, agg[m], strict=True)) / len(base)
        beats = sum(1 for b, a in zip(base, agg[m], strict=True) if a > b)
        print('%-8s 平均噪声收益 %+6.1f  跑赢基线 %d/6' % (m, gain, beats))
