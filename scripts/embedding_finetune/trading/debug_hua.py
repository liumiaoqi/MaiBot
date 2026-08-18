import sys, os
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test, make_features
from sklearn.linear_model import LogisticRegression

df = load_stock('600340')
train, test = split_train_test(df)
X_tr, y_tr = make_features(train)
X_te, y_te = make_features(test)
model = LogisticRegression(max_iter=1000)
model.fit(X_tr, y_tr)
pred = model.predict(X_te)
print('预测分布: 买', sum(pred), '卖', len(pred)-sum(pred))
print('测试段股价: 首', round(test['close'].iloc[0],2), '末', round(test['close'].iloc[-1],2))
print('测试段最低', round(test['close'].min(),2), '最高', round(test['close'].max(),2))
# 华夏幸福测试段(2021-2026)跌幅
print('测试段跌幅:', round((test['close'].iloc[-1]/test['close'].iloc[0]-1)*100,1), '%')