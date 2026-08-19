#!/usr/bin/env python3
"""exp60b: 协方差矩阵漂移——参数相关性感知的角色漂移（lmq"矩阵化空间"直觉验证）

背景: exp51-60 的漂移用独立高斯扰动（rise_force = sigma_i * randn）——参数间互不相关。
但真实角色参数有结构: polarity(反从众)高的人 empathy(共情)通常不高、
explore(探索)高的人 decay(热情衰减)也不低——独立扰动无视相关性 = 可能把角色漂成"矛盾体"
（反从众 + 高共情——现实中不存在的性格组合）。

设计（对照 exp60 框架，只改漂移算子）:
1. 独立高斯（现有）: drift ~ N(0, sigma^2 * I)        ——基线
2. 固定协方差矩阵: drift ~ N(0, sigma^2 * Sigma_fixed) ——人为定义合理的性格相关性
3. 学习协方差:     Sigma 从角色群的参数变化历史在线估计
   —— 角色在漂移中"学到"自己参数间的合理相关性，矩阵随演化

对照组:
  indep       独立高斯（exp60 drift_only 复现）——基线
  cov_fixed    固定协方差（定义: polarity↔empathy 负相关, explore↔decay 正相关等）
  cov_learned  协方差从历史估计（EMA 更新）

指标: 适应度 / 差异度 / 参数离初始 / **性格自洽度**（矛盾体比例:
  |polarity| > 0.5 且 empathy > 0.7 的角色比例——反从众高共情的矛盾组合）
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
REGRESS_RATE = 0.03   # exp60 落地建议 3-4%，用 3%

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]
N_PARAM = len(PARAM_NAMES)

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']


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


def fixed_covariance():
    """人为定义"合理的性格相关性"——对角 1 + 关键相关项。
    polarity↔empathy 负相关（反从众者共情低）、explore↔decay 正相关、
    social↔empathy 正相关、persist↔explore 负相关（执着者不好奇）"""
    S = np.eye(N_PARAM)
    idx = {n: i for i, n in enumerate(PARAM_NAMES)}
    S[idx['polarity'], idx['empathy']] = -0.5
    S[idx['empathy'], idx['polarity']] = -0.5
    S[idx['explore'], idx['decay']] = 0.4
    S[idx['decay'], idx['explore']] = 0.4
    S[idx['social'], idx['empathy']] = 0.4
    S[idx['empathy'], idx['social']] = 0.4
    S[idx['persist'], idx['explore']] = -0.3
    S[idx['explore'], idx['persist']] = -0.3
    return S


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
    """性格自洽度指标: 矛盾体比例——反从众(|polarity|>0.5)且高共情(empathy>0.7) 或
    高探索(explore>0.4)且高坚持(persist>0.8)（探索者不该太执着）"""
    n = len(params)
    cnt = 0
    for i in range(n):
        c1 = abs(params[i, 1]) > 0.5 and params[i, 7] > 0.7
        c2 = params[i, 0] > 0.4 and params[i, 6] > 0.8
        if c1 or c2:
            cnt += 1
    return cnt / n


def drift_step_cov(params, initial_params, fitness, t, cov_mode, learned_cov, drift_history):
    """漂移步——协方差矩阵版本
    cov_mode: 'indep'(独立高斯基线) / 'cov_fixed'(固定协方差) / 'cov_learned'(学习协方差)"""
    sigma = DRIFT_SIGMA0 * (TEMP_DECAY ** (t // DRIFT_EVERY))
    fit_max = float(fitness.max())
    fit_min = float(fitness.min())
    fit_span = max(fit_max - fit_min, 1e-9)

    if cov_mode == 'indep':
        cov = np.eye(N_PARAM)
    elif cov_mode == 'cov_fixed':
        cov = fixed_covariance()
    else:  # cov_learned
        cov = learned_cov

    # 保证协方差矩阵正定（PSD 投影 + 对角加小量）
    cov = (cov + cov.T) / 2.0
    eigvals, eigvecs = np.linalg.eigh(cov)
    eigvals = np.maximum(eigvals, 1e-4)
    cov_pd = eigvecs @ np.diag(eigvals) @ eigvecs.T

    for i in range(N_CHARS):
        rel_fit = (fitness[i] - fit_min) / fit_span
        sigma_i = sigma * (1.6 - rel_fit)
        # 协方差采样: 多元高斯 N(0, sigma_i^2 * cov)
        noise = sigma_i * (eigvecs @ (np.sqrt(eigvals) * rng.randn(N_PARAM)))
        regress_force = (initial_params[i] - params[i]) * REGRESS_RATE
        params[i] = clamp_params(params[i] + noise + regress_force)
        # 学习协方差: 记录漂移增量到历史
        if cov_mode == 'cov_learned':
            drift_history.append(params[i] - initial_params[i])

    # 学习协方差更新（EMA——用所有角色的漂移增量估计相关性）
    if cov_mode == 'cov_learned' and len(drift_history) > N_PARAM * 5:
        recent = np.array(drift_history[-N_PARAM * 10:])
        learned_cov[:] = 0.7 * learned_cov + 0.3 * np.cov(recent.T)
    return params, learned_cov


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
    """mode: baseline / indep / cov_fixed / cov_learned"""
    rng.seed(seed)
    params = init_params()
    initial_params = params.copy()
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    learned_cov = np.eye(N_PARAM)
    drift_history = []

    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships = simulate_round(
            params, topic, topic_state, opinions, relationships)
        fitness += inc
        if (t + 1) % DRIFT_EVERY == 0:
            if mode != 'baseline':
                params, learned_cov = drift_step_cov(
                    params, initial_params, fitness, t, mode, learned_cov, drift_history)
                params = select_and_breed(params, fitness)

    return {'params': params, 'fitness': fitness, 'relationships': relationships}


def diversity(params):
    d = 0.0
    cnt = 0
    for i in range(len(params)):
        for j in range(i + 1, len(params)):
            d += np.linalg.norm(params[i] - params[j])
            cnt += 1
    return d / cnt


def main():
    print("=" * 70)
    print("exp60b: 协方差矩阵漂移——参数相关性感知的角色漂移")
    print("=" * 70)
    seeds = [7, 11, 23, 42, 99]
    modes = ['baseline', 'indep', 'cov_fixed', 'cov_learned']
    stats = {m: {'gain': [], 'div': [], 'contra': []} for m in modes}

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

    print(f"\n{'模式':<12}{'适应度增益':>12}{'差异度':>8}{'矛盾体比例':>12}")
    print("-" * 46)
    for m in modes:
        print(f"{m:<12}"
              f"{np.mean(stats[m]['gain']):>+11.1f}%"
              f"{np.mean(stats[m]['div']):>8.3f}"
              f"{np.mean(stats[m]['contra']):>12.1%}")

    print("\n各 seed 明细(适应度增益%):")
    print(f"{'seed':<6}{'baseline':>10}{'indep':>10}{'cov_fixed':>12}{'cov_learned':>14}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}" + "".join(f"{stats[m]['gain'][k]:>+9.1f}%" for m in modes))

    print("\n各 seed 明细(矛盾体比例):")
    print(f"{'seed':<6}{'indep':>10}{'cov_fixed':>12}{'cov_learned':>14}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}"
              f"{stats['indep']['contra'][k]:>10.1%}"
              f"{stats['cov_fixed']['contra'][k]:>12.1%}"
              f"{stats['cov_learned']['contra'][k]:>14.1%}")

    np.savez(os.path.join(ARCHIVE, 'exp60b_cov_drift.npz'),
             seeds=np.array(seeds),
             gain={m: np.array(stats[m]['gain']) for m in modes},
             div={m: np.array(stats[m]['div']) for m in modes},
             contra={m: np.array(stats[m]['contra']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp60b_cov_drift.npz")


if __name__ == '__main__':
    main()
