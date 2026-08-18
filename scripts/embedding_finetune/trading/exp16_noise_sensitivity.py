#!/usr/bin/env python3
"""exp16: 噪声受益股票的识别特征——哪类股票该加噪声?

问题:exp15 发现噪声对部分股票是救命药(五粮液/恒瑞),对部分股票是毒药(三一)。
本实验:找"噪声收益"与股票特征的关联——什么特征的股票,训练段加噪声能提升测试段收益?

特征候选(训练段/测试段均可从数据算出,不依赖训练):
- train_vol    训练段日收益 std(训练段波动率)
- test_vol     测试段日收益 std(测试段波动率)
- vol_ratio    测试段波动率 / 训练段波动率(模式漂移代理)
- ret_shift    测试段与训练段日均收益差绝对值(均值漂移)
- train_trend  训练段总涨幅(涨跌方向)
- dist_dist    训练/测试收益分布距离(10 分位点平均绝对差——模式差异)
- n_trade_0    noise=0 时的交易次数(纪律性代理)

噪声收益 = max(noise>0 的平均终值) - noise=0 平均终值(>0 受益,<0 受害)
输出:特征 × 噪声收益的 Spearman 秩相关 + 每只股票明细。
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np
from data_loader import load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2, BEST_W, run_noise

NOISES = [0.0, 0.02, 0.05, 0.1, 0.2]
SEEDS = range(5)


def spearman(x, y):
    """Spearman 秩相关(numpy 实现)。"""
    rx = np.argsort(np.argsort(np.array(x, dtype=float)))
    ry = np.argsort(np.argsort(np.array(y, dtype=float)))
    rx = rx.astype(float)
    ry = ry.astype(float)
    n = len(rx)
    mx = rx.mean(); my = ry.mean()
    cov = ((rx - mx) * (ry - my)).sum()
    sx = np.sqrt(((rx - mx) ** 2).sum())
    sy = np.sqrt(((ry - my) ** 2).sum())
    return cov / (sx * sy) if sx * sy > 0 else 0.0


def features(code):
    df = load_stock(code)
    train, test = split_train_test(df)
    tr = train['close'].pct_change().dropna().values
    te = test['close'].pct_change().dropna().values
    f = {}
    f['train_vol'] = float(np.std(tr))
    f['test_vol'] = float(np.std(te))
    f['vol_ratio'] = f['test_vol'] / f['train_vol'] if f['train_vol'] > 0 else 1.0
    f['ret_shift'] = float(abs(te.mean() - tr.mean()))
    f['train_trend'] = float(train['close'].iloc[-1] / train['close'].iloc[0] - 1.0)
    # 分布距离:10 分位点平均绝对差
    qs = np.percentile(tr, [10, 20, 30, 40, 50, 60, 70, 80, 90])
    qe = np.percentile(te, [10, 20, 30, 40, 50, 60, 70, 80, 90])
    f['dist_dist'] = float(np.mean(np.abs(qs - qe)))
    return f


def count_trades(code, window):
    """noise=0 时的测试段交易次数(用单 seed 估计)。"""
    df = load_stock(code)
    train, test = split_train_test(df)
    t = __import__('exp15_noise_vs_deterministic').TraderNoise(seed=42, input_noise=0.0)
    plan = __import__('exp15_noise_vs_deterministic').PLAN_PRIOR.get(code, 0.0)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-window:] if len(rets) > window else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s, 100.0 * p / prices[0], noisy=True)
        else:
            hist.append(p)
        prev = p
    tp = test['close'].values
    trades = 0
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-window:] if len(rets3) > window else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            a, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3, 100.0 * p / tp[0], noisy=False)
            if a in ('buy', 'sell'):
                trades += 1
        else:
            hist3.append(p)
        prev3 = p
    return trades


if __name__ == '__main__':
    print('=== 实验16: 噪声受益股票的识别特征 ===')
    print('噪声收益 = max(noise>0) - noise=0(5 seeds 平均);batch2 10 只\n')

    rows = []
    for code, name in POOL2.items():
        f = features(code)
        # 每个噪声水平 5 seeds 平均
        avgs = {}
        for n in NOISES:
            vals = [run_noise(code, BEST_W[code], seed=s, input_noise=n) for s in SEEDS]
            avgs[n] = sum(vals) / len(vals)
        gain = max(avgs[n] for n in NOISES[1:]) - avgs[0.0]
        best_n = max(NOISES[1:], key=lambda n: avgs[n])
        trades = count_trades(code, BEST_W[code])
        row = {'name': name, 'gain': gain, 'best_noise': best_n, 'trades': trades}
        row.update(f)
        rows.append(row)
        print('%-6s 噪声收益 %+7.1f (最佳噪声 %.2f) 交易%3d | train_vol %.4f test_vol %.4f vol_ratio %.2f ret_shift %.4f dist_dist %.4f trend %+.2f'
              % (name, gain, best_n, trades, row['train_vol'], row['test_vol'],
                 row['vol_ratio'], row['ret_shift'], row['dist_dist'], row['train_trend']))

    print()
    print('=== 特征 × 噪声收益 Spearman 相关 ===')
    print('(正相关 = 该特征越大,噪声越受益;负相关 = 该特征越大,噪声越受害)')
    for key, label in [
        ('train_vol', '训练段波动率'),
        ('test_vol', '测试段波动率'),
        ('vol_ratio', '测试/训练波动比'),
        ('ret_shift', '均值漂移'),
        ('dist_dist', '分布距离'),
        ('train_trend', '训练段趋势'),
        ('trades', '测试段交易次数'),
    ]:
        x = [r[key] for r in rows]
        y = [r['gain'] for r in rows]
        s = spearman(x, y)
        print('%-12s %-10s Spearman = %+.3f' % (key, label, s))

    print()
    print('=== 受益 vs 受害分组 ===')
    winners = [r for r in rows if r['gain'] > 0]
    losers = [r for r in rows if r['gain'] <= 0]
    print('受益(%d): %s' % (len(winners), ' '.join(r['name'] for r in winners)))
    print('受害(%d): %s' % (len(losers), ' '.join(r['name'] for r in losers)))
    if winners and losers:
        for key, label in [('vol_ratio', '测试/训练波动比'), ('dist_dist', '分布距离'), ('ret_shift', '均值漂移')]:
            wm = sum(r[key] for r in winners) / len(winners)
            lm = sum(r[key] for r in losers) / len(losers)
            print('%-12s 受益组均值 %8.4f vs 受害组均值 %8.4f' % (label, wm, lm))
