#!/usr/bin/env python3
"""exp43: 线虫进化 v2——生存环境=整个股市(多股票组合),非单只股票

用户纠正(正确):生存环境应该是整个股市,而不是单只股——单只=幸运环境,
线虫能碰运气;市场组合=真实环境,必须适配市场整体。

设计(基于 exp42 升级):
- 股票池:18 只(batch1 8 + batch2 10,30 年数据)
- 每条线虫的世界 = 随机抽 4 只股票(行业分散)
- 每日:对每只股票独立决策(同一套基因 -> 各自信号)持有/空仓
- 适配度 = 组合期末资产(4 只等权,破产=死)
- 其余同 exp42:10 基因/交叉突变/top20% 繁殖/冠军存档

对比:exp42(单股)vs exp43(市场组合)——冠军基因差异 = 环境塑造行为
"""

import json
import math
import os
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_market')
os.makedirs(ARCHIVE, exist_ok=True)

N_POP = 50
N_GENS = 50
N_DAYS = 750
N_STOCKS = 4          # 每条线虫的世界:4 只股票
N_STEPS_DYN = 5

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
    """18 只股票(全部 30 年行情)。"""
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
    mask = rng.random(len(a)) < 0.5
    return np.where(mask, a, b)


def phenotype(gene, W_real, groups):
    W = W_real.copy()
    all_idx = np.arange(W.shape[0])
    for gi, key in enumerate(['back', 'fwd', 'turn', 'motor', 'sense']):
        idx = groups[key]
        if idx:
            W[np.ix_(idx, all_idx)] *= gene[2 + gi]
            W[np.ix_(all_idx, idx)] *= gene[2 + gi]
    return W


def run_life(W, groups, gene, world):
    """一条线虫的一生:世界=4 只股票,组合决策,期末组合资产。"""
    polarity, gain = gene[0], gene[1]
    decay, explore, thresh = gene[7], gene[8], gene[9]
    sense_idx = groups['sense']
    fwd_idx = groups['fwd']
    back_idx = groups['back']

    # 每只股票独立现金/持仓,但共享同一套神经系统(基因)
    cashes = [100.0 / N_STOCKS] * N_STOCKS
    shares = [0.0] * N_STOCKS
    holdings = [False] * N_STOCKS
    mem = [0.0] * N_STOCKS

    n = min(N_DAYS, min(len(p) for p in world) - 1)
    for t in range(n):
        for si, prices in enumerate(world):
            r1 = prices[t + 1] / prices[t] - 1.0
            trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)]
            sense_in = math.tanh(gain * (r1 * 50 + trend * 20)) * polarity
            mem[si] = mem[si] * (1 - decay) + sense_in
            # 动力学(每只股票独立但共用网络结构)
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

    value = sum(c + s * p[-1] for c, s, p in zip(cashes, shares, world))
    return max(0.0, value - 100.0)


if __name__ == '__main__':
    print('=== exp43: 线虫进化 v2——生存环境=整个股市(4 股票组合) ===')
    W_real, groups = load_worm()
    all_prices = load_all_prices()
    print('股票池: %d 只 30 年 | 每条线虫的世界 = 随机 4 只 | %d 代 x %d 线虫' % (
        len(all_prices), N_GENS, N_POP))
    print()

    base = np.array([1.0] * 10)
    base[0] = rng.uniform(-1, 1)
    pop = [base] + [mutate(base, rate=0.5, sigma=0.5) for _ in range(N_POP - 1)]

    best_history = []
    avg_history = []
    for gen in range(N_GENS):
        fitness = []
        for worm in pop:
            W = phenotype(worm, W_real, groups)
            # 世界 = 随机 4 只(每次评估换世界——避免适配某组股票)
            world = [all_prices[rng.randint(len(all_prices))]
                     for _ in range(N_STOCKS)]
            fitness.append(run_life(W, groups, worm, world))
        fitness = np.array(fitness)
        best_i = int(np.argmax(fitness))
        best_history.append(fitness[best_i])
        avg_history.append(fitness.mean())
        if gen % 10 == 0 or gen == N_GENS - 1:
            print('第 %2d 代: 平均 %7.2f | 最佳 %7.2f | 冠军: %s' % (
                gen, fitness.mean(), fitness[best_i],
                ' '.join('%.2f' % v for v in pop[best_i][:4])))

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
                      'genes': {GENE_NAMES[i]: float(champ[i]) for i in range(10)}}
            with open(os.path.join(ARCHIVE, 'champion_gen%03d.json' % gen),
                      'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=1)

    print()
    print('=== 结果(市场组合环境) ===')
    print('最佳适配度: %.1f' % max(best_history))
    print('平均适配度(每10代):', ' '.join('%.0f' % v for v in avg_history[::10]))
    champ_gene = pop[0]
    print('冠军基因:')
    for i, name in enumerate(GENE_NAMES):
        print('  %-10s %+.3f' % (name, champ_gene[i]))
    print()
    print('=== 对照 exp42(单股环境) ===')
    print('exp42 冠军: scal_fwd=2.93 scal_back=0.10(增强持有抑制空仓)')
    print('exp43 冠军: 见上——市场环境下行为守则是否不同?')
