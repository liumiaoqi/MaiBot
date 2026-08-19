#!/usr/bin/env python3
"""exp53: 角色参数漂移——性格基因组版(调控-表达两层结构) × 量子信道对照

用户判断(正确):exp52 量子信道失效 = 角色参数复杂度不够(8 个裸标量=单层表型,
量子算子在基因层的威力(exp49)来自"调控基因→发育映射→表型"两层结构——角色层没有这层结构)。

本实验升级(对齐 exp48/49 基因结构):
1. 角色基因组:2 条"性格染色体",每条 = [regA, regB, s0, s1, s2, s3]
   regA 控制 s0-s1, regB 控制 s2-s3(调控基因=模块开关,GRN 简化)
2. 发育映射(develop):表型 8 参数 = 表达的结构基因;调控基因=0 时取中性值
   (未表达的"性格维度"不参与行为——一个调控翻转 = 一组性格剧变)
3. 三组对照(exp49 同款算子,作用于基因组):
   classic        经典(高斯点突变+调控翻转)
   quantum_channel 量子信道(bitflip 调控翻转/ampdamp 向中性衰减/depolar 随机化)
   quantum_tunnel  经典 + 2% 整染色体大跳
4. 群聊模拟 = exp51/52 同款(表型驱动)

验证:两层结构下量子信道是否恢复 exp49 的多样性优势(9.1 vs 3.4 表达基因)
"""

import json
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
N_CHROMO = 2
GENES_PER_CHROMO = 6   # [regA, regB, s0, s1, s2, s3]
N_STRUCT = 8           # 表型参数数(角色行为参数)

PHENO_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
PHENO_NEUTRAL = [0.25, 0.0, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']


# ============ 基因组: 2 条染色体 × [regA, regB, s0..s3] ============

def random_chromosome():
    return [rng.randint(0, 2), rng.randint(0, 2)] + [rng.uniform(-1.0, 1.0) for _ in range(4)]


def random_genome():
    return [random_chromosome() for _ in range(N_CHROMO)]


def develop(genome):
    """发育映射: 表型 8 参数 = 表达的结构基因; reg=0 时取中性值"""
    pheno = list(PHENO_NEUTRAL)
    struct_idx = 0
    for chromo in genome:
        regA, regB = chromo[0], chromo[1]
        for j, s in enumerate(chromo[2:]):
            if struct_idx >= N_STRUCT:
                break
            reg = regA if j < 2 else regB
            if reg == 1:
                lo, hi = PHENO_RANGES[struct_idx]
                pheno[struct_idx] = lo + (s + 1.0) / 2.0 * (hi - lo)
            struct_idx += 1
    return np.array(pheno)


def count_expressed(genome):
    """假基因化指标: 表达的基因数(reg=1 且位点在表型范围内)"""
    n = 0
    for chromo in genome:
        for j, s in enumerate(chromo[2:]):
            reg = chromo[0] if j < 2 else chromo[1]
            if reg == 1:
                n += 1
    return n


def mutate_classic(genome):
    """经典变异: 高斯点突变 + 调控翻转"""
    new = []
    for chromo in genome:
        c = chromo.copy()
        for r_ in range(2):
            if rng.random() < 0.05:
                c[r_] = 1 - c[r_]
        for j in range(2, len(c)):
            if rng.random() < 0.15:
                c[j] += rng.normal(0, 0.3)
                c[j] = max(-1.0, min(1.0, c[j]))
        new.append(c)
    return new


def mutate_quantum_channel(genome):
    """量子信道变异(exp49 同款): bitflip/ampdamp/depolar"""
    new = []
    for chromo in genome:
        c = chromo.copy()
        for r_ in range(2):
            if rng.random() < 0.05:
                c[r_] = 1 - c[r_]
        for j in range(2, len(c)):
            roll = rng.random()
            if roll < 0.05:
                c[j] = rng.uniform(-1.0, 1.0)          # depolar 退极化
            elif roll < 0.15:
                c[j] *= 0.5                              # ampdamp 向中性衰减
                if abs(c[j]) < 0.05:
                    c[j] = 0.0
            elif roll < 0.25:
                c[j] += rng.normal(0, 0.3)               # 高斯微扰
                c[j] = max(-1.0, min(1.0, c[j]))
        new.append(c)
    return new


def mutate_quantum_tunnel(genome):
    """经典 + 2% 整染色体大跳(隧穿)"""
    new = mutate_classic(genome)
    for ci in range(len(new)):
        if rng.random() < 0.02:
            for j in range(2, len(new[ci])):
                new[ci][j] = rng.uniform(-1.0, 1.0)
            if rng.random() < 0.5:
                new[ci][0] = 1 - new[ci][0]
                new[ci][1] = 1 - new[ci][1]
    return new


MUTATORS = {'classic': mutate_classic,
            'quantum_channel': mutate_quantum_channel,
            'quantum_tunnel': mutate_quantum_tunnel}


# ============ 群聊模拟(exp51 同款, 表型驱动) ============

def topic_affinity(pheno, topic):
    desire = pheno[:, 3]
    recall = pheno[:, 5]
    return np.clip(0.3 + 0.7 * desire * np.abs(np.sin(topic * 1.7 + recall * 3.1)), 0, 1)


def simulate_round(pheno, topic, topic_state, opinions, relationships):
    n = len(pheno)
    aff = topic_affinity(pheno, topic)
    speak_prob = 0.15 + 0.6 * pheno[:, 3] * aff
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    for i in np.where(speakers)[0]:
        own = opinions[i]
        if pheno[i, 1] < 0:
            lean = own * (1 - abs(pheno[i, 1])) - np.sign(topic_state) * abs(pheno[i, 1])
        else:
            lean = own
        if rng.uniform(0, 1) < pheno[i, 0] * 0.5:
            actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
        elif rng.uniform(0, 1) < pheno[i, 7] * 0.6 and abs(opinions[i] - topic_state) < 0.5:
            actions.append((i, 'agree', topic_state))
        else:
            actions.append((i, 'argue', lean))
    if actions:
        non_new = [(i, v) for i, k, v in actions if k != 'new_topic']
        if non_new:
            w2 = np.array([pheno[i, 3] for i, _ in non_new])
            if w2.sum() <= 0:
                w2 = np.ones_like(w2)
            v2 = np.array([v for _, v in non_new])
            topic_state = np.clip(np.average(v2, weights=w2), -1, 1)
    for i in range(n):
        social_influence = pheno[i, 2] * pheno[i, 1] * (topic_state - opinions[i])
        opinions[i] = np.clip(opinions[i] * pheno[i, 6] + social_influence, -1, 1)
    fitness_inc = np.zeros(n)
    for i, k, v in actions:
        if k == 'new_topic':
            fitness_inc[i] += 0.5
        else:
            fitness_inc[i] += 0.3 + 0.7 * abs(v - topic_state)
    for a in range(len(actions)):
        for b in range(a + 1, len(actions)):
            i, k1, v1 = actions[a]
            j, k2, v2 = actions[b]
            if k1 == k2 and k1 != 'new_topic' and abs(v1 - v2) < 0.5:
                relationships[i, j] += 1
                relationships[j, i] += 1
    return actions, fitness_inc, topic_state, opinions, relationships


def run_experiment(mode, seed):
    rng.seed(seed)
    genomes = [random_genome() for _ in range(N_CHARS)]
    phenos = np.array([develop(g) for g in genomes])
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    expr_history = []
    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships = simulate_round(
            phenos, topic, topic_state, opinions, relationships)
        fitness += inc
        if (t + 1) % DRIFT_EVERY == 0:
            sigma = DRIFT_SIGMA0 * (TEMP_DECAY ** (t // DRIFT_EVERY))
            # 适应度梯度调制变异强度(exp51 洞见: 高适应度保守/低适应度探索)
            fit_max = float(fitness.max())
            fit_min = float(fitness.min())
            fit_span = max(fit_max - fit_min, 1e-9)
            for i in range(N_CHARS):
                rel_fit = (fitness[i] - fit_min) / fit_span
                # 变异次数随适应度缩放: 最差 ~2 次, 最好 ~0.5 次
                n_mut = int(round(0.5 + 1.5 * (1.0 - rel_fit)))
                for _ in range(n_mut):
                    genomes[i] = MUTATORS[mode](genomes[i])
            phenos = np.array([develop(g) for g in genomes])
            expr_history.append(np.mean([count_expressed(g) for g in genomes]))
    return {'genomes': genomes, 'phenos': phenos, 'fitness': fitness,
            'relationships': relationships, 'opinions': opinions,
            'expr_history': expr_history}


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
    print("exp53: 性格基因组版角色漂移(调控-表达两层) × 量子信道对照")
    print("=" * 70)
    seeds = [7, 11, 23, 42, 99]
    modes = ['classic', 'quantum_channel', 'quantum_tunnel']
    results = {m: {'div_delta': [], 'gain': [], 'expr': []} for m in modes}

    for s in seeds:
        # 固定基线(不漂移)
        rng.seed(s)
        genomes0 = [random_genome() for _ in range(N_CHARS)]
        phenos0 = np.array([develop(g) for g in genomes0])
        opinions = rng.uniform(-1, 1, N_CHARS)
        rel = np.zeros((N_CHARS, N_CHARS))
        topic = rng.randint(N_TOPICS)
        ts = 0.0
        fit0 = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(N_TOPICS)
            _, inc, ts, opinions, rel = simulate_round(phenos0, topic, ts, opinions, rel)
            fit0 += inc
        d0 = diversity_pheno(phenos0)
        for m in modes:
            res = run_experiment(m, s)
            dd = diversity_pheno(res['phenos']) - d0
            gain = (res['fitness'].mean() / fit0.mean() - 1) * 100
            results[m]['div_delta'].append(dd)
            results[m]['gain'].append(gain)
            results[m]['expr'].append(res['expr_history'][-1])

    print(f"\n{'模式':<16}{'差异度Δ':>10}{'适应度增益':>12}{'终态表达基因':>14}")
    print("-" * 56)
    for m in modes:
        dd = np.mean(results[m]['div_delta'])
        gain = np.mean(results[m]['gain'])
        expr = np.mean(results[m]['expr'])
        print(f"{m:<16}{dd:>+10.3f}{gain:>+11.1f}%{expr:>14.1f}")

    print(f"\n各 seed 明细:")
    print(f"{'seed':<6}", end="")
    for m in modes:
        print(f"{'Δ'+m[:3]:>11}", end="")
    for m in modes:
        print(f"{'增益'+m[:3]:>11}", end="")
    print()
    for k, s in enumerate(seeds):
        print(f"{s:<6}", end="")
        for m in modes:
            print(f"{results[m]['div_delta'][k]:>+11.3f}", end="")
        for m in modes:
            print(f"{results[m]['gain'][k]:>+10.1f}%", end="")
        print()

    # 终态表型(seed 42 量子信道)
    print("\n=== seed 42 终态表型(量子信道) ===")
    res = run_experiment('quantum_channel', 42)
    for i, name in enumerate(NAMES):
        p = res['phenos'][i]
        print(f"  {name}: " + " ".join(f"{pn}={pv:.2f}" for pn, pv in zip(PARAM_NAMES, p)))
    # 表达基因演化
    print("\n表达基因数演化(量子信道, 每10轮):")
    for k, e in enumerate(res['expr_history'][::3]):
        print(f"  轮 {k*30}: {e:.1f}")

    np.savez(os.path.join(ARCHIVE, 'exp53_genome_drift.npz'),
             seeds=np.array(seeds),
             div_delta={m: np.array(results[m]['div_delta']) for m in modes},
             gain={m: np.array(results[m]['gain']) for m in modes},
             expr={m: np.array(results[m]['expr']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp53_genome_drift.npz")


if __name__ == '__main__':
    main()
