#!/usr/bin/env python3
"""exp38b: QSNN 相位放大适配稀疏任务——双路径干涉版(修 exp38 失败)

exp38 结论:QSNN(双神经元 softmax)在稀疏 0/1 特征 + 二元决策上学不会——
sin² 压缩 + softmax 把相位差异拉平。修复设计(更贴量子语义):
**趋近/逃避 = 量子比特的两个基态,气味的嗅小球激活调制相位差 Δ**:
P(趋近) = sin²(Δ/2), P(逃避) = cos²(Δ/2)——双路径干涉,互补选择。
单一相位权重向量(不是双神经元):Δ = gain × Σφ·feat。
学习:奖励调制相位(wrap),好气味 → Δ→π(趋近),坏气味 → Δ→0(逃避)。

对比:R-STDP(exp38 胜者) vs 原 QSNN(失败) vs QSNN2(相位干涉+增益)
"""

import math
import random
import numpy as np

rng = np.random.RandomState(20260818)

N_ODORS = 8
N_FEAT = 8
GOOD = [0, 1, 2, 3]
BAD = [4, 5, 6, 7]
TRAIN_ROUNDS = 100


def make_odors():
    odors = []
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


class FlyRSTDP:
    def __init__(self, seed=42, lr=0.05, explore=0.2):
        random.seed(seed)
        self.lr = lr
        self.explore = explore
        self.decay = 0.9
        self.w = [[random.uniform(-1.0, 1.0) for _ in range(N_FEAT)]
                  for _ in range(2)]
        self.trace = [[0.0] * N_FEAT for _ in range(2)]

    def decide(self, feat):
        a0 = sum(self.w[0][i] * feat[i] for i in range(N_FEAT))
        a1 = sum(self.w[1][i] * feat[i] for i in range(N_FEAT))
        n = random.uniform(-self.explore, self.explore)
        return 0 if a0 + n > a1 else 1

    def learn(self, reward, action, feat):
        sense = [1.0 if f > 0 else 0.0 for f in feat]
        for i in range(N_FEAT):
            self.trace[action][i] = (self.trace[action][i] * self.decay + sense[i])
            self.w[action][i] += self.lr * reward * self.trace[action][i]


class FlyQSNN1:
    """原 QSNN(exp38 失败版):双神经元 sin² + softmax。"""

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
            if self.phi[action][i] > math.pi:
                self.phi[action][i] -= 2 * math.pi
            elif self.phi[action][i] < -math.pi:
                self.phi[action][i] += 2 * math.pi


class FlyQSNN2:
    """QSNN2 相位干涉版:单相位向量,Δ = gain×Σφ·feat,
    P(趋近)=sin²(Δ/2)——趋近/逃避 = 量子比特两基态的干涉互补。"""

    def __init__(self, seed=42, lr=0.3, gain=4.0, explore=0.1):
        random.seed(seed)
        self.lr = lr
        self.gain = gain
        self.explore = explore
        self.decay = 0.9
        self.phi = [random.uniform(-1.0, 1.0) for _ in range(N_FEAT)]
        self.trace = [0.0] * N_FEAT

    def decide(self, feat):
        delta = self.gain * sum(self.phi[i] * feat[i] for i in range(N_FEAT))
        # P(趋近) = 0.5 + 0.5·sin(Δ)——sin 是奇函数保留相位符号,
        # 学习方向一致(Δ>0 偏趋近,Δ<0 偏逃避);sin² 偶函数丢符号是 exp38b v1 失败根因
        p_approach = 0.5 + 0.5 * math.sin(delta)
        n = random.uniform(-self.explore, self.explore)
        return 0 if p_approach + n > 0.5 else 1

    def learn(self, reward, action, feat):
        # 方向由动作决定:趋近(0)→ Δ 需增大;逃避(1)→ Δ 需减小
        # 不用 trace 资格迹——每轮气味独立,且 trace 饱和(1/(1-decay)=10)
        # 会让相位每步跳 lr×10=3 弧度 = 周期函数上的随机游走(v3 失败根因)
        direction = 1.0 if action == 0 else -1.0
        for i in range(N_FEAT):
            self.phi[i] += (self.lr * reward * direction * feat[i])
            if self.phi[i] > math.pi:
                self.phi[i] -= 2 * math.pi
            elif self.phi[i] < -math.pi:
                self.phi[i] += 2 * math.pi


def run_fly(fly, odors, rounds=TRAIN_ROUNDS):
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
    print('=== exp38b: QSNN 相位放大适配——双路径干涉版 vs 原版 vs R-STDP ===')
    print('8 气味 × 100 轮 × 20 次模拟\n')

    odors = make_odors()
    makers = [
        ('rstdp 经典R-STDP', FlyRSTDP),
        ('qsnn1 原版(失败)', FlyQSNN1),
        ('qsnn2 相位干涉', FlyQSNN2),
    ]
    print('%-20s %10s %12s %12s' % ('组', '最终正确率', '坏气味逃避率', '50轮正确率'))
    print('-' * 56)
    curves = {}
    for name, maker in makers:
        accs, avoids, cs = [], [], []
        for _ in range(20):
            c, a, av = run_fly(maker(), odors)
            cs.append(c); accs.append(a); avoids.append(av)
        mc = np.mean(cs, axis=0)
        curves[name] = mc
        print('%-20s %10.1f%% %12.1f%% %12.1f%%' % (
            name, np.mean(accs) * 100, np.mean(avoids) * 100, mc[4] * 100))

    print()
    print('--- 学习曲线 ---')
    print('%-8s %8s %8s %8s %8s %8s' % ('组', '10', '30', '50', '70', '100'))
    for name, _ in makers:
        c = curves[name]
        print('%-8s %8.2f %8.2f %8.2f %8.2f %8.2f' % (name[:6], c[0], c[2], c[4], c[6], c[9]))
