#!/usr/bin/env python3
"""exp53b: 性格基因组 + 选择压力——量子信道完整复刻(exp49 条件齐)

exp53 发现: 量子信道在角色层仍弱 = 缺选择压力(无淘汰时 ampdamp 让全体向中性塌缩)。
本实验给漂移加"温和选择": 每 10 轮淘汰适应度最低 2 角色, 用冠军基因组变异繁殖替代。
对照: 无选择 vs 有选择 × 三算子(6 组), 看量子信道在选择下是否恢复 exp49 威力。
"""

import os
import numpy as np
import exp53_genome_drift as E  # 复用基因组/发育/变异/群聊

rng = np.random.RandomState(20260819)
ARCHIVE = E.ARCHIVE
N_CHARS = E.N_CHARS
N_ROUNDS = E.N_ROUNDS
DRIFT_EVERY = E.DRIFT_EVERY
N_ELIMINATE = 2  # 每漂移轮淘汰数


def run_exp53b(mode, seed, select):
    rng.seed(seed)
    E.rng.seed(seed)  # 关键: 变异算子用的是 E.rng——必须同步播种
    genomes = [E.random_genome() for _ in range(N_CHARS)]
    phenos = np.array([E.develop(g) for g in genomes])
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(E.N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(E.N_TOPICS)
        _, inc, topic_state, opinions, relationships = E.simulate_round(
            phenos, topic, topic_state, opinions, relationships)
        fitness += inc
        if (t + 1) % DRIFT_EVERY == 0:
            sigma = E.DRIFT_SIGMA0 * (E.TEMP_DECAY ** (t // DRIFT_EVERY))
            if select:
                # 温和选择: 淘汰最低 2, 冠军变异繁殖(保留冠军本体)
                order = np.argsort(fitness)
                worst = order[:N_ELIMINATE]
                best = int(order[-1])
                for wi in worst:
                    # 冠军基因组变异两次 = 繁殖(冠军本体保留, 新个体=变异后代)
                    child = E.MUTATORS[mode]([c.copy() for c in genomes[best]])
                    child = E.MUTATORS[mode](child)
                    genomes[wi] = child
                    fitness[wi] = fitness[best] * 0.5  # 新个体适应度重置(半继承)
            # 其余个体变异(适应度梯度调制)
            fit_max = float(fitness.max())
            fit_min = float(fitness.min())
            fit_span = max(fit_max - fit_min, 1e-9)
            for i in range(N_CHARS):
                rel_fit = (fitness[i] - fit_min) / fit_span
                n_mut = int(round(0.5 + 1.5 * (1.0 - rel_fit)))
                for _ in range(n_mut):
                    genomes[i] = E.MUTATORS[mode](genomes[i])
            phenos = np.array([E.develop(g) for g in genomes])
    return phenos, fitness


def main():
    print("=" * 76)
    print("exp53b: 性格基因组 + 选择压力——量子信道完整复刻(exp49 条件齐)")
    print("=" * 76)
    seeds = [7, 11, 23, 42, 99]
    modes = ['classic', 'quantum_channel', 'quantum_tunnel']
    # (select, mode) → metrics
    stats = {}
    for sel in [False, True]:
        for m in modes:
            stats[(sel, m)] = {'div': [], 'gain': []}
    # 基线(不漂移不选择)
    for s in seeds:
        rng.seed(s)
        E.rng.seed(s)
        genomes0 = [E.random_genome() for _ in range(N_CHARS)]
        phenos0 = np.array([E.develop(g) for g in genomes0])
        opinions = rng.uniform(-1, 1, N_CHARS)
        rel = np.zeros((N_CHARS, N_CHARS))
        topic = rng.randint(E.N_TOPICS)
        ts = 0.0
        fit0 = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(E.N_TOPICS)
            _, inc, ts, opinions, rel = E.simulate_round(phenos0, topic, ts, opinions, rel)
            fit0 += inc
        d0 = E.diversity_pheno(phenos0)
        for sel in [False, True]:
            for m in modes:
                phenos, fit = run_exp53b(m, s, sel)
                stats[(sel, m)]['div'].append(E.diversity_pheno(phenos) - d0)
                stats[(sel, m)]['gain'].append((fit.mean() / fit0.mean() - 1) * 100)

    print(f"\n{'条件':<28}{'差异度Δ':>10}{'适应度增益':>12}")
    print("-" * 52)
    for sel in [False, True]:
        for m in modes:
            dd = np.mean(stats[(sel, m)]['div'])
            gain = np.mean(stats[(sel, m)]['gain'])
            tag = "选择+ " if sel else "无选择 "
            print(f"{tag}{m:<20}{dd:>+10.3f}{gain:>+11.1f}%")
    print("\n明细(差异度Δ):")
    print(f"{'seed':<6}{'无选cla':>9}{'无选cha':>9}{'无选tun':>9}{'选cla':>9}{'选cha':>9}{'选tun':>9}")
    for k, s in enumerate(seeds):
        row = f"{s:<6}"
        for sel in [False, True]:
            for m in modes:
                row += f"{stats[(sel,m)]['div'][k]:>+9.3f}"
        print(row)
    print("\n明细(适应度增益%):")
    print(f"{'seed':<6}{'无选cla':>9}{'无选cha':>9}{'无选tun':>9}{'选cla':>9}{'选cha':>9}{'选tun':>9}")
    for k, s in enumerate(seeds):
        row = f"{s:<6}"
        for sel in [False, True]:
            for m in modes:
                row += f"{stats[(sel,m)]['gain'][k]:>+9.1f}"
        print(row)

    np.savez(os.path.join(ARCHIVE, 'exp53b_select_drift.npz'),
             seeds=np.array(seeds),
             div={f"{'s' if sel else 'n'}_{m}": np.array(stats[(sel, m)]['div'])
                  for sel in [False, True] for m in modes},
             gain={f"{'s' if sel else 'n'}_{m}": np.array(stats[(sel, m)]['gain'])
                   for sel in [False, True] for m in modes})
    print(f"\n存档已保存 evolution_chat/exp53b_select_drift.npz")


if __name__ == '__main__':
    main()
