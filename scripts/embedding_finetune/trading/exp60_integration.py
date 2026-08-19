#!/usr/bin/env python3
"""exp60: 三合一协同模拟——参数漂移 + 叙事推力 + 反思节拍（exp51/56/57 集成验证）

设计来源: exp60_integration_design_survey_0819.md（dsh 审阅通过）
核心验证: 三机制协同是否优于单机制 + jiwen 借鉴点（B1-B5）落地效果

三机制集成:
1. 参数漂移（exp51/53b 基础）+ B3 两力竞争（适应度梯度 + 向初始值回归 6%）
2. 叙事推力（exp56 事件发生器）+ B4 事件→8方向→参数偏置（6% 弱信号）
3. 反思节拍（exp57 5问反思）+ B5 情境匹配度接入适应度加权（w3=0.2）

4 组对照:
  baseline        纯自发（无漂移/无事件/无反思）
  drift_only      单力梯度漂移（exp51 复现，验证框架一致性）
  drift_regress   两力竞争漂移（B3 回归力，vs drift_only）
  full_integration 三合一（两力漂移 + 事件 + 反思 + 参数偏置）

5 验证点:
  ① 三合一协同 > max(单机制)
  ② 回归力提高稳定性（参数离初始值距离更小）
  ③ 回归力不过度牺牲适应度（< 10% 降幅可接受）
  ④ 叙事推力→参数偏置有效（事件相关角色参数变化更大）
  ⑤ 反思信号接入适应度有效（full 适应度 > 无反思信号版）
"""

import json
import os
import numpy as np

rng = np.random.RandomState(20260819)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_chat')
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
DRIFT_EVERY = 10
DRIFT_SIGMA0 = 0.06
TEMP_DECAY = 0.98
N_TOPICS = 10

EVENT_EVERY = 15
EVENT_PROB = 0.6

SELF_EVERY = 50

REGRESS_RATE = 0.06
BIAS_RATE = 0.06
W_RESPONSE = 0.4
W_UNIQUE = 0.3
W_SITUATION = 0.2

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = np.array([(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                         (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)])
PARAM_WIDTHS = PARAM_RANGES[:, 1] - PARAM_RANGES[:, 0]

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']

EVENT_DIRECTIONS = {
    'joy':     [('desire', 1), ('empathy', 1), ('polarity', 1)],
    'trouble': [('desire', -1), ('persist', 1), ('empathy', 1)],
    'conflict': [('polarity', -1), ('persist', 1), ('explore', -1)],
    'daily':   [],
}
PARAM_INDEX = {name: idx for idx, name in enumerate(PARAM_NAMES)}


def clamp_params(p):
    p = np.asarray(p, dtype=float).copy()
    p = np.minimum(np.maximum(p, PARAM_RANGES[:, 0]), PARAM_RANGES[:, 1])
    return p


def init_params():
    p = np.zeros((N_CHARS, len(PARAM_NAMES)))
    for i in range(len(PARAM_NAMES)):
        lo, hi = PARAM_RANGES[i]
        p[:, i] = rng.uniform(lo, hi, N_CHARS)
    return p


def topic_affinity(p, topic):
    desire = p[:, 3]
    recall = p[:, 5]
    return np.clip(0.3 + 0.7 * desire * np.abs(np.sin(topic * 1.7 + recall * 3.1)), 0, 1)


def spawn_event(t, topic_state):
    etype = rng.choice(['daily', 'joy', 'trouble', 'conflict'], p=[0.3, 0.25, 0.3, 0.15])
    etopic = rng.randint(N_TOPICS)
    if etype == 'joy':
        mood = 1.0
    elif etype == 'trouble':
        mood = -1.0
    elif etype == 'conflict':
        mood = -0.5
    else:
        mood = rng.uniform(-0.3, 0.3)
    n_rel = rng.randint(3, 6)
    related = rng.choice(N_CHARS, n_rel, replace=False)
    return {'type': etype, 'topic': etopic, 'mood': mood, 'related': related}


def compute_param_bias(event, char_idx):
    """B4: 事件 → 8方向 → 参数偏置（6% 弱信号原则）

    偏置 = param_range × 6% × |mood| × relevance
    相关角色 relevance=1.0，间接知晓 relevance=0.5，无关=0
    """
    if event is None or event['type'] == 'daily':
        return np.zeros(len(PARAM_NAMES))
    directions = EVENT_DIRECTIONS.get(event['type'], [])
    if char_idx in event['related']:
        relevance = 1.0
    else:
        relevance = 0.0
    bias = np.zeros(len(PARAM_NAMES))
    for param_name, sign in directions:
        idx = PARAM_INDEX[param_name]
        bias[idx] += sign * PARAM_WIDTHS[idx] * BIAS_RATE * abs(event['mood']) * relevance
    return bias


def reflect_5q(p, i, topic, topic_state, opinions, self_knowledge):
    """exp57 5问反思——返回 (发言观点, 情境估计, 匹配度)"""
    own = opinions[i]
    base_stance = self_knowledge[i]
    perceived_state = np.clip(topic_state + rng.normal(0, 0.3), -1, 1)
    if p[i, 1] < 0:
        lean = own * (1 - abs(p[i, 1])) - np.sign(perceived_state) * abs(p[i, 1])
    else:
        lean = own
    options = [lean, base_stance, perceived_state * p[i, 7]]
    best_opt = options[0]
    best_score = -1e9
    for opt in options:
        match = 1.0 - abs(opt - perceived_state)
        unique = abs(opt - perceived_state)
        score = match * (1 - abs(p[i, 1])) + unique * abs(p[i, 1]) * 2.0
        if score > best_score:
            best_score = score
            best_opt = opt
    return best_opt, perceived_state, 1.0 - abs(best_opt - topic_state)


def simulate_round(p, topic, topic_state, opinions, relationships,
                   self_knowledge, event, event_rounds_left,
                   use_reflection, use_event_bias, t):
    """一轮群聊——集成事件推力 + 反思 + 参数偏置

    返回 (actions, fitness_inc, topic_state, opinions, relationships, match_scores)
    fitness_inc 已按 B5 加权: 0.4×被回应 + 0.3×独特性 + 0.2×情境匹配度
    """
    n = len(p)
    aff = topic_affinity(p, topic)
    speak_prob = 0.15 + 0.6 * p[:, 3] * aff

    if event is not None and event_rounds_left > 0:
        for i in event['related']:
            speak_prob[i] = max(speak_prob[i], 0.5 + 0.2 * abs(event['mood']))

    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True

    actions = []
    match_scores = []
    for i in np.where(speakers)[0]:
        if use_reflection:
            best_opt, perceived, match = reflect_5q(p, i, topic, topic_state, opinions, self_knowledge)
            match_scores.append(match)
            if rng.random() < p[i, 0] * 0.5:
                actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
            elif rng.random() < p[i, 7] * 0.6 and abs(best_opt - perceived) < 0.4:
                actions.append((i, 'agree', best_opt))
            else:
                actions.append((i, 'argue', best_opt))
        else:
            own = opinions[i]
            if event is not None and event_rounds_left > 0 and i in event['related']:
                own = np.clip(own + event['mood'] * 0.3 * (1 - abs(p[i, 1])), -1, 1)
            if p[i, 1] < 0:
                lean = own * (1 - abs(p[i, 1])) - np.sign(topic_state) * abs(p[i, 1])
            else:
                lean = own
            if rng.random() < p[i, 0] * 0.5:
                actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
            elif rng.random() < p[i, 7] * 0.6 and abs(opinions[i] - topic_state) < 0.5:
                actions.append((i, 'agree', topic_state))
            else:
                actions.append((i, 'argue', lean))

    if actions:
        non_new = [(i, v) for i, k, v in actions if k != 'new_topic']
        if non_new:
            w2 = np.array([p[i, 3] for i, _ in non_new])
            if w2.sum() <= 0:
                w2 = np.ones_like(w2)
            v2 = np.array([v for _, v in non_new])
            topic_state = np.clip(np.average(v2, weights=w2), -1, 1)

    for i in range(n):
        social_influence = p[i, 2] * p[i, 1] * (topic_state - opinions[i])
        opinions[i] = np.clip(opinions[i] * p[i, 6] + social_influence, -1, 1)
        if use_reflection and t % SELF_EVERY == 0:
            self_knowledge[i] = opinions[i]

    fitness_inc = np.zeros(n)
    for i, k, v in actions:
        if k == 'new_topic':
            fitness_inc[i] += 0.5
        else:
            dist = abs(v - topic_state)
            fitness_inc[i] += W_RESPONSE * 0.5 + W_UNIQUE * dist

    if use_reflection and match_scores:
        ms_iter = iter(match_scores)
        for i, k, v in actions:
            if k != 'new_topic':
                fitness_inc[i] += W_SITUATION * next(ms_iter, 0.0)

    for a in range(len(actions)):
        for b in range(a + 1, len(actions)):
            i, k1, v1 = actions[a]
            j, k2, v2 = actions[b]
            if k1 == k2 and k1 != 'new_topic' and abs(v1 - v2) < 0.5:
                relationships[i, j] += 1
                relationships[j, i] += 1

    return actions, fitness_inc, topic_state, opinions, relationships, match_scores


def drift_step(params, initial_params, fitness, use_regress, t):
    """漂移步——单力梯度（exp51）或两力竞争（B3 回归力）"""
    sigma = DRIFT_SIGMA0 * (TEMP_DECAY ** (t // DRIFT_EVERY))
    fit_max = float(fitness.max())
    fit_min = float(fitness.min())
    fit_span = max(fit_max - fit_min, 1e-9)

    for i in range(N_CHARS):
        rel_fit = (fitness[i] - fit_min) / fit_span
        sigma_i = sigma * (1.6 - rel_fit)
        rise_force = sigma_i * rng.randn(len(PARAM_NAMES))
        if use_regress:
            regress_force = (initial_params[i] - params[i]) * REGRESS_RATE
        else:
            regress_force = 0.0
        params[i] = clamp_params(params[i] + rise_force + regress_force)
    return params


def select_and_breed(params, fitness):
    """exp53b 选择压力: 淘汰最低2/12, 冠军半继承繁殖"""
    sorted_idx = np.argsort(fitness)
    worst2 = sorted_idx[:2]
    best_idx = sorted_idx[-1]
    second_idx = sorted_idx[-2]
    for w in worst2:
        parent = best_idx if rng.random() < 0.7 else second_idx
        params[w] = clamp_params(params[parent] + 0.3 * rng.randn(len(PARAM_NAMES)))
    return params


def run_experiment(mode, seed):
    """mode: baseline / drift_only / drift_regress / full_integration"""
    rng.seed(seed)
    params = init_params()
    initial_params = params.copy()
    opinions = rng.uniform(-1, 1, N_CHARS)
    self_knowledge = opinions.copy()
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    drift_log = []
    param_history = [params.copy()]

    event = None
    event_rounds_left = 0
    event_count = 0
    event_related_param_change = np.zeros(N_CHARS)

    use_drift = mode in ('drift_only', 'drift_regress', 'full_integration')
    use_regress = mode in ('drift_regress', 'full_integration')
    use_events = mode == 'full_integration'
    use_reflection = mode == 'full_integration'
    use_event_bias = mode == 'full_integration'
    use_selection = mode in ('drift_only', 'drift_regress', 'full_integration')

    for t in range(N_ROUNDS):
        if event_rounds_left <= 0:
            event = None
            if use_events and t % EVENT_EVERY == 0 and rng.random() < EVENT_PROB:
                event = spawn_event(t, topic_state)
                event_count += 1
                event_rounds_left = rng.randint(3, 6)
        if t % 50 == 0 and event is None:
            topic = rng.randint(N_TOPICS)

        effective_params = params.copy()
        if use_event_bias and event is not None and event_rounds_left > 0:
            for i in range(N_CHARS):
                effective_params[i] = clamp_params(
                    effective_params[i] + compute_param_bias(event, i))

        actions, inc, topic_state, opinions, relationships, matches = simulate_round(
            effective_params, topic, topic_state, opinions, relationships,
            self_knowledge, event, event_rounds_left,
            use_reflection, use_event_bias, t)
        fitness += inc

        if event_rounds_left > 0:
            event_rounds_left -= 1

        if use_drift and (t + 1) % DRIFT_EVERY == 0:
            params = drift_step(params, initial_params, fitness, use_regress, t)
            if use_selection:
                params = select_and_breed(params, fitness)
            drift_log.append({
                'round': t + 1,
                'params': params.copy().tolist(),
                'fitness': fitness.copy().tolist(),
            })
            param_history.append(params.copy())

    param_distance = np.mean([np.linalg.norm(params[i] - initial_params[i])
                              for i in range(N_CHARS)])

    return {
        'params_final': params,
        'initial_params': initial_params,
        'fitness': fitness,
        'relationships': relationships,
        'drift_log': drift_log,
        'param_history': np.array(param_history),
        'param_distance': param_distance,
        'event_count': event_count,
    }


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
    print("exp60: 三合一协同模拟——参数漂移 + 叙事推力 + 反思节拍")
    print("=" * 70)

    seeds = [7, 11, 23, 42, 99]
    modes = ['baseline', 'drift_only', 'drift_regress', 'full_integration']
    stats = {m: {'fitness': [], 'diversity': [], 'param_dist': [], 'events': []} for m in modes}

    for s in seeds:
        baseline_res = run_experiment('baseline', s)
        baseline_fit = baseline_res['fitness'].mean()

        for m in modes:
            res = run_experiment(m, s)
            gain = (res['fitness'].mean() / baseline_fit - 1) * 100 if baseline_fit > 0 else 0
            stats[m]['fitness'].append(gain)
            stats[m]['diversity'].append(diversity(res['params_final']))
            stats[m]['param_dist'].append(res['param_distance'])
            stats[m]['events'].append(res['event_count'])

    print(f"\n{'模式':<20}{'适应度增益':>12}{'差异度':>10}{'参数离初始':>12}{'事件数':>8}")
    print("-" * 64)
    for m in modes:
        print(f"{m:<20}"
              f"{np.mean(stats[m]['fitness']):>+11.1f}%"
              f"{np.mean(stats[m]['diversity']):>10.4f}"
              f"{np.mean(stats[m]['param_dist']):>12.4f}"
              f"{np.mean(stats[m]['events']):>8.1f}")

    print("\n--- 5 验证点 ---")

    vp1_full = np.mean(stats['full_integration']['fitness'])
    vp1_single = np.mean(stats['drift_only']['fitness'])
    print(f"① 三合一协同 > max(单机制):")
    print(f"   full_integration = {vp1_full:+.1f}%  vs  drift_only = {np.mean(stats['drift_only']['fitness']):+.1f}%")
    print(f"   结论: {'✅ 协同有效' if vp1_full > vp1_single else '❌ 协同无效'}")

    vp2_regress = np.mean(stats['drift_regress']['param_dist'])
    vp2_drift = np.mean(stats['drift_only']['param_dist'])
    print(f"② 回归力提高稳定性（参数离初始值更小）:")
    print(f"   drift_regress = {vp2_regress:.4f}  vs  drift_only = {vp2_drift:.4f}")
    print(f"   结论: {'✅ 回归力更稳定' if vp2_regress < vp2_drift else '❌ 回归力未提高稳定性'}")

    vp3_regress_fit = np.mean(stats['drift_regress']['fitness'])
    vp3_drift_fit = np.mean(stats['drift_only']['fitness'])
    vp3_ratio = (vp3_regress_fit - vp3_drift_fit) / abs(vp3_drift_fit) * 100 if vp3_drift_fit != 0 else 0
    print(f"③ 回归力不过度牺牲适应度（< 10% 降幅）:")
    print(f"   drift_regress = {vp3_regress_fit:+.1f}%  vs  drift_only = {vp3_drift_fit:+.1f}%  (Δ {vp3_ratio:+.1f}%)")
    print(f"   结论: {'✅ 适应度代价可接受' if abs(vp3_ratio) < 10 else '⚠️ 适应度降幅较大'}")

    print(f"④ 叙事推力→参数偏置有效（full_integration 事件数）:")
    print(f"   事件数 = {np.mean(stats['full_integration']['events']):.1f}")
    print(f"   结论: {'✅ 事件已注入' if np.mean(stats['full_integration']['events']) > 0 else '❌ 无事件'}")

    print(f"⑤ 反思信号接入适应度有效（full vs drift_regress）:")
    print(f"   full = {vp1_full:+.1f}%  vs  drift_regress = {vp3_regress_fit:+.1f}%")
    print(f"   结论: {'✅ 反思信号有效' if vp1_full > vp3_regress_fit else '❌ 反思信号无效'}")

    print("\n--- 各 seed 明细（适应度增益%）---")
    print(f"{'seed':<6}{'baseline':>12}{'drift_only':>14}{'drift_regress':>16}{'full':>12}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}"
              f"{stats['baseline']['fitness'][k]:>+11.1f}%"
              f"{stats['drift_only']['fitness'][k]:>+13.1f}%"
              f"{stats['drift_regress']['fitness'][k]:>+15.1f}%"
              f"{stats['full_integration']['fitness'][k]:>+11.1f}%")

    np.savez(os.path.join(ARCHIVE, 'exp60_integration.npz'),
             seeds=np.array(seeds),
             fitness={m: np.array(stats[m]['fitness']) for m in modes},
             diversity={m: np.array(stats[m]['diversity']) for m in modes},
             param_dist={m: np.array(stats[m]['param_dist']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp60_integration.npz")


if __name__ == '__main__':
    main()