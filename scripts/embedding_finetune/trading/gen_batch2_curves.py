#!/usr/bin/env python3
"""生成第二批净值曲线:完整AI(政策先验+信度)vs 满仓"""

import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp14_full_pipeline import TraderFull, PLAN_PRIOR

OUT = r'E:\Users\lmq\Documents\finance\trading_curves'

# 手动定义最优窗口(和 exp14 一致)
BEST_W = {'600036': 40, '600887': 20, '601398': 40, '600050': 20, '601668': 20,
          '600276': 20, '002415': 40, '600031': 40, '601899': 20, '000858': 20}

POOL2 = {'600036': '招商银行', '600887': '伊利股份', '601398': '工商银行',
         '600050': '中国联通', '601668': '中国建筑', '600276': '恒瑞医药',
         '002415': '海康威视', '600031': '三一重工', '601899': '紫金矿业',
         '000858': '五粮液'}

def curve_full(code, window, seed=42):
    df = load_stock(code)
    train, test = split_train_test(df)
    t = TraderFull(seed=seed)
    plan = PLAN_PRIOR.get(code, 0.0)
    prices = train['close'].values
    start_p = prices[0]
    rets=[]; hist=[]; h=False; c=100.0; s=0.0; prev=None
    for p in prices:
        if prev is not None:
            rets.append(p/prev-1); rets = rets[-window:] if len(rets)>window else rets
            hist.append(p); hist = hist[-40:] if len(hist)>40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s, 100.0*p/start_p)
        else: hist.append(p)
        prev = p
    tp = test['close'].values
    start_t = tp[0]
    curve = np.zeros(len(tp))
    rets3=[]; hist3=[]; h3=False; c3=100.0; s3=0.0; prev3=None
    for i, p in enumerate(tp):
        if prev3 is not None:
            rets3.append(p/prev3-1); rets3 = rets3[-window:] if len(rets3)>window else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3)>40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3, 100.0*p/start_t)
        else:
            c3 = 100.0; s3 = 0.0; h3 = False
        curve[i] = c3 + s3*p
        prev3 = p
    return curve

for code, name in POOL2.items():
    df = load_stock(code)
    train, test = split_train_test(df)
    tp = test['close'].values
    full = 100.0 * tp / tp[0]
    try:
        ai = curve_full(code, BEST_W[code])
        out = pd.DataFrame({'date': test['date'].values, 'full': full, 'ai_full': ai})
        out.to_csv(os.path.join(OUT, code + '_batch2_curves.csv'), index=False)
        print(f'{name}: 已保存')
    except Exception as e:
        print(f'{name}: 失败 {str(e)[:60]}')