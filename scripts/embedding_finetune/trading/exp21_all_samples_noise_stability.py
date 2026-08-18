#!/usr/bin/env python3
"""exp21: 全样本(34 只)× 多 seeds(10)量子噪声稳定性验证

用户要求:所有样本都要跑(exp19 16 只 + batch1 8 + batch2 10 = 34),多跑几次看随机性。
设计:5 模式(det/gauss0.02/bitflip0.02/ampdamp0.02/depolar0.1)× 10 seeds × 34 只
输出:每模式跨 seeds 的 mean/std(随机性) + 每只股票 10 seeds 中跑赢 det 的次数(稳定受益计数)
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statistics
from data_loader import POOL, load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2, BEST_W, PLAN_PRIOR
from exp12_policy_prior import PLAN_PRIOR as PLAN_PRIOR_B1
from exp19_quantum_noise import TraderQNoise, POOL3

SEEDS = range(10)
MODES = [('det', 0.0), ('gauss', 0.02), ('bitflip', 0.02), ('ampdamp', 0.02),
         ('depolar', 0.1)]

# 全部 34 只:(code, name, window, plan)
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
    print('=== exp21: 全样本 34 只 × 10 seeds——量子噪声稳定性 ===')
    print('模式: det / gauss0.02 / bitflip0.02 / ampdamp0.02 / depolar0.1\n')

    # 每模式:每只股票 10 seeds 结果
    results = {m: {} for m, _ in MODES}
    for idx, (code, name, window, plan) in enumerate(STOCKS):
        for m, s in MODES:
            vals = [run_stock(code, window, seed=k, mode=m, strength=s, plan=plan)
                    for k in SEEDS]
            results[m][code] = vals
        if (idx + 1) % 5 == 0 or idx == len(STOCKS) - 1:
            print('... %d/%d 只完成' % (idx + 1, len(STOCKS)))

    print()
    print('=== 每模式汇总(34 只 × 10 seeds) ===')
    header = '%-10s %8s %8s %8s %8s %8s %8s' % (
        '模式', '均值', '中位', 'std均', '跑赢满仓', '跑赢基线', '稳定受益')
    print(header)
    print('-' * len(header))
    fulls = {}
    for code, name, window, plan in STOCKS:
        df = load_stock(code)
        _, test = split_train_test(df)
        fulls[code] = 100 * test['close'].iloc[-1] / test['close'].iloc[0]

    for m, s in MODES:
        means = [statistics.mean(results[m][c]) for c, *_ in STOCKS]
        meds = [statistics.median(results[m][c]) for c, *_ in STOCKS]
        stds = [statistics.stdev(results[m][c]) for c, *_ in STOCKS]
        wins = sum(1 for i, (c, *_ ) in enumerate(STOCKS) if means[i] > fulls[c])
        if m == 'det':
            beats = '-'
            stable = '-'
        else:
            beats = sum(1 for c, *_ in STOCKS
                        if statistics.mean(results[m][c]) >
                        statistics.mean(results['det'][c]))
            # 稳定受益:10 seeds 中至少 8 次跑赢 det
            stable = sum(1 for c, *_ in STOCKS
                         if sum(1 for a, b in zip(results[m][c], results['det'][c], strict=True)
                                if a > b) >= 8)
        print('%-10s %8.1f %8.1f %8.2f %8s %8s %8s' % (
            m, sum(means) / len(means), statistics.median(meds),
            sum(stds) / len(stds), wins, beats, stable))

    print()
    print('=== 受益/受害股票清单(相对 det 均值) ===')
    for m, s in MODES[1:]:
        gainers = []
        losers = []
        for code, name, *_ in STOCKS:
            g = statistics.mean(results[m][code]) - statistics.mean(results['det'][code])
            if g > 1.0:
                gainers.append('%s(%+.0f)' % (name, g))
            elif g < -1.0:
                losers.append('%s(%+.0f)' % (name, g))
        print('%-9s 受益: %s' % (m, ' '.join(gainers) if gainers else '无'))
        print('%-9s 受害: %s' % ('', ' '.join(losers) if losers else '无'))

    print()
    print('=== 随机性观察(每模式 std 均 vs det) ===')
    det_std = statistics.mean([statistics.stdev(results['det'][c]) for c, *_ in STOCKS])
    print('det std 均 = %.2f' % det_std)
    for m, s in MODES[1:]:
        std_m = statistics.mean([statistics.stdev(results[m][c]) for c, *_ in STOCKS])
        print('%-9s std 均 = %.2f (%s)' % (m, std_m, '更高' if std_m > det_std else '更低'))
