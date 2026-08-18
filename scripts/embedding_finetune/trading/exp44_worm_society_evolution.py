#!/usr/bin/env python3
"""exp44: 线虫社会进化——环境+基因+社会三重复杂化 + 环境极限测试

用户方向:①生存环境和基因结构多样性同步加强 ②线虫社会存在复杂化
③实验线虫环境极限

升级(基于 exp43):
1. 基因 10→20:
   g0-9   同 exp43(极性/增益/5行为组/遗忘/探索/阈值)
   g10-12 特征偏好(ret 日内/trend 趋势/vol 波动率权重)
   g13-14 社交基因(从众强度/从众极性——从众 or 反从众)
   g15-19 社区块缩放(exp41 谱聚类 5 社区,每个社区连接块独立缩放)
2. 线虫社会:所有线虫共享同一个世界(5 只股票),每日同步生存:
   - 群体信号:其他线虫昨日平均持仓 -> 社交基因调制(从众/反从众)
   - 拥挤惩罚:>60% 线虫持有同一股票时,该股收益 0.98 折价(资源竞争)
3. 环境极限:最后测冠军线虫在"历史最差 750 天窗口"(每只股票最差段)的存活
"""

import json
import math
import os
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_society')
os.makedirs(ARCHIVE, exist_ok=True)

N_POP = 40
N_GENS = 40
N_DAYS = 600
N_STOCKS = 5
N_STEPS_DYN = 4
CROWD_RATIO = 0.6
CROWD_DISCOUNT = 0.98

GENE_NAMES = (['polarity', 'gain', 'scal_back', 'scal_fwd', 'scal_turn',
               'scal_motor', 'scal_sense', 'decay', 'explore', 'threshold']
              + ['w_ret', 'w_trend', 'w_vol']
              + ['social_strength', 'social_polarity']
              + ['comm_%d' % i for i in range(5)])
GENE_RANGES = ([(-1, 1), (0.1, 3), (0.1, 3), (0.1, 3), (0.1, 3), (0.1, 3),
                (0.1, 3), (0, 1), (0, 0.5), (-0.5, 0.5)]
               + [(0, 1)] * 3 + [(0, 1), (-1, 1)] + [(0.1, 3)] * 5)

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


def spectral_clusters(W, k=5):
    d = W.sum(axis=1) + 1e-9
    Dinv = np.diag(1.0 / np.sqrt(d))
    L = np.eye(len(W)) - Dinv @ W @ Dinv
    evals, evecs = np.linalg.eigh(L)
    feats = evecs[:, :k]
    centroids = feats[rng.choice(len(feats), k, replace=False)]
    labels = np.zeros(len(feats), dtype=int)
    for _ in range(20):
        dist = ((feats[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        labels = dist.argmin(axis=1)
        for c in range(k):
            if (labels == c).sum() > 0:
                centroids[c] = feats[labels == c].mean(axis=0)
    return labels


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


def phenotype(gene, W_real, groups, comm_labels):
    W = W_real.copy()
    all_idx = np.arange(W.shape[0])
    for gi, key in enumerate(['back', 'fwd', 'turn', 'motor', 'sense']):
        idx = groups[key]
        if idx:
            W[np.ix_(idx, all_idx)] *= gene[2 + gi]
            W[np.ix_(all_idx, idx)] *= gene[2 + gi]
    for c in range(5):
        idx = np.where(comm_labels == c)[0]
        if len(idx) > 0:
            W[np.ix_(idx, all_idx)] *= gene[15 + c]
            W[np.ix_(all_idx, idx)] *= gene[15 + c]
    return W


def make_world(all_prices, n_stocks=N_STOCKS, days=N_DAYS):
    """世界 = 随机 n 只股票,每只随机起点(随机时代切片)。"""
    world = []
    for _ in range(n_stocks):
        p = all_prices[rng.randint(len(all_prices))]
        start = rng.randint(0, max(1, len(p) - days - 1))
        world.append(p[start:start + days])
    return world


def run_generation(W_list, groups, genes, world):
    """一代所有线虫在同一世界共享生存(社会模型)。"""
    n = len(genes)
    n_days = min(N_DAYS, min(len(p) for p in world) - 1)
    n_stocks = len(world)
    cashes = np.full((n, n_stocks), 100.0 / n_stocks)
    shares = np.zeros((n, n_stocks))
    holdings = np.zeros((n, n_stocks), dtype=bool)
    mem = np.zeros((n, n_stocks))
    group_hold = np.zeros(n_stocks)  # 群体持仓比例

    for t in range(n_days):
        for si in range(n_stocks):
            prices = world[si]
            r1 = prices[t + 1] / prices[t] - 1.0
            trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)]
            vol = np.std(prices[max(0, t - 20):t + 1]) / prices[t] if t >= 20 else 0.01
            exec_p = prices[t]
            # 拥挤惩罚:群体持仓比例高 -> 折价(提前判断当日群体)
            crowd_discount = 1.0
            for i in range(n):
                g = genes[i]
                sense_in = math.tanh(g[1] * (g[10] * r1 * 50 + g[11] * trend * 20
                                             + g[12] * vol * 200)) * g[0]
                mem[i][si] = mem[i][si] * (1 - g[7]) + sense_in
                act = np.zeros(279)
                act[groups['sense']] = mem[i][si]
                for _ in range(N_STEPS_DYN):
                    act = np.tanh(W_list[i] @ act)
                fwd_act = act[groups['fwd']].mean() if groups['fwd'] else 0
                back_act = act[groups['back']].mean() if groups['back'] else 0
                # 社交信号:群体持仓 -> 从众/反从众
                social = (g[13] * (group_hold[si] - 0.5) * g[14])
                signal = (fwd_act - back_act) + social + rng.uniform(-g[8], g[8])
                if signal > g[9] and not holdings[i][si] and cashes[i][si] > 0:
                    shares[i][si] = cashes[i][si] / exec_p * 0.999
                    cashes[i][si] = 0.0
                    holdings[i][si] = True
                elif signal < -g[9] and holdings[i][si]:
                    cashes[i][si] = shares[i][si] * exec_p * 0.999
                    shares[i][si] = 0.0
                    holdings[i][si] = False
            # 当日更新后:拥挤惩罚作用于下一日价格
            hold_ratio = holdings[:, si].mean()
            group_hold[si] = hold_ratio
        # 拥挤折价:高拥挤股票的持仓者次日收益折扣(模拟资源竞争)
        for si in range(n_stocks):
            if group_hold[si] > CROWD_RATIO:
                for i in range(n):
                    if holdings[i][si]:
                        shares[i][si] *= CROWD_DISCOUNT

    fitness = []
    for i in range(n):
        value = sum(cashes[i][si] + shares[i][si] * world[si][-1]
                    for si in range(n_stocks))
        fitness.append(max(0.0, value - 100.0))
    return np.array(fitness)


def extreme_test(W, groups, gene, all_prices):
    """环境极限:每只股票历史最差 750 天窗口,冠军线虫存活测试。"""
    results = []
    for p in all_prices:
        if len(p) < N_DAYS + 1:
            continue
        worst_start = None
        worst_ret = float('inf')
        for s in range(0, len(p) - N_DAYS, 30):
            r = p[s + N_DAYS] / p[s] - 1
            if r < worst_ret:
                worst_ret = r
                worst_start = s
        world = [p[worst_start:worst_start + N_DAYS]]
        f = run_generation([W], groups, [gene], world)
        results.append(f[0] + 100.0)
    return np.mean(results), min(results), results


if __name__ == '__main__':
    print('=== exp44: 线虫社会进化(20基因 + 共享世界 + 拥挤竞争 + 从众/反从众) ===')
    W_real, groups = load_worm()
    comm_labels = spectral_clusters(W_real, 5)
    all_prices = load_all_prices()
    print('股票池 %d | 世界 = 5 只共享 | 40 线虫 x 40 代 | 基因 %d' % (
        len(all_prices), len(GENE_NAMES)))
    print()

    base = random_gene()
    pop = [base] + [mutate(base, rate=0.5, sigma=0.5) for _ in range(N_POP - 1)]
    best_history = []
    avg_history = []
    for gen in range(N_GENS):
        world = make_world(all_prices)
        W_list = [phenotype(g, W_real, groups, comm_labels) for g in pop]
        fitness = run_generation(W_list, groups, pop, world)
        best_i = int(np.argmax(fitness))
        best_history.append(fitness[best_i])
        avg_history.append(fitness.mean())
        if gen % 8 == 0 or gen == N_GENS - 1:
            print('第 %2d 代: 平均 %8.1f | 最佳 %9.1f' % (gen, fitness.mean(),
                                                         fitness[best_i]))
        order = np.argsort(fitness)[::-1]
        survivors = [pop[i] for i in order[:max(2, N_POP // 5)]]
        new_pop = [survivors[0].copy()]
        while len(new_pop) < N_POP:
            a, b = rng.choice(len(survivors), 2, replace=False)
            new_pop.append(mutate(crossover(survivors[a], survivors[b])))
        pop = new_pop
        if gen % 10 == 0 or gen == N_GENS - 1:
            champ = pop[0]
            record = {'gen': gen, 'fitness': float(max(fitness)),
                      'genes': {GENE_NAMES[i]: float(champ[i]) for i in range(len(GENE_NAMES))}}
            with open(os.path.join(ARCHIVE, 'champion_gen%03d.json' % gen),
                      'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=1)

    print()
    print('=== 结果(社会环境) ===')
    print('最佳适配度: %.1f' % max(best_history))
    print('平均(每8代):', ' '.join('%.0f' % v for v in avg_history[::8]))
    champ = pop[0]
    print('冠军基因(关键):')
    for i, name in enumerate(['polarity', 'gain', 'scal_back', 'scal_fwd',
                              'w_ret', 'w_trend', 'w_vol', 'social_strength',
                              'social_polarity', 'decay', 'explore']):
        print('  %-16s %+.3f' % (name, champ[GENE_NAMES.index(name)]))
    print()
    print('=== 环境极限测试(历史最差 750 天窗口) ===')
    mean_w, min_w, all_r = extreme_test(phenotype(champ, W_real, groups, comm_labels),
                                        groups, champ, all_prices)
    print('冠军线虫在最差行情: 平均资产 %.1f | 最惨 %.1f(初始 100)' % (mean_w, min_w))
    print('存活(>0): %d/%d 段' % (sum(1 for r in all_r if r > 1), len(all_r)))
