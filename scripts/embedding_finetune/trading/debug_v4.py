import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import load_stock, split_train_test
from exp6_rstdp_v4 import RSTDPTraderV4

df = load_stock('600519')
train, test = split_train_test(df)
prices = train['close'].values
trader = RSTDPTraderV4(seed=42)
rets = []; holding = False; cash = 100.0; shares = 0.0; prev = None
actions = {}
for p in prices:
    if prev is not None:
        rets.append(p / prev - 1)
        if len(rets) > 20: rets = rets[-20:]
        action, holding, cash, shares = trader.step(rets, p, holding, cash, shares, explore=True)
        actions[action] = actions.get(action, 0) + 1
    prev = p
print('动作分布:', actions)
print('权重 w:', trader.w)