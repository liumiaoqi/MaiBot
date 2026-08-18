#!/usr/bin/env python3
"""exp18: 行为反馈自适应噪声——交易频率实时调噪(不靠静态特征)

exp16b 教训:静态特征规则跨批次不稳定;exp17 教训:退火免选择但高起始噪声伤稳定股。
本实验:训练段实时监测 R-STDP 行为(交易频率),动态调输入噪声:
- 交易太少(死寂/探索不足) → 自动加噪(推动探索)
- 交易太多(过度活跃)     → 自动降噪(稳定)
- 行为即信号,不需要任何静态特征/外部知识。

实现:每 CHECK_STEPS(500) 步统计交易次数,与目标区间 [T_MIN, T_MAX] 比较,
噪声 += / -= STEP(0.02),clamp [0, NOISE_MAX(0.2)]。测试段干净。
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2, BEST_W, PLAN_PRIOR, TraderNoise

COST = 0.001
CHECK_STEPS = 500
T_MIN = 5
T_MAX = 50
NOISE_STEP = 0.02
NOISE_MAX = 0.2


class TraderAdaptive(TraderNoise):
    """行为反馈自适应噪声:训练段按交易频率实时调输入噪声。"""

    def __init__(self, seed=42, lr=0.02, explore=0.1):
        super().__init__(seed=seed, lr=lr, explore=explore)
        self._n_steps = 0
        self._trades_in_window = 0

    def step(self, rets, price, prices_hist, plan, holding, cash, shares, bench,
             noisy=True):
        if not noisy:
            return super().step(rets, price, prices_hist, plan, holding, cash,
                                shares, bench, noisy=False)
        self._n_steps += 1
        # 每 CHECK_STEPS 步检查一次交易频率,调整噪声
        if self._n_steps % CHECK_STEPS == 0:
            if self._trades_in_window < T_MIN:
                self.input_noise = min(NOISE_MAX,
                                       self.input_noise + NOISE_STEP)
            elif self._trades_in_window > T_MAX:
                self.input_noise = max(0.0,
                                       self.input_noise - NOISE_STEP)
            self._trades_in_window = 0
        action, h, c, s = super().step(rets, price, prices_hist, plan, holding,
                                       cash, shares, bench, noisy=True)
        if action in ('buy', 'sell'):
            self._trades_in_window += 1
        return action, h, c, s


def run_adaptive(code, window, seed):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderAdaptive(seed=seed)
    plan = PLAN_PRIOR.get(code, 0.0)
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
    return c3 + s3 * tp[-1], t.input_noise


if __name__ == '__main__':
    print('=== exp18: 行为反馈自适应噪声(交易频率实时调噪) ===')
    print('每 500 步检查:交易<5 加噪 0.02 / 交易>50 降噪 0.02 / clamp [0, 0.2];batch2 5 seeds\n')
    MODES = [('det', '确定性 0'), ('fix002', '固定 0.02'), ('anneal', '退火 0.2->0.02'),
             ('adaptive', '行为自适应'), ('oracle', 'oracle 最佳固定')]
    header = '%-8s' % '股票'
    for m, label in MODES:
        header += ' %11s' % label
    header += ' %8s %10s' % ('终噪', '满仓')
    print(header)
    print('-' * len(header))

    agg = {m: [] for m, _ in MODES}
    for code, name in POOL2.items():
        row = '%-8s' % name
        df = load_stock(code)
        _, test = split_train_test(df)
        full = 100 * test['close'].iloc[-1] / test['close'].iloc[0]
        for m, _ in MODES:
            if m == 'adaptive':
                vals = [run_adaptive(code, BEST_W[code], seed=s)[0] for s in range(5)]
                final_noise = run_adaptive(code, BEST_W[code], seed=42)[1]
            else:
                from exp17_annealing import run_any
                vals = [run_any(code, BEST_W[code], seed=s, mode=m) for s in range(5)]
                final_noise = float('nan')
            avg = sum(vals) / len(vals)
            agg[m].append(avg)
            row += ' %11.1f' % avg
        row += ' %8.2f %10.1f' % (final_noise, full)
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
    base = agg['det']
    print('\n=== 相对确定性基线 ===')
    for m in ['fix002', 'anneal', 'adaptive', 'oracle']:
        beats = sum(1 for b, a in zip(base, agg[m], strict=True) if a > b)
        print('%-10s 跑赢基线 %d/10' % (m, beats))
