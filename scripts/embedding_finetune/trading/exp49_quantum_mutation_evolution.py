#!/usr/bin/env python3
"""exp49: 量子遗传变异——量子信道变异算子 vs 经典变异(量子线 x 线虫进化线交叉)

用户:遗传变异加量子计算因素。复用 exp19-26 验证的量子信道 + exp32 隧穿:
- bitflip 变异:调控基因 0<->1 翻转(量子 X 门错误)
- ampdamp 变异:结构基因向中性值衰减(振幅阻尼=向基态衰减 -> 基因失活方向,
  与 exp48 假基因化呼应——量子信道加速失活?)
- depolar 变异:基因完全随机化(退极化=完全混合态)
- quantum_tunnel:经典小步 + 低概率大幅跳跃(量子隧穿跳出局部最优)

三组对照(exp48 框架,只换变异算子):
  classic        经典(高斯点突变+调控翻转)——基线
  quantum_channel 量子信道算子(bitflip/ampdamp/depolar)
  quantum_tunnel  经典 + 隧穿大突变

指标:种群/谱系/基因数/持仓振荡/假基因化比例(中性表达基因数)/适应度
"""

import json
import math
import os
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_quantum_mut')
os.makedirs(ARCHIVE, exist_ok=True)

N0 = 60
CAPACITY = 150
EPOCH_DAYS = 100
N_EPOCHS = 12
N_STOCKS = 4
LIFESPAN_EPOCHS = 3
REPRO_LINE = 130.0
CONSUME_RATE = 0.08
N_CHROMO = 3
N_STRUCT = 12
MODES = ['classic', 'quantum_channel', 'quantum_tunnel']

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


def load_all_prices():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from data_loader import load_stock
    from exp15_noise_vs_deterministic import POOL2
    from exp12_policy_prior import POOL as POOL1
    series = []
    for code in list(POOL1.keys()) + list(POOL2.keys()):
        try:
            series.append(load_stock(code)['close'].values)
        except Exception:
            pass
    return series


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


def count_expressed(genome):
    """假基因化指标:表达的基因数(reg=1 且位点存在)。"""
    n = 0
    for chromo in genome:
        for j, s in enumerate(chromo[2:]):
            reg = chromo[0] if j < 2 else chromo[1]
            if reg == 1:
                n += 1
    return n


def mutate_classic(genome):
    """经典变异(exp48 基线):高斯点突变 + 调控翻转。"""
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


def mutate_quantum_channel(genome):
    """量子信道变异:bitflip(调控翻转)/ampdamp(向中性衰减)/depolar(随机化)。"""
    new = []
    for chromo in genome:
        c = chromo.copy()
        # bitflip:调控基因翻转(量子 X 门错误)
        for r in range(2):
            if rng.random() < 0.05:
                c[r] = 1 - c[r]
        for j in range(2, len(c)):
            roll = rng.random()
            if roll < 0.05:
                # depolar 退极化:完全随机化(混合态)
                c[j] = rng.uniform(-1.0, 1.0)
            elif roll < 0.15:
                # ampdamp 振幅阻尼:向中性值(0)衰减——基因失活方向
                c[j] *= 0.5
                if abs(c[j]) < 0.05:
                    c[j] = 0.0
            elif roll < 0.25:
                # 高斯微扰(经典保留一部分)
                c[j] += rng.normal(0, 0.3)
                c[j] = max(-1.0, min(1.0, c[j]))
        new.append(c)
    return new


def mutate_quantum_tunnel(genome):
    """经典变异 + 量子隧穿大突变(低概率大幅跳跃,跳出局部最优)。"""
    new = mutate_classic(genome)
    for ci in range(len(new)):
        if rng.random() < 0.02:  # 隧穿概率 2%
            # 整条染色体大扰动(穿过能量壁垒的跳跃)
            for j in range(2, len(new[ci])):
                new[ci][j] = rng.uniform(-1.0, 1.0)
            # 调控基因也可能一起翻(隧穿到新的"表达模式")
            if rng.random() < 0.5:
                new[ci][0] = 1 - new[ci][0]
                new[ci][1] = 1 - new[ci][1]
    return new


MUTATORS = {'classic': mutate_classic,
            'quantum_channel': mutate_quantum_channel,
            'quantum_tunnel': mutate_quantum_tunnel}


def crossover_genome(a, b):
    return [ca if rng.random() < 0.5 else cb for ca, cb in zip(a, b)]


def make_world(all_prices):
    world = []
    for _ in range(N_STOCKS):
        p = all_prices[rng.randint(len(all_prices))]
        start = rng.randint(0, max(1, len(p) - EPOCH_DAYS - 1))
        seg = p[start:start + EPOCH_DAYS].copy()
        if rng.random() < 0.2:
            seg[rng.randint(1, len(seg) - 1)] *= 0.85
        world.append(seg)
    return world


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


def reproduce(worms, world, mutator):
    next_gen = []
    for w in worms:
        if w.age > EPOCH_DAYS * LIFESPAN_EPOCHS:
            continue
        v = w.value(world)
        if v <= 0:
            continue
        if v >= REPRO_LINE:
            n_children = max(1, min(5, int((v - 100.0) / 50.0)))
            for _ in range(n_children):
                g = mutator(w.genome)
                if rng.random() < 0.5:
                    partner = rng.choice([x for x in worms if x is not w] or [w])
                    g = mutator(crossover_genome(g, partner.genome))
                next_gen.append(Worm(g, ancestors=w.ancestors + 1))
        else:
            next_gen.append(w)
    if len(next_gen) > CAPACITY:
        next_gen.sort(key=lambda x: -x.ancestors)
        next_gen = next_gen[:CAPACITY]
    return next_gen


def evolve(mode, W_real, groups, all_prices):
    base = random_genome()
    worms = [Worm(base) for _ in range(N0)]
    mutator = MUTATORS[mode]
    holds = []
    expressed = []
    for ep in range(N_EPOCHS):
        world = make_world(all_prices)
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
        worms = run_epoch(worms, W_map, groups, world)
        worms = reproduce(worms, world, mutator)
        if worms:
            holds.append(np.mean([sum(w.holdings) / N_STOCKS for w in worms]))
            expressed.append(np.mean([count_expressed(w.genome) for w in worms]))
        else:
            holds.append(0.0)
            expressed.append(0.0)
    return worms, holds, expressed


if __name__ == '__main__':
    print('=== exp49: 量子遗传变异——信道算子/隧穿 vs 经典(量子 x 线虫进化) ===')
    W_real, groups = load_worm()
    all_prices = load_all_prices()
    print('变异算子: classic / quantum_channel(bitflip+ampdamp+depolar) / quantum_tunnel\n')

    print('%-18s %10s %10s %12s %10s %12s' % (
        '变异算子', '种群末', '最深谱系', '平均持仓率', '表达基因数', '平均资产'))
    print('-' * 76)
    results = {}
    for mode in MODES:
        worms, holds, expressed = evolve(mode, W_real, groups, all_prices)
        final_world = make_world(all_prices)
        avg_v = np.mean([w.value(final_world) for w in worms]) if worms else 0
        max_anc = max(w.ancestors for w in worms) if worms else 0
        results[mode] = (worms, holds, expressed, avg_v)
        print('%-18s %10d %10d %12.1f%% %10.1f %12.1f' % (
            mode, len(worms), max_anc, np.mean(holds) * 100,
            np.mean(expressed) if expressed else 0, avg_v))

    print()
    print('=== 假基因化速度(表达基因数下降 = 失活) ===')
    for mode in MODES:
        ex = results[mode][2]
        if ex:
            print('%-18s 起点 %.1f -> 终点 %.1f(12纪元)' % (mode, ex[0], ex[-1]))
    print()
    print('=== 持仓振荡模式 ===')
    for mode in MODES:
        hs = results[mode][1]
        print('%-18s %s' % (mode, ' '.join('%.0f' % (v * 100) for v in hs)))
