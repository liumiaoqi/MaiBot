#!/usr/bin/env python3
"""exp56: 叙事推力注入——场景事件驱动角色生长(Concordia maybe_inject_narrative_push 验证)

来源: CA 调研(zh_remaining_surveys_0818)——Concordia 3 项可映射 MaiBot 之一:
  "叙事推力注入: 重复检测 → 5 候选推力事件(不假设用户行动) → 组合"

核心思想: 角色生长不能全靠自己主动(desire 驱动),还要有"外因"——
场景里发生事件(客厅停电/朋友生日/新邻居搬来),事件把角色拉进互动。
类比真实生活: 不是每天都有话说,是"发生了事"才有话可说。

设计(exp51 群聊框架扩展):
1. 事件发生器: 每 N 轮以概率 p 产生一个事件(话题+情绪极性+相关角色)
   - 事件类型: 日常(低情绪)/惊喜(正)/麻烦(负)/冲突(角色间)
2. 事件驱动发言: 事件相关角色(高 affinity)被"推"着发言(不依赖 desire)
   —— vs 无事件基线(exp51 式纯 desire 驱动)
3. 对照组:
   none     无事件(纯自发)——基线
   event    有事件(事件+自发混合)
   event_x2 高事件频率(事件为主)
4. 指标: 群聊活力(发言覆盖角色数/话题多样性)/适应度/沉默率(无人发言轮数)

假设: 事件推力让群聊更有活力(少沉默、多角色参与),角色生长有了外因土壤
"""

import os
import numpy as np

rng = np.random.RandomState(20260819)
ARCHIVE = r'E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune\\snn_behavior\\worm_data\\evolution_chat'
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
N_TOPICS = 10
EVENT_EVERY = 15        # 每 15 轮检查一次事件
EVENT_PROB = 0.6        # 检查时产生事件的概率
EVENT_PROB_X2 = 1.0     # 高频率版

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']

EVENT_NAMES = {
    'daily': '日常琐事',
    'joy': '惊喜事件',
    'trouble': '麻烦事件',
    'conflict': '角色冲突',
}


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
    """产生一个事件: (类型, 话题, 情绪极性, 相关角色集)"""
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
    # 相关角色: 随机 3-5 个(事件落在谁身上)
    n_rel = rng.randint(3, 6)
    related = rng.choice(N_CHARS, n_rel, replace=False)
    return {'type': etype, 'topic': etopic, 'mood': mood, 'related': related}


def simulate_round(p, topic, topic_state, opinions, relationships, event=None, event_rounds_left=0):
    n = len(p)
    aff = topic_affinity(p, topic)
    # 事件推力: 相关角色发言概率大幅提升(即使 desire 低)
    speak_prob = 0.15 + 0.6 * p[:, 3] * aff
    if event is not None and event_rounds_left > 0:
        for i in event['related']:
            # 事件相关角色被"推"着发言: 基础概率 +0.5
            speak_prob[i] = max(speak_prob[i], 0.5 + 0.2 * abs(event['mood']))
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    for i in np.where(speakers)[0]:
        own = opinions[i]
        # 事件影响发言方向: 情绪事件让角色观点偏向事件极性
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
    silent_rounds = 0
    event_count = 0
    topics_used = set()
    speakers_per_round = []
    for t in range(N_ROUNDS):
        # 事件生命周期
        if event_rounds_left <= 0:
            event = None
            if mode == 'event' and t % EVENT_EVERY == 0 and rng.random() < EVENT_PROB:
                event = spawn_event(t, topic_state)
                event_count += 1
                event_rounds_left = rng.randint(3, 6)
            elif mode == 'event_x2' and t % EVENT_EVERY == 0:
                event = spawn_event(t, topic_state)
                event_count += 1
                event_rounds_left = rng.randint(3, 6)
        if t % 50 == 0 and event is None:
            topic = rng.randint(N_TOPICS)
        actions, inc, topic_state, opinions, relationships = simulate_round(
            p, topic, topic_state, opinions, relationships, event, event_rounds_left)
        fitness += inc
        topics_used.add(topic)
        if not actions:
            silent_rounds += 1
        else:
            speakers_per_round.append(len(actions))
        if event_rounds_left > 0:
            event_rounds_left -= 1
    return {'fitness': fitness, 'relationships': relationships,
            'silent_rounds': silent_rounds, 'topics': len(topics_used),
            'events': event_count,
            'avg_speakers': float(np.mean(speakers_per_round)) if speakers_per_round else 0.0}


def main():
    print("=" * 66)
    print("exp56: 叙事推力注入——场景事件驱动角色生长(Concordia 验证)")
    print("=" * 66)
    seeds = [7, 11, 23, 42, 99]
    modes = ['none', 'event', 'event_x2']
    stats = {m: {'gain': [], 'silent': [], 'topics': [], 'events': [], 'speakers': []} for m in modes}
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
            _, inc, ts, opinions, rel = simulate_round(p, topic, ts, opinions, rel)
            fit0 += inc
        for m in modes:
            res = run_experiment(m, s)
            stats[m]['gain'].append((res['fitness'].mean() / fit0.mean() - 1) * 100)
            stats[m]['silent'].append(res['silent_rounds'])
            stats[m]['topics'].append(res['topics'])
            stats[m]['events'].append(res['events'])
            stats[m]['speakers'].append(res['avg_speakers'])

    print(f"\n{'模式':<10}{'适应度增益':>12}{'沉默轮数':>10}{'话题数':>8}{'事件数':>8}{'平均发言者':>10}")
    print("-" * 60)
    for m in modes:
        print(f"{m:<10}"
              f"{np.mean(stats[m]['gain']):>+11.1f}%"
              f"{np.mean(stats[m]['silent']):>10.1f}"
              f"{np.mean(stats[m]['topics']):>8.1f}"
              f"{np.mean(stats[m]['events']):>8.1f}"
              f"{np.mean(stats[m]['speakers']):>10.2f}")

    print("\n各 seed 明细(增益%/沉默轮):")
    print(f"{'seed':<6}{'none':>18}{'event':>18}{'event_x2':>18}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}"
              f"{stats['none']['gain'][k]:>+7.1f}%/{stats['none']['silent'][k]:>4.0f}"
              f"{stats['event']['gain'][k]:>+7.1f}%/{stats['event']['silent'][k]:>4.0f}"
              f"{stats['event_x2']['gain'][k]:>+8.1f}%/{stats['event_x2']['silent'][k]:>4.0f}")

    np.savez(os.path.join(ARCHIVE, 'exp56_narrative_push.npz'),
             seeds=np.array(seeds),
             gain={m: np.array(stats[m]['gain']) for m in modes},
             silent={m: np.array(stats[m]['silent']) for m in modes},
             topics={m: np.array(stats[m]['topics']) for m in modes},
             events={m: np.array(stats[m]['events']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp56_narrative_push.npz")


if __name__ == '__main__':
    main()
