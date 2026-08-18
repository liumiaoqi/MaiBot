#!/usr/bin/env python3
"""exp24: 种子相关性验证——连续小种子 vs 大随机种子 vs 硬随机

假说(exp23 推论):Mersenne Twister 连续小种子(0,1,2,...)生成的初始状态
高度相关 → 运行结果也相关 → 方差被低估。
验证:6 只股票 × 三组各 20 次(det 配置):
- small: 种子 0..19(TraderQNoise seed=k,内部 random.seed(k))
- big:   大随机种子(random.randrange(10^9),分散)
- hard:  secrets 硬随机(exp23 方式)
若假说成立:small 的 std << big ≈ hard;big 与 hard 的 std 接近。
"""

import random
import secrets
import sys
import os
import statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp19_quantum_noise import TraderQNoise

WINDOW = 20
N_RUNS = 20
STOCKS = [('601088', '中国神华'), ('601919', '中远海控'), ('601899', '紫金矿业'),
          ('000858', '五粮液'), ('600276', '恒瑞医药'), ('600036', '招商银行')]


def make_trader(kind, k):
    if kind == 'small':
        return TraderQNoise(seed=k, noise_mode=None)
    if kind == 'big':
        # 大随机种子:用系统随机源选一个大而分散的种子
        big = secrets.randbelow(10**9)
        return TraderQNoise(seed=big, noise_mode=None)
    # hard: 硬随机直接喂权重
    r = random.Random(secrets.randbits(256))
    t = TraderQNoise(seed=0, noise_mode=None)
    t.w = [[r.uniform(-1.0, 1.0) for _ in range(3)] for _ in range(3)]
    return t


def run_with(code, window, trader):
    df = load_stock(code)
    train, test = split_train_test(df)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-window:] if len(rets) > window else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            _, h, c, s = trader.step(rets, p, hist, 0.0, h, c, s,
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
            _, h3, c3, s3 = trader.step(rets3, p, hist3, 0.0, h3, c3, s3,
                                        100.0 * p / tp[0], noisy=False)
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1]


if __name__ == '__main__':
    print('=== exp24: 种子相关性验证(连续小种子 vs 大随机种子 vs 硬随机) ===')
    print('6 只股票 × 3 组 × 20 次(det 配置)\n')
    print('%-8s %14s %14s %14s %10s %10s' % ('股票', 'small均值', 'big均值', 'hard均值', 'small std', 'big std',))
    print('%-8s %14s %14s %14s %10s %10s' % ('', '', '', '', '', 'hard std'))
    for code, name in STOCKS:
        vals = {}
        for kind in ('small', 'big', 'hard'):
            vals[kind] = [run_with(code, WINDOW, make_trader(kind, k))
                          for k in range(N_RUNS)]
        ms = statistics.mean(vals['small'])
        mb = statistics.mean(vals['big'])
        mh = statistics.mean(vals['hard'])
        ss = statistics.stdev(vals['small'])
        sb = statistics.stdev(vals['big'])
        sh = statistics.stdev(vals['hard'])
        print('%-8s %14.1f %14.1f %14.1f %10.1f %10.1f %10.1f' % (
            name, ms, mb, mh, ss, sb, sh))

    print()
    print('=== 假说检验:std_small < std_big ≈ std_hard? ===')
    print('(若连续种子相关,small 的 std 应明显小于 big/hard)')
