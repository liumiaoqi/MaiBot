#!/usr/bin/env python3
"""exp16b: batch1 验证——交易频率规则是否跨批次成立

exp16 在 batch2 发现:噪声收益 × 测试段交易次数 Spearman = -0.818
(低频交易者受益/高频交易者受害)。本实验在 batch1 8 只上验证该规则。

方法:与 exp16 完全一致(noise 0/0.02/0.05/0.1/0.2 × 5 seeds 平均,
噪声收益 = max(noise>0)-noise=0),batch1 用 window=20 + 时代年轮政策先验。
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from data_loader import POOL, load_stock, split_train_test
from exp15_noise_vs_deterministic import TraderNoise

NOISES = [0.0, 0.02, 0.05, 0.1, 0.2]
SEEDS = range(5)
WINDOW = 20

# batch1 时代年轮政策先验(exp12——当时可得)
PLAN_PRIOR_B1 = {'600519': 0.5, '600900': 1.0, '601919': 0.0, '600340': -1.0,
                 '000001': 0.0, '601857': -0.3, '600028': -0.3, '000300': 0.3}


def spearman(x, y):
    rx = np.argsort(np.argsort(np.array(x, dtype=float))).astype(float)
    ry = np.argsort(np.argsort(np.array(y, dtype=float))).astype(float)
    n = len(rx)
    mx = rx.mean(); my = ry.mean()
    cov = ((rx - mx) * (ry - my)).sum()
    sx = np.sqrt(((rx - mx) ** 2).sum())
    sy = np.sqrt(((ry - my) ** 2).sum())
    return cov / (sx * sy) if sx * sy > 0 else 0.0


def run_noise_b1(code, seed, input_noise):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderNoise(seed=seed, input_noise=input_noise)
    plan = PLAN_PRIOR_B1.get(code, 0.0)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-WINDOW:] if len(rets) > WINDOW else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s,
                                100.0 * p / prices[0], noisy=True)
        else:
            hist.append(p)
        prev = p
    tp = test['close'].values
    trades = 0
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-WINDOW:] if len(rets3) > WINDOW else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            a, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3,
                                   100.0 * p / tp[0], noisy=False)
            if a in ('buy', 'sell'):
                trades += 1
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1], trades


if __name__ == '__main__':
    print('=== exp16b: batch1 验证——交易频率规则跨批次成立? ===')
    print('噪声收益 = max(noise>0) - noise=0(5 seeds 平均);batch1 8 只,window=20\n')

    rows = []
    for code, name in POOL.items():
        avgs = {}
        for n in NOISES:
            vals = [run_noise_b1(code, seed=s, input_noise=n)[0] for s in SEEDS]
            avgs[n] = sum(vals) / len(vals)
        gain = max(avgs[n] for n in NOISES[1:]) - avgs[0.0]
        best_n = max(NOISES[1:], key=lambda n: avgs[n])
        trades = run_noise_b1(code, seed=42, input_noise=0.0)[1]
        df = load_stock(code)
        _, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        rows.append({'name': name, 'gain': gain, 'best_noise': best_n,
                     'trades': trades, 'n0': avgs[0.0], 'full': full})
        print('%-6s 噪声收益 %+7.1f (最佳 %.2f) 交易%3d | noise0 %7.1f 满仓 %7.1f'
              % (name, gain, best_n, trades, avgs[0.0], full))

    s = spearman([r['trades'] for r in rows], [r['gain'] for r in rows])
    print()
    print('=== 交易次数 × 噪声收益 Spearman = %+.3f (batch2 为 -0.818) ===' % s)
    winners = [r for r in rows if r['gain'] > 0]
    losers = [r for r in rows if r['gain'] <= 0]
    print('受益(%d): %s' % (len(winners), ' '.join(r['name'] for r in winners)))
    print('受害(%d): %s' % (len(losers), ' '.join(r['name'] for r in losers)))
    if winners and losers:
        wm = sum(r['trades'] for r in winners) / len(winners)
        lm = sum(r['trades'] for r in losers) / len(losers)
        print('受益组平均交易 %6.1f vs 受害组平均交易 %6.1f' % (wm, lm))
    if abs(s) >= 0.5:
        print('结论:规则在 batch1 成立(|r|>=0.5)')
    else:
        print('结论:规则在 batch1 弱化/不成立(|r|<0.5)——跨批次稳定性存疑')
