#!/usr/bin/env python3
"""exp60c: 自我认知协方差——每角色独立的"自我环"矩阵（exp57 自我认知 × exp60b 矩阵化）

用户洞察: ①自我认知重要(exp57 的 self_knowledge 是标量,但角色对自己的认知应该是矩阵)
②"自我环"(对角线上自己对自己的关系)在参数协方差里是有意义的:
   对角线 = 每个参数和自己的相关性(=1, 自我环)
   非对角 = "我认为我的性格参数该有的相关结构"

设计(exp60b 框架升级):
1. 全局学习协方差(exp60b) —— 角色群共享一个 Σ, 环境塑造"通用性格结构"
2. 每角色自我认知协方差(本实验) —— 每个角色自己学自己的 Σ_i:
   - 初始 = 单位阵(无自我认知)
   - 每轮漂移后, 用该角色自己的漂移增量更新自己的 Σ_i(EMA)
   - 对角线恒为 1(自我环), 非对角 = 该角色"学到"的自我结构
3. 对照: exp60b 全局 vs 本实验自我认知(逐角色)

指标: 适应度 / 差异度 / 矛盾体比例 / 自我认知矩阵异质性(角色间 Σ 差异)
"""

import os
import numpy as np

rng = np.random.RandomState(20260819)
ARCHIVE = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data\evolution_chat'
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
DRIFT_EVERY = 10
DRIFT_SIGMA0 = 0.06
TEMP_DECAY = 0.98
N_TOPICS = 10
REGRESS_RATE = 0.03

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
N_PARAM = len(PARAM_NAMES)


def clamp_params(p):
    p = np.asarray(p, dtype=float).copy()
    for i, (lo, hi) in enumerate(PARAM_RANGES):
        p[i] = min(max(p[i], lo), hi)
    return p


def init_params():
    p = np.zeros((N_CHARS, N_PARAM))
    for i in range(N_PARAM):
        lo, hi = PARAM_RANGES[i]
        p[:, i] = rng.uniform(lo, hi, N_CHARS)
    return p


def topic_affinity(p, topic):
    desire = p[:, 3]
    recall = p[:, 5]
    return np.clip(0.3 + 0.7 * desire * np.abs(np.sin(topic * 1.7 + recall * 3.1)), 0, 1)


def simulate_round(params, topic, topic_state, opinions, relationships):
    n = len(params)
    aff = topic_affinity(params, topic)
    speak_prob = 0.15 + 0.6 * params[:, 3] * aff
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    for i in np.where(speakers)[0]:
        own = opinions[i]
        if params[i, 1] < 0:
            lean = own * (1 - abs(params[i, 1])) - np.sign(topic_state) * abs(params[i, 1])
        else:
            lean = own
        if rng.random() < params[i, 0] * 0.5:
            actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
        elif rng.random() < params[i, 7] * 0.6 and abs(opinions[i] - topic_state) < 0.5:
            actions.append((i, 'agree', topic_state))
        else:
            actions.append((i, 'argue', lean))
    if actions:
        non_new = [(i, v) for i, k, v in actions if k != 'new_topic']
        if non_new:
            w2 = np.array([params[i, 3] for i, _ in non_new])
            if w2.sum() <= 0:
                w2 = np.ones_like(w2)
            v2 = np.array([v for _, v in non_new])
            topic_state = np.clip(np.average(v2, weights=w2), -1, 1)
    for i in range(n):
        social_influence = params[i, 2] * params[i, 1] * (topic_state - opinions[i])
        opinions[i] = np.clip(opinions[i] * params[i, 6] + social_influence, -1, 1)
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


def contradiction_ratio(params):
    n = len(params)
    cnt = 0
    for i in range(n):
        c1 = abs(params[i, 1]) > 0.5 and params[i, 7] > 0.7
        c2 = params[i, 0] > 0.4 and params[i, 6] > 0.8
        if c1 or c2:
            cnt += 1
    return cnt / n


def psd_projection(cov):
    cov = (cov + cov.T) / 2.0
    eigvals, eigvecs = np.linalg.eigh(cov)
    eigvals = np.maximum(eigvals, 1e-4)
    return eigvecs @ np.diag(eigvals) @ eigvecs.T


def drift_step(params, initial_params, fitness, t, mode, learned_cov, per_char_covs, drift_histories):
    """漂移步: mode='global'(exp60b 全局共享) / mode='self'(每角色自我认知协方差)"""
    sigma = DRIFT_SIGMA0 * (TEMP_DECAY ** (t // DRIFT_EVERY))
    fit_max = float(fitness.max())
    fit_min = float(fitness.min())
    fit_span = max(fit_max - fit_min, 1e-9)

    for i in range(N_CHARS):
        rel_fit = (fitness[i] - fit_min) / fit_span
        sigma_i = sigma * (1.6 - rel_fit)
        if mode == 'global':
            cov = learned_cov
        else:  # self
            cov = per_char_covs[i]
        cov_pd = psd_projection(cov)
        eigvals, eigvecs = np.linalg.eigh(cov_pd)
        noise = sigma_i * (eigvecs @ (np.sqrt(eigvals) * rng.randn(N_PARAM)))
        regress_force = (initial_params[i] - params[i]) * REGRESS_RATE
        params[i] = clamp_params(params[i] + noise + regress_force)
        # 记录该角色自己的漂移增量(自我认知学习用)
        drift_histories[i].append(params[i] - initial_params[i])

    # 更新协方差
    if mode == 'global':
        if len(drift_histories[0]) > N_PARAM * 5:
            all_recent = np.concatenate([np.array(h[-N_PARAM * 2:]) for h in drift_histories])
            learned_cov[:] = 0.7 * learned_cov + 0.3 * np.cov(all_recent.T)
    else:  # self —— 每个角色用自己的历史学自己的 Σ
        for i in range(N_CHARS):
            if len(drift_histories[i]) > N_PARAM * 2:
                recent = np.array(drift_histories[i][-N_PARAM * 3:])
                if len(recent) >= 2:
                    c = np.cov(recent.T)
                    if c.ndim == 2:
                        per_char_covs[i] = 0.7 * per_char_covs[i] + 0.3 * c
                        np.fill_diagonal(per_char_covs[i], 1.0)  # 对角线=自我环(恒1)
    return params, learned_cov, per_char_covs


def select_and_breed(params, fitness):
    sorted_idx = np.argsort(fitness)
    worst2 = sorted_idx[:2]
    best_idx = sorted_idx[-1]
    second_idx = sorted_idx[-2]
    for w in worst2:
        parent = best_idx if rng.random() < 0.7 else second_idx
        params[w] = clamp_params(params[parent] + 0.3 * rng.randn(N_PARAM))
    return params


def run_experiment(mode, seed):
    """mode: baseline / global / self"""
    rng.seed(seed)
    params = init_params()
    initial_params = params.copy()
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    learned_cov = np.eye(N_PARAM)
    per_char_covs = np.stack([np.eye(N_PARAM)] * N_CHARS)
    drift_histories = [[] for _ in range(N_CHARS)]

    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships = simulate_round(
            params, topic, topic_state, opinions, relationships)
        fitness += inc
        if (t + 1) % DRIFT_EVERY == 0:
            if mode != 'baseline':
                params, learned_cov, per_char_covs = drift_step(
                    params, initial_params, fitness, t, mode, learned_cov, per_char_covs, drift_histories)
                params = select_and_breed(params, fitness)

    return {'params': params, 'fitness': fitness, 'covs': per_char_covs.copy()}


def diversity(params):
    d = 0.0
    cnt = 0
    for i in range(len(params)):
        for j in range(i + 1, len(params)):
            d += np.linalg.norm(params[i] - params[j])
            cnt += 1
    return d / cnt


def cov_heterogeneity(covs):
    """自我认知矩阵异质性: 角色间 Σ 的平均距离"""
    d = 0.0
    cnt = 0
    for i in range(len(covs)):
        for j in range(i + 1, len(covs)):
            d += np.linalg.norm(covs[i] - covs[j])
            cnt += 1
    return d / cnt


def main():
    print("=" * 70)
    print("exp60c: 自我认知协方差——每角色独立自我环矩阵")
    print("=" * 70)
    seeds = [7, 11, 23, 42, 99]
    modes = ['baseline', 'global', 'self']
    stats = {m: {'gain': [], 'div': [], 'contra': [], 'hetero': []} for m in modes}

    for s in seeds:
        rng.seed(s)
        p0 = init_params()
        opinions = rng.uniform(-1, 1, N_CHARS)
        rel = np.zeros((N_CHARS, N_CHARS))
        topic = rng.randint(N_TOPICS)
        ts = 0.0
        fit0 = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(N_TOPICS)
            _, inc, ts, opinions, rel = simulate_round(p0, topic, ts, opinions, rel)
            fit0 += inc
        for m in modes:
            res = run_experiment(m, s)
            stats[m]['gain'].append((res['fitness'].mean() / fit0.mean() - 1) * 100)
            stats[m]['div'].append(diversity(res['params']))
            stats[m]['contra'].append(contradiction_ratio(res['params']))
            if m == 'self':
                stats[m]['hetero'].append(cov_heterogeneity(res['covs']))

    print(f"\n{'模式':<10}{'适应度增益':>12}{'差异度':>8}{'矛盾体':>8}{'Σ异质性':>10}")
    print("-" * 50)
    for m in modes:
        hetero = f"{np.mean(stats[m]['hetero']):.3f}" if stats[m]['hetero'] else "-"
        print(f"{m:<10}"
              f"{np.mean(stats[m]['gain']):>+11.1f}%"
              f"{np.mean(stats[m]['div']):>8.3f}"
              f"{np.mean(stats[m]['contra']):>8.1%}"
              f"{hetero:>10}")

    print("\n各 seed 明细(适应度增益%):")
    print(f"{'seed':<6}{'baseline':>10}{'global':>10}{'self':>10}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}" + "".join(f"{stats[m]['gain'][k]:>+9.1f}%" for m in modes))

    np.savez(os.path.join(ARCHIVE, 'exp60c_self_cov.npz'),
             seeds=np.array(seeds),
             gain={m: np.array(stats[m]['gain']) for m in modes},
             div={m: np.array(stats[m]['div']) for m in modes},
             contra={m: np.array(stats[m]['contra']) for m in modes},
             hetero=np.array(stats['self']['hetero']))
    print(f"\n存档已保存 evolution_chat/exp60c_self_cov.npz")


if __name__ == '__main__':
    main()
