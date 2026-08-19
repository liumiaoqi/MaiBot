#!/usr/bin/env python3
"""exp54: 三层 GRN 性格基因组 + 关系记忆群聊——复杂度第三级

用户:继续 AI 线,加复杂度。exp53 两层(调控-表达)已证复杂度有效(classic 差异度翻 6 倍),
本实验三面升级:

1. 基因调控网络(GRN)——exp48/53 的 reg 是 0/1 二值开关,升级为:
   - 调控基因连续值(-1~1,负=抑制)
   - 每个结构基因受"多个调控基因加权控制"(连接矩阵 W 固定=发育蓝图,调控值进化)
   - 表达 = clamp(Σ W*reg, 0, 1), 低于表达阈值取中性值(不参与行为)
   → "调控网络重加权"替代"单开关翻转":一个调控基因漂移 = 一整组性格维度渐变

2. 表型 12 参数(8 旧 + 4 新):
   leadership 领导力(发言权重) / curiosity 好奇心(新话题增益)
   mood_swing 情绪波动 / grudge 记仇(对立角色反驳倾向)

3. 群聊复杂度:
   - 关系记忆: 互动过的角色观点互相靠拢加权(关系好→影响大), 对立角色反驳
   - 情绪传染: 群聊氛围(主流观点极性)→ 角色情绪状态, empathy 高被传染快,
     mood_swing 高波动大 → 影响发言倾向

指标: 差异度/适应度/表达基因数/关系网络密度/情绪极化
"""

import os
import numpy as np

rng = np.random.RandomState(20260819)
DATA = r'E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune\\snn_behavior\\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_chat')
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
DRIFT_EVERY = 10
DRIFT_SIGMA0 = 0.06
TEMP_DECAY = 0.98
N_TOPICS = 10
N_REG = 6               # 调控基因数(3 染色体 × 2)
N_STRUCT = 12           # 结构基因数 = 表型参数数
EXPR_THRESHOLD = 0.35   # 表达阈值: ΣW*reg 低于此取中性值

PHENO_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
PHENO_NEUTRAL = [0.25, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5,
                 0.5, 0.5, 0.5, 0.5]
PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall',
               'persist', 'empathy', 'leadership', 'curiosity', 'mood_swing', 'grudge']

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']


# ============ GRN 基因组: 3 染色体 × [r1, r2, s1, s2, s3, s4] ============
# reg 连续(-1~1), 结构基因 s(-1~1) 是"基因值", 表达量由调控网络决定

def random_genome():
    """3 染色体 × 6 基因: [reg, reg, s, s, s, s] 全连续"""
    return [rng.uniform(-1.0, 1.0, 6) for _ in range(3)]


def make_connectome():
    """发育蓝图: 连接矩阵 W (N_STRUCT × N_REG)——固定随机, 稀疏(每个结构基因连 2-3 个调控基因)"""
    W = np.zeros((N_STRUCT, N_REG))
    for i in range(N_STRUCT):
        n_conn = rng.randint(2, 4)
        conns = rng.choice(N_REG, n_conn, replace=False)
        for c in conns:
            W[i, c] = rng.uniform(-1.0, 1.0)
    return W


CONNECTOME = make_connectome()  # 种群共享发育蓝图(所有角色同蓝图, 调控值各自进化)


def develop(genome):
    """GRN 发育(exp54b 修复): sigmoid 表达量——默认半表达, 调控漂移=渐变非开关。
    语义: signal>0 表达增强(表型逼近结构基因目标值), signal<0 表达减弱(逼近中性值)。
    exp54 教训: 硬阈值让大多数维度不表达 → 角色塌缩中性人 → 多样性低"""
    reg = np.concatenate([chromo[:2] for chromo in genome])      # (6,)
    s_vals = np.concatenate([chromo[2:] for chromo in genome])    # (12,)
    signal = CONNECTOME @ reg                                     # (12,)
    expr = 1.0 / (1.0 + np.exp(-signal * 2.0))                    # sigmoid: 0→0.5 半表达
    pheno = np.array(PHENO_NEUTRAL, dtype=float)
    for i in range(N_STRUCT):
        lo, hi = PHENO_RANGES[i]
        frac = (s_vals[i] + 1.0) / 2.0
        target = lo + frac * (hi - lo)                            # 结构基因目标值
        pheno[i] = PHENO_NEUTRAL[i] + (target - PHENO_NEUTRAL[i]) * expr[i]
    return pheno


def count_expressed(genome):
    """表达基因数: 表达量 > 0.6(接近目标值, 明显非中性)"""
    reg = np.concatenate([chromo[:2] for chromo in genome])
    signal = CONNECTOME @ reg
    expr = 1.0 / (1.0 + np.exp(-signal * 2.0))
    return int((expr > 0.6).sum())


# ============ 变异算子(作用于连续基因组) ============

def mutate_classic(genome):
    new = []
    for chromo in genome:
        c = chromo.copy()
        for j in range(len(c)):
            if rng.random() < 0.10:
                c[j] += rng.normal(0, 0.25)
                c[j] = max(-1.0, min(1.0, c[j]))
        new.append(c)
    return new


def mutate_quantum_channel(genome):
    new = []
    for chromo in genome:
        c = chromo.copy()
        for j in range(len(c)):
            roll = rng.random()
            if roll < 0.05:
                c[j] = rng.uniform(-1.0, 1.0)          # depolar
            elif roll < 0.15:
                c[j] *= 0.5                              # ampdamp 向 0(失活方向)
                if abs(c[j]) < 0.05:
                    c[j] = 0.0
            elif roll < 0.25:
                c[j] += rng.normal(0, 0.25)              # 高斯微扰
                c[j] = max(-1.0, min(1.0, c[j]))
        new.append(c)
    return new


def mutate_quantum_tunnel(genome):
    new = mutate_classic(genome)
    for ci in range(len(new)):
        if rng.random() < 0.02:
            for j in range(len(new[ci])):
                new[ci][j] = rng.uniform(-1.0, 1.0)
    return new


MUTATORS = {'classic': mutate_classic,
            'quantum_channel': mutate_quantum_channel,
            'quantum_tunnel': mutate_quantum_tunnel}


# ============ 群聊: 关系记忆 + 情绪传染 ============

def topic_affinity(pheno, topic):
    desire = pheno[:, 3]
    recall = pheno[:, 5]
    curiosity = pheno[:, 9]
    return np.clip(0.3 + 0.7 * desire * np.abs(np.sin(topic * 1.7 + recall * 3.1))
                   + 0.3 * curiosity * (1.0 if topic % 2 == 0 else 0.3), 0, 1)


def simulate_round(pheno, topic, topic_state, opinions, relationships, moods):
    n = len(pheno)
    aff = topic_affinity(pheno, topic)
    # 情绪调制发言: 情绪高→更想说话
    speak_prob = 0.15 + 0.6 * pheno[:, 3] * aff + 0.1 * np.clip(moods, 0, 1)
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    for i in np.where(speakers)[0]:
        own = opinions[i]
        # 记仇: 对立关系角色多反驳
        grudge_targets = np.where(relationships[i] < -3)[0]
        if len(grudge_targets) > 0 and rng.random() < pheno[i, 11]:
            actions.append((i, 'argue', -np.sign(opinions[grudge_targets[0]])))
            continue
        if pheno[i, 1] < 0:
            lean = own * (1 - abs(pheno[i, 1])) - np.sign(topic_state) * abs(pheno[i, 1])
        else:
            lean = own
        if rng.uniform(0, 1) < pheno[i, 0] * 0.5 + pheno[i, 9] * 0.2:
            actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
        elif rng.uniform(0, 1) < pheno[i, 7] * 0.6 and abs(opinions[i] - topic_state) < 0.5:
            actions.append((i, 'agree', topic_state))
        else:
            actions.append((i, 'argue', lean))
    # 主流观点更新(leadership 加权)
    if actions:
        non_new = [(i, v) for i, k, v in actions if k != 'new_topic']
        if non_new:
            w2 = np.array([pheno[i, 3] * (1.0 + pheno[i, 8]) for i, _ in non_new])
            if w2.sum() <= 0:
                w2 = np.ones_like(w2)
            v2 = np.array([v for _, v in non_new])
            topic_state = np.clip(np.average(v2, weights=w2), -1, 1)
    # 观点更新: 社会影响 × 关系加权(关系好影响大)
    for i in range(n):
        social_influence = 0.0
        for j in range(n):
            if j == i:
                continue
            rel = relationships[i, j]
            if abs(rel) < 0.5:
                continue
            # 关系正→靠拢, 负→远离(对立)
            influence = pheno[i, 2] * pheno[i, 1] * (opinions[j] - opinions[i])
            social_influence += np.sign(rel) * influence * min(abs(rel), 3.0) / 3.0
        opinions[i] = np.clip(opinions[i] * pheno[i, 6] + social_influence, -1, 1)
    # 情绪传染: 氛围(topic_state 极性) → 情绪; empathy 高被传染快, mood_swing 高波动大
    for i in range(n):
        target = topic_state
        pull = pheno[i, 7] * 0.3 * (target - moods[i])
        noise = pheno[i, 10] * rng.uniform(-0.3, 0.3)
        moods[i] = np.clip(moods[i] + pull + noise, -1, 1)
    # 适应度 + 关系更新
    fitness_inc = np.zeros(n)
    for i, k, v in actions:
        if k == 'new_topic':
            fitness_inc[i] += 0.5 + 0.5 * pheno[i, 9]
        else:
            fitness_inc[i] += 0.3 + 0.7 * abs(v - topic_state)
    for a in range(len(actions)):
        for b in range(a + 1, len(actions)):
            i, k1, v1 = actions[a]
            j, k2, v2 = actions[b]
            if k1 == k2 and k1 != 'new_topic':
                same = 1.0 if abs(v1 - v2) < 0.5 else -0.5
                relationships[i, j] += same
                relationships[j, i] += same
    return actions, fitness_inc, topic_state, opinions, relationships, moods


def run_experiment(mode, seed, select=True):
    rng.seed(seed)
    genomes = [random_genome() for _ in range(N_CHARS)]
    phenos = np.array([develop(g) for g in genomes])
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    moods = rng.uniform(-0.3, 0.3, N_CHARS)
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships, moods = simulate_round(
            phenos, topic, topic_state, opinions, relationships, moods)
        fitness += inc
        if (t + 1) % DRIFT_EVERY == 0:
            if select:
                order = np.argsort(fitness)
                worst = order[:2]
                best = int(order[-1])
                for wi in worst:
                    child = MUTATORS[mode]([c.copy() for c in genomes[best]])
                    child = MUTATORS[mode](child)
                    genomes[wi] = child
                    fitness[wi] = fitness[best] * 0.5
            fit_max = float(fitness.max())
            fit_min = float(fitness.min())
            fit_span = max(fit_max - fit_min, 1e-9)
            for i in range(N_CHARS):
                rel_fit = (fitness[i] - fit_min) / fit_span
                n_mut = int(round(0.5 + 1.5 * (1.0 - rel_fit)))
                for _ in range(n_mut):
                    genomes[i] = MUTATORS[mode](genomes[i])
            phenos = np.array([develop(g) for g in genomes])
    return {'phenos': phenos, 'fitness': fitness, 'relationships': relationships,
            'moods': moods, 'expr': np.mean([count_expressed(g) for g in genomes])}


def diversity_pheno(phenos):
    d = 0.0
    cnt = 0
    for i in range(len(phenos)):
        for j in range(i + 1, len(phenos)):
            d += np.linalg.norm(phenos[i] - phenos[j])
            cnt += 1
    return d / cnt


def main():
    print("=" * 70)
    print("exp54: 三层 GRN 性格基因组 + 关系记忆群聊(复杂度第三级)")
    print("=" * 70)
    seeds = [7, 11, 23, 42, 99]
    modes = ['classic', 'quantum_channel', 'quantum_tunnel']
    stats = {m: {'div': [], 'gain': [], 'expr': []} for m in modes}
    for s in seeds:
        # 基线
        rng.seed(s)
        genomes0 = [random_genome() for _ in range(N_CHARS)]
        phenos0 = np.array([develop(g) for g in genomes0])
        opinions = rng.uniform(-1, 1, N_CHARS)
        rel = np.zeros((N_CHARS, N_CHARS))
        moods = rng.uniform(-0.3, 0.3, N_CHARS)
        topic = rng.randint(N_TOPICS)
        ts = 0.0
        fit0 = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(N_TOPICS)
            _, inc, ts, opinions, rel, moods = simulate_round(phenos0, topic, ts, opinions, rel, moods)
            fit0 += inc
        d0 = diversity_pheno(phenos0)
        for m in modes:
            res = run_experiment(m, s, select=True)
            stats[m]['div'].append(diversity_pheno(res['phenos']) - d0)
            stats[m]['gain'].append((res['fitness'].mean() / fit0.mean() - 1) * 100)
            stats[m]['expr'].append(res['expr'])

    print(f"\n{'模式':<18}{'差异度Δ':>10}{'适应度增益':>12}{'表达基因':>10}{'关系密度':>10}{'情绪极化':>10}")
    print("-" * 72)
    for m in modes:
        dd = np.mean(stats[m]['div'])
        gain = np.mean(stats[m]['gain'])
        expr = np.mean(stats[m]['expr'])
        res = run_experiment(m, 42, select=True)
        rel_density = (np.abs(res['relationships']) > 0.5).mean()
        mood_pol = np.abs(res['moods']).mean()
        print(f"{m:<18}{dd:>+10.3f}{gain:>+11.1f}%{expr:>10.1f}{rel_density:>10.3f}{mood_pol:>10.3f}")

    print("\n各 seed 明细(差异度Δ / 增益%):")
    print(f"{'seed':<6}{'cla':>18}{'cha':>18}{'tun':>18}")
    for k, s in enumerate(seeds):
        row = f"{s:<6}"
        for m in modes:
            row += f"{stats[m]['div'][k]:>+8.3f}/{stats[m]['gain'][k]:>+7.1f}%"
        print(row)

    # 终态表型(seed 42 classic)
    print("\n=== seed 42 终态表型(classic+选择) ===")
    res = run_experiment('classic', 42, select=True)
    for i, name in enumerate(NAMES):
        p = res['phenos'][i]
        print(f"  {name}: " + " ".join(f"{pn}={pv:.2f}" for pn, pv in zip(PARAM_NAMES, p)))
    print("\n=== seed 42 关系网络(±: 友好/敌对, 取显著边) ===")
    rel = res['relationships']
    for i in range(N_CHARS):
        friends = [NAMES[j] for j in range(N_CHARS) if rel[i, j] > 2]
        foes = [NAMES[j] for j in range(N_CHARS) if rel[i, j] < -2]
        if friends or foes:
            print(f"  {NAMES[i]}: 友[{', '.join(friends) or '-'}] 敌[{', '.join(foes) or '-'}]")

    np.savez(os.path.join(ARCHIVE, 'exp54_grn_drift.npz'),
             seeds=np.array(seeds),
             div={m: np.array(stats[m]['div']) for m in modes},
             gain={m: np.array(stats[m]['gain']) for m in modes},
             expr={m: np.array(stats[m]['expr']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp54_grn_drift.npz")


if __name__ == '__main__':
    main()
