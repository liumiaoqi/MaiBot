#!/usr/bin/env python3
"""exp50: 线虫炒股——训练段进化,测试段(2021-2026真未来)实盘对比

进化线(exp48 框架:真实连接+染色体基因+收益消费)的训练-测试范式:
- 训练:1996-2020 训练段随机窗口进化 20 代(60 线虫)
- 测试:2021-2026 测试段(对线虫是真未来)——冠军线虫实际交易
- 对比:满仓 / 线虫策略 / exp14 完整 AI(历史最优 110.9 平均)

诚实预期:弱式有效市场——进化可能过拟合训练段,测试段才是真相。
"""

import json
import math
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'

N0 = 60
N_GENS = 20
EPOCH_DAYS = 100
N_STOCKS = 4
REPRO_LINE = 130.0
CONSUME_RATE = 0.08
LIFESPAN_EPOCHS = 3
N_CHROMO = 3
N_STRUCT = 12

PHENO_RANGES = [(-1.0, 1.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0),
                (0.1, 3.0), (0.1, 3.0), (0.0, 1.0), (0.0, 0.5), (-0.5, 0.5),
                (0.0, 0.5), (0.1, 3.0)]
PHENO_NEUTRAL = [0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.2, 0.0, 0.1, 1.0]

BEHAVIOR = {
    'back': ['AVAL', 'AVAR', 'DD01', 'DD02'],
    'fwd': ['AVBL', 'AVBR', 'DB01', 'DB02', 'DB03'],
    'turn': ['RIVL', 'RIVR', 'SMDDL'],
    'motor': ['PVCL', 'PVCR'],
    'sense': ['IL2DL', 'IL2VL', 'URXL', 'URXR'],
}


def load_worm():
    Gs = np.load(os.path.join(DATA, 'Gs.npy'))
    chem = json.load(open(os.path.join(DATA, 'chem.json'), encoding='utf-8'))
    names = [n.get('name') or str(n.get('id')) for n in chem['nodes']]
    W = (Gs + Gs.T) / 2.0
    np.fill_diagonal(W, 0.0)
    m = np.abs(W).max()
    W = W / m if m > 0 else W
    n2i = {n: i for i, n in enumerate(names)}
    groups = {k: [n2i[x] for x in v if x in n2i] for k, v in BEHAVIOR.items()}
    return W, groups


def random_chromosome():
    return [rng.randint(0, 2), rng.randint(0, 2)] + [rng.uniform(-1.0, 1.0)
                                                     for _ in range(4)]


def random_genome():
    return [random_chromosome() for _ in range(N_CHROMO)]


def develop(genome):
    pheno = list(PHENO_NEUTRAL)
    struct_idx = 0
    for chromo in genome:
        regA, regB = chromo[0], chromo[1]
        for j, s in enumerate(chromo[2:]):
            if struct_idx >= N_STRUCT:
                break
            reg = regA if j < 2 else regB
            if reg == 1:
                lo, hi = PHENO_RANGES[struct_idx]
                pheno[struct_idx] = lo + (s + 1.0) / 2.0 * (hi - lo)
            struct_idx += 1
    return np.array(pheno)


def mutate_genome(genome):
    new = []
    for chromo in genome:
        c = chromo.copy()
        for r in range(2):
            if rng.random() < 0.05:
                c[r] = 1 - c[r]
        for j in range(2, len(c)):
            if rng.random() < 0.15:
                c[j] += rng.normal(0, 0.3)
                c[j] = max(-1.0, min(1.0, c[j]))
        new.append(c)
    return new


def crossover_genome(a, b):
    return [ca if rng.random() < 0.5 else cb for ca, cb in zip(a, b)]


class Worm:
    __slots__ = ('genome', 'cash', 'shares', 'holdings', 'mem', 'age',
                 'ancestors', 'consume_fund')

    def __init__(self, genome, ancestors=1):
        self.genome = genome
        self.cash = [100.0 / N_STOCKS] * N_STOCKS
        self.shares = [0.0] * N_STOCKS
        self.holdings = [False] * N_STOCKS
        self.mem = [0.0] * N_STOCKS
        self.age = 0
        self.ancestors = ancestors
        self.consume_fund = 0.0

    def value(self, world):
        return sum(c + s * p[-1] for c, s, p in zip(self.cash, self.shares, world))

    def consume(self, world):
        need = self.value(world) * CONSUME_RATE
        if self.consume_fund >= need:
            self.consume_fund -= need
            return True
        return False


def make_pheno_map(worms, W_real, groups):
    W_map = {}
    for w in worms:
        pheno = develop(w.genome)
        W = W_real.copy()
        all_idx = np.arange(W.shape[0])
        for gi, key in enumerate(['back', 'fwd', 'turn', 'motor', 'sense']):
            idx = groups[key]
            if idx:
                W[np.ix_(idx, all_idx)] *= pheno[2 + gi]
                W[np.ix_(all_idx, idx)] *= pheno[2 + gi]
        W_map[id(w)] = {'W': W, 'pheno': pheno}
    return W_map


def run_epoch(worms, W_map, groups, world):
    for t in range(EPOCH_DAYS - 1):
        for w in worms:
            for si, prices in enumerate(world):
                r1 = prices[t + 1] / prices[t] - 1.0
                trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)]
                pheno = W_map[id(w)]['pheno']
                sense_in = math.tanh(pheno[1] * (r1 * 50 + trend * 20)) * pheno[0]
                w.mem[si] = w.mem[si] * (1 - pheno[7]) + sense_in
                act = np.zeros(279)
                act[groups['sense']] = w.mem[si]
                for _ in range(4):
                    act = np.tanh(W_map[id(w)]['W'] @ act)
                fwd_act = act[groups['fwd']].mean() if groups['fwd'] else 0
                back_act = act[groups['back']].mean() if groups['back'] else 0
                signal = (fwd_act - back_act) + rng.uniform(-pheno[8], pheno[8])
                if signal > pheno[9] and not w.holdings[si] and w.cash[si] > 0:
                    w.shares[si] = w.cash[si] / prices[t] * 0.999
                    w.cash[si] = 0.0
                    w.holdings[si] = True
                elif signal < -pheno[9] and w.holdings[si]:
                    gain = w.shares[si] * prices[t] * 0.999
                    profit = gain - w.shares[si] * prices[max(0, t - 1)]
                    w.consume_fund += max(0.0, profit)
                    w.cash[si] = gain
                    w.shares[si] = 0.0
                    w.holdings[si] = False
            w.age += 1
    return [w for w in worms if w.consume(world)]


def reproduce(worms, world):
    next_gen = []
    for w in worms:
        if w.age > EPOCH_DAYS * LIFESPAN_EPOCHS:
            continue
        v = w.value(world)
        if v <= 0:
            continue
        if v >= REPRO_LINE:
            n = max(1, min(5, int((v - 100.0) / 50.0)))
            for _ in range(n):
                g = mutate_genome(w.genome)
                if rng.random() < 0.5:
                    partner = rng.choice([x for x in worms if x is not w] or [w])
                    g = mutate_genome(crossover_genome(g, partner.genome))
                next_gen.append(Worm(g, ancestors=w.ancestors + 1))
        else:
            next_gen.append(w)
    if len(next_gen) > 150:
        next_gen.sort(key=lambda x: -x.ancestors)
        next_gen = next_gen[:150]
    return next_gen


def evolve_train(W_real, groups, train_prices):
    """训练段进化 20 代。"""
    base = random_genome()
    worms = [Worm(base) for _ in range(N0)]
    for gen in range(N_GENS):
        world = []
        for _ in range(N_STOCKS):
            p = train_prices[rng.randint(len(train_prices))]
            start = rng.randint(0, max(1, len(p) - EPOCH_DAYS - 1))
            world.append(p[start:start + EPOCH_DAYS])
        W_map = make_pheno_map(worms, W_real, groups)
        worms = run_epoch(worms, W_map, groups, world)
        worms = reproduce(worms, world)
    return worms


def test_worm_trade(worm, W_real, groups, prices):
    """测试段实际交易(单只股票,从头到尾)。"""
    pheno = develop(worm.genome)
    W = W_real.copy()
    all_idx = np.arange(W.shape[0])
    for gi, key in enumerate(['back', 'fwd', 'turn', 'motor', 'sense']):
        idx = groups[key]
        if idx:
            W[np.ix_(idx, all_idx)] *= pheno[2 + gi]
            W[np.ix_(all_idx, idx)] *= pheno[2 + gi]
    cash = 100.0
    shares = 0.0
    holding = False
    mem = 0.0
    for t in range(len(prices) - 1):
        r1 = prices[t + 1] / prices[t] - 1.0
        trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)]
        sense_in = math.tanh(pheno[1] * (r1 * 50 + trend * 20)) * pheno[0]
        mem = mem * (1 - pheno[7]) + sense_in
        act = np.zeros(279)
        act[groups['sense']] = mem
        for _ in range(4):
            act = np.tanh(W @ act)
        fwd_act = act[groups['fwd']].mean() if groups['fwd'] else 0
        back_act = act[groups['back']].mean() if groups['back'] else 0
        signal = (fwd_act - back_act) + rng.uniform(-pheno[8], pheno[8])
        if signal > pheno[9] and not holding and cash > 0:
            shares = cash / prices[t] * 0.999
            cash = 0.0
            holding = True
        elif signal < -pheno[9] and holding:
            cash = shares * prices[t] * 0.999
            shares = 0.0
            holding = False
    return cash + shares * prices[-1]


if __name__ == '__main__':
    print('=== exp50: 线虫炒股——训练段进化,测试段(2021-2026)实盘 ===')
    W_real, groups = load_worm()

    # 训练段数据(1996-2020)
    train_prices = []
    test_data = {}
    for code, name in POOL2.items():
        df = load_stock(code)
        train, test = split_train_test(df)
        train_prices.append(train['close'].values)
        test_data[name] = (code, test['close'].values)
    print('训练: %d 只 x 1996-2020 | 进化 %d 代 x %d 线虫' % (
        len(train_prices), N_GENS, N0))

    # 进化
    worms = evolve_train(W_real, groups, train_prices)
    worms.sort(key=lambda w: -w.ancestors)
    champion = worms[0]
    print('进化完成: 种群 %d,冠军谱系 %d 代' % (len(worms), champion.ancestors))

    # 测试段(2021-2026)实盘
    print()
    print('%-8s %12s %12s %12s' % ('股票', '线虫策略', '满仓', '线虫-满仓'))
    print('-' * 46)
    results = {}
    for name, (code, tp) in test_data.items():
        worm_v = test_worm_trade(champion, W_real, groups, tp)
        full = 100 * tp[-1] / tp[0]
        results[name] = (worm_v, full)
        print('%-8s %12.1f %12.1f %12.1f' % (name, worm_v, full, worm_v - full))

    wins = sum(1 for v, f in results.values() if v > f)
    avg_w = np.mean([v for v, _ in results.values()])
    avg_f = np.mean([f for _, f in results.values()])
    print('-' * 46)
    print('跑赢满仓: %d/%d | 线虫平均 %.1f vs 满仓平均 %.1f' % (
        wins, len(results), avg_w, avg_f))
    print()
    print('=== 对照历史最优 AI ===')
    print('exp14 完整方法(batch2 5-run): 平均 110.9,跑赢 4/10')
    print('线虫策略(测试段,单次): 平均 %.1f,跑赢 %d/%d' % (avg_w, wins, len(results)))
    print()
    print('=== 结论观察 ===')
    print('线虫能否在真未来泛化?vs 满仓 vs exp14 完整 AI?')
