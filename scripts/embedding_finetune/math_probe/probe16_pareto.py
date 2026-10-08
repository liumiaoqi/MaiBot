#!/usr/bin/env python3
"""probe16_pareto.py -- exp27 策略家族的参数扫描（公平 Pareto 对照）。

发现（见 NOTES）：原表的「多样性增益/损失」比是不同工作点的局部斜率互比——
三策略的强度（gauss σ=0.05 / ampdamp p=0.02 / qbit p=0.10）没有对齐。
本脚本把三者参数化扫描，在「同重叠率」下比质量（这才是公平对照），
并验证 qbit(取负) 与 ampdamp(压0) 在正分数池下是否等价。
跑法: ../.venv/Scripts/python.exe probe16_pareto.py
"""
import os
import sys

import numpy as np

T = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, T)
import exp27_maibot_retrieval_diversity as E27  # noqa: E402


def evaluate(fn, base, drift, reps=5):
    ovs, qs = [], []
    for _ in range(reps):
        ov, q = E27.run(fn, base, drift)
        ovs.append(ov)
        qs.append(q)
    return float(np.mean(ovs)), float(np.mean(qs))


if __name__ == '__main__':
    base, drift = E27.make_pool()
    print('=== probe16: strategy families — Pareto sweep (exp27 pool) ===')
    print('%-24s %10s %10s' % ('config', 'overlap', 'quality'))
    rows = {}
    for sig in [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]:
        ov, q = evaluate(lambda s, sg=sig: E27.gauss_sample(s, sigma=sg), base, drift)
        rows[('gauss', sig)] = (ov, q)
        print('gauss   sigma=%-6.3f      %10.4f %10.4f' % (sig, ov, q))
    for p in [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]:
        ov, q = evaluate(lambda s, pp=p: E27.ampdamp_sample(s, p=pp), base, drift)
        rows[('ampdamp', p)] = (ov, q)
        print('ampdamp p=%-10.3f      %10.4f %10.4f' % (p, ov, q))
    for p in [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]:
        ov, q = evaluate(lambda s, pp=p: E27.qbit_sample(s, p=pp), base, drift)
        rows[('qbit', p)] = (ov, q)
        print('qbit    p=%-10.3f      %10.4f %10.4f' % (p, ov, q))

    print()
    print('--- fair comparison: quality AT matched overlap levels ---')
    def qual_at(family, target):
        pts = sorted([(v[0], v[1]) for k2, v in rows.items() if k2[0] == family])
        xs = [pt[0] for pt in pts]
        ys = [pt[1] for pt in pts]
        if target < min(xs) or target > max(xs):
            return float('nan')
        return float(np.interp(target, xs, ys))
    print('%-12s %12s %12s %12s' % ('overlap', 'gauss', 'ampdamp', 'qbit'))
    for tgt in [0.95, 0.9, 0.85, 0.8, 0.7, 0.6, 0.5]:
        print('%-12.2f %12.4f %12.4f %12.4f' % (
            tgt, qual_at('gauss', tgt), qual_at('ampdamp', tgt), qual_at('qbit', tgt)))

    print()
    print('--- qbit (negate) vs ampdamp (zero-out) equivalence on a positive pool ---')
    for p in [0.01, 0.05, 0.1]:
        ov1, q1 = rows[('ampdamp', p)]
        ov2, q2 = rows[('qbit', p)]
        print('p=%.2f : ampdamp (%.4f, %.4f)  qbit (%.4f, %.4f)  d_overlap %+.4f' % (
            p, ov1, q1, ov2, q2, ov2 - ov1))
