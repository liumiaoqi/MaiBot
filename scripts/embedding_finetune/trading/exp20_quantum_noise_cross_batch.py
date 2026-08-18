#!/usr/bin/env python3
"""exp20: 量子信道噪声跨批次验证——batch1 + batch2 全部 18 只

exp19 在 16 只新样本发现量子信道噪声(bitflip/ampdamp/depolar)优于高斯。
本实验:exp19 最佳三配置在 batch1(8 只,高波动)+ batch2(10 只,平稳)验证
跨批次稳定性(exp16b 教训:batch2 规则在 batch1 反转——量子噪声是否也翻车?)

配置:bitflip 0.02 / ampdamp 0.02 / depolar 0.1(exp19 最佳),det 基线;
带各自政策先验(实用配置);5 seeds 平均。
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2, BEST_W, PLAN_PRIOR
from exp12_policy_prior import PLAN_PRIOR as PLAN_PRIOR_B1
from exp19_quantum_noise import TraderQNoise

WINDOW_B1 = 20
MODES = [('det', 0.0), ('bitflip', 0.02), ('ampdamp', 0.02), ('depolar', 0.1)]


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
    print('=== exp20: 量子信道噪声跨批次验证(batch1 8 + batch2 10 = 18 只) ===')
    print('配置: bitflip 0.02 / ampdamp 0.02 / depolar 0.1(exp19 最佳);带政策先验;5 seeds\n')

    # 批次定义:(code, name, window, plan)
    stocks_b1 = [(c, n, WINDOW_B1, PLAN_PRIOR_B1.get(c, 0.0)) for c, n in POOL.items()]
    stocks_b2 = [(c, n, BEST_W[c], PLAN_PRIOR.get(c, 0.0)) for c, n in POOL2.items()]
    batches = [('batch1(高波动)', stocks_b1), ('batch2(平稳)', stocks_b2)]

    for bname, stocks in batches:
        print('=== %s ===' % bname)
        header = '%-8s' % '股票'
        for m, _ in MODES:
            header += ' %10s' % m
        header += ' %9s' % '满仓'
        print(header)
        print('-' * len(header))
        agg = {m: [] for m, _ in MODES}
        fulls = []
        for code, name, window, plan in stocks:
            df = load_stock(code)
            _, test = split_train_test(df)
            full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
            fulls.append(full)
            row = '%-8s' % name
            for m, s in MODES:
                vals = [run_stock(code, window, seed=k, mode=m, strength=s, plan=plan)
                        for k in range(5)]
                avg = sum(vals) / len(vals)
                agg[m].append(avg)
                row += ' %10.1f' % avg
            row += ' %9.1f' % full
            print(row)
        print('-' * len(header))
        base = agg['det']
        for m, s in MODES:
            if m == 'det':
                continue
            mean = sum(agg[m]) / len(agg[m])
            wins = sum(1 for i, f in enumerate(fulls) if agg[m][i] > f)
            beats = sum(1 for b, a in zip(base, agg[m], strict=True) if a > b)
            gain = sum(a - b for b, a in zip(base, agg[m], strict=True)) / len(base)
            print('%-8s 平均 %7.1f 跑赢满仓 %2d/%d 跑赢基线 %2d/%d 平均噪声收益 %+6.1f'
                  % (m, mean, wins, len(stocks), beats, len(stocks), gain))
        print()
