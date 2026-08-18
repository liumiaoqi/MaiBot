import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test, make_features

# 交易成本(单边 0.1%)——防止 AI 过度交易刷收益
COST = 0.001

def run_linear_ai(code):
    df = load_stock(code)
    train, test = split_train_test(df)
    X_tr, y_tr = make_features(train)
    X_te, y_te = make_features(test)
    if len(X_tr) < 100 or len(X_te) < 100:
        return None
    # 线性模型(逻辑回归——最简单的 AI)
    model = LogisticRegression(max_iter=1000)
    model.fit(X_tr, y_tr)
    # 测试段预测
    pred = model.predict(X_te)
    acc = accuracy_score(y_te, pred)
    return model, X_te, y_te, pred, acc, test

def simulate_trading(pred, close, initial=100):
    """按预测交易:预测涨->持有,预测跌->空仓。算交易成本。"""
    cash = initial
    shares = 0
    holding = False
    for i in range(len(pred)):
        p = pred[i]
        c = close[i]
        if p == 1 and not holding:
            shares = cash / c * (1 - COST)
            cash = 0
            holding = True
        elif p == 0 and holding:
            cash = shares * c * (1 - COST)
            shares = 0
            holding = False
    # 期末总资产
    if holding:
        return shares * close[-1]
    return cash

def run_rule_baseline(test, initial=100):
    """规则基线:满仓持有(最简单的规则——测试段全程持有)。"""
    return initial * test['close'].iloc[-1] / test['close'].iloc[0]

if __name__ == '__main__':
    print('=' * 60)
    print('实验1: 线性纯AI vs 规则(满仓) —— 测试段 2021-2026(真未来)')
    print('=' * 60)
    rows = []
    for code, name in POOL.items():
        res = run_linear_ai(code)
        if res is None:
            print(f'{name}: 数据不足,跳过')
            continue
        model, X_te, y_te, pred, acc, test = res
        ai_val = simulate_trading(pred, test['close'].values)
        rule_val = run_rule_baseline(test)
        rows.append({'股票': name, 'AI预测准确率': f'{acc:.3f}',
                     'AI终值': round(ai_val, 1), '规则终值': round(rule_val, 1),
                     'AI vs 规则': round(ai_val - rule_val, 1)})
        print(f'{name}: 准确率{acc:.3f} | AI {ai_val:.1f} vs 规则 {rule_val:.1f} ({ai_val-rule_val:+.1f})')
    print('\n(注:准确率>0.5 才算有预测力;0.5=瞎猜)')