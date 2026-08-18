#!/usr/bin/env python3
"""exp22: 完整方法组合——之前所有积累 + 量子噪声(修正 exp19-21 的变量隔离偏差)

用户质疑:exp19-21 为隔离变量丢掉了积累(16 只新样本 plan=0 无先验/周期股被给政策先验/窗口没按波动率调)。
本实验:完整方法 = 政策先验 + 信度学习 + 周期股纯数据(exp9 教训:周期股政策先验是毒药)
+ 波动率窗口(exp13:BEST_W) + 量子噪声 ampdamp 0.02(exp21 全样本最佳)。

对比(34 只 × 10 seeds):
- A 裸基线:无先验无噪声 w=20(引用 exp21 det 数据,不重跑)
- B 完整方法无噪声(先验+信度+周期纯数据+w)
- C 完整方法+ampdamp 0.02(全积累 + 量子噪声)
关键问题:完整方法下噪声还有增量吗?周期股纯数据是否修复紫金/宝钢?
"""

import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import statistics
from data_loader import POOL, load_stock, split_train_test
from exp15_noise_vs_deterministic import POOL2, BEST_W, PLAN_PRIOR
from exp12_policy_prior import PLAN_PRIOR as PLAN_PRIOR_B1
from exp19_quantum_noise import POOL3, TraderQNoise

COST = 0.001
SEEDS = range(10)

# 16 只新样本的政策先验(时代年轮方向——当时可得,对齐 exp12 风格)
PLAN_PRIOR_NEW = {
    '000002': -1.0,  # 万科A:地产三道红线
    '601318': 0.0,   # 中国平安:金融中性
    '000333': 0.3,   # 美的:家电消费
    '000651': 0.3,   # 格力:家电消费
    '000568': 0.5,   # 泸州老窖:白酒促消费
    '000538': 0.5,   # 云南白药:医药扶持
    '600019': -0.3,  # 宝钢:钢铁周期(双碳去产能)
    '601088': -0.3,  # 神华:煤炭周期(双碳压制)
    '000725': 0.8,   # 京东方:面板科技自主
    '000063': 0.8,   # 中兴:通信科技
    '601012': 1.0,   # 隆基:光伏双碳
    '002594': 1.0,   # 比亚迪:新能源车
    '600030': 0.0,   # 中信证券:金融中性
    '601988': 0.0,   # 中国银行:金融中性
    '600104': 0.3,   # 上汽:汽车消费
    '600585': -0.3,  # 海螺:建材周期
}

# 周期股(exp9 教训:政策先验对周期股是毒药——改用纯数据 plan=0)
CYCLE_STOCKS = {'601899', '600019', '601088', '600585', '601919'}


class TraderComplete(TraderQNoise):
    """完整方法:政策先验 + 信度学习 + 可选量子噪声(训练段)。"""

    def __init__(self, seed=42, lr=0.02, explore=0.1, noise_mode=None,
                 strength=0.02):
        super().__init__(seed=seed, lr=lr, explore=explore,
                         noise_mode=noise_mode, strength=strength)
        self.trust = 1.0

    def step(self, rets, price, prices_hist, plan, holding, cash, shares, bench,
             noisy=True):
        # 信度学习版:plan_sig = plan * trust * 3.0(覆盖父类,trust 可学习)
        ret1 = rets[-1] * 100 if len(rets) else 0.0
        trend = 0.0
        if len(prices_hist) >= 21:
            trend = (price - prices_hist[-21]) / prices_hist[-21] * 100
        plan_sig = plan * self.trust * 3.0
        feats = [ret1, trend, plan_sig]
        if noisy:
            feats = self._noise(feats)
        sense_spikes = [1.0 if f > 0.3 else 0.0 for f in feats]
        noise = random.uniform(-self.explore, self.explore)
        a_b = sum(self.w[i][0] * feats[i] for i in range(3)) + noise
        a_s = sum(self.w[i][1] * feats[i] for i in range(3)) + noise
        a_h = sum(self.w[i][2] * feats[i] for i in range(3)) + noise
        action = 'hold'
        if a_b > 0.1 and a_b > a_s and a_b > a_h and not holding:
            action = 'buy'
        elif a_s > 0.1 and a_s > a_b and a_s > a_h and holding:
            action = 'sell'
        if action == 'buy' and cash > 0:
            shares = cash / price * (1 - COST); cash = 0.0; holding = True
        elif action == 'sell' and holding:
            cash = shares * price * (1 - COST); shares = 0.0; holding = False
        value = cash + shares * price
        reward = 0.0
        if action in ('buy', 'sell'):
            reward = 1.0 if value >= bench else -1.0
        if reward != 0.0:
            act_idx = {'buy': 0, 'sell': 1, 'hold': 2}[action]
            post = [0.0, 0.0, 0.0]
            post[act_idx] = 1.0
            for i in range(3):
                self.trace_pre[i] = self.trace_pre[i] * self.decay + sense_spikes[i]
                for j in range(3):
                    self.w[i][j] += self.lr * reward * self.trace_pre[i] * post[j]
            self.trust = max(0.0, min(2.0, self.trust + self.lr * reward * 0.5 * abs(plan)))
        return action, holding, cash, shares


def get_plan(code):
    """周期股用纯数据(plan=0),非周期用政策先验。"""
    if code in CYCLE_STOCKS:
        return 0.0
    if code in PLAN_PRIOR:
        return PLAN_PRIOR[code]
    if code in PLAN_PRIOR_B1:
        return PLAN_PRIOR_B1[code]
    if code in PLAN_PRIOR_NEW:
        return PLAN_PRIOR_NEW[code]
    return 0.0


def get_window(code):
    """波动率窗口:batch2 用 exp13 BEST_W,其余 20。"""
    if code in BEST_W:
        return BEST_W[code]
    return 20


def run_full(code, window, seed, use_noise):
    df = load_stock(code)
    train, test = split_train_test(df)
    plan = get_plan(code)
    if use_noise:
        t = TraderComplete(seed=seed, noise_mode='ampdamp', strength=0.02)
    else:
        t = TraderComplete(seed=seed, noise_mode=None)
    prices = train['close'].values
    rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
    for p in prices:
        if prev is not None:
            rets.append(p / prev - 1)
            rets = rets[-window:] if len(rets) > window else rets
            hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
            _, h, c, s = t.step(rets, p, hist, plan, h, c, s,
                                100.0 * p / prices[0], noisy=True)
        else:
            hist.append(p)
        prev = p
    tp = test['close'].values
    rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
    for p in tp:
        if prev3 is not None:
            rets3.append(p / prev3 - 1)
            rets3 = rets3[-window:] if len(rets3) > window else rets3
            hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
            _, h3, c3, s3 = t.step(rets3, p, hist3, plan, h3, c3, s3,
                                   100.0 * p / tp[0], noisy=False)
        else:
            hist3.append(p)
        prev3 = p
    return c3 + s3 * tp[-1]


if __name__ == '__main__':
    print('=== exp22: 完整方法组合(先验+信度+周期纯数据+窗口+量子噪声) ===')
    print('A 裸基线(引用 exp21 det) / B 完整无噪声 / C 完整+ampdamp0.02;34 只 × 10 seeds\n')

    STOCKS = []
    for c, n in POOL.items():
        STOCKS.append((c, n))
    for c, n in POOL2.items():
        STOCKS.append((c, n))
    for c, n in POOL3.items():
        STOCKS.append((c, n))

    resB = {}
    resC = {}
    for idx, (code, name) in enumerate(STOCKS):
        w = get_window(code)
        resB[code] = [run_full(code, w, seed=k, use_noise=False) for k in SEEDS]
        resC[code] = [run_full(code, w, seed=k, use_noise=True) for k in SEEDS]
        if (idx + 1) % 5 == 0 or idx == len(STOCKS) - 1:
            print('... %d/%d 完成' % (idx + 1, len(STOCKS)))

    # 引用 exp21 的 A(det) 数据:重新算一次 det(同脚本一致性优先,10 seeds)
    resA = {}
    for code, name in STOCKS:
        w = get_window(code)
        t = TraderComplete(seed=42, noise_mode=None)
        # 用无先验跑 A(裸基线)——注意:TraderComplete 带 trust,但 plan=0 时 trust 不生效
        df = load_stock(code)
        train, test = split_train_test(df)
        plan = 0.0
        resA[code] = [run_full(code, w, seed=k, use_noise=False) for k in SEEDS]
        # 修正:A 用无先验——重新定义 run_bare
    print('\n(注:A 裸基线用无先验版——下面直接重算)')

    # 重算 A:无先验无噪声
    def run_bare(code, window, seed):
        df = load_stock(code)
        train, test = split_train_test(df)
        t = TraderQNoise(seed=seed, noise_mode=None)
        prices = train['close'].values
        rets = []; hist = []; h = False; c = 100.0; s = 0.0; prev = None
        for p in prices:
            if prev is not None:
                rets.append(p / prev - 1)
                rets = rets[-window:] if len(rets) > window else rets
                hist.append(p); hist = hist[-40:] if len(hist) > 40 else hist
                _, h, c, s = t.step(rets, p, hist, 0.0, h, c, s,
                                    100.0 * p / prices[0], noisy=True)
            else:
                hist.append(p)
            prev = p
        tp = test['close'].values
        rets3 = []; hist3 = []; h3 = False; c3 = 100.0; s3 = 0.0; prev3 = None
        for p in tp:
            if prev3 is not None:
                rets3.append(p / prev3 - 1)
                rets3 = rets3[-window:] if len(rets3) > window else rets3
                hist3.append(p); hist3 = hist3[-40:] if len(hist3) > 40 else hist3
                _, h3, c3, s3 = t.step(rets3, p, hist3, 0.0, h3, c3, s3,
                                       100.0 * p / tp[0], noisy=False)
            else:
                hist3.append(p)
            prev3 = p
        return c3 + s3 * tp[-1]

    for code, name in STOCKS:
        w = get_window(code)
        resA[code] = [run_bare(code, w, seed=k) for k in SEEDS]

    fulls = {}
    for code, name in STOCKS:
        df = load_stock(code)
        _, test = split_train_test(df)
        fulls[code] = 100 * test['close'].iloc[-1] / test['close'].iloc[0]

    print()
    print('=== 汇总(34 只 × 10 seeds) ===')
    for label, res in [('A 裸基线', resA), ('B 完整无噪声', resB), ('C 完整+噪声', resC)]:
        means = [statistics.mean(res[c]) for c, _ in STOCKS]
        wins = sum(1 for i, (c, _) in enumerate(STOCKS) if means[i] > fulls[c])
        print('%-12s 平均 %7.1f  跑赢满仓 %2d/34' % (label, sum(means) / len(means), wins))

    print()
    print('=== 增量分析 ===')
    mb = [statistics.mean(resB[c]) for c, _ in STOCKS]
    ma = [statistics.mean(resA[c]) for c, _ in STOCKS]
    mc = [statistics.mean(resC[c]) for c, _ in STOCKS]
    print('完整方法(B) vs 裸基线(A): 平均 %+6.1f  跑赢 %2d/34' %
          (sum(b - a for b, a in zip(mb, ma, strict=True)) / len(mb),
           sum(1 for b, a in zip(mb, ma, strict=True) if b > a)))
    print('量子噪声增量(C vs B):    平均 %+6.1f  跑赢 %2d/34' %
          (sum(c - b for c, b in zip(mc, mb, strict=True)) / len(mc),
           sum(1 for c, b in zip(mc, mb, strict=True) if c > b)))

    print()
    print('=== 周期股修复检查(纯数据 vs 之前政策先验) ===')
    for code, name in STOCKS:
        if code in CYCLE_STOCKS:
            print('%-6s 裸基线 %6.1f  完整无噪声 %6.1f  完整+噪声 %6.1f  满仓 %6.1f' % (
                name,
                statistics.mean(resA[code]), statistics.mean(resB[code]),
                statistics.mean(resC[code]), fulls[code]))
