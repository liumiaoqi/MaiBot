#!/usr/bin/env python3
"""exp51: 角色参数漂移系统——虚拟角色群聊模拟（ZH 候选立项实验验证）

洞见链（exp41-50 → ZH 角色参数漂移系统）:
  环境塑造行为(exp43) / 多样性-适应度权衡(exp49) / 目标函数决定行为(exp50)
  → 8-10 个行为参数随互动环境温和漂移, 而非写死

设计（对齐 ZH 立项初稿）:
1. 角色"基因型": 8 个行为参数
   explore   探索率(0~0.5)       —— 多爱引入新话题
   polarity  社交极性(-1~1)      —— 从众(+) / 反从众(-)
   social    社交强度(0~1)       —— 多大程度参考群体
   desire    欲望强度(0~1)       —— 多想说话/被关注
   decay     热情衰减(0~1)       —— 兴趣多快转移
   recall    回忆多样性(0~1)     —— 发言话题的多样性(高=跳话题, 低=钉住旧话题)
   persist   目标坚持(0~1)       —— 多执着于自己的观点
   empathy   共情(0~1)           —— 多附和他人情绪
2. 模拟群聊: 每轮一个话题, 角色按参数决定:
   - 是否发言(desire × 话题兴趣)
   - 发言倾向: 支持/反对/引入新话题(explore) / 附和(empathy)
   - 观点更新: polarity × social × 群体主流 → 自己的观点漂移
3. 适应度(设计决策, 用户拍板前先用代理):
   - 被回应次数(他人引用你的观点) + 关系强度(与谁常互动)
   - 表达独特性(与群体观点距离)
4. 漂移循环(温和版, 非残酷淘汰):
   - 每 10 轮一次: 小步高斯扰动(σ=0.05), 方向偏向高适应度角色
   - 进化笼子: 参数边界 + 每次漂移存档 + 漂移幅度上限(温度调度)
5. 对照: 固定参数基线(同样初始化, 不漂移)

验证点(ZH 立项四节):
  ① 漂移后角色差异是否增大(多样性保持)  ② 适应度是否上升  ③ 边界约束是否防失控
"""

import json
import os
import numpy as np

rng = np.random.RandomState(20260819)
DATA = r'E:\Users\lmq\MaiBot\scripts\embedding_finetune\snn_behavior\worm_data'
ARCHIVE = os.path.join(DATA, 'evolution_chat')
os.makedirs(ARCHIVE, exist_ok=True)

N_CHARS = 12          # 角色数
N_ROUNDS = 300        # 群聊轮数
DRIFT_EVERY = 10      # 每 10 轮漂移一次
DRIFT_SIGMA0 = 0.06   # 初始漂移幅度
TEMP_DECAY = 0.98     # 温度调度: 漂移幅度随轮数衰减(防后期乱漂)
N_TOPICS = 10         # 话题空间大小

PARAM_NAMES = ['explore', 'polarity', 'social', 'desire', 'decay', 'recall', 'persist', 'empathy']
PARAM_RANGES = [(0.0, 0.5), (-1.0, 1.0), (0.0, 1.0), (0.0, 1.0),
                (0.0, 1.0), (0.0, 1.0), (0.0, 1.0), (0.0, 1.0)]

# 角色名字(彼岸居风格——MaiBot 十三角色理念)
NAMES = ['阿晨', '小满', '青梧', '墨白', '苏黎', '洛可可', '白鹭', '砚秋', '棠梨', '顾言', '南栀', '云野']


def clamp_params(p):
    p = np.asarray(p, dtype=float).copy()
    for i, (lo, hi) in enumerate(PARAM_RANGES):
        p[i] = min(max(p[i], lo), hi)
    return p


def init_params():
    """初始参数: 均匀随机(不刻意差异化——看漂移能否自然分化)"""
    p = np.zeros(N_CHARS * len(PARAM_NAMES)).reshape(N_CHARS, len(PARAM_NAMES))
    for i in range(len(PARAM_NAMES)):
        lo, hi = PARAM_RANGES[i]
        p[:, i] = rng.uniform(lo, hi, N_CHARS)
    return p


def topic_affinity(p, topic):
    """角色对话题的初始兴趣(每个角色对每个话题有个性化亲和度)
    p: (N, 8) 参数矩阵; 返回 (N,) 亲和度"""
    desire = p[:, 3]   # explore=0, polarity=1, social=2, desire=3
    recall = p[:, 5]   # decay=4, recall=5, persist=6, empathy=7
    return np.clip(0.3 + 0.7 * desire * np.abs(np.sin(topic * 1.7 + recall * 3.1)), 0, 1)


def simulate_round(params, topic, topic_state, opinions, relationships, round_i):
    """一轮群聊: 返回 (发言记录, 适应度增量)
    topic_state: 该话题当前主流观点(-1~1)
    opinions: 每角色当前观点(-1~1)
    """
    n = len(params)
    # 1. 谁发言: desire 高 + 话题亲和度高
    aff = topic_affinity(params, topic)
    speak_prob = 0.15 + 0.6 * params[:, 3] * aff  # desire
    speakers = rng.uniform(0, 1, n) < speak_prob
    if not speakers.any():
        speakers[rng.randint(n)] = True  # 保证每轮有人说话
    # 2. 发言内容: 支持/反对/新话题/附和
    actions = []
    for i in np.where(speakers)[0]:
        # 观点立场 = 自己的观点(极性调制: 反从众者与主流相反)
        own = opinions[i]
        if params[i, 1] < 0:  # polarity
            lean = own * (1 - abs(params[i, 1])) - np.sign(topic_state) * abs(params[i, 1])
        else:
            lean = own
        # 探索: 引入新话题
        if rng.uniform(0, 1) < params[i, 0] * 0.5:  # explore
            actions.append((i, 'new_topic', rng.randint(N_TOPICS)))
        # 附和(高共情且观点接近)
        elif rng.uniform(0, 1) < params[i, 7] * 0.6 and abs(opinions[i] - topic_state) < 0.5:  # empathy
            actions.append((i, 'agree', topic_state))
        else:
            actions.append((i, 'argue', lean))
    # 3. 群体主流更新: 发言者观点的加权平均(desire 为权重)
    if actions:
        weights = np.array([params[i, 3] for i, _, _ in actions])  # desire
        vals = np.array([v for _, _, v in actions if _ != 'new_topic'] if any(_ == 'argue' or _ == 'agree' for _, _, _ in actions) else [topic_state])
        # 简化: 用所有非 new_topic 发言的观点加权
        non_new = [(i, v) for i, k, v in actions if k != 'new_topic']
        if non_new:
            w2 = np.array([params[i, 3] for i, _ in non_new])  # desire
            if w2.sum() <= 0:
                w2 = np.ones_like(w2)  # 全零权重兜底: 等权平均
            v2 = np.array([v for _, v in non_new])
            topic_state = np.clip(np.average(v2, weights=w2), -1, 1)
    # 4. 观点更新: 社会影响(极性×social) + 坚持度(自己的观点惯性)
    for i in range(n):
        social_influence = params[i, 2] * params[i, 1] * (topic_state - opinions[i])  # social × polarity
        opinions[i] = np.clip(opinions[i] * params[i, 6] + social_influence, -1, 1)  # persist
    # 5. 适应度增量:
    #    - 被回应: 与自己观点同向的发言者数量(反向则是对立, 也是互动)
    #    - 表达独特性: 与群体主流的距离
    fitness_inc = np.zeros(n)
    for i, k, v in actions:
        if k == 'new_topic':
            fitness_inc[i] += 0.5  # 新话题引入者受益
        else:
            dist = abs(v - topic_state)
            fitness_inc[i] += 0.3 + 0.7 * dist  # 表达越独特(离主流越远)得分越高, 但主流附和也有基础分
    # 关系: 同向发言者之间关系+1
    for a in range(len(actions)):
        for b in range(a + 1, len(actions)):
            i, k1, v1 = actions[a]
            j, k2, v2 = actions[b]
            if k1 == k2 and k1 != 'new_topic' and abs(v1 - v2) < 0.5:
                relationships[i, j] += 1
                relationships[j, i] += 1
    return actions, fitness_inc, topic_state, opinions, relationships


def run_experiment(drift=True, seed=None):
    if seed is not None:
        rng.seed(seed)
    params = init_params()
    opinions = rng.uniform(-1, 1, N_CHARS)
    relationships = np.zeros((N_CHARS, N_CHARS))
    topic = rng.randint(N_TOPICS)
    topic_state = 0.0
    fitness = np.zeros(N_CHARS)
    drift_log = []  # 每次漂移的参数快照(进化笼子审计)
    param_history = [params.copy()]

    for t in range(N_ROUNDS):
        if t % 50 == 0:
            topic = rng.randint(N_TOPICS)  # 偶尔换话题
        _, inc, topic_state, opinions, relationships = simulate_round(
            params, topic, topic_state, opinions, relationships, t)
        fitness += inc
        # 漂移: 每 DRIFT_EVERY 轮, 温和高斯扰动, 方向偏向高适应度
        if drift and (t + 1) % DRIFT_EVERY == 0:
            sigma = DRIFT_SIGMA0 * (TEMP_DECAY ** (t // DRIFT_EVERY))
            # 适应度梯度调节漂移幅度(exp49 多样性维持洞见):
            #   高适应度角色→小漂移(保守稳定), 低适应度角色→大漂移(探索)
            #   不做"向最优者靠拢"——模仿=趋同=多样性杀手(首版实测差异度 1.21→1.05)
            fit_max = float(fitness.max())
            fit_min = float(fitness.min())
            fit_span = max(fit_max - fit_min, 1e-9)
            for i in range(N_CHARS):
                rel_fit = (fitness[i] - fit_min) / fit_span  # 0(最差)~1(最好)
                sigma_i = sigma * (1.6 - rel_fit)             # 最差 1.6σ, 最好 0.6σ
                params[i] = clamp_params(params[i] + sigma_i * rng.randn(len(PARAM_NAMES)))
            drift_log.append({
                'round': t + 1,
                'sigma': float(sigma),
                'params': params.copy().tolist(),
                'fitness': fitness.copy().tolist(),
            })
            param_history.append(params.copy())
    return {
        'params_final': params,
        'fitness': fitness,
        'relationships': relationships,
        'opinions': opinions,
        'drift_log': drift_log,
        'param_history': np.array(param_history),
    }


def diversity(params):
    """参数差异度: 角色间参数矩阵的成对距离均值"""
    d = 0.0
    cnt = 0
    for i in range(len(params)):
        for j in range(i + 1, len(params)):
            d += np.linalg.norm(params[i] - params[j])
            cnt += 1
    return d / cnt


def main():
    print("=" * 60)
    print("exp51: 角色参数漂移系统——虚拟角色群聊模拟")
    print("=" * 60)

    # 对照: 固定参数 vs 漂移(同种子, 保证初始参数一致)
    rng.seed(42)
    base_params = init_params()
    fixed = run_experiment(drift=False, seed=42)
    drifted = run_experiment(drift=True, seed=42)

    div0 = diversity(base_params)
    div_fixed = diversity(fixed['params_final'])
    div_drift = diversity(drifted['params_final'])

    print(f"初始参数差异度:      {div0:.4f}")
    print(f"固定基线终态差异度:  {div_fixed:.4f}  (Δ {div_fixed - div0:+.4f})")
    print(f"漂移组终态差异度:    {div_drift:.4f}  (Δ {div_drift - div0:+.4f})")

    # 适应度
    print(f"固定基线适应度均值: {fixed['fitness'].mean():.1f}  (max {fixed['fitness'].max():.1f})")
    print(f"漂移组适应度均值:   {drifted['fitness'].mean():.1f}  (max {drifted['fitness'].max():.1f})")

    # 漂移是否让角色分化(终态参数分布)
    print(f"漂移组终态参数(12角色 × 8参数):")
    for i, name in enumerate(NAMES):
        p = drifted['params_final'][i]
        print(f"  {name}: " + " ".join(f"{pn}={pv:.2f}" for pn, pv in zip(PARAM_NAMES, p)))

    # 参数边界审计(进化笼子)
    in_bounds = all(
        PARAM_RANGES[j][0] <= drifted['params_final'][i][j] <= PARAM_RANGES[j][1]
        for i in range(N_CHARS) for j in range(len(PARAM_NAMES)))
    print(f"进化笼子边界检查: {'✅ 全部在界内' if in_bounds else '❌ 越界!'}")

    # 保存存档
    np.savez(os.path.join(ARCHIVE, 'exp51_chat_drift.npz'),
             base=base_params, fixed=fixed['params_final'], drifted=drifted['params_final'],
             fit_fixed=fixed['fitness'], fit_drift=drifted['fitness'],
             rel_drift=drifted['relationships'],
             hist=drifted['param_history'])
    with open(os.path.join(ARCHIVE, 'exp51_drift_log.json'), 'w', encoding='utf-8') as f:
        json.dump(drifted['drift_log'], f, ensure_ascii=False, indent=1)

    # 多样性与适应度随漂移的演化
    print(f"漂移轮次: {len(drifted['drift_log'])} 次, 存档已保存 evolution_chat/exp51_*")
    # 输出多样性演化轨迹
    print("参数差异度演化(每10轮):")
    for k, hist in enumerate(drifted['param_history'][::3]):
        print(f"  轮 {k*30}: {diversity(hist):.4f}")


if __name__ == '__main__':
    main()
