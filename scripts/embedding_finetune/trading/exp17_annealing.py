#!/usr/bin/env python3
"""exp17: 自适应噪声——噪声退火 vs 固定噪声 vs 确定性

exp15/16 结论:固定噪声对部分股票有效但方向跨批次不稳定;静态特征规则不可靠。
本实验:噪声退火(训练段噪声从高到低线性衰减——早期探索晚期收敛)是否
对全部股票通用地接近"每只股票的最佳固定噪声"(oracle 上界)?

对比组(batch2 10 只 × 5 seeds):
- det       确定性基线(noise=0,exp15 数据)
- fix002    固定 0.02(安全默认)
- anneal    退火 0.2 → 0.02(训练段按步数线性衰减)
- anneal2   退火 0.1 → 0.02
- oracle    exp15/16 每只股票最佳固定噪声(上界参考)

若退火平均接近 oracle 且跑赢 det——自适应噪声成立,无需知道哪只股票该加噪。
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2, BEST_W, PLAN_PRIOR, TraderNoise

COST = 0.001

# exp15/16 每只股票的最佳固定噪声(oracle)
ORACLE_N = {'600036': 0.05, '600887': 0.10, '601398': 0.02, '600050': 0.02,
            '601668': 0.02, '600276': 0.02, '002415': 0.20, '600031': 0.02,
            '601899': 0.02, '000858': 0.20}


class TraderAnneal(TraderNoise):
    """噪声退火版:训练段噪声按步数线性衰减 start→end,测试段干净。"""

    def __init__(self, seed=42, lr=0.02, explore=0.1, anneal_start=0.2,
                 anneal_end=0.02):
        super().__init__(seed=seed, lr=lr, explore=explore)
        self.anneal_start = anneal_start
        self.anneal_end = anneal_end
        self._n_steps = 0

    def step(self, rets, price, prices_hist, plan, holding, cash, shares, bench,
             noisy=True):
        if noisy:
            # 按训练步数线性衰减噪声(模拟退火式:早期探索晚期收敛)
            progress = min(1.0, self._n_steps / 4000.0)
            self.input_noise = (self.anneal_start +
                                (self.anneal_end - self.anneal_start) * progress)
            self._n_steps += 1
        return super().step(rets, price, prices_hist, plan, holding, cash,
                            shares, bench, noisy=noisy)


def run_any(code, window, seed, mode):
    df = load_stock(code)
    train, test = split_train_test(df)
    plan = PLAN_PRIOR.get(code, 0.0)
    if mode == 'anneal':
        t = TraderAnneal(seed=seed)
    elif mode == 'anneal2':
        t = TraderAnneal(seed=seed, anneal_start=0.1, anneal_end=0.02)
    elif mode == 'oracle':
        t = TraderNoise(seed=seed, input_noise=ORACLE_N[code])
    elif mode == 'fix002':
        t = TraderNoise(seed=seed, input_noise=0.02)
    else:  # det
        t = TraderNoise(seed=seed, input_noise=0.0)
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
    print('=== exp17: 噪声退火 vs 固定噪声 vs 确定性(batch2) ===')
    print('退火 = 训练段噪声 0.2→0.02 线性衰减(早期探索晚期收敛);5 seeds 平均\n')
    MODES = [('det', '确定性 0'), ('fix002', '固定 0.02'), ('anneal2', '退火 0.1→0.02'),
             ('anneal', '退火 0.2→0.02'), ('oracle', 'oracle 最佳固定')]
    header = '%-8s' % '股票'
    for m, label in MODES:
        header += ' %12s' % label
    header += ' %10s' % '满仓'
    print(header)
    print('-' * len(header))

    agg = {m: [] for m, _ in MODES}
    for code, name in POOL2.items():
        row = '%-8s' % name
        df = load_stock(code)
        _, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        for m, _ in MODES:
            vals = [run_any(code, BEST_W[code], seed=s, mode=m) for s in range(5)]
            avg = sum(vals) / len(vals)
            agg[m].append(avg)
            row += ' %12.1f' % avg
        row += ' %10.1f' % full
        print(row)

    print('-' * len(header))
    codes = list(POOL2.keys())
    fulls = {}
    for code in codes:
        df = load_stock(code)
        _, test = split_train_test(df)
        fulls[code] = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
    print('\n=== 汇总 ===')
    for m, label in MODES:
        mean = sum(agg[m]) / len(agg[m])
        wins = sum(1 for i, code in enumerate(codes) if agg[m][i] > fulls[code])
        print('%-10s %-12s 平均 %7.1f  跑赢满仓 %d/10' % (m, label, mean, wins))
    # 退火 vs 确定性/固定 的配对胜率
    base = agg['det']
    print('\n=== 相对确定性基线 ===')
    for m in ['fix002', 'anneal2', 'anneal', 'oracle']:
        beats = sum(1 for b, a in zip(base, agg[m], strict=True) if a > b)
        print('%-10s 跑赢基线 %d/10' % (m, beats))
