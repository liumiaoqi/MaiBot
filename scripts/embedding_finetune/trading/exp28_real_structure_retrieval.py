#!/usr/bin/env python3
"""exp28: 真实结构检索模拟——A_memorix 三通道融合下的量子信道扰动

exp27 用单一高斯分数;本实验用 A_memorix 真实融合结构:
score = 0.6*semantic + 0.3*graph + 0.1*evidence(dual_path.py:1030)
- semantic: 向量相似度(0-1,集中在高值区,beta 分布)
- graph:    PPR 分数(长尾,大部分低值,少数高——枢纽)
- evidence: 证据数(稀疏小整数 0-3)
候选分层:段落层(多,~2000) + 关系层(少,~300)——融合后取 top。
连续对话:话题缓慢漂移(query 中心移动,相关候选集合变化)。
对比:topk / gauss / ampdamp / qbit——多样性与质量。
"""

import math
import random
import numpy as np

random.seed(20260818)
np.random.seed(20260818)

PARA_N = 2000
REL_N = 300
RETRIEVALS = 80
K = 10


def make_pool():
    """生成段落+关系两层候选,带三通道分数。"""
    rng = np.random.RandomState(7)
    # 段落:semantic beta(2,5)(高值集中),graph 长尾(大部分 0.1 以下),evidence 稀疏
    sem_p = rng.beta(2.0, 5.0, PARA_N)
    graph_p = np.where(rng.random(PARA_N) < 0.15,
                       rng.random(PARA_N) * 0.8 + 0.2, rng.random(PARA_N) * 0.1)
    evi_p = rng.choice([0, 1, 2, 3], PARA_N, p=[0.6, 0.25, 0.1, 0.05])
    # 关系:分数整体更高(关系更精选),graph 占比更重
    sem_r = rng.beta(3.0, 4.0, REL_N)
    graph_r = np.where(rng.random(REL_N) < 0.3,
                       rng.random(REL_N) * 0.8 + 0.2, rng.random(REL_N) * 0.15)
    evi_r = rng.choice([0, 1, 2], REL_N, p=[0.3, 0.4, 0.3])
    sem = np.concatenate([sem_p, sem_r])
    graph = np.concatenate([graph_p, graph_r])
    evi = np.concatenate([evi_p, evi_r])
    # 话题坐标:每个候选在话题空间有一个位置(2D),检索 query 也在话题空间
    topics = rng.normal(0.0, 1.0, (PARA_N + REL_N, 2))
    return sem, graph, evi, topics


def query_scores(sem, graph, evi, topics, q):
    """第 q 次检索:query 沿话题空间缓慢漂移,分数 = 融合 + 话题距离衰减。"""
    qpos = np.array([math.sin(q / 8.0) * 2.0, math.cos(q / 11.0) * 2.0])
    dist = np.linalg.norm(topics - qpos, axis=1)
    topic_aff = np.exp(-dist / 1.2)  # 话题相关度 0-1
    fusion = 0.6 * sem + 0.3 * graph + 0.1 * (evi / 3.0)
    return fusion * (0.3 + 0.7 * topic_aff)


def topk(scores, k=K):
    return list(np.argsort(scores)[::-1][:k])


def gauss_sample(scores, k=K, sigma=0.05):
    noisy = scores + np.random.normal(0.0, sigma, len(scores))
    return list(np.argsort(noisy)[::-1][:k])


def ampdamp_sample(scores, k=K, p=0.02):
    damp = np.random.random(len(scores)) < p
    perturbed = scores.copy()
    perturbed[damp] = 0.0
    return list(np.argsort(perturbed)[::-1][:k])


def qbit_sample(scores, k=K, p=0.10):
    flip = np.random.random(len(scores)) < p
    perturbed = scores.copy()
    perturbed[flip] = scores[flip] * -1.0
    return list(np.argsort(perturbed)[::-1][:k])


def overlap(a, b):
    return len(set(a) & set(b))


def run(strategy_fn, sem, graph, evi, topics):
    overlaps = []
    quality = []
    prev = None
    for q in range(RETRIEVALS):
        scores = query_scores(sem, graph, evi, topics, q)
        picked = strategy_fn(scores)
        ideal = topk(scores)
        if prev is not None:
            overlaps.append(overlap(prev, picked) / K)
        prev = picked
        quality.append(sum(scores[i] for i in picked) / sum(scores[i] for i in ideal))
    return np.mean(overlaps), np.mean(quality)


if __name__ == '__main__':
    print('=== exp28: 真实结构检索模拟(A_memorix 三通道融合 + 量子信道扰动) ===')
    print('段落 2000 + 关系 300,融合 0.6sem+0.3graph+0.1evi,话题漂移 80 次检索,top-10\n')
    sem, graph, evi, topics = make_pool()

    strategies = [
        ('topk 纯top-k', lambda s: topk(s)),
        ('gauss σ=0.05', lambda s: gauss_sample(s, sigma=0.05)),
        ('ampdamp p=0.02', lambda s: ampdamp_sample(s, p=0.02)),
        ('qbit p=0.10', lambda s: qbit_sample(s, p=0.10)),
    ]
    print('%-20s %10s %10s %14s' % ('策略', '重叠率', '质量保留', '多样性/损失'))
    print('-' * 58)
    tk_ov, tk_q = run(lambda s: topk(s), sem, graph, evi, topics)
    print('%-20s %10.3f %10.3f %14s' % ('topk 纯top-k', tk_ov, tk_q, '—'))
    for name, fn in strategies[1:]:
        ov, q = run(fn, sem, graph, evi, topics)
        ratio = (tk_ov - ov) / (1.0 - q) if (1.0 - q) > 1e-6 else float('inf')
        print('%-20s %10.3f %10.3f %14.2f' % (name, ov, q, ratio))

    print()
    print('=== 落地判断 ===')
    print('若 ampdamp/qbit 的效率比 > gauss:量子信道扰动在真实结构下依然划算')
    print('角色多样性偏好 = agent 层配置(记忆参数分层:机制→A_memorix/策略→智能体)')
