#!/usr/bin/env python3
"""exp59: pymdp 精度调制——动态 gamma(注意力×置信度调制回复确定性)

来源: CA 调研项 4——pymdp 中 gamma(策略精度)/alpha(采样精度)静态,但 MCTS 中
β(o) 折扣基于观测置信度实时计算。动态 gamma 设计:
  gamma(t) = gamma_base * (1 + κ_attn * attention(t)) * (1 + κ_conf * confidence(t))
MaiBot 映射: gamma → 回复决策确定性温度(高 gamma=更确定=发言更果断)

设计(exp51 群聊框架——发言确定性调制):
1. 每个角色每轮的 gamma:
   attention(t) = 当前话题与角色偏好的匹配度(话题亲和)——注意力高=更确定
   confidence(t) = 角色近期发言被回应率(EMA)——被回应多=自信高
   gamma(t) = gamma_base * (1 + κ_attn*attn) * (1 + κ_conf*conf)
2. gamma 调制发言: 高 gamma → 发言观点更贴近"自己真实想法"(少犹豫/少漂移)
   低 gamma → 发言更多探索(带噪声偏移,像没把握时的试探)
3. 对照:
   none      静态 gamma(1.0, exp51 原样)——基线
   dynamic   动态 gamma(κ_attn=0.5, κ_conf=0.5)
   dyn_conf  仅置信度调制(κ_attn=0)——分离注意力/置信度贡献
4. 指标: 适应度/发言果断度(发言观点与内心观点距离)/置信度演化

假设: 注意力高+自信高时果断发言(减少无效试探),低自信时探索——比恒定确定性更好
"""

import os
import numpy as np

rng = np.random.RandomState(20260819)
ARCHIVE = r'E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune\\snn_behavior\\worm_data\\evolution_chat'
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
N_TOPICS = 10
GAMMA_BASE = 1.0
KAPPA_ATTN = 0.5
KAPPA_CONF = 0.5
CONF_EMA = 0.9       # 置信度 EMA 衰减

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']


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


def compute_gamma(p, i, topic, confidence, mode):
    """动态 gamma: 注意力(话题亲和) × 置信度(近期被回应率)"""
    if mode == 'none':
        return GAMMA_BASE
    attn = topic_affinity(p[i:i+1], topic)[0]
    if mode == 'dynamic':
        return GAMMA_BASE * (1 + KAPPA_ATTN * attn) * (1 + KAPPA_CONF * confidence[i])
    elif mode == 'dyn_conf':
        return GAMMA_BASE * (1 + KAPPA_CONF * confidence[i])
    return GAMMA_BASE


def simulate_round(p, topic, topic_state, opinions, relationships, confidence, mode):
    n = len(p)
    aff = topic_affinity(p, topic)
    speak_prob = 0.15 + 0.6 * p[:, 3] * aff
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    for i in np.where(speakers)[0]:
        own = opinions[i]
        gamma = compute_gamma(p, i, topic, confidence, mode)
        # gamma 调制发言确定性: 高 gamma → 贴近内心(少噪声); 低 gamma → 探索(多噪声)
        if p[i, 1] < 0:
            lean = own * (1 - abs(p[i, 1])) - np.sign(topic_state) * abs(p[i, 1])
        else:
            lean = own
        noise_scale = 0.3 / max(gamma, 0.3)   # 低 gamma → 噪声大(试探), 高 gamma → 噪声小(果断)
        lean = np.clip(lean + rng.normal(0, noise_scale * 0.5), -1, 1)
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
    # 置信度更新: 发言者被回应(观点被主流采纳)→ 自信升; 没人理 → 自信降
    got_response = np.zeros(n)
    for a in range(len(actions)):
        for b in range(a + 1, len(actions)):
            i, k1, v1 = actions[a]
            j, k2, v2 = actions[b]
            if k1 == k2 and k1 != 'new_topic' and abs(v1 - v2) < 0.5:
                relationships[i, j] += 1
                relationships[j, i] += 1
                got_response[i] += 1
                got_response[j] += 1
    for i in range(n):
        target = 0.5 if got_response[i] > 0 else 0.3
        confidence[i] = CONF_EMA * confidence[i] + (1 - CONF_EMA) * target
    fitness_inc = np.zeros(n)
    for i, k, v in actions:
        if k == 'new_topic':
            fitness_inc[i] += 0.5
        else:
            fitness_inc[i] += 0.3 + 0.7 * abs(v - topic_state)
    return actions, fitness_inc, topic_state, opinions, relationships, confidence


def run_experiment(mode, seed):
    rng.seed(seed)
    p = init_params()
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    confidence = np.full(N_CHARS, 0.4)  # 初始中等自信
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships, confidence = simulate_round(
            p, topic, topic_state, opinions, relationships, confidence, mode)
        fitness += inc
    return {'fitness': fitness, 'confidence': confidence}


def main():
    print("=" * 66)
    print("exp59: pymdp 精度调制——动态 gamma(注意力×置信度)")
    print("=" * 66)
    seeds = [7, 11, 23, 42, 99]
    modes = ['none', 'dynamic', 'dyn_conf']
    stats = {m: {'gain': [], 'conf': []} for m in modes}
    for s in seeds:
        rng.seed(s)
        p = init_params()
        opinions = rng.uniform(-1, 1, N_CHARS)
        rel = np.zeros((N_CHARS, N_CHARS))
        conf = np.full(N_CHARS, 0.4)
        topic = rng.randint(N_TOPICS)
        ts = 0.0
        fit0 = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(N_TOPICS)
            _, inc, ts, opinions, rel, conf = simulate_round(p, topic, ts, opinions, rel, conf, 'none')
            fit0 += inc
        for m in modes:
            res = run_experiment(m, s)
            stats[m]['gain'].append((res['fitness'].mean() / fit0.mean() - 1) * 100)
            stats[m]['conf'].append(res['confidence'].mean())

    print(f"\n{'模式':<10}{'适应度增益':>12}{'终态置信度':>12}")
    print("-" * 36)
    for m in modes:
        print(f"{m:<10}{np.mean(stats[m]['gain']):>+11.1f}%{np.mean(stats[m]['conf']):>12.3f}")

    print("\n各 seed 明细(增益%):")
    print(f"{'seed':<6}{'none':>12}{'dynamic':>12}{'dyn_conf':>12}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}" + "".join(f"{stats[m]['gain'][k]:>+11.1f}%" for m in modes))

    np.savez(os.path.join(ARCHIVE, 'exp59_precision_mod.npz'),
             seeds=np.array(seeds),
             gain={m: np.array(stats[m]['gain']) for m in modes},
             conf={m: np.array(stats[m]['conf']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp59_precision_mod.npz")


if __name__ == '__main__':
    main()
