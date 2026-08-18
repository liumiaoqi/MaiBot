#!/usr/bin/env python3
"""exp48: 真实基因结构进化——染色体/调控基因/结构变异/发育映射

用户批评(正确):基因=10个实数标量太简单。升级:
1. 染色体组织:3 条染色体,每条 = [regA, regB, s0, s1, s2, s3]
   regA 控制 s0-s1, regB 控制 s2-s3(调控基因=模块开关,GRN 简化)
2. 发育过程:表型参数 = 表达的结构基因值;调控基因=0 时该参数取中性值
   (1.0 缩放/0 参数)——一个调控翻转 = 一组表型剧变(大突变)
3. 结构变异:基因复制(位点数+1,表型取拷贝均值)/基因删除(位点-1,参数永久中性)
   ——基因数量可变!
4. 遗传:染色体整体交叉(同源交换)+ 点突变 + 调控翻转 + 复制/删除
5. 基因不传财:后代一律从 100 起步(只有基因传递)
6. 消费只由交易收益支付:持仓收益先进可消费账户,空仓无可消费=饿死
   (exp47 更强机制——绝对逼迫流动)

表型 12 参数 = 10 旧(极性/增益/5组/遗忘/探索/阈值)+ 2 新(危机敏感/连接密度)
"""

import json
import math
import os
import numpy as np

rng = np.random.RandomState(20260818)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_genes')
os.makedirs(ARCHIVE, exist_ok=True)

N0 = 60
CAPACITY = 150
EPOCH_DAYS = 100
N_EPOCHS = 12
N_STOCKS = 4
LIFESPAN_EPOCHS = 3
REPRO_LINE = 130.0
CONSUME_RATE = 0.08
N_CHROMO = 3
GENES_PER_CHROMO = 6   # [regA, regB, s0, s1, s2, s3]
N_STRUCT = 12           # 表型参数数

PHENO_RANGES = [(-1.0, 1.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0), (0.1, 3.0),
                (0.1, 3.0), (0.1, 3.0), (0.0, 1.0), (0.0, 0.5), (-0.5, 0.5),
                (0.0, 0.5), (0.1, 3.0)]
PHENO_NEUTRAL = [0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.2, 0.0, 0.1, 1.0]

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


def load_all_prices():
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from data_loader import load_stock
    from exp15_noise_vs_deterministic import POOL2
    from exp12_policy_prior import POOL as POOL1
    series = []
    for code in list(POOL1.keys()) + list(POOL2.keys()):
        try:
            series.append(load_stock(code)['close'].values)
        except Exception:
            pass
    return series


def random_chromosome():
    """随机染色体:[regA(0/1), regB(0/1), s0..s3(连续)]。"""
    regs = [rng.randint(0, 2) for _ in range(2)]
    structs = [rng.uniform(-1.0, 1.0) for _ in range(4)]
    return [regs[0], regs[1]] + structs


def random_genome():
    return [random_chromosome() for _ in range(N_CHROMO)]


def develop(genome):
    """发育:基因型 -> 表型 12 参数(调控基因决定表达)。"""
    pheno = list(PHENO_NEUTRAL)  # 默认中性(不表达)
    struct_idx = 0
    for chromo in genome:
        regA, regB = chromo[0], chromo[1]
        structs = chromo[2:]
        # regA 控制 s0-s1, regB 控制 s2-s3
        for j, s in enumerate(structs):
            if struct_idx >= N_STRUCT:
                break
            reg = regA if j < 2 else regB
            if reg == 1:
                # 表达:映射到参数范围
                lo, hi = PHENO_RANGES[struct_idx]
                pheno[struct_idx] = lo + (s + 1.0) / 2.0 * (hi - lo)
            struct_idx += 1
    return np.array(pheno)


def mutate_genome(genome):
    """变异:点突变/调控翻转/基因复制/基因删除。"""
    new = []
    for chromo in genome:
        c = chromo.copy()
        # 调控翻转
        for r in range(2):
            if rng.random() < 0.05:
                c[r] = 1 - c[r]
        # 结构基因点突变
        for j in range(2, len(c)):
            if rng.random() < 0.15:
                c[j] += rng.normal(0, 0.3)
                c[j] = max(-1.0, min(1.0, c[j]))
        new.append(c)
    # 基因复制(某染色体复制一个结构位点)
    if rng.random() < 0.08:
        ci = rng.randint(len(new))
        if len(new[ci]) < GENES_PER_CHROMO + 3:
            new[ci] = new[ci][:2] + [new[ci][rng.randint(2, len(new[ci]))]] + new[ci][2:]
    # 基因删除(某染色体删一个结构位点,至少保留 2 个)
    if rng.random() < 0.08:
        ci = rng.randint(len(new))
        if len(new[ci]) > 4:
            di = rng.randint(2, len(new[ci]))
            del new[ci][di]
    return new


def crossover_genome(a, b):
    """染色体整体交换(同源染色体交叉)。"""
    child = []
    for ca, cb in zip(a, b):
        child.append(ca if rng.random() < 0.5 else cb)
    return child


def make_world(all_prices):
    world = []
    for _ in range(N_STOCKS):
        p = all_prices[rng.randint(len(all_prices))]
        start = rng.randint(0, max(1, len(p) - EPOCH_DAYS - 1))
        seg = p[start:start + EPOCH_DAYS].copy()
        if rng.random() < 0.2:
            seg[rng.randint(1, len(seg) - 1)] *= 0.85
        world.append(seg)
    return world


class Worm:
    __slots__ = ('genome', 'cash', 'shares', 'holdings', 'mem', 'age',
                 'ancestors', 'consume_fund')

    def __init__(self, genome, ancestors=1):
        self.genome = genome
        self.cash = [100.0 / N_STOCKS] * N_STOCKS
        self.shares = [0.0] * N_STOCKS
        self.holdings = [False] * N_STOCKS
        self.mem = [0.0] * N_STOCKS
        self.age = 0
        self.ancestors = ancestors
        self.consume_fund = 0.0  # 可消费账户(只由交易收益进账)

    def value(self, world):
        return sum(c + s * p[-1] for c, s, p in zip(self.cash, self.shares, world))

    def consume(self, world):
        """消费只由交易收益支付:consume_fund 不足 = 饿死。"""
        need = self.value(world) * CONSUME_RATE
        if self.consume_fund >= need:
            self.consume_fund -= need
            return True
        return False


def run_epoch(worms, W_map, groups, world):
    for t in range(EPOCH_DAYS - 1):
        for w in worms:
            for si, prices in enumerate(world):
                r1 = prices[t + 1] / prices[t] - 1.0
                trend = (prices[t] - prices[max(0, t - 20)]) / prices[max(0, t - 20)]
                pheno = W_map[id(w)]['pheno']
                sense_in = math.tanh(pheno[1] * (r1 * 50 + trend * 20)) * pheno[0]
                w.mem[si] = w.mem[si] * (1 - pheno[7]) + sense_in
                act = np.zeros(279)
                act[groups['sense']] = w.mem[si]
                for _ in range(4):
                    act = np.tanh(W_map[id(w)]['W'] @ act)
                fwd_act = act[groups['fwd']].mean() if groups['fwd'] else 0
                back_act = act[groups['back']].mean() if groups['back'] else 0
                signal = (fwd_act - back_act) + rng.uniform(-pheno[8], pheno[8])
                if signal > pheno[9] and not w.holdings[si] and w.cash[si] > 0:
                    cost = w.cash[si] / prices[t] * 0.999
                    w.shares[si] = cost
                    w.cash[si] = 0.0
                    w.holdings[si] = True
                elif signal < -pheno[9] and w.holdings[si]:
                    gain = w.shares[si] * prices[t] * 0.999
                    # 交易收益进入可消费账户(结构性流动!)
                    profit = gain - w.shares[si] * prices[max(0, t - 1)]
                    w.consume_fund += max(0.0, profit)
                    w.cash[si] = gain
                    w.shares[si] = 0.0
                    w.holdings[si] = False
            w.age += 1
    alive = []
    for w in worms:
        if w.consume(world):
            alive.append(w)
    return alive


def reproduce(worms, world):
    next_gen = []
    for w in worms:
        if w.age > EPOCH_DAYS * LIFESPAN_EPOCHS:
            continue
        v = w.value(world)
        if v <= 0:
            continue
        if v >= REPRO_LINE:
            n_children = max(1, min(5, int((v - 100.0) / 50.0)))
            for _ in range(n_children):
                g = mutate_genome(w.genome)
                if rng.random() < 0.5:
                    partner = rng.choice([x for x in worms if x is not w] or [w])
                    g = crossover_genome(g, partner.genome)
                    g = mutate_genome(g)
                next_gen.append(Worm(g, ancestors=w.ancestors + 1))
            # 繁殖即清算:父代退出,基因不传财(后代从 100 起步——构造已定)
        else:
            next_gen.append(w)
    if len(next_gen) > CAPACITY:
        next_gen.sort(key=lambda x: -x.ancestors)
        next_gen = next_gen[:CAPACITY]
    return next_gen


def count_genes(genome):
    return sum(len(c) - 2 for c in genome)


if __name__ == '__main__':
    print('=== exp48: 真实基因结构进化(染色体/调控/复制删除/发育/收益消费) ===')
    W_real, groups = load_worm()
    all_prices = load_all_prices()
    base = random_genome()
    worms = [Worm(mutate_genome(base)) for _ in range(N0)]
    holds = []
    gene_counts = []
    for ep in range(N_EPOCHS):
        world = make_world(all_prices)
        W_map = {}
        for w in worms:
            pheno = develop(w.genome)
            W = W_real.copy()
            all_idx = np.arange(W.shape[0])
            for gi, key in enumerate(['back', 'fwd', 'turn', 'motor', 'sense']):
                idx = groups[key]
                if idx:
                    W[np.ix_(idx, all_idx)] *= pheno[2 + gi]
                    W[np.ix_(all_idx, idx)] *= pheno[2 + gi]
            W_map[id(w)] = {'W': W, 'pheno': pheno}
        worms = run_epoch(worms, W_map, groups, world)
        worms = reproduce(worms, world)
        holds.append(np.mean([sum(w.holdings) / N_STOCKS for w in worms]) if worms else 0)
        gene_counts.append(np.mean([count_genes(w.genome) for w in worms]) if worms else 0)
        if worms:
            max_anc = max(w.ancestors for w in worms)
            print('纪元 %2d: 种群 %3d | 基因数/个体 %.1f | 持仓率 %.1f%% | 谱系 %d' % (
                ep, len(worms), gene_counts[-1], holds[-1] * 100, max_anc))
        else:
            print('纪元 %2d: 灭绝' % ep)
            break

    print()
    print('=== 结果(真实基因结构) ===')
    print('基因数演化(复制/删除):', ' '.join('%.1f' % v for v in gene_counts))
    print('持仓率演化(收益消费逼迫):', ' '.join('%.0f%%' % (v * 100) for v in holds))
    if worms:
        print('最深谱系:', max(w.ancestors for w in worms))
        best = max(worms, key=lambda w: w.value(make_world(all_prices)))
        pheno = develop(best.genome)
        print('冠军表型(12 参数):', ' '.join('%.2f' % v for v in pheno))
        print('冠军基因数:', count_genes(best.genome))
