#!/usr/bin/env python3
"""exp25: exp21 复核——大随机种子列表(方差修正后)

exp24 发现:连续小种子 std 低估 30-40%。本实验用固定大随机种子列表
(secrets.randbelow(10^9) 生成,存列表保证可复现)重跑 exp21 全部配置,
复核:均值微正(+2.1)是否稳健?std 是否如预期放大?稳定受益是否变化?
"""

import random
import secrets
import sys
import os
import statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2, BEST_W, PLAN_PRIOR
from exp12_policy_prior import PLAN_PRIOR as PLAN_PRIOR_B1
from exp19_quantum_noise import TraderQNoise, POOL3

# 固定大随机种子列表(10 个,secrets 生成——可复现 + 方差正确)
BIG_SEEDS = [secrets.randbelow(10**9) for _ in range(10)]
print('大随机种子列表:', BIG_SEEDS)

MODES = [('det', 0.0), ('gauss', 0.02), ('bitflip', 0.02), ('ampdamp', 0.02),
         ('depolar', 0.1)]

STOCKS = []
for c, n in POOL.items():
    STOCKS.append((c, n, 20, PLAN_PRIOR_B1.get(c, 0.0)))
for c, n in POOL2.items():
    STOCKS.append((c, n, BEST_W[c], PLAN_PRIOR.get(c, 0.0)))
for c, n in POOL3.items():
    STOCKS.append((c, n, 20, 0.0))


def run_stock(code, window, seed, mode, strength, plan):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderQNoise(seed=seed, noise_mode=mode, strength=strength)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-window:] if len(rets) > window else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s,
                                100.0 * p / prices[0], noisy=True)
        else:
            hist.append(p)
        prev = p
    tp = test['close'].values
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-window:] if len(rets3) > window else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3,
                                   100.0 * p / tp[0], noisy=False)
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1]


if __name__ == '__main__':
    print('=== exp25: exp21 复核(大随机种子,方差修正) ===')
    print('34 只 × 5 模式 × 10 大随机种子\n')

    results = {m: {} for m, _ in MODES}
    for idx, (code, name, window, plan) in enumerate(STOCKS):
        for m, s in MODES:
            vals = [run_stock(code, window, seed=seed, mode=m, strength=s, plan=plan)
                    for seed in BIG_SEEDS]
            results[m][code] = vals
        if (idx + 1) % 10 == 0 or idx == len(STOCKS) - 1:
            print('... %d/%d 只完成' % (idx + 1, len(STOCKS)))

    fulls = {}
    for code, name, window, plan in STOCKS:
        df = load_stock(code)
        _, test = split_train_test(df)
        fulls[code] = 100 * test['close'].iloc[-1] / test['close'].iloc[0]

    print()
    print('=== 汇总(34 只 × 10 大随机种子)vs exp21(连续小种子) ===')
    print('%-10s %8s %8s %8s %8s %8s %8s %8s' % (
        '模式', '均值', 'exp21均值', 'std均', 'exp21std', '跑赢满仓', '跑赢基线', '稳定受益'))
    print('-' * 76)
    for m, s in MODES:
        means = [statistics.mean(results[m][c]) for c, *_ in STOCKS]
        stds = [statistics.stdev(results[m][c]) for c, *_ in STOCKS]
        wins = sum(1 for i, (c, *_ ) in enumerate(STOCKS) if means[i] > fulls[c])
        exp21_means = {'det': 109.9, 'gauss': 110.6, 'bitflip': 111.9,
                       'ampdamp': 112.0, 'depolar': 111.3}
        exp21_stds = {'det': 33.75, 'gauss': 34.29, 'bitflip': 36.00,
                      'ampdamp': 35.51, 'depolar': 34.01}
        if m == 'det':
            beats = '-'
            stable = '-'
        else:
            beats = sum(1 for c, *_ in STOCKS
                        if statistics.mean(results[m][c]) >
                        statistics.mean(results['det'][c]))
            stable = sum(1 for c, *_ in STOCKS
                         if sum(1 for a, b in zip(results[m][c], results['det'][c], strict=True)
                                if a > b) >= 8)
        print('%-10s %8.1f %8.1f %8.2f %8.2f %8s %8s %8s' % (
            m, sum(means) / len(means), exp21_means[m],
            sum(stds) / len(stds), exp21_stds[m], wins, beats, stable))

    print()
    print('=== 复核结论 ===')
    base = [statistics.mean(results['det'][c]) for c, *_ in STOCKS]
    for m, s in MODES[1:]:
        mm = [statistics.mean(results[m][c]) for c, *_ in STOCKS]
        gain = sum(a - b for b, a in zip(base, mm, strict=True)) / len(mm)
        print('%-10s 平均噪声收益 %+6.1f (exp21 为 %+6.1f)' % (
            m, gain, {'gauss': 0.7, 'bitflip': 2.0, 'ampdamp': 2.1, 'depolar': 1.4}[m]))
