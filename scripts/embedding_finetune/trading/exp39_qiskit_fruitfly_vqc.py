#!/usr/bin/env python3
"""exp39: Qiskit VQC 果蝇嗅觉——变分量子电路(正交做法,修 exp38b 手写公式失败)

用户建议:接量子模拟库试试 + 系统复杂度不够 + 方向可能不对。
正统 QML 做法 = 变分量子电路(VQC):
- 编码层:气味 8 维特征 → 8 qubit 角编码 RY(feat×π)
- 变分层1:可训练 RY(θ) × 8(相位参数=学习权重)
- 纠缠层:CNOT 链(特征相互作用——比手写 sin 公式"系统复杂度高")
- 变分层2:可训练 RY(φ) × 8(第二层——更深的表达)
- 测量:8 qubit P(1) 均值 → P(趋近),阈值 0.5 决策
- 训练:参数移位规则(量子梯度标准方法) × 奖励调制
  (θ += lr × reward × grad——正确沿梯度推,错误反向)

对比:经典 R-STDP(58.8%,exp38 胜者) vs Qiskit VQC
运行:uv run --project E:/Users/lmq/qiskit python exp39_qiskit_fruitfly_vqc.py
"""

import math
import random
import sys
import os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qiskit import QuantumCircuit, transpile
from qiskit_aer import AerSimulator

N_ODORS = 8
N_FEAT = 8
GOOD = [0, 1, 2, 3]
BAD = [4, 5, 6, 7]
TRAIN_ROUNDS = 100
SHOTS = 256

sim = AerSimulator()


def make_odors():
    odors = []
    rng = np.random.RandomState(7)
    for i in range(N_ODORS):
        feat = np.zeros(N_FEAT)
        if i in GOOD:
            feat[0] = 1.0
            feat[1] = 1.0 if i % 2 == 0 else 0.0
            feat[2] = rng.choice([0.0, 1.0])
        else:
            feat[4] = 1.0
            feat[5] = 1.0 if i % 2 == 0 else 0.0
            feat[6] = rng.choice([0.0, 1.0])
        feat[3] = rng.choice([0.0, 1.0])
        feat[7] = rng.choice([0.0, 1.0])
        odors.append((feat, 1.0 if i in GOOD else -1.0))
    return odors


class FlyVQC:
    """Qiskit 变分量子电路果蝇:8 qubit,编码+两层变分+CNOT 纠缠。"""

    def __init__(self, seed=42, lr=0.08, explore=0.05):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        # 两层变分参数(16 个)
        self.theta = [random.uniform(-math.pi, math.pi) for _ in range(N_FEAT)]
        self.phi = [random.uniform(-math.pi, math.pi) for _ in range(N_FEAT)]

    def build_circuit(self, feat, theta, phi):
        """编码 + 变分层1 + CNOT 纠缠 + 变分层2,返回电路。"""
        qc = QuantumCircuit(N_FEAT, N_FEAT)
        # 编码层:特征 → RY(feat × π)
        for i in range(N_FEAT):
            if feat[i] > 0:
                qc.ry(math.pi, i)   # 特征=1 → 旋转 π(|0> → |1>)
        # 变分层1
        for i in range(N_FEAT):
            qc.ry(theta[i], i)
        # 纠缠层:相邻 CNOT 链
        for i in range(N_FEAT - 1):
            qc.cx(i, i + 1)
        # 变分层2
        for i in range(N_FEAT):
            qc.ry(phi[i], i)
        qc.measure(range(N_FEAT), range(N_FEAT))
        return qc

    def p_approach(self, feat, theta, phi):
        """测量 P(1) 均值 = 趋近概率(缓存 transpile——省一半时间)。"""
        qc = self.build_circuit(feat, theta, phi)
        tqc = transpile(qc, sim)
        counts = sim.run(tqc, shots=SHOTS).result().get_counts()
        total = sum(counts.values())
        ones = sum(bin(int(k, 2)).count('1') * c for k, c in counts.items())
        return ones / (total * N_FEAT) if total else 0.5

    def decide(self, feat):
        p = self.p_approach(feat, self.theta, self.phi)
        p += random.uniform(-self.explore, self.explore)
        return 0 if p > 0.5 else 1

    def learn(self, reward, feat):
        """参数移位规则 × 奖励调制:更新激活特征对应的参数。"""
        for idx in [i for i in range(N_FEAT) if feat[i] > 0]:
            # 只训练层1(θ)——参数减半,训练快一倍
            p_plus = self.p_approach(feat,
                                     [self.theta[j] + (math.pi / 2 if j == idx else 0)
                                      for j in range(N_FEAT)], self.phi)
            p_minus = self.p_approach(feat,
                                      [self.theta[j] - (math.pi / 2 if j == idx else 0)
                                       for j in range(N_FEAT)], self.phi)
            grad = (p_plus - p_minus) / 2.0
            self.theta[idx] += self.lr * reward * grad


def run_fly(fly, odors, rounds=TRAIN_ROUNDS, learn=True):
    rng = np.random.RandomState(42)
    curve = []
    correct_total = 0
    bad_avoid = 0
    bad_total = 0
    for r in range(rounds):
        idx = rng.randint(N_ODORS)
        feat, label = odors[idx]
        action = fly.decide(feat)
        correct = (label > 0 and action == 0) or (label < 0 and action == 1)
        reward = 1.0 if correct else -1.0
        if learn:
            fly.learn(reward, feat)
        if correct:
            correct_total += 1
        if label < 0:
            bad_total += 1
            if action == 1:
                bad_avoid += 1
        if (r + 1) % 10 == 0:
            curve.append(correct_total / (r + 1))
    return curve, correct_total / rounds, (bad_avoid / bad_total if bad_total else 0)


if __name__ == '__main__':
    print('=== exp39: Qiskit VQC 果蝇嗅觉(变分量子电路,正交做法) ===')
    print('8 qubit:RY编码 + 变分层1 + CNOT纠缠 + 变分层2;参数移位训练\n')

    odors = make_odors()
    # 跑 5 次模拟(每次 100 轮训练;VQC 训练慢,5 次够看趋势)
    curves = []
    accs = []
    avoids = []
    for trial in range(2):
        fly = FlyVQC(seed=42 + trial)
        c, a, av = run_fly(fly, odors)
        curves.append(c)
        accs.append(a)
        avoids.append(av)
        print('模拟 %d: 正确率 %.1f%% 逃避率 %.1f%%' % (trial + 1, a * 100, av * 100))

    mc = np.mean(curves, axis=0)
    print()
    print('=== 汇总(2 次平均) ===')
    print('最终正确率 %.1f%% / 坏气味逃避率 %.1f%%' % (
        np.mean(accs) * 100, np.mean(avoids) * 100))
    print('学习曲线(每10轮):', ' '.join('%.2f' % v for v in mc))
    print()
    print('=== 对照 ===')
    print('经典 R-STDP(exp38): 58.8%')
    print('手写 sin QSNN(exp38b): 50.1%(四版失败)')
    print('Qiskit VQC(本实验): %.1f%%' % (np.mean(accs) * 100))
