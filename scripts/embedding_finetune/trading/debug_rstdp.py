import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp5_rstdp import RSTDPTrader

df = load_stock('600519')
train, test = split_train_test(df)
prices = train['close'].values

trader = RSTDPTrader(seed=42)
rets = []
holding = False
cash = 100.0
shares = 0.0
prev = None
buys = 0
sells = 0
for p in prices:
    if prev is not None:
        rets.append(p / prev - 1)
        if len(rets) > 20: rets = rets[-20:]
        action, holding, cash, shares = trader.step(rets, p, holding, cash, shares)
        if action == 'buy': buys += 1
        if action == 'sell': sells += 1
    prev = p
print('训练段: 买入', buys, '卖出', sells, '终值', round(cash + shares*prices[-1], 1))
print('学到的权重 w:', trader.w)