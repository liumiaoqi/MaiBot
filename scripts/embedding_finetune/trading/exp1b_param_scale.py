import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test, make_features
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score

def run_linear(df, window):
    train, test = split_train_test(df)
    X_tr, y_tr = make_features(train, window)
    X_te, y_te = make_features(test, window)
    if len(X_tr) < 100 or len(X_te) < 100: return None
    m = LogisticRegression(max_iter=2000)
    m.fit(X_tr, y_tr)
    return accuracy_score(y_te, m.predict(X_te))

print('=== 参数量对比:线性窗口20 vs 线性窗口100 ===')
print('%-8s %10s %10s %8s' % ('股票', '窗口20', '窗口100', '差异'))
for code, name in POOL.items():
    df = load_stock(code)
    a = run_linear(df, 20)
    b = run_linear(df, 100)
    if a is None or b is None: continue
    diff = b - a
    print('%-8s %10.3f %10.3f %+8.3f' % (name, a, b, diff))
print('\n(若差异≈0,证明线性放大参数没用——弱式有效市场)')