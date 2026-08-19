#!/usr/bin/env python3
"""exp57: 固定反思节拍——行动前 5 个固定感知问题(Concordia QuestionOfRecentMemories 验证)

来源: CA 调研项 2——Concordia PRE_ACT 并行反思,5 个固定感知问题:
  ①自我认知(我是谁/立场) ②情境(现在什么情况) ③行为倾向(我倾向怎么做)
  ④可用选项(有哪些做法) ⑤最优选项(哪个最好)——add_to_memory 布尔控制选择性写回
MaiBot 映射: think() 前插入反思节拍,并行 3 LLM,自我认知低频写回(每 10 轮),情境不写回

设计(exp51 群聊框架扩展——反思价值=减少盲目发言,提高发言与情境匹配):
1. 每个角色发言前"反思"5 问(用自身参数+全局可见信息回答):
   ① 自我认知: 自己的观点立场(opinions[i])——低频更新(每 50 轮,对齐"自我认知低频写回")
   ② 情境: 当前话题 topic + 主流观点 topic_state 的估计(带噪声——情境感知不完美)
   ③ 行为倾向: 按自身参数计算基线发言方向(同 exp51)
   ④ 可用选项: 生成 3 个候选发言观点(自己的观点/反从众观点/情境偏向观点)
   ⑤ 最优选项: 选与"估计情境"最匹配的(用估计的 topic_state 算独特性+一致性收益)
2. 对照: none(直接按参数发言,exp51 原样)/ reflect(5 问后发言)/ reflect_low(低频反思: 每 5 轮反思一次,其余直接)
3. 指标: 适应度/发言与情境匹配度(发言观点 vs 实际主流观点的距离)/预测情境准确度

假设: 反思让角色"先想清楚再说话"——发言更贴合情境,适应度上升
"""

import os
import numpy as np

rng = np.random.RandomState(20260819)
ARCHIVE = r'E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune\\snn_behavior\\worm_data\\evolution_chat'
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
N_TOPICS = 10
REFLECT_EVERY = 5      # reflect_low: 每 5 轮反思一次
SELF_EVERY = 50        # 自我认知更新周期(低频写回)

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


def reflect_5q(p, i, topic, topic_state, opinions, self_knowledge):
    """5 问反思——返回 (发言观点, 情境估计, 匹配度)
    ① 自我认知: self_knowledge[i](低频更新的立场, 比实时观点更"稳")
    ② 情境: 估计主流观点 = topic_state + 感知噪声(感知不完美)
    ③ 行为倾向: 按参数基线(同 exp51 lean 计算)
    ④ 选项: 3 候选 = [自己观点, 反从众观点, 情境偏向观点]
    ⑤ 最优: 与估计情境匹配 + 独特性权衡
    """
    own = opinions[i]
    # ① 自我认知(用低频更新的稳定立场)
    base_stance = self_knowledge[i]
    # ② 情境估计(带噪声——不能完美感知)
    perceived_state = np.clip(topic_state + rng.normal(0, 0.3), -1, 1)
    # ③ 行为倾向(exp51 基线 lean)
    if p[i, 1] < 0:
        lean = own * (1 - abs(p[i, 1])) - np.sign(perceived_state) * abs(p[i, 1])
    else:
        lean = own
    # ④ 选项: 3 候选
    options = [lean, base_stance, perceived_state * p[i, 7]]
    # ⑤ 最优: 与估计情境的"匹配收益" + 独特性收益(极性调制)
    best_opt = options[0]
    best_score = -1e9
    for opt in options:
        match = 1.0 - abs(opt - perceived_state)      # 与情境匹配
        unique = abs(opt - perceived_state)            # 独特性
        # 从众者重匹配, 反从众者重独特
        score = match * (1 - abs(p[i, 1])) + unique * abs(p[i, 1]) * 2.0
        if score > best_score:
            best_score = score
            best_opt = opt
    return best_opt, perceived_state, 1.0 - abs(best_opt - topic_state)


def simulate_round(p, topic, topic_state, opinions, relationships, self_knowledge, mode, t):
    n = len(p)
    aff = topic_affinity(p, topic)
    speak_prob = 0.15 + 0.6 * p[:, 3] * aff
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    match_scores = []
    for i in np.where(speakers)[0]:
        reflect = False
        if mode == 'reflect':
            reflect = True
        elif mode == 'reflect_low':
            reflect = (t % REFLECT_EVERY == 0)
        if reflect:
            best_opt, perceived, match = reflect_5q(p, i, topic, topic_state, opinions, self_knowledge)
            match_scores.append(match)
            if rng.random() < p[i, 0] * 0.5:
                actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
            elif rng.random() < p[i, 7] * 0.6 and abs(best_opt - perceived) < 0.4:
                actions.append((i, 'agree', best_opt))
            else:
                actions.append((i, 'argue', best_opt))
        else:
            # 直接发言(exp51 原样)
            own = opinions[i]
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
        # 自我认知低频更新(选择性写回: 每 SELF_EVERY 轮)
        if t % SELF_EVERY == 0:
            self_knowledge[i] = opinions[i]
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
    return actions, fitness_inc, topic_state, opinions, relationships, match_scores


def run_experiment(mode, seed):
    rng.seed(seed)
    p = init_params()
    opinions = rng.uniform(-1, 1, N_CHARS)
    self_knowledge = opinions.copy()  # 自我认知初始=当前观点
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    all_matches = []
    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships, matches = simulate_round(
            p, topic, topic_state, opinions, relationships, self_knowledge, mode, t)
        fitness += inc
        all_matches.extend(matches)
    return {'fitness': fitness, 'match': float(np.mean(all_matches)) if all_matches else 0.0}


def main():
    print("=" * 66)
    print("exp57: 固定反思节拍——行动前 5 问(Concordia 验证 2/3)")
    print("=" * 66)
    seeds = [7, 11, 23, 42, 99]
    modes = ['none', 'reflect', 'reflect_low']
    stats = {m: {'gain': [], 'match': []} for m in modes}
    for s in seeds:
        rng.seed(s)
        p = init_params()
        opinions = rng.uniform(-1, 1, N_CHARS)
        sk = opinions.copy()
        rel = np.zeros((N_CHARS, N_CHARS))
        topic = rng.randint(N_TOPICS)
        ts = 0.0
        fit0 = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(N_TOPICS)
            _, inc, ts, opinions, rel, _ = simulate_round(p, topic, ts, opinions, rel, sk, 'none', t)
            fit0 += inc
        for m in modes:
            res = run_experiment(m, s)
            stats[m]['gain'].append((res['fitness'].mean() / fit0.mean() - 1) * 100)
            stats[m]['match'].append(res['match'])

    print(f"\n{'模式':<12}{'适应度增益':>12}{'发言情境匹配':>12}")
    print("-" * 38)
    for m in modes:
        print(f"{m:<12}{np.mean(stats[m]['gain']):>+11.1f}%{np.mean(stats[m]['match']):>12.3f}")

    print("\n各 seed 明细(增益%):")
    print(f"{'seed':<6}{'none':>12}{'reflect':>12}{'reflect_low':>14}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}" + "".join(f"{stats[m]['gain'][k]:>+11.1f}%" for m in modes))

    np.savez(os.path.join(ARCHIVE, 'exp57_reflection.npz'),
             seeds=np.array(seeds),
             gain={m: np.array(stats[m]['gain']) for m in modes},
             match={m: np.array(stats[m]['match']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp57_reflection.npz")


if __name__ == '__main__':
    main()
