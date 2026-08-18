#!/usr/bin/env python3
"""exp23: 硬随机(secrets) vs 伪随机(PRNG)——统计等效验证

用户问题:开启硬随机器(操作系统真随机源)会有什么不同?
理论:PRNG 统计性质与真随机不可区分——分布相同,期望收敛同一值。
验证:6 只代表股(神华受益/中远海控修复/紫金受害/五粮液翻盘/恒瑞/招商)
× 2 RNG(伪随机 20 seeds vs 硬随机 20 次独立初始化)× det 配置,
对比均值/方差——若差异在采样误差内,统计等效成立。

注意:硬随机每次权重初始化不同(相当于无限种子),不可复现。
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
STOCKS = [('601088', '中国神华'), ('601919', '中远海控'), ('601899', '紫金矿业'),
          ('000858', '五粮液'), ('600276', '恒瑞医药'), ('600036', '招商银行')]
N_RUNS = 20


def make_trader(rng_kind):
    if rng_kind == 'prng':
        return TraderQNoise(seed=random.randrange(10**9), noise_mode=None)
    # 硬随机:用 secrets 熵喂给 RNG——等价于用真随机源初始化
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
    print('=== exp23: 硬随机(secrets) vs 伪随机(PRNG)——统计等效验证 ===')
    print('6 只代表股 × 各 20 次运行(det 配置)\n')
    print('%-8s %12s %12s %12s %12s' % ('股票', 'PRNG均值', '硬随机均值', 'PRNG std', '硬随机 std'))
    diffs = []
    for code, name in STOCKS:
        prng_vals = []
        hw_vals = []
        for _ in range(N_RUNS):
            prng_vals.append(run_with(code, WINDOW, make_trader('prng')))
            hw_vals.append(run_with(code, WINDOW, make_trader('hard')))
        pm = statistics.mean(prng_vals)
        hm = statistics.mean(hw_vals)
        ps = statistics.stdev(prng_vals)
        hs = statistics.stdev(hw_vals)
        diff = hm - pm
        diffs.append(diff)
        print('%-8s %12.1f %12.1f %12.1f %12.1f  差 %+5.1f' % (name, pm, hm, ps, hs, diff))
    # 汇总:差异 vs 采样噪声
    mean_diff = sum(diffs) / len(diffs)
    # 合并 std 估计:差异若在 sqrt(2)*std/sqrt(N) 内 = 采样误差
    print()
    print('平均差异 %+.2f —— 若 |差异| < 采样误差(约 std/√N),统计等效成立' % mean_diff)
