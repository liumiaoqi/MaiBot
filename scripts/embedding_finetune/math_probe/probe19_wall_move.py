#!/usr/bin/env python3
"""probe19_wall_move.py -- probe11「挪墙实验」：验证「界外最优」。

假设（probe11）：scal_back 钉死下界 0.1、scal_fwd 贴上界 3.0 —— 最优在盒子外。
做法：猴补丁 E.GENE_RANGES（运行时改界），复用 exp42 全部机制与主循环，
同 seed 重跑三组：
  full      : back ∈ [-2, 3], fwd ∈ [0.1, 6]（两面墙都挪）
  back-only : back ∈ [-2, 3]
  fwd-only  : fwd ∈ [0.1, 6]
基线（不挪）= probe11 已跑的 data_exp42/curve.csv（同 seed 同流程）。
若变体 best 显著高于基线 => 实锤「墙挡路」并量化挡掉多少。
跑法: ../.venv/Scripts/python.exe probe19_wall_move.py
"""
import json
import os
import sys

import numpy as np

TRADING = r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading'
sys.path.insert(0, TRADING)
import exp42_worm_evolution as E  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data_exp42')
os.makedirs(OUT, exist_ok=True)

BASE = [(-1.0, 1.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0),
        (0.1, 3.0), (0.1, 3.0), (0.0, 1.0), (0.0, 0.5), (-0.5, 0.5)]


def make_ranges(back_lo=0.1, fwd_hi=3.0):
    r = list(BASE)
    r[2] = (back_lo, 3.0)     # scal_back
    r[3] = (0.1, fwd_hi)      # scal_fwd
    return r


def run_variant(ranges, tag, gens=None, seed=20260818):
    E.GENE_RANGES = ranges
    E.rng = np.random.RandomState(seed)   # 同起点，可比
    W_real, groups = E.load_worm()
    prices_all = E.load_prices()
    rng = E.rng
    pop = []
    base = np.array([1.0] * 10)
    base[0] = rng.uniform(-1, 1)
    pop.append(base)
    for _ in range(E.N_POP - 1):
        pop.append(E.mutate(base, rate=0.5, sigma=0.5))
    curve = []
    for gen in range(E.N_GENS):
        fitness = []
        for worm in pop:
            W = E.phenotype(worm, W_real, groups)
            prices = prices_all[rng.randint(len(prices_all))]
            fitness.append(E.run_life(W, groups, worm, prices))
        fitness = np.array(fitness)
        best_i = int(np.argmax(fitness))
        curve.append((gen, float(fitness[best_i]), float(fitness.mean())))
        order = np.argsort(fitness)[::-1]
        survivors = [pop[i] for i in order[:max(2, E.N_POP // 5)]]
        new_pop = [survivors[0].copy()]
        while len(new_pop) < E.N_POP:
            a, b = rng.choice(len(survivors), 2, replace=False)
            child = E.crossover(survivors[a], survivors[b])
            child = E.mutate(child)
            new_pop.append(child)
        pop = new_pop
    arr = np.array(curve)
    np.savetxt(os.path.join(OUT, 'wall_%s.csv' % tag), arr, fmt='%.4f', delimiter=',')
    print('%s: gen0 %.1f -> gen49 %.1f' % (tag, arr[0, 1], arr[-1, 1]))
    return arr


if __name__ == '__main__':
    print('=== probe19: wall-move experiment (exp42 mechanics, same seed) ===')
    print('baseline (probe11) = data_exp42/curve.csv')
    runs = [
        (make_ranges(back_lo=-2.0, fwd_hi=6.0), 'full'),
        (make_ranges(back_lo=-2.0, fwd_hi=3.0), 'backonly'),
        (make_ranges(back_lo=0.1, fwd_hi=6.0), 'fwdonly'),
    ]
    results = {}
    for r, tag in runs:
        results[tag] = run_variant(r, tag)

    base_arr = np.loadtxt(os.path.join(OUT, 'curve.csv'), delimiter=',', skiprows=1)
    print()
    print('%-10s %12s %12s %12s %12s' % ('gen', 'baseline', 'full', 'backonly', 'fwdonly'))
    for g in [0, 10, 20, 30, 40, 49]:
        b = base_arr[base_arr[:, 0] == g][0, 1]
        f = results['full'][g, 1]
        bo = results['backonly'][g, 1]
        fo = results['fwdonly'][g, 1]
        print('%-10d %12.1f %12.1f %12.1f %12.1f' % (g, b, f, bo, fo))
    b_final = base_arr[-1, 1]
    print()
    print('final ratios vs baseline: full x%.2f | backonly x%.2f | fwdonly x%.2f' % (
        results['full'][-1, 1] / b_final,
        results['backonly'][-1, 1] / max(b_final, 1e-9),
        results['fwdonly'][-1, 1] / max(b_final, 1e-9)))
