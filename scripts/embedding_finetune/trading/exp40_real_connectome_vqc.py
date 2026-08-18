#!/usr/bin/env python3
"""exp40: 真实果蝇连接组 VQC——真实 KC->MBON 突触权重 vs exp39 随机连接

用 NeuPrint 拉到的真实蘑菇体连接(mb_connections.csv: KC->MBON 30496 条):
1. 选连接最密集的 8 个 KC + 8 个 MBON,真实突触权重归一化成 8x8 邻接矩阵
2. 气味 -> 8 qubit 编码(RY) -> 变分层1 -> **CNOT 纠缠按真实连接布线** ->
   变分层2 -> 测量(8 qubit P(1) 均值 = 趋近概率)
3. 训练:参数移位规则(Statevector 直读概率,快 100 倍) x 奖励调制
对比:exp39 随机连接 VQC(82.5%) vs 真实连接 VQC vs R-STDP(58.8%)
运行:uv run --project E:/Users/lmq/qiskit python exp40_real_connectome_vqc.py
"""

import math
import random
import sys
import os
import csv
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from qiskit import QuantumCircuit
from qiskit.quantum_info import Statevector

N_ODORS = 8
N_FEAT = 8
GOOD = [0, 1, 2, 3]
BAD = [4, 5, 6, 7]
TRAIN_ROUNDS = 100
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      '..', 'snn_behavior', 'flywire_data')


def load_real_connectome():
    """读真实 KC->MBON 连接,选 top 神经元构建 8x8 邻接矩阵(归一化)。"""
    edges = []
    with open(os.path.join(DATA_DIR, 'mb_connections.csv'), encoding='utf-8') as f:
        for row in csv.DictReader(f):
            edges.append((int(row['src']), int(row['dst']), float(row['weight'])))
    # KC->MBON 边(带权重)
    kc_edges = [e for e in edges if e[2] > 0]
    # 按权重排序选 8 个 KC + 8 个 MBON(连接最密集的核心)
    kc_ids = []
    mb_ids = []
    for src, dst, w in sorted(kc_edges, key=lambda x: -x[2]):
        if src not in kc_ids:
            kc_ids.append(src)
        if dst not in mb_ids:
            mb_ids.append(dst)
        if len(kc_ids) >= 8 and len(mb_ids) >= 8:
            break
    # 8x8 邻接(真实突触权重 -> [0,1] 归一化)
    adj = np.zeros((8, 8))
    for src, dst, w in kc_edges:
        if src in kc_ids[:8] and dst in mb_ids[:8]:
            adj[kc_ids.index(src)][mb_ids.index(dst)] = w
    maxw = adj.max() if adj.max() > 0 else 1.0
    adj = adj / maxw
    return adj


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


class FlyVQCReal:
    """VQC + 真实连接布线:CNOT 层按真实邻接矩阵(权重>阈值)生成。"""

    def __init__(self, adj, seed=42, lr=0.08, explore=0.05, cn_thresh=0.3):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.adj = adj
        self.cn_thresh = cn_thresh
        self.theta = [random.uniform(-math.pi, math.pi) for _ in range(N_FEAT)]
        self.phi = [random.uniform(-math.pi, math.pi) for _ in range(N_FEAT)]

    def build_circuit(self, feat, theta, phi):
        qc = QuantumCircuit(N_FEAT)
        # 编码层
        for i in range(N_FEAT):
            if feat[i] > 0:
                qc.ry(math.pi, i)
        # 变分层1
        for i in range(N_FEAT):
            qc.ry(theta[i], i)
        # 纠缠层:按真实连接布线(权重 > 阈值的 KC->MBON 对之间加 CNOT,跳过对角)
        for i in range(N_FEAT):
            for j in range(N_FEAT):
                if i != j and self.adj[i][j] > self.cn_thresh:
                    qc.cx(i, j)
        # 变分层2
        for i in range(N_FEAT):
            qc.ry(phi[i], i)
        return qc

    def p_approach(self, feat, theta, phi):
        """Statevector 直读概率(快 100 倍,不用 shots)。"""
        qc = self.build_circuit(feat, theta, phi)
        sv = Statevector(qc)
        probs = sv.probabilities()
        # P(1) 均值 = 趋近概率
        p1 = 0.0
        for i, p in enumerate(probs):
            p1 += bin(i).count('1') * p
        return p1 / N_FEAT

    def decide(self, feat):
        p = self.p_approach(feat, self.theta, self.phi)
        p += random.uniform(-self.explore, self.explore)
        return 0 if p > 0.5 else 1

    def learn(self, reward, feat):
        for idx in [i for i in range(N_FEAT) if feat[i] > 0]:
            p_plus = self.p_approach(feat,
                                     [self.theta[j] + (math.pi / 2 if j == idx else 0)
                                      for j in range(N_FEAT)], self.phi)
            p_minus = self.p_approach(feat,
                                      [self.theta[j] - (math.pi / 2 if j == idx else 0)
                                       for j in range(N_FEAT)], self.phi)
            grad = (p_plus - p_minus) / 2.0
            self.theta[idx] += self.lr * reward * grad


def run_fly(fly, odors, rounds=TRAIN_ROUNDS):
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
    import time
    t0 = time.time()
    print('=== exp40: 真实果蝇连接组 VQC(真实 KC->MBON 突触权重布线) ===')
    adj = load_real_connectome()
    print('真实邻接矩阵(top 8 KC x 8 MBON,归一化突触权重):')
    print(np.round(adj, 2))
    print('CNOT 边数(权重>0.3):', int((adj > 0.3).sum()))
    print()

    odors = make_odors()
    curves, accs, avoids = [], [], []
    for trial in range(5):
        fly = FlyVQCReal(adj, seed=42 + trial)
        c, a, av = run_fly(fly, odors)
        curves.append(c); accs.append(a); avoids.append(av)
        print('模拟 %d: 正确率 %.1f%% 逃避率 %.1f%%' % (trial + 1, a * 100, av * 100))

    mc = np.mean(curves, axis=0)
    elapsed = time.time() - t0
    print()
    print('=== 汇总(5 次平均) ===')
    print('真实连接 VQC: %.1f%% / 坏气味逃避 %.1f%%' % (
        np.mean(accs) * 100, np.mean(avoids) * 100))
    print('学习曲线:', ' '.join('%.2f' % v for v in mc))
    print('运行时长: %.1f 秒' % elapsed)
    print()
    print('=== 对照 ===')
    print('exp39 随机连接 VQC: 82.5%')
    print('经典 R-STDP: 58.8%')
