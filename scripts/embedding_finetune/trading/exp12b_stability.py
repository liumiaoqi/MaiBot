#!/usr/bin/env python3
"""exp12b: 多次运行取平均——验证真实政策先验的稳定性(10次不同种子)"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test
from exp12_policy_prior import run, PLAN_PRIOR

print('=== exp12b: 10次运行取平均(稳定性验证) ===')
print('%-8s %10s %10s %10s %10s' % ('股票', '均值', '最小', '最大', '满仓'))
for code, name in POOL.items():
    df = load_stock(code)
    train, test = split_train_test(df)
    full = 100 * test['close'].iloc[-1]/test['close'].iloc[0]
    results = [run(code, seed=s) for s in range(10)]
    vals = [r[0] for r in results]
    avg = sum(vals)/len(vals)
    print('%-8s %10.1f %10.1f %10.1f %10.1f' % (name, avg, min(vals), max(vals), full))