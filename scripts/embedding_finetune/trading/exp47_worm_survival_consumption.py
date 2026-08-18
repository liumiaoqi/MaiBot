#!/usr/bin/env python3
"""exp47: 生存消费机制逼迫经济流动 + 繁殖即清算(exp45结论 + exp46修正)

exp45 结论:现金税(成本惩罚)推不动流动——需要结构性机制(不流动就没饭吃)
exp46 修正:父代不清算=老虫复利垄断——繁殖即清算 + 寿命 + 后代数适应度

结构性流动机制(本实验):
- 每纪元末必须"消费"(生存成本 = 资产 x consume_rate)
- 消费从现金扣;现金不足 -> 强制卖出持仓(流动行为!)
- 空仓线虫:资产=现金不增长 + 消费吞本金 -> 几纪元后必然饿死
- 持仓线虫:资产随市场增长覆盖消费 -> 存活
=> 不流动=饿死,流动=活——结构性逼迫(不是现金税)

繁殖修正(exp46):
- 繁殖即清算:父代资产按后代数分配,父代退出
- 寿命上限:3 纪元(300 天)强制死亡
- 适应度 = 后代数量(不是资产)

对比:消费率 0 / 5% / 10%——持仓率(流动)是否被迫上升?
"""

import json
import math
import os
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_survival')
os.makedirs(ARCHIVE, exist_ok=True)

N0 = 100
CAPACITY = 200
EPOCH_DAYS = 100
N_EPOCHS = 15
N_STOCKS = 4
SURVIVE_LINE = 130.0
MAX_CHILDREN = 5
LIFESPAN_EPOCHS = 3
CONSUME_RATES = [0.0, 0.05, 0.10]
CRISIS_PROB = 0.2
MUT_RATE = 0.2
CROSS_RATE = 0.3

GENE_NAMES = ['polarity', 'gain', 'scal_back', 'scal_fwd', 'scal_turn',
              'scal_motor', 'scal_sense', 'decay', 'explore', 'threshold']
GENE_RANGES = [(-1.0, 1.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0),
               (0.1, 3.0), (0.1, 3.0), (0.0, 1.0), (0.0, 0.5), (-0.5, 0.5)]

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


def random_gene():
    return np.array([rng.uniform(lo, hi) for lo, hi in GENE_RANGES])


def mutate(gene, rate=MUT_RATE, sigma=0.3):
    g = gene.copy()
    for i in range(len(g)):
        if rng.random() < rate:
            lo, hi = GENE_RANGES[i]
            g[i] += rng.normal(0, sigma) * (hi - lo)
            g[i] = max(lo, min(hi, g[i]))
    return g


def crossover(a, b):
    return np.where(rng.random(len(a)) < 0.5, a, b)


def phenotype(gene, W_real, groups):
    W = W_real.copy()
    all_idx = np.arange(W.shape[0])
    for gi, key in enumerate(['back', 'fwd', 'turn', 'motor', 'sense']):
        idx = groups[key]
        if idx:
            W[np.ix_(idx, all_idx)] *= gene[2 + gi]
            W[np.ix_(all_idx, idx)] *= gene[2 + gi]
    return W


def make_world(all_prices):
    world = []
    for _ in range(N_STOCKS):
        p = all_prices[rng.randint(len(all_prices))]
        start = rng.randint(0, max(1, len(p) - EPOCH_DAYS - 1))
        seg = p[start:start + EPOCH_DAYS].copy()
        if rng.random() < CRISIS_PROB:
            cd = rng.randint(1, len(seg) - 1)
            seg[cd] *= 0.85
        world.append(seg)
    return world


class Worm:
    __slots__ = ('gene', 'cash', 'shares', 'holdings', 'mem', 'age',
                 'ancestors', 'children_count')

    def __init__(self, gene, ancestors=1):
        self.gene = gene
        self.cash = [100.0 / N_STOCKS] * N_STOCKS
        self.shares = [0.0] * N_STOCKS
        self.holdings = [False] * N_STOCKS
        self.mem = [0.0] * N_STOCKS
        self.age = 0
        self.ancestors = ancestors
        self.children_count = 0

    def value(self, world):
        return sum(c + s * p[-1] for c, s, p in zip(self.cash, self.shares, world))

    def consume(self, world, rate):
        """结构性消费:扣现金,不足强制卖出持仓(流动行为);资产不足=饿死。"""
        need = self.value(world) * rate
        # 先扣现金
        for si in range(N_STOCKS):
            pay = min(self.cash[si], need / N_STOCKS * 0 + need)
            pass
        # 简化:总消费从总资产扣,现金不足强制卖股
        total_cash = sum(self.cash)
        if total_cash >= need:
            # 按比例从各现金扣
            for si in range(N_STOCKS):
                frac = self.cash[si] / total_cash if total_cash > 0 else 1.0 / N_STOCKS
                self.cash[si] -= need * frac
        else:
            # 现金不足:强制卖出持仓补足(流动!)
            short = need - total_cash
            for si in range(N_STOCKS):
                self.cash[si] = 0.0
                if self.holdings[si] and short > 0:
                    sell_val = self.shares[si] * world[si][-1] * 0.999
                    self.shares[si] = 0.0
                    self.holdings[si] = False
                    short -= sell_val
            if short > 0:
                return False  # 全部变卖仍不够 = 饿死
        return True


def run_epoch(worms, W_map, groups, world, consume_rate):
    for t in range(EPOCH_DAYS - 1):
        for w in worms:
            for si, prices in enumerate(world):
                r1 = prices[t + 1] / prices[t] - 1.0
                trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)]
                g = w.gene
                sense_in = math.tanh(g[1] * (r1 * 50 + trend * 20)) * g[0]
                w.mem[si] = w.mem[si] * (1 - g[7]) + sense_in
                act = np.zeros(279)
                act[groups['sense']] = w.mem[si]
                for _ in range(4):
                    act = np.tanh(W_map[id(w)] @ act)
                fwd_act = act[groups['fwd']].mean() if groups['fwd'] else 0
                back_act = act[groups['back']].mean() if groups['back'] else 0
                signal = (fwd_act - back_act) + rng.uniform(-g[8], g[8])
                if signal > g[9] and not w.holdings[si] and w.cash[si] > 0:
                    w.shares[si] = w.cash[si] / prices[t] * 0.999
                    w.cash[si] = 0.0
                    w.holdings[si] = True
                elif signal < -g[9] and w.holdings[si]:
                    w.cash[si] = w.shares[si] * prices[t] * 0.999
                    w.shares[si] = 0.0
                    w.holdings[si] = False
            w.age += 1
    # 纪元末:消费(结构性逼迫流动)
    alive = []
    for w in worms:
        if w.consume(world, consume_rate):
            alive.append(w)
    return alive


def reproduce(worms, world):
    """繁殖即清算:达繁殖线者生后代(资产分配后退出);未达者保留继续
    (被消费吃资产,最终饿死或繁殖)——种群不断代。"""
    next_gen = []
    for w in worms:
        if w.age > EPOCH_DAYS * LIFESPAN_EPOCHS:
            continue  # 寿命到期
        v = w.value(world)
        if v <= 0:
            continue
        if v >= SURVIVE_LINE:
            n_children = max(1, min(MAX_CHILDREN, int((v - 100.0) / 50.0)))
            w.children_count += n_children
            inherit = v / n_children
            for _ in range(n_children):
                child = Worm(mutate(w.gene), ancestors=w.ancestors + 1)
                for si in range(N_STOCKS):
                    child.cash[si] = inherit / N_STOCKS
                if rng.random() < CROSS_RATE:
                    partner = rng.choice([x for x in worms if x is not w] or [w])
                    child.gene = mutate(crossover(child.gene, partner.gene))
                next_gen.append(child)
            # 繁殖即清算:父代退出(资产已传给后代)
        else:
            next_gen.append(w)  # 未达繁殖线:保留继续
    # 容量淘汰:按谱系贡献(后代数)优先,保持种群
    if len(next_gen) > CAPACITY:
        next_gen.sort(key=lambda x: -x.ancestors)
        next_gen = next_gen[:CAPACITY]
    return next_gen


def evolve(consume_rate, W_real, groups, all_prices):
    base = random_gene()
    worms = [Worm(mutate(base, rate=0.6, sigma=0.6)) for _ in range(N0)]
    holds = []
    pop_sizes = []
    max_anc = 0
    for ep in range(N_EPOCHS):
        world = make_world(all_prices)
        W_map = {id(w): phenotype(w.gene, W_real, groups) for w in worms}
        worms = run_epoch(worms, W_map, groups, world, consume_rate)
        worms = reproduce(worms, world)
        pop_sizes.append(len(worms))
        hold_ratio = np.mean([sum(w.holdings) / N_STOCKS for w in worms]) if worms else 0
        holds.append(hold_ratio)
        if worms:
            max_anc = max(w.ancestors for w in worms)
    if not worms:
        return 0.0, 0.0, None, pop_sizes, holds, 0
    final_world = make_world(all_prices)
    best = max(worms, key=lambda w: w.value(final_world))
    return (np.mean([w.value(final_world) for w in worms]),
            np.mean(holds[-3:]),
            best.gene, pop_sizes, holds, max_anc)


if __name__ == '__main__':
    print('=== exp47: 生存消费机制逼迫流动 + 繁殖即清算 ===')
    W_real, groups = load_worm()
    all_prices = load_all_prices()
    print('消费率组: %s | 纪元 %d x %d 天 | 寿命 %d 纪元 | 繁殖即清算' % (
        CONSUME_RATES, N_EPOCHS, EPOCH_DAYS, LIFESPAN_EPOCHS))
    print()
    print('%-12s %12s %12s %12s %10s' % ('消费率', '平均资产', '持仓率(末3纪元)', '种群末规模', '最深谱系'))
    print('-' * 62)
    results = {}
    for rate in CONSUME_RATES:
        avg_v, hold, gene, pops, holds, anc = evolve(rate, W_real, groups, all_prices)
        results[rate] = (avg_v, hold, gene, anc)
        print('%-12s %12.1f %12.1f%% %12d %10d' % (
            rate, avg_v, hold * 100, pops[-1] if pops else 0, anc))

    print()
    print('=== 关键对比:生存消费是否逼迫流动(持仓率)? ===')
    base_hold = results[0.0][1]
    for rate in CONSUME_RATES[1:]:
        h = results[rate][1]
        print('消费 %.0f%%: 持仓率 %5.1f%% vs 无消费 %5.1f%% (%s)' % (
            rate * 100, h * 100, base_hold * 100,
            '被迫流动!' if h > base_hold + 0.1 else '未明显变化'))
    print()
    print('=== 谱系深度(世代交替是否发生) ===')
    for rate in CONSUME_RATES:
        print('消费 %.0f%%: 最深谱系 %d 代' % (rate * 100, results[rate][3]))
