import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_loader import POOL, load_stock, split_train_test
from exp5_rstdp import RSTDPTrader

print('=== R-STDP 交易频率 ===')
print('%-8s %10s %10s %10s %10s' % ('股票', '训练买', '训练卖', '测试买', '测试卖'))
for code, name in POOL.items():
    df = load_stock(code)
    train, test = split_train_test(df)
    trader = RSTDPTrader(seed=42)
    # 训练段
    prices = train['close'].values
    rets = []; holding = False; cash = 100.0; shares = 0.0; prev = None
    buys_tr = sells_tr = 0
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            if len(rets) > 20: rets = rets[-20:]
            action, holding, cash, shares = trader.step(rets, p, holding, cash, shares, explore=True)
            if action == 'buy': buys_tr += 1
            if action == 'sell': sells_tr += 1
        prev = p
    # 测试段
    test_prices = test['close'].values
    rets3 = []; holding3 = False; cash3 = 100.0; shares3 = 0.0; prev3 = None
    buys_te = sells_te = 0
    for p in test_prices:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            if len(rets3) > 20: rets3 = rets3[-20:]
            action, holding3, cash3, shares3 = trader.step(rets3, p, holding3, cash3, shares3, explore=True)
            if action == 'buy': buys_te += 1
            if action == 'sell': sells_te += 1
        prev3 = p
    print('%-8s %10d %10d %10d %10d' % (name, buys_tr, sells_tr, buys_te, sells_te))