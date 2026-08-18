#!/usr/bin/env python3
"""exp38: 果蝇级嗅觉趋避——三组对比(无学习/R-STDP/QSNN)

落地 snn_behavior 规划的 exp3(果蝇级嗅觉趋避)+ 用户要求 QSNN 组:
果蝇嗅觉回路:气味 → 触角叶(嗅小球特征) → 蘑菇体(R-STDP 学习中心) → 趋近/逃避

三组:
- no_learn  无学习(随机决策基线——不会学习的果蝇)
- rstdp     经典 R-STDP(奖励调制三因子——会学习的果蝇)
- qsnn      QSNN 复振幅相位学习(exp34 机制——量子果蝇)

场景:8 种气味(4 好 4 坏),每轮随机给一种气味,决策趋近/逃避,奖励 ±1。
指标:训练后正确率 / 学习曲线(每 10 轮正确率) / 坏气味逃避率(安全)
"""

import math
import random
import numpy as np

rng = np.random.RandomState(20260818)

N_ODORS = 8
N_FEAT = 8          # 嗅小球特征维度
GOOD = [0, 1, 2, 3]
BAD = [4, 5, 6, 7]
TRAIN_ROUNDS = 100


def make_odors():
    """8 种气味:好气味共享嗅小球[0,1]激活,坏气味共享嗅小球[4,5]激活。
    ——有结构的特征(嗅觉回路里好/坏气味确实激活不同嗅小球),可学习。"""
    odors = []
    for i in range(N_ODORS):
        feat = np.zeros(N_FEAT)
        if i in GOOD:
            feat[0] = 1.0
            feat[1] = 1.0 if i % 2 == 0 else 0.0  # 好气味内部细节
            feat[2] = rng.choice([0.0, 1.0])
        else:
            feat[4] = 1.0
            feat[5] = 1.0 if i % 2 == 0 else 0.0
            feat[6] = rng.choice([0.0, 1.0])
        feat[3] = rng.choice([0.0, 1.0])  # 噪声位
        feat[7] = rng.choice([0.0, 1.0])
        odors.append((feat, 1.0 if i in GOOD else -1.0))
    return odors


class FlyRSTDP:
    """经典 R-STDP 果蝇:蘑菇体权重 w[8],奖励调制三因子。"""

    def __init__(self, seed=42, lr=0.05, explore=0.2):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.decay = 0.9
        # 两个输出神经元:趋近/逃避,各 8 维权重
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(N_FEAT)]
                  for _ in range(2)]
        self.trace = [[0.0] * N_FEAT for _ in range(2)]

    def decide(self, feat):
        a_approach = sum(self.w[0][i] * feat[i] for i in range(N_FEAT))
        a_avoid = sum(self.w[1][i] * feat[i] for i in range(N_FEAT))
        n = random.uniform(-self.explore, self.explore)
        return 0 if a_approach + n > a_avoid else 1  # 0=趋近 1=逃避

    def learn(self, reward, action, feat):
        sense = [1.0 if f > 0 else 0.0 for f in feat]
        for i in range(N_FEAT):
            self.trace[action][i] = (self.trace[action][i] * self.decay + sense[i])
            self.w[action][i] += self.lr * reward * self.trace[action][i]


class FlyQSNN:
    """QSNN 果蝇:蘑菇体相位权重 φ[8],发放概率 sin²(相位),测量选动作。"""

    def __init__(self, seed=42, lr=0.3, explore=0.1):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.decay = 0.9
        self.phi = [[random.uniform(-1.2, 1.2) for _ in range(N_FEAT)]
                    for _ in range(2)]
        self.trace = [[0.0] * N_FEAT for _ in range(2)]

    def decide(self, feat):
        ps = []
        for a in range(2):
            phase = sum(self.phi[a][i] * feat[i] for i in range(N_FEAT))
            ps.append(math.sin(phase) ** 2 + random.uniform(-self.explore,
                                                           self.explore))
        # 概率采样(量子测量)
        e = [math.exp(p) for p in ps]
        r = random.random() * sum(e)
        acc = 0.0
        for a in range(2):
            acc += e[a]
            if r <= acc:
                return a
        return 1

    def learn(self, reward, action, feat):
        for i in range(N_FEAT):
            self.trace[action][i] = (self.trace[action][i] * self.decay + feat[i])
            self.phi[action][i] += (self.lr * reward
                                    * self.trace[action][i] * feat[i])
            # wrap 回 [-pi, pi]
            if self.phi[action][i] > math.pi:
                self.phi[action][i] -= 2 * math.pi
            elif self.phi[action][i] < -math.pi:
                self.phi[action][i] += 2 * math.pi


def run_fly(fly, odors, rounds=TRAIN_ROUNDS):
    """训练 + 返回学习曲线和最终正确率。"""
    curve = []
    correct_total = 0
    bad_avoid = 0
    bad_total = 0
    for r in range(rounds):
        idx = rng.randint(N_ODORS)
        feat, label = odors[idx]
        action = fly.decide(feat)
        # 正确:好气味趋近(0) / 坏气味逃避(1)
        correct = (label > 0 and action == 0) or (label < 0 and action == 1)
        reward = 1.0 if correct else -1.0
        fly.learn(reward, action, feat)
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
    print('=== exp38: 果蝇级嗅觉趋避——无学习 / R-STDP / QSNN ===')
    print('8 气味(4好4坏) × 100 训练轮 × 20 次模拟\n')

    odors = make_odors()
    groups = [
        ('no_learn 无学习', 'none'),
        ('rstdp 经典R-STDP', 'rstdp'),
        ('qsnn 复振幅QSNN', 'qsnn'),
    ]
    print('%-20s %10s %12s %12s' % ('组', '最终正确率', '坏气味逃避率', '50轮时正确率'))
    print('-' * 58)
    results = {}
    for name, kind in groups:
        curves = []
        accs = []
        avoids = []
        for _ in range(20):
            if kind == 'rstdp':
                fly = FlyRSTDP()
            elif kind == 'qsnn':
                fly = FlyQSNN()
            else:
                fly = None
            if fly is None:
                # 无学习:随机决策基线
                accs.append(0.5)
                avoids.append(0.5)
                curves.append([0.5] * 10)
                continue
            curve, acc, avoid = run_fly(fly, odors)
            curves.append(curve)
            accs.append(acc)
            avoids.append(avoid)
        mean_curve = np.mean(curves, axis=0)
        results[kind] = mean_curve
        print('%-20s %10.1f%% %12.1f%% %14.1f%%' % (
            name, np.mean(accs) * 100, np.mean(avoids) * 100,
            mean_curve[4] * 100))

    print()
    print('--- 学习曲线(每 10 轮正确率) ---')
    print('%-8s %8s %8s %8s %8s %8s' % ('轮次', '10', '30', '50', '70', '100'))
    for kind, label in [('rstdp', 'R-STDP'), ('qsnn', 'QSNN')]:
        c = results[kind]
        print('%-8s %8.2f %8.2f %8.2f %8.2f %8.2f' % (
            label, c[0], c[2], c[4], c[6], c[9]))

    print()
    print('=== 结论观察 ===')
    print('R-STDP vs QSNN:谁学得快?谁最终更准?坏气味逃避率(安全)差异?')
