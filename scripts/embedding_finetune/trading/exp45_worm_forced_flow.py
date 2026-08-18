#!/usr/bin/env python3
"""exp45: 胁迫环境——现金税逼迫经济流动(用户构想)

当前(exp43/44):进化出"空仓保命"——现金不流动也能活。
用户:制造胁迫环境,逼迫经济必须流动——给现金加持有成本(现金税/通胀):
  持有现金每日贬值 tax——躺着不动资产缩水,必须把钱投入市场(流动)。

4 组对照(控制变量,exp43 框架):
  tax=0       无税(基线——可空仓保命)
  tax=0.0005  温和(年化 ~12% 通胀)
  tax=0.001   强(年化 ~24%)
  tax=0.002   极端(现金烫手)

指标:进化后平均持仓率(经济流动指标)/适配度/冠军基因(空仓是否被迫放弃)
+ 极限测试(最差行情被迫流动 vs 保命)的代价
"""

import json
import math
import os
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_flow')
os.makedirs(ARCHIVE, exist_ok=True)

N_POP = 40
N_GENS = 30
N_DAYS = 600
N_STOCKS = 4
N_STEPS_DYN = 4
TAXES = [0.0, 0.0005, 0.001, 0.002]

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


def mutate(gene, rate=0.2, sigma=0.3):
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


def run_life(W, groups, gene, world, tax):
    """一生:4 股票组合 + 现金税;返回(收益, 持仓率)。"""
    polarity, gain = gene[0], gene[1]
    decay, explore, thresh = gene[7], gene[8], gene[9]
    sense_idx = groups['sense']
    fwd_idx = groups['fwd']
    back_idx = groups['back']

    cashes = [100.0 / N_STOCKS] * N_STOCKS
    shares = [0.0] * N_STOCKS
    holdings = [False] * N_STOCKS
    mem = [0.0] * N_STOCKS
    hold_days = 0
    n = min(N_DAYS, min(len(p) for p in world) - 1)

    for t in range(n):
        for si, prices in enumerate(world):
            r1 = prices[t + 1] / prices[t] - 1.0
            trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)]
            sense_in = math.tanh(gain * (r1 * 50 + trend * 20)) * polarity
            mem[si] = mem[si] * (1 - decay) + sense_in
            act = np.zeros(279)
            act[sense_idx] = mem[si]
            for _ in range(N_STEPS_DYN):
                act = np.tanh(W @ act)
            fwd_act = act[fwd_idx].mean() if fwd_idx else 0
            back_act = act[back_idx].mean() if back_idx else 0
            signal = (fwd_act - back_act) + rng.uniform(-explore, explore)
            if signal > thresh and not holdings[si] and cashes[si] > 0:
                shares[si] = cashes[si] / prices[t] * 0.999
                cashes[si] = 0.0
                holdings[si] = True
            elif signal < -thresh and holdings[si]:
                cashes[si] = shares[si] * prices[t] * 0.999
                shares[si] = 0.0
                holdings[si] = False
            if holdings[si]:
                hold_days += 1
            # 现金税:持有现金每日贬值(胁迫流动)
            cashes[si] *= (1.0 - tax)

    value = sum(c + s * p[-1] for c, s, p in zip(cashes, shares, world))
    hold_rate = hold_days / (n * N_STOCKS)
    return max(0.0, value - 100.0), hold_rate


def make_world(all_prices):
    world = []
    for _ in range(N_STOCKS):
        p = all_prices[rng.randint(len(all_prices))]
        start = rng.randint(0, max(1, len(p) - N_DAYS - 1))
        world.append(p[start:start + N_DAYS])
    return world


def evolve(tax, W_real, groups, all_prices):
    base = random_gene()
    pop = [base] + [mutate(base, rate=0.5, sigma=0.5) for _ in range(N_POP - 1)]
    for gen in range(N_GENS):
        fitness = []
        W_list = [phenotype(g, W_real, groups) for g in pop]
        for i, worm in enumerate(pop):
            world = make_world(all_prices)
            f, _ = run_life(W_list[i], groups, worm, world, tax)
            fitness.append(f)
        fitness = np.array(fitness)
        order = np.argsort(fitness)[::-1]
        survivors = [pop[i] for i in order[:max(2, N_POP // 5)]]
        new_pop = [survivors[0].copy()]
        while len(new_pop) < N_POP:
            a, b = rng.choice(len(survivors), 2, replace=False)
            new_pop.append(mutate(crossover(survivors[a], survivors[b])))
        pop = new_pop
    # 最后一代评估:收益 + 持仓率(多世界平均)
    champ = pop[0]
    W = phenotype(champ, W_real, groups)
    fits = []
    holds = []
    for _ in range(8):
        world = make_world(all_prices)
        f, h = run_life(W, groups, champ, world, tax)
        fits.append(f)
        holds.append(h)
    return np.mean(fits), np.mean(holds), champ


if __name__ == '__main__':
    print('=== exp45: 胁迫环境——现金税逼迫经济流动 ===')
    W_real, groups = load_worm()
    all_prices = load_all_prices()
    print('股票池 %d | 40 线虫 x 30 代 x %d 天 | 现金税组: %s' % (
        len(all_prices), N_DAYS, TAXES))
    print()

    print('%-10s %12s %12s %12s %12s %12s' % (
        '现金税/日', '最佳适配度', '平均持仓率', 'polarity', 'scal_back', 'scal_fwd'))
    print('-' * 72)
    results = {}
    for tax in TAXES:
        best, hold_rate, champ = evolve(tax, W_real, groups, all_prices)
        results[tax] = (best, hold_rate, champ)
        print('%-10s %12.1f %12.1f%% %12.2f %12.2f %12.2f' % (
            tax, best, hold_rate * 100, champ[0], champ[2], champ[3]))

    print()
    print('=== 关键对比:现金税是否逼迫流动? ===')
    base_hold = results[0.0][1]
    for tax in TAXES[1:]:
        h = results[tax][1]
        print('tax=%.4f: 持仓率 %5.1f%% vs 无税 %5.1f%% (%s)' % (
            tax, h * 100, base_hold * 100,
            '被迫流动' if h > base_hold + 0.05 else '未明显变化'))
    print()
    print('=== 进化策略变化 ===')
    for tax in TAXES:
        champ = results[tax][2]
        print('tax=%.4f: polarity %+.2f | scal_back %.2f | scal_fwd %.2f' % (
            tax, champ[0], champ[2], champ[3]))
