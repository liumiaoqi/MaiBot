#!/usr/bin/env python3
"""生成实验12净值曲线:政策先验AI vs 纯数据v5 vs 满仓(代表性3只)"""

import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp12_policy_prior import TraderPolicyTrust, PLAN_PRIOR

OUT = r'E:\Users\lmq\Documents\finance\trading_curves'

def curve_policy(code, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderPolicyTrust(seed=seed)
    plan = PLAN_PRIOR.get(code, 0.0)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; hist=[]; h=False; c=100.0; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-20:] if len(rets)>20 else rets
            hist.append(p); hist = hist[-40:] if len(hist)>40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s, 100.0*p/start_p, explore=True)
        else: hist.append(p)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    curve = np.zeros(len(tp))
    rets3=[]; hist3=[]; h3=False; c3=100.0; s3=0.0; prev3=None
    for i, p in enumerate(tp):
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-20:] if len(rets3)>20 else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3)>40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3, 100.0*p/start_t, explore=True)
        else:
            c3 = 100.0; s3 = 0.0; h3 = False
        curve[i] = c3 + s3*p
        prev3 = p
    return curve

# 从已有 CSV 读满仓
for code, name in [('600340','华夏幸福'), ('601919','中远海控'), ('601857','中国石油')]:
    df = load_stock(code)
    train, test = split_train_test(df)
    tp = test['close'].values
    full = 100.0 * tp / tp[0]
    policy = curve_policy(code)
    # 纯数据v5曲线(用已有 gen_curves 的 rstdp 列 = v5)
    try:
        old = pd.read_csv(os.path.join(OUT, code + '_curves.csv'))
        out = pd.DataFrame({'date': test['date'].values, 'full': full,
                            'policy_prior': policy, 'pure_data_v5': old['rstdp'].values})
    except Exception:
        out = pd.DataFrame({'date': test['date'].values, 'full': full, 'policy_prior': policy})
    out.to_csv(os.path.join(OUT, code + '_policy_curves.csv'), index=False)
    print(f'{name}: 已保存')