import pandas as pd
import os

DATA_DIR = r'E:\Users\lmq\Documents\finance\data'

# 选定股票池(固定不可换——2026-08-18 用户拍板)
POOL = {
    '600519': '贵州茅台',
    '600900': '长江电力',
    '601919': '中远海控',
    '600340': '华夏幸福',
    '000001': '平安银行',
    '601857': '中国石油',
    '600028': '中国石化',
    '000300': '沪深300指数',
}

TRAIN_END = '2020-12-31'

def load_stock(code):
    fpath = os.path.join(DATA_DIR, code + '_daily.csv')
    if not os.path.exists(fpath):
        raise FileNotFoundError(code + ' 数据不存在')
    df = pd.read_csv(fpath)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df

def split_train_test(df, train_end=TRAIN_END):
    train = df[df['date'] <= train_end].copy()
    test = df[df['date'] > train_end].copy()
    return train, test

def make_features(df, window=20):
    import numpy as np
    close = df['close'].values
    rets = pd.Series(close).pct_change().values
    X, y = [], []
    for i in range(window, len(rets) - 1):
        window_rets = rets[i-window:i]
        if np.isnan(window_rets).any() or np.isnan(rets[i+1]):
            continue
        X.append(window_rets)
        y.append(1 if rets[i+1] > 0 else 0)
    return np.array(X), np.array(y)

if __name__ == '__main__':
    for code, name in POOL.items():
        df = load_stock(code)
        train, test = split_train_test(df)
        print(name + '(' + code + '): 共' + str(len(df)) + '行, 训练' + str(len(train)) + ', 测试' + str(len(test)))