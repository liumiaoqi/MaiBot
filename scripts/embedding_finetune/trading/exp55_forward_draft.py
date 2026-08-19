#!/usr/bin/env python3
"""exp55: 前向 rollout 草稿评分——角色发言前先推演"我这么说对方怎么反应"

来源: CA 调研核心差距("MaiBot 零步前向,缺前向 rollout + 反应预测")→ ZH draft_scorer 候选
机制: pymdp 决策前向模型(B 转移 + A 似然 → info_gain + utility → softmax 选策略)的角色对话版

设计(对齐 exp51 群聊框架,只升级发言决策):
1. 每个角色发言前生成 K=5 条候选草稿(观点偏移量采样: 支持/反对/中立/新话题)
2. 每条草稿做"前向推演"(角色用自己知道的对方公开观点+关系,预测每个对方会怎么反应):
   - 对方会回应吗? (对方 desire × 观点距离 × 关系亲疏)
   - 回应方向? (同意/反对/无视)
   - 预测收益 = Σ(被回应 + 关系增益 + 独特性) 
3. softmax(收益/温度) 选一条 → 真实发言
4. 对照: 无前向(exp51 式直接按参数发言) vs 有前向(上述) vs 完美前向(全知 oracle)
5. 指标: 适应度(被回应+独特性) / 预测准确性(预测反应 vs 实际反应) / 群聊多样性

假设: 前向推演让角色"想好再说"——适应度上升,群聊更有结构
"""

import os
import numpy as np

rng = np.random.RandomState(20260819)
ARCHIVE = r'E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune\\snn_behavior\\worm_data\\evolution_chat'
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12
N_ROUNDS = 300
N_TOPICS = 10
K_DRAFTS = 5          # 草稿数
TEMPERATURE = 0.8     # softmax 温度
N_LOOKAHEAD = 3       # 前向推演深度(轮)

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]

NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']


def clamp_params(p):
    p = np.asarray(p, dtype=float).copy()
    for i, (lo, hi) in enumerate(PARAM_RANGES):
        p[i] = min(max(p[i], lo), hi)
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


def would_respond(p, i, j, opinion_i, opinion_j, relationship, topic):
    """角色 j 对角色 i 的发言(观点 opinion_i)会不会回应——用 j 的参数预测"""
    # 兴趣: desire × 话题亲和
    aff = topic_affinity(p[j:j+1], topic)[0]
    interest = 0.15 + 0.6 * p[j, 3] * aff
    # 观点距离: 越远越可能反驳(互动), 太近可能附和(也算回应)
    dist = abs(opinion_i - opinion_j)
    # 关系: 好友更可能回应, 敌对也可能(反驳)
    rel_bonus = 0.2 if relationship > 1 else (0.1 if relationship < -1 else 0.0)
    prob = interest * (0.5 + 0.5 * min(dist * 2, 1.0)) + rel_bonus
    return min(prob, 0.95)


def predict_response(p, i, draft_opinion, topic_state, opinions, relationships, topic, depth=1):
    """前向推演: 角色 i 发 draft_opinion, 预测一轮内其他角色的反应
    返回 (预测被回应数, 预测关系增益, 预测独特性)"""
    n_resp = 0
    rel_gain = 0.0
    unique = abs(draft_opinion - topic_state)
    for j in range(N_CHARS):
        if j == i:
            continue
        if would_respond(p, i, j, draft_opinion, opinions[j], relationships[i, j], topic) > rng.random():
            n_resp += 1
            # 回应方向: 观点距离近→同意(关系+), 远→反驳(关系+, 互动也是关系)
            if abs(draft_opinion - opinions[j]) < 0.5:
                rel_gain += 0.3
            else:
                rel_gain += 0.15
    return n_resp, rel_gain, unique


def pick_draft_forward(p, i, topic, topic_state, opinions, relationships, oracle=False):
    """前向草稿评分: K 条草稿 → 预测收益 → softmax 选一条
    oracle=True: 用真实反应预测(完美前向, 上界)"""
    drafts = []
    for k in range(K_DRAFTS):
        # 草稿观点: 围绕自己的观点采样偏移(支持/反对/中立/新话题由 explore 决定)
        if rng.random() < p[i, 0] * 0.5:
            drafts.append(('new_topic', rng.randint(N_TOPICS)))
        else:
            bias = rng.uniform(-1, 1) * (1.0 - abs(p[i, 1])) * 0.6
            draft = np.clip(opinions[i] + bias, -1, 1)
            drafts.append(('argue', draft))
    # 评分
    scores = []
    for kind, val in drafts:
        if kind == 'new_topic':
            # 新话题: 收益 = 好奇心 + 预测对方对新话题的兴趣
            gain = 0.5 + 0.5 * p[i, 9] if len(p[i]) > 9 else 0.5
            n_resp = sum(would_respond(p, i, j, 0.0, opinions[j], relationships[i, j], rng.randint(N_TOPICS))
                         for j in range(N_CHARS) if j != i)
            scores.append(gain + 0.3 * n_resp)
        else:
            if oracle:
                # 完美前向: 直接模拟真实反应(用当前全局状态)
                n_resp = 0
                rel_gain = 0.0
                for j in range(N_CHARS):
                    if j == i:
                        continue
                    if would_respond(p, i, j, val, opinions[j], relationships[i, j], topic) > rng.random():
                        n_resp += 1
                unique = abs(val - topic_state)
                scores.append(0.3 + 0.7 * unique + 0.4 * n_resp)
            else:
                n_resp, rel_gain, unique = predict_response(
                    p, i, val, topic_state, opinions, relationships, topic)
                scores.append(0.3 + 0.7 * unique + 0.4 * n_resp + 0.1 * rel_gain)
    # softmax 采样
    scores = np.array(scores)
    exp_s = np.exp((scores - scores.max()) / TEMPERATURE)
    probs = exp_s / exp_s.sum()
    chosen = rng.choice(len(drafts), p=probs)
    return drafts[chosen], scores, probs


def simulate_round(p, topic, topic_state, opinions, relationships, mode):
    """mode: 'none'(直接发言) / 'forward'(前向推演) / 'oracle'(完美前向)"""
    n = len(p)
    aff = topic_affinity(p, topic)
    speak_prob = 0.15 + 0.6 * p[:, 3] * aff
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True
    actions = []
    pred_acc = []  # (预测, 实际) 反应数对比
    for i in np.where(speakers)[0]:
        if mode == 'none':
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
        else:
            (kind, val), scores, probs = pick_draft_forward(
                p, i, topic, topic_state, opinions, relationships, oracle=(mode == 'oracle'))
            # 预测 vs 实际(粗略: 预测反应数 vs 发言后实际被回应)
            if kind == 'argue':
                n_pred = sum(would_respond(p, i, j, val, opinions[j], relationships[i, j], topic) > rng.random()
                             for j in range(n) if j != i)
                actions.append((i, kind, val))
                # 实际反应数在下面统计后比对
                pred_acc.append((i, n_pred))
            else:
                actions.append((i, kind, val))
    # 主流观点更新
    if actions:
        non_new = [(i, v) for i, k, v in actions if k != 'new_topic']
        if non_new:
            w2 = np.array([p[i, 3] for i, _ in non_new])
            if w2.sum() <= 0:
                w2 = np.ones_like(w2)
            v2 = np.array([v for _, v in non_new])
            topic_state = np.clip(np.average(v2, weights=w2), -1, 1)
    # 观点更新
    for i in range(n):
        social_influence = p[i, 2] * p[i, 1] * (topic_state - opinions[i])
        opinions[i] = np.clip(opinions[i] * p[i, 6] + social_influence, -1, 1)
    # 适应度 + 关系
    fitness_inc = np.zeros(n)
    for i, k, v in actions:
        if k == 'new_topic':
            fitness_inc[i] += 0.5
        else:
            fitness_inc[i] += 0.3 + 0.7 * abs(v - topic_state)
    actual_resp = {i: 0 for i, _, _ in actions}
    for a in range(len(actions)):
        for b in range(a + 1, len(actions)):
            i, k1, v1 = actions[a]
            j, k2, v2 = actions[b]
            if k1 == k2 and k1 != 'new_topic' and abs(v1 - v2) < 0.5:
                relationships[i, j] += 1
                relationships[j, i] += 1
                actual_resp[i] += 1
                actual_resp[j] += 1
    # 预测准确度(有前向模式)
    acc = None
    if pred_acc:
        errs = []
        for i, n_pred in pred_acc:
            errs.append(abs(n_pred - actual_resp.get(i, 0)))
        acc = 1.0 - min(1.0, np.mean(errs) / 3.0)
    return actions, fitness_inc, topic_state, opinions, relationships, acc


def run_experiment(mode, seed):
    rng.seed(seed)
    p = init_params()
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    accs = []
    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)
        _, inc, topic_state, opinions, relationships, acc = simulate_round(
            p, topic, topic_state, opinions, relationships, mode)
        fitness += inc
        if acc is not None:
            accs.append(acc)
    return {'fitness': fitness, 'relationships': relationships, 'opinions': opinions,
            'acc': float(np.mean(accs)) if accs else None}


def main():
    print("=" * 66)
    print("exp55: 前向 rollout 草稿评分——角色发言前先推演对方反应")
    print("=" * 66)
    seeds = [7, 11, 23, 42, 99]
    modes = ['none', 'forward', 'oracle']
    stats = {m: {'gain': [], 'acc': []} for m in modes}
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
            _, inc, ts, opinions, rel, _ = simulate_round(p, topic, ts, opinions, rel, 'none')
            fit0 += inc
        for m in modes:
            res = run_experiment(m, s)
            stats[m]['gain'].append((res['fitness'].mean() / fit0.mean() - 1) * 100)
            stats[m]['acc'].append(res['acc'])

    print(f"\n{'模式':<12}{'适应度增益':>12}{'预测准确度':>12}")
    print("-" * 38)
    for m in modes:
        gain = np.mean(stats[m]['gain'])
        acc = np.mean([a for a in stats[m]['acc'] if a is not None]) if any(stats[m]['acc']) else None
        acc_s = f"{acc*100:.1f}%" if acc is not None else "—"
        print(f"{m:<12}{gain:>+11.1f}%{acc_s:>12}")

    print("\n各 seed 明细(增益%):")
    print(f"{'seed':<6}{'none':>12}{'forward':>12}{'oracle':>12}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}" + "".join(f"{stats[m]['gain'][k]:>+11.1f}%" for m in modes))

    print("\n预测准确度(forward/oracle):")
    print(f"{'seed':<6}{'forward':>12}{'oracle':>12}")
    for k, s in enumerate(seeds):
        print(f"{s:<6}{stats['forward']['acc'][k]*100:>11.1f}%{stats['oracle']['acc'][k]*100:>11.1f}%")

    np.savez(os.path.join(ARCHIVE, 'exp55_forward_draft.npz'),
             seeds=np.array(seeds),
             gain={m: np.array(stats[m]['gain']) for m in modes},
             acc={m: np.array(stats[m]['acc']) for m in modes})
    print(f"\n存档已保存 evolution_chat/exp55_forward_draft.npz")


if __name__ == '__main__':
    main()
