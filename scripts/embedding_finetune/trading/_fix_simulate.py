def simulate_trading(pred, close, initial=100):
    cash = initial
    shares = 0
    holding = False
    for i in range(len(pred)):
        p = pred[i]
        c = close[i]
        if p == 1 and not holding and cash > 0:
            shares = cash / c * (1 - COST)
            cash = 0
            holding = True
        elif p == 0 and holding:
            cash = shares * c * (1 - COST)
            shares = 0
            holding = False
    if holding:
        return shares * close[-1]
    if shares > 0:
        return shares * close[-1]
    return cash  # 全程空仓 = 保本(返回初始资金)