#!/usr/bin/env python3
"""exp46: 线虫繁殖进化——连续世代种群动态(用户三方向:繁殖/残酷筛选/环境+基因多样性)

vs exp42-45(固定代数 top20% 繁殖):本实验是**连续世代种群**:
- 时间 = 纪元(每 100 天换一次世界=环境漂移,线虫必须泛化不能适配单段行情)
- 繁殖行为:每纪元末,资产 > 生存线(150,即+50%)的线虫繁殖,后代数 ∝ 超出资产
  (后代 = 父基因突变 + 概率交叉 = 有性繁殖)
- 残酷筛选:资产≤0 死;未达生存线且未繁殖 → 绝后;种群超容量 → 资产排序淘汰
- 基因多样性:20 基因 + 繁殖时突变率 0.2 交叉率 0.3;统计种群基因标准差(多样性)
- 环境多样性:每纪元随机 4 股票世界 + 20% 概率混入 -15% 危机日
"""

import json
import math
import os
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_repro')
os.makedirs(ARCHIVE, exist_ok=True)

N0 = 100            # 初始种群
CAPACITY = 200      # 种群容量(残酷)
EPOCH_DAYS = 100    # 纪元长度(环境漂移周期)
N_EPOCHS = 15       # 纪元数(1500 天)
N_STOCKS = 4
SURVIVE_LINE = 150.0  # 繁殖生存线(+50%)
REPRO_COST = 50.0     # 每 50 资产多 1 后代
MAX_CHILDREN = 5
CRISIS_PROB = 0.2     # 纪元含危机日概率
CRISIS_DROP = 0.15    # 危机日跌幅
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


def make_world(all_prices, crisis=False):
    """世界 = 随机 4 股票 + 可选危机日。"""
    world = []
    for _ in range(N_STOCKS):
        p = all_prices[rng.randint(len(all_prices))]
        start = rng.randint(0, max(1, len(p) - EPOCH_DAYS - 1))
        seg = p[start:start + EPOCH_DAYS].copy()
        if crisis:
            cd = rng.randint(1, len(seg) - 1)
            seg[cd] *= (1.0 - CRISIS_DROP)  # 危机日暴跌
        world.append(seg)
    return world


class Worm:
    __slots__ = ('gene', 'cash', 'shares', 'holdings', 'mem', 'age', 'ancestors')

    def __init__(self, gene, ancestors=1):
        self.gene = gene
        self.cash = [100.0 / N_STOCKS] * N_STOCKS
        self.shares = [0.0] * N_STOCKS
        self.holdings = [False] * N_STOCKS
        self.mem = [0.0] * N_STOCKS
        self.age = 0
        self.ancestors = ancestors  # 谱系深度(繁殖代数)

    def value(self, world):
        return sum(c + s * p[-1] for c, s, p in zip(self.cash, self.shares, world))


def run_epoch(worms, W_map, groups, world):
    """所有线虫在一个纪元(100 天)内生存。"""
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


def reproduce(worms, W_map, groups, world):
    """纪元末繁殖+筛选(残酷):资产>生存线繁殖,≤0死,未繁殖绝后,容量淘汰。"""
    survivors = []
    children = []
    for w in worms:
        v = w.value(world)
        if v <= 0:
            continue  # 破产死
        if v >= SURVIVE_LINE:
            # 繁殖:后代数 ∝ 超出资产
            n_children = min(MAX_CHILDREN, int((v - 100.0) / REPRO_COST))
            n_children = max(1, n_children)
            # 存活(交配机会)
            survivors.append(w)
            for _ in range(n_children):
                child_gene = mutate(w.gene)
                if rng.random() < CROSS_RATE:
                    partner = rng.choice([x for x in worms if x is not w]
                                         or [w])
                    child_gene = crossover(child_gene, partner.gene)
                    child_gene = mutate(child_gene)
                children.append(Worm(child_gene, ancestors=w.ancestors + 1))
        elif v < SURVIVE_LINE and w.age > EPOCH_DAYS * 2:
            continue  # 长期未达生存线:绝后淘汰
        else:
            survivors.append(w)  # 幼年期宽容
    # 容量淘汰(残酷):按资产排序留 CAPACITY
    pool = survivors + children
    if len(pool) > CAPACITY:
        vals = [(w.value(world), w) for w in pool]
        vals.sort(key=lambda x: -x[0])
        pool = [w for _, w in vals[:CAPACITY]]
    return pool


if __name__ == '__main__':
    print('=== exp46: 线虫繁殖进化(连续世代/繁殖行为/残酷筛选/环境漂移) ===')
    W_real, groups = load_worm()
    all_prices = load_all_prices()
    print('初始 %d 线虫 | 容量 %d | 纪元 %d x %d 天 | 生存线 %d(+50%%)' % (
        N0, CAPACITY, N_EPOCHS, EPOCH_DAYS, SURVIVE_LINE))
    print('繁殖: 资产每 +50 多 1 后代(最多 5) | 交叉率 %.1f 突变率 %.1f' % (
        CROSS_RATE, MUT_RATE))
    print()

    # 初始种群(真实连接基因 + 变异)
    base = random_gene()
    worms = [Worm(mutate(base, rate=0.6, sigma=0.6)) for _ in range(N0)]

    pop_size_hist = []
    avg_val_hist = []
    diversity_hist = []
    for ep in range(N_EPOCHS):
        world = make_world(all_prices, crisis=(rng.random() < CRISIS_PROB))
        W_map = {id(w): phenotype(w.gene, W_real, groups) for w in worms}
        run_epoch(worms, W_map, groups, world)
        worms = reproduce(worms, W_map, groups, world)
        vals = [w.value(world) for w in worms]
        pop_size_hist.append(len(worms))
        avg_val_hist.append(np.mean(vals))
        # 基因多样性(种群基因标准差均值)
        genes = np.array([w.gene for w in worms])
        diversity_hist.append(genes.std(axis=0).mean())
        max_anc = max(w.ancestors for w in worms)
        print('纪元 %2d: 种群 %3d | 平均资产 %7.1f | 基因多样性 %.3f | 最深谱系 %d 代' % (
            ep, len(worms), np.mean(vals), diversity_hist[-1], max_anc))
        # 存档代表线虫(每 5 纪元)
        if ep % 5 == 0 or ep == N_EPOCHS - 1:
            best = max(worms, key=lambda w: w.value(world))
            record = {'epoch': ep, 'population': len(worms),
                      'max_ancestors': max_anc,
                      'genes': {GENE_NAMES[i]: float(best.gene[i])
                                for i in range(len(GENE_NAMES))}}
            with open(os.path.join(ARCHIVE, 'epoch%02d.json' % ep),
                      'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=1)

    print()
    print('=== 结果(连续世代繁殖进化) ===')
    print('种群规模轨迹:', ' '.join(str(v) for v in pop_size_hist))
    print('平均资产轨迹:', ' '.join('%.0f' % v for v in avg_val_hist))
    print('基因多样性轨迹:', ' '.join('%.3f' % v for v in diversity_hist))
    print('最深谱系: %d 代(赛博永生的血脉深度)' % max(w.ancestors for w in worms))
    print()
    print('=== 冠军基因(最终存活种群中资产最高) ===')
    final_world = make_world(all_prices)
    best = max(worms, key=lambda w: w.value(final_world))
    for i, name in enumerate(GENE_NAMES):
        print('  %-10s %+.3f' % (name, best.gene[i]))
