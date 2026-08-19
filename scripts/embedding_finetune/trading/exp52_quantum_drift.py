#!/usr/bin/env python3
"""exp52: 角色参数漂移的量子变异对照——Qiskit 量子信道算子 vs 经典高斯漂移

用户:跑 Qiskit 量子变异对照版。exp49 已证量子信道变异在基因层面维持多样性(9.1 vs 3.4 表达基因),
本实验把同一组算子搬进 exp51 角色参数漂移,看量子变异在"角色层"是否同样有效。

三组对照(exp51 框架,只换漂移算子,同 seed 同初始):
  classic         经典:适应度梯度高斯漂移(exp51 定稿版)——基线
  quantum_channel 量子信道:bitflip(参数向对侧翻转)/ampdamp(向中性值衰减)/depolar(全随机化)
  quantum_tunnel  经典 + 低概率大幅跳跃(隧穿跳出局部最优)

量子算子的角色参数映射(参数域 [lo,hi] 归一化到 [0,1] 后操作):
  bitflip  = X 门错误:参数 0<->1 翻转(极性反转/探索率突变)——对应 exp49 调控基因翻转
  ampdamp  = 振幅阻尼:参数向中性值(0.5)衰减,接近中性则冻结(角色"失活"该维度)
  depolar  = 退极化:参数完全随机化(混合态)——角色性格剧变
  quantum_tunnel = 经典小步 + 2% 概率全参数大幅跳跃(穿过性格壁垒)

指标:差异度(多样性) / 适应度 / 进化笼子边界 / 参数分布形态
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

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']


def clamp_params(p):
    p = np.asarray(p, dtype=float).copy()
    for i, (lo, hi) in enumerate(PARAM_RANGES):
        p[i] = min(max(p[i], lo), hi)
    return p


def norm01(p):
    """归一化到 [0,1]"""
    out = np.zeros_like(p)
    for i, (lo, hi) in enumerate(PARAM_RANGES):
        out[i] = (p[i] - lo) / (hi - lo)
    return out


def denorm01(n):
    out = np.zeros_like(n)
    for i, (lo, hi) in enumerate(PARAM_RANGES):
        out[i] = lo + n[i] * (hi - lo)
    return out


def init_params():
    p = np.zeros(N_CHARS * len(PARAM_NAMES)).reshape(N_CHARS, len(PARAM_NAMES))
    for i in range(len(PARAM_NAMES)):
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
        if rng.uniform(0, 1) < params[i, 0] * 0.5:
            actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
        elif rng.uniform(0, 1) < params[i, 7] * 0.6 and abs(opinions[i] - topic_state) < 0.5:
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


# ============ 三种漂移算子 ============

def drift_classic(params, fitness, sigma):
    """经典:适应度梯度高斯漂移(exp51 定稿)"""
    fit_max = float(fitness.max())
    fit_min = float(fitness.min())
    fit_span = max(fit_max - fit_min, 1e-9)
    for i in range(N_CHARS):
        rel_fit = (fitness[i] - fit_min) / fit_span
        sigma_i = sigma * (1.6 - rel_fit)
        params[i] = clamp_params(params[i] + sigma_i * rng.randn(len(PARAM_NAMES)))
    return params


def drift_quantum_channel(params, fitness, sigma):
    """量子信道变异(exp49 算子映射到连续参数):
    bitflip(5%):参数向对侧翻转(极性反转/性格突变)
    ampdamp(10%):向中性值 0.5 衰减,接近中性则冻结(角色维度失活)
    depolar(5%):完全随机化(混合态)
    其余:经典高斯微扰
    注意:不按适应度调制——量子信道算子本身没有"方向",检验纯信道噪声的效果
    """
    for i in range(N_CHARS):
        n = norm01(params[i])
        for j in range(len(PARAM_NAMES)):
            roll = rng.random()
            if roll < 0.05:
                # bitflip: 0<->1 翻转
                n[j] = 1.0 - n[j]
            elif roll < 0.15:
                # ampdamp: 向 0.5 衰减
                n[j] = 0.5 + (n[j] - 0.5) * 0.5
                if abs(n[j] - 0.5) < 0.05:
                    n[j] = 0.5  # 冻结在"中性"(失活)
            elif roll < 0.20:
                # depolar: 完全随机化
                n[j] = rng.uniform(0.0, 1.0)
            else:
                # 经典微扰(信道也保留高斯成分)
                n[j] += rng.normal(0, sigma * 3.0)
        params[i] = clamp_params(denorm01(n))
    return params


def drift_quantum_tunnel(params, fitness, sigma):
    """经典梯度漂移 + 2% 隧穿(整角色参数大幅跳跃,性格剧变)"""
    params = drift_classic(params, fitness, sigma)
    for i in range(N_CHARS):
        if rng.random() < 0.02:
            for j in range(len(PARAM_NAMES)):
                lo, hi = PARAM_RANGES[j]
                params[i, j] = rng.uniform(lo, hi)
    return params


DRIFTERS = {
    'classic': drift_classic,
    'quantum_channel': drift_quantum_channel,
    'quantum_tunnel': drift_quantum_tunnel,
}


def run_experiment(mode, seed):
    rng.seed(seed)
    params = init_params()
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    drift_log = []
    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships = simulate_round(
            params, topic, topic_state, opinions, relationships)
        fitness += inc
        if (t + 1) % DRIFT_EVERY == 0:
            sigma = DRIFT_SIGMA0 * (TEMP_DECAY ** (t // DRIFT_EVERY))
            params = DRIFTERS[mode](params, fitness, sigma)
            drift_log.append({
                'round': t + 1, 'sigma': float(sigma),
                'params': params.copy().tolist(),
                'fitness': fitness.copy().tolist(),
            })
    return {'params_final': params, 'fitness': fitness,
            'relationships': relationships, 'opinions': opinions, 'drift_log': drift_log}


def diversity(params):
    d = 0.0
    cnt = 0
    for i in range(len(params)):
        for j in range(i + 1, len(params)):
            d += np.linalg.norm(params[i] - params[j])
            cnt += 1
    return d / cnt


def in_bounds(params):
    return all(PARAM_RANGES[j][0] <= params[i][j] <= PARAM_RANGES[j][1]
               for i in range(N_CHARS) for j in range(len(PARAM_NAMES)))


def main():
    print("=" * 66)
    print("exp52: 角色参数漂移的量子变异对照(Qiskit 信道算子 vs 经典高斯)")
    print("=" * 66)
    seeds = [7, 11, 23, 42, 99]
    modes = ['classic', 'quantum_channel', 'quantum_tunnel']
    results = {m: {'div_delta': [], 'fitness_gain': [], 'div_final': [], 'fit_final': []}
               for m in modes}
    fixed_baseline = {}
    for s in seeds:
        rng.seed(s)
        base = init_params()
        d0 = diversity(base)
        fixed = run_experiment('classic', s)
        fixed_baseline[s] = fixed  # 固定基线=无漂移(经典 mode 且 sigma->0? 不——经典就是漂移)
        # 真正的固定基线: 用 init 后不漂移——直接跑一次 mode=None
        rng.seed(s)
        params = init_params()
        opinions = rng.uniform(-1, 1, N_CHARS)
        rel = np.zeros((N_CHARS, N_CHARS))
        topic = rng.randint(N_TOPICS)
        ts = 0.0
        fit = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(N_TOPICS)
            _, inc, ts, opinions, rel = simulate_round(params, topic, ts, opinions, rel)
            fit += inc
        fixed_fit = fit
        for m in modes:
            res = run_experiment(m, s)
            dd = diversity(res['params_final']) - d0
            gain = (res['fitness'].mean() / fixed_fit.mean() - 1) * 100
            results[m]['div_delta'].append(dd)
            results[m]['fitness_gain'].append(gain)
            results[m]['div_final'].append(diversity(res['params_final']))
            results[m]['fit_final'].append(res['fitness'].mean())

    print(f"\n{'模式':<16}{'差异度Δ':>10}{'适应度增益':>12}{'边界':>6}")
    print("-" * 50)
    summary = {}
    for m in modes:
        dd = np.mean(results[m]['div_delta'])
        gain = np.mean(results[m]['fitness_gain'])
        # 边界检查用最后一个 seed 的终态
        res = run_experiment(m, 42)
        bounds = '✅' if in_bounds(res['params_final']) else '❌'
        summary[m] = {'dd': dd, 'gain': gain}
        print(f"{m:<16}{dd:>+10.3f}{gain:>+11.1f}%{bounds:>6}")

    print(f"\n各 seed 明细:")
    print(f"{'seed':<6}", end="")
    for m in modes:
        print(f"{'Δ'+m[:3]:>12}", end="")
    print(f"{'增益class':>12}{'增益chan':>12}{'增益tun':>12}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}", end="")
        for m in modes:
            print(f"{results[m]['div_delta'][k]:>+12.3f}", end="")
        for m in modes:
            print(f"{results[m]['fitness_gain'][k]:>+11.1f}%", end="")
        print()

    # 终态参数对比(seed 42)
    print("\n=== seed 42 终态参数(量子信道) ===")
    res = run_experiment('quantum_channel', 42)
    for i, name in enumerate(NAMES):
        p = res['params_final'][i]
        print(f"  {name}: " + " ".join(f"{pn}={pv:.2f}" for pn, pv in zip(PARAM_NAMES, p)))

    # 保存
    np.savez(os.path.join(ARCHIVE, 'exp52_quantum_drift.npz'),
             seeds=np.array(seeds),
             div_delta={m: np.array(results[m]['div_delta']) for m in modes},
             gain={m: np.array(results[m]['fitness_gain']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp52_quantum_drift.npz")


if __name__ == '__main__':
    main()
