#!/usr/bin/env python3
"""exp58: 事件因果化——Event → 因果句 → 广播相关者(Concordia 验证 3/3)

来源: CA 调研项 1——GM 裁决链: putative event 入库 → EventResolution thought 链
(maybe_inject_narrative_push → account_for_agency_of_others → result_to_who_what_where)
→ 广播(LLM 选 observers/player_filter/位置过滤)
MaiBot 映射: 消息加 stage 字段(RAW→裁决链→ADJUDICATED) + result_to_who_what_where 等价插件(重写为因果句)

设计(exp51 群聊框架扩展):
1. 事件发生时(复用 exp56 事件发生器):
   - RAW 阶段: 事件原始发生(只影响相关角色)
   - 裁决链: ①注入推力(事件成为话题) ②代理他人(相关角色各自表态)
     ③who_what_where: 重写为"因果句"(谁→做了什么→影响谁)
   - 广播: 因果句传播给 observers(未直接相关的角色也知晓——消息传播)
2. 对照组:
   none      无事件(纯自发)——基线
   event_raw 事件仅影响相关角色(不广播, 因果句缺失)
   event_adj  事件+因果句+广播(完整裁决链)
3. 指标: 适应度/知识扩散(知道事件的角色数)/群聊活力

假设: 因果句广播让"间接相关"角色也参与进来——知识扩散扩大社交圈,适应度更高
"""

import os
import numpy as np

rng = np.random.RandomState(20260819)
ARCHIVE = r'E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune\\snn_behavior\\worm_data\\evolution_chat'
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
N_TOPICS = 10
EVENT_EVERY = 15

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


def spawn_event():
    etype = rng.choice(['daily', 'joy', 'trouble', 'conflict'], p=[0.3, 0.25, 0.3, 0.15])
    etopic = rng.randint(N_TOPICS)
    mood = {'joy': 1.0, 'trouble': -1.0, 'conflict': -0.5}.get(etype, rng.uniform(-0.3, 0.3))
    n_rel = rng.randint(3, 6)
    related = rng.choice(N_CHARS, n_rel, replace=False)
    return {'type': etype, 'topic': etopic, 'mood': mood, 'related': related}


def adjudicate(event, related_set):
    """裁决链: 因果句 + 广播对象
    who_what_where: 谁(相关者)→做了什么(事件)→影响谁(observers=与相关者有关系的角色)"""
    causal_sentence = f"{NAMES[event['related'][0]]}引发{event['type']},影响{len(event['related'])}人"
    # observers: 与相关角色"有关系"(关系矩阵非零)的角色 = 广播对象
    observers = set()
    for r_ in event['related']:
        for j in range(N_CHARS):
            if j != r_ and related_set[r_, j] != 0:
                observers.add(j)
    return causal_sentence, observers


def simulate_round(p, topic, topic_state, opinions, relationships, event, mode, event_rounds_left):
    n = len(p)
    aff = topic_affinity(p, topic)
    speak_prob = 0.15 + 0.6 * p[:, 3] * aff
    if event is not None and event_rounds_left > 0:
        # 事件推力: 相关角色被推着发言
        for i in event['related']:
            speak_prob[i] = max(speak_prob[i], 0.5 + 0.2 * abs(event['mood']))
        # 广播模式: observers 也收到推力(减半)
        if mode == 'event_adj' and 'observers' in event:
            for i in event['observers']:
                speak_prob[i] = max(speak_prob[i], 0.3)
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    for i in np.where(speakers)[0]:
        own = opinions[i]
        lean = own
        if event is not None and event_rounds_left > 0 and i in event['related']:
            lean = np.clip(lean + event['mood'] * 0.3 * (1 - abs(p[i, 1])), -1, 1)
        if p[i, 1] < 0:
            lean = own * (1 - abs(p[i, 1])) - np.sign(topic_state) * abs(p[i, 1])
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
    p = init_params()
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    event = None
    event_rounds_left = 0
    knowledge = np.zeros(N_CHARS)  # 每个角色"知道事件"的累积
    for t in range(N_ROUNDS):
        if event_rounds_left <= 0:
            event = None
            if mode != 'none' and t % EVENT_EVERY == 0 and rng.random() < 0.7:
                event = spawn_event()
                event_rounds_left = rng.randint(3, 6)
                if mode == 'event_adj':
                    # 完整裁决链: 因果句 + 广播
                    causal, observers = adjudicate(event, relationships)
                    event['observers'] = observers
                    event['causal'] = causal
                    # 知识扩散: 相关者+观察者都知道
                    knowledge[event['related']] += 1
                    for o in observers:
                        knowledge[o] += 0.5
                else:
                    # RAW 无广播: 只有相关者知道
                    knowledge[event['related']] += 1
        if t % 50 == 0 and event is None:
            topic = rng.randint(N_TOPICS)
        actions, inc, topic_state, opinions, relationships = simulate_round(
            p, topic, topic_state, opinions, relationships, event, mode, event_rounds_left)
        fitness += inc
        if event_rounds_left > 0:
            event_rounds_left -= 1
    return {'fitness': fitness, 'knowledge': knowledge}


def main():
    print("=" * 66)
    print("exp58: 事件因果化——Event → 因果句 → 广播(Concordia 验证 3/3)")
    print("=" * 66)
    seeds = [7, 11, 23, 42, 99]
    modes = ['none', 'event_raw', 'event_adj']
    stats = {m: {'gain': [], 'knowledge': []} for m in modes}
    for s in seeds:
        rng.seed(s)
        p = init_params()
        opinions = rng.uniform(-1, 1, N_CHARS)
        rel = np.zeros((N_CHARS, N_CHARS))
        topic = rng.randint(N_TOPICS)
        ts = 0.0
        fit0 = np.zeros(N_CHARS)
        for t in range(N_ROUNDS):
            if t % 50 == 0:
                topic = rng.randint(N_TOPICS)
            _, inc, ts, opinions, rel = simulate_round(p, topic, ts, opinions, rel, None, 'none', 0)
            fit0 += inc
        for m in modes:
            res = run_experiment(m, s)
            stats[m]['gain'].append((res['fitness'].mean() / fit0.mean() - 1) * 100)
            stats[m]['knowledge'].append(res['knowledge'].mean())

    print(f"\n{'模式':<12}{'适应度增益':>12}{'平均知识扩散':>14}")
    print("-" * 40)
    for m in modes:
        print(f"{m:<12}{np.mean(stats[m]['gain']):>+11.1f}%{np.mean(stats[m]['knowledge']):>14.2f}")

    print("\n各 seed 明细(增益%):")
    print(f"{'seed':<6}{'none':>12}{'event_raw':>14}{'event_adj':>14}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}"
              f"{stats['none']['gain'][k]:>+11.1f}%"
              f"{stats['event_raw']['gain'][k]:>+13.1f}%"
              f"{stats['event_adj']['gain'][k]:>+13.1f}%")

    np.savez(os.path.join(ARCHIVE, 'exp58_event_causal.npz'),
             seeds=np.array(seeds),
             gain={m: np.array(stats[m]['gain']) for m in modes},
             knowledge={m: np.array(stats[m]['knowledge']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp58_event_causal.npz")


if __name__ == '__main__':
    main()
