#!/usr/bin/env python3
"""exp42: 线虫进化实验——基因型(10基因)调制真实连接组,股市为自然选择环境

用户构想:"把股市当自然界,让线虫演化,每个轮回选择出一定数量的线虫,
MaiBot 加线虫彩蛋——千千万万的电脑里赛博永生"

基因型(10 个可演化基因,直接调制真实结构):
  g0 polarity   趋化极性(感觉输入 -> 持有/空仓的方向)
  g1 gain       整体增益(反应强度)
  g2-g6 行为组缩放(5 组:后退/前进/转向/运动/感觉——exp41b 的行为组!)
  g7 decay      遗忘率(行情记忆)
  g8 explore    探索噪声
  g9 threshold  决策阈值

表型: W = W_real(279x279 真实连接) × 组缩放基因;感觉组读行情特征 ->
动力学收敛几步 -> 前进组 vs 后退组激活差 -> 持有/空仓(买卖决策)

选择:期末资产 = 适配度(破产=死);top 20% 繁殖(交叉+突变)->下一代
存档:每代冠军基因型 JSON 存 worm_data/evolution/(赛博永生血脉)

运行:分钟级(50 线虫 x 50 代 x 3 年行情,numpy 批量)
"""

import json
import math
import os
import copy
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution')
os.makedirs(ARCHIVE, exist_ok=True)

N_POP = 50
N_GENS = 50
N_DAYS = 750          # 3 年
N_STEPS_DYN = 5       # 每步决策的动力学收敛步数

GENE_NAMES = ['polarity', 'gain', 'scal_back', 'scal_fwd', 'scal_turn',
              'scal_motor', 'scal_sense', 'decay', 'explore', 'threshold']
GENE_RANGES = [(-1.0, 1.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0),
               (0.1, 3.0), (0.1, 3.0), (0.0, 1.0), (0.0, 0.5), (-0.5, 0.5)]

# 行为组(exp41b 同款)——279 索引
BEHAVIOR = {
    'back': ['AVAL', 'AVAR', 'DD01', 'DD02'],
    'fwd': ['AVBL', 'AVBR', 'DB01', 'DB02', 'DB03'],
    'turn': ['RIVL', 'RIVR', 'SMDDL'],
    'motor': ['PVCL', 'PVCR'],
    'sense': ['IL2DL', 'IL2VL', 'URXL', 'URXR'],
}


def load_worm():
    Gs = np.load(os.path.join(DATA, 'Gs.npy'))
    chem = json.load(open(os.path.join(DATA, 'chem.json'), encoding='utf-8'))
    names = [n.get('name') or str(n.get('id')) for n in chem['nodes']]
    W = (Gs + Gs.T) / 2.0
    np.fill_diagonal(W, 0.0)
    m = np.abs(W).max()
    W = W / m if m > 0 else W
    n2i = {n: i for i, n in enumerate(names)}
    groups = {k: [n2i[x] for x in v if x in n2i] for k, v in BEHAVIOR.items()}
    return W, groups


def load_prices():
    """加载 8 只股票价格(用 data_loader),随机抽一只。"""
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from data_loader import load_stock
    codes = ['600519', '600900', '601919', '600340',
             '000001', '601857', '600028', '000300']
    series = []
    for c in codes:
        try:
            df = load_stock(c)
            series.append(df['close'].values)
        except Exception:
            pass
    return series


def random_gene():
    g = []
    for lo, hi in GENE_RANGES:
        g.append(rng.uniform(lo, hi))
    return np.array(g)


def mutate(gene, rate=0.2, sigma=0.3):
    g = gene.copy()
    for i in range(len(g)):
        if rng.random() < rate:
            lo, hi = GENE_RANGES[i]
            g[i] += rng.normal(0, sigma) * (hi - lo)
            g[i] = max(lo, min(hi, g[i]))
    return g


def crossover(a, b):
    mask = rng.random(len(a)) < 0.5
    return np.where(mask, a, b)


def phenotype(gene, W_real, groups):
    """基因 -> 调制连接矩阵 + 行为参数。"""
    W = W_real.copy()
    # 组缩放基因 g2-g6 应用到对应组的输入+输出连接
    all_idx = np.arange(W.shape[0])
    for gi, key in enumerate(['back', 'fwd', 'turn', 'motor', 'sense']):
        idx = groups[key]
        if idx:
            W[np.ix_(idx, all_idx)] *= gene[2 + gi]
            W[np.ix_(all_idx, idx)] *= gene[2 + gi]
    return W


def run_life(W, groups, gene, prices):
    """一只线虫的一生:随机行情,每日决策,期末资产。"""
    prices = prices.copy()
    start = rng.randint(0, max(1, len(prices) - N_DAYS - 1))
    prices = prices[start:start + N_DAYS]
    rets = np.diff(prices) / prices[:-1]

    polarity, gain = gene[0], gene[1]
    decay, explore, thresh = gene[7], gene[8], gene[9]
    sense_idx = groups['sense']
    fwd_idx = groups['fwd']
    back_idx = groups['back']

    cash = 100.0
    shares = 0.0
    holding = False
    mem = 0.0  # 行情记忆(decay 基因控制)
    for t in range(len(rets)):
        # 感觉输入:行情特征注入感觉神经元
        r1 = rets[t]
        trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)] if t >= 20 else 0.0
        sense_in = math.tanh(gain * (r1 * 50 + trend * 20)) * polarity
        mem = mem * (1 - decay) + sense_in  # 遗忘基因
        # 动力学收敛(简化:一步读出前进/后退组激活差)
        # 感觉组激活 -> 经真实连接传播 -> 行为组
        act = np.zeros(len(prices) * 0 + 279) if False else np.zeros(279)
        act[sense_idx] = mem
        for _ in range(N_STEPS_DYN):
            h = W @ act
            act = np.tanh(h)  # 平滑激活
        fwd_act = act[fwd_idx].mean() if fwd_idx else 0
        back_act = act[back_idx].mean() if back_idx else 0
        signal = (fwd_act - back_act) + rng.uniform(-explore, explore)

        # 决策:signal > thresh 持有,< -thresh 空仓
        if signal > thresh and not holding and cash > 0:
            shares = cash / prices[t] * 0.999
            cash = 0.0
            holding = True
        elif signal < -thresh and holding:
            cash = shares * prices[t] * 0.999
            shares = 0.0
            holding = False

    value = cash + shares * prices[-1]
    # 生存惩罚:大幅亏损的线虫"死"得更快(适配度非线性)
    return max(0.0, value - 100.0)  # 相对初始的收益(负数=0)


if __name__ == '__main__':
    print('=== exp42: 线虫进化实验(10基因 x 真实连接组,股市=自然环境) ===')
    W_real, groups = load_worm()
    prices_all = load_prices()
    print('连接组: 279 神经元 | 行情: %d 只股票 30 年' % len(prices_all))
    print('基因:', GENE_NAMES)
    print()

    # 初始种群:真实线虫(1.0 缩放 = 无突变) + 随机变异体
    pop = []
    base = np.array([1.0] * 10)
    base[0] = rng.uniform(-1, 1)  # polarity 随机
    pop.append(base)
    for _ in range(N_POP - 1):
        pop.append(mutate(base, rate=0.5, sigma=0.5))

    best_history = []
    avg_history = []
    for gen in range(N_GENS):
        fitness = []
        for worm in pop:
            W = phenotype(worm, W_real, groups)
            prices = prices_all[rng.randint(len(prices_all))]
            fitness.append(run_life(W, groups, worm, prices))
        fitness = np.array(fitness)
        best_i = int(np.argmax(fitness))
        best_history.append(fitness[best_i])
        avg_history.append(fitness.mean())
        if gen % 10 == 0 or gen == N_GENS - 1:
            print('第 %2d 代: 平均 %7.2f | 最佳 %7.2f | 冠军基因 %s' % (
                gen, fitness.mean(), fitness[best_i],
                ' '.join('%.2f' % v for v in pop[best_i][:4])))

        # 选择 top 20% 繁殖
        order = np.argsort(fitness)[::-1]
        survivors = [pop[i] for i in order[:max(2, N_POP // 5)]]
        new_pop = [survivors[0].copy()]  # 精英保留(冠军不死)
        while len(new_pop) < N_POP:
            a, b = rng.choice(len(survivors), 2, replace=False)
            child = crossover(survivors[a], survivors[b])
            child = mutate(child)
            new_pop.append(child)
        pop = new_pop

        # 存档冠军(赛博永生血脉)
        if gen % 10 == 0 or gen == N_GENS - 1:
            champ = pop[0] if fitness[order[0]] >= fitness[best_i] else pop[best_i]
            record = {'gen': gen, 'fitness': float(max(fitness)),
                      'genes': {GENE_NAMES[i]: float(champ[i]) for i in range(10)}}
            with open(os.path.join(ARCHIVE, 'champion_gen%03d.json' % gen),
                      'w', encoding='utf-8') as f:
                json.dump(record, f, ensure_ascii=False, indent=1)

    print()
    print('=== 结果 ===')
    print('最佳适配度: %.1f(初始 100,正=跑赢)' % max(best_history))
    print('平均适配度曲线(每10代):', ' '.join('%.0f' % v for v in avg_history[::10]))
    print('冠军基因(最终代):')
    champ_gene = pop[0]
    for i, name in enumerate(GENE_NAMES):
        print('  %-10s %+.3f' % (name, champ_gene[i]))
    print()
    print('存档: worm_data/evolution/champion_gen*.json(血脉,赛博永生)')
