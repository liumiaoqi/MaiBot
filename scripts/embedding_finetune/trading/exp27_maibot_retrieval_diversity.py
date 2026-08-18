#!/usr/bin/env python3
"""exp27: 量子信道噪声迁移到 MaiBot 检索——检索多样性 vs 质量损失

背景:exp19-26 证明量子信道噪声(bitflip/ampdamp/depolar)对 R-STDP 是
比高斯更强的探索信号。MaiBot 应用候选(用户拍板方向):A_memorix 检索
"受控的不确定"——纯 top-k 每次返回相同结果,角色像复读机;
概率采样引入多样性,但代价是质量(可能带出低分结果)。

本实验(模拟,不动生产):构造检索候选池(模拟向量分数分布),
三种采样策略对比:
- topk   纯 top-k(确定性基线)
- gauss  高斯扰动分数后取 top-k(经典探索)
- qbit   量子信道式扰动(bitflip 翻转排名/ampdamp 压制分数,查表式)
指标:
- 多样性:相邻两次检索结果的重叠率(越低越多样;连续 query 相关时,纯 topk 重叠高)
- 质量:返回结果的平均分 vs 理想 top-k 平均分(损失)
- 效率:多样性增益 / 质量损失 比值
"""

import math
import random
import numpy as np

random.seed(20260818)
np.random.seed(20260818)

POOL = 500       # 候选池大小
RETRIEVALS = 60  # 连续检索次数
K = 8            # 返回条数


def make_pool():
    """模拟候选池:500 个记忆项,分数 = 基础相关 + 位置噪声。"""
    base = np.random.RandomState(7).normal(0.5, 0.12, POOL)
    drift = np.random.RandomState(11).normal(0.0, 0.05, POOL)
    return base, drift


def query_scores(base, drift, q):
    """第 q 次检索:分数 = 基础分 + 随 query 缓慢漂移(模拟连续对话话题漂移)。"""
    return base + drift * math.sin(q / 6.0)


def topk(scores, k=K):
    return list(np.argsort(scores)[::-1][:k])


def gauss_sample(scores, k=K, sigma=0.05):
    """高斯扰动:分数加 N(0,sigma) 后取 top-k。"""
    noisy = scores + np.random.normal(0.0, sigma, len(scores))
    return list(np.argsort(noisy)[::-1][:k])


def qbit_sample(scores, k=K, p=0.1):
    """量子信道式扰动:比特翻转——以概率 p 翻转排名符号(高分变低分参与竞争)。

    对应 exp19-26 的 bitflip 信道:离散翻转 >> 连续微扰(脉冲网络/排名结构的直觉)。
    排名翻转 = 把"本该靠前"的换成"本该靠后"的,制造结构性探索。
    """
    n = len(scores)
    flip = np.random.random(n) < p
    # 翻转符号后重排:被翻转的项从高分池掉入低分池,等价于"突然想起别的"
    perturbed = scores.copy()
    flipped_idx = np.where(flip)[0]
    if len(flipped_idx) > 0:
        ranks = np.argsort(np.argsort(scores))  # 排名 0=最低
        # 翻转项改为"反向竞争分":低排名项获得高扰动,高排名项被压制
        perturbed[flipped_idx] = scores[flipped_idx] * -1.0
    return list(np.argsort(perturbed)[::-1][:k])


def ampdamp_sample(scores, k=K, p=0.02):
    """振幅阻尼:以概率 p 把某些项"压制到 0"(信息丢失/遗忘),其余不变。"""
    damp = np.random.random(len(scores)) < p
    perturbed = scores.copy()
    perturbed[damp] = 0.0
    return list(np.argsort(perturbed)[::-1][:k])


def overlap(a, b):
    return len(set(a) & set(b))


def run(strategy_fn, base, drift):
    """跑 60 次连续检索,统计多样性与质量。"""
    overlaps = []
    quality = []
    prev = None
    for q in range(RETRIEVALS):
        scores = query_scores(base, drift, q)
        picked = strategy_fn(scores)
        ideal = topk(scores)
        if prev is not None:
            overlaps.append(overlap(prev, picked) / K)
        prev = picked
        # 质量:返回结果平均分 vs 理想 top-k 平均分(1.0 = 无损失)
        quality.append(sum(scores[i] for i in picked) / sum(scores[i] for i in ideal))
    return np.mean(overlaps), np.mean(quality)


if __name__ == '__main__':
    print('=== exp27: 量子信道噪声 × MaiBot 检索多样性(模拟) ===')
    print('候选池 500,连续检索 60 次,返回 top-8;话题缓慢漂移\n')

    base, drift = make_pool()
    strategies = [
        ('topk 纯top-k(确定性)', lambda s: topk(s)),
        ('gauss 高斯扰动(σ=0.05)', lambda s: gauss_sample(s, sigma=0.05)),
        ('ampdamp 振幅阻尼(p=0.02)', lambda s: ampdamp_sample(s, p=0.02)),
        ('qbit 比特翻转(p=0.10)', lambda s: qbit_sample(s, p=0.10)),
    ]
    print('%-28s %10s %10s %14s' % ('策略', '重叠率', '质量保留', '多样性增益/损失'))
    print('-' * 66)
    topk_overlap, topk_quality = run(lambda s: topk(s), base, drift)
    print('%-28s %10.3f %10.3f %14s' % ('topk 纯top-k', topk_overlap, topk_quality, '—'))
    for name, fn in strategies[1:]:
        ov, q = run(fn, base, drift)
        # 多样性增益 = topk重叠率 - 本策略重叠率(重叠越低越多样);质量损失 = 1 - q
        div_gain = topk_overlap - ov
        qual_loss = 1.0 - q
        ratio = div_gain / qual_loss if qual_loss > 1e-6 else float('inf')
        print('%-28s %10.3f %10.3f %14.2f' % (name, ov, q, ratio))

    print()
    print('=== 解读 ===')
    print('重叠率越低 = 检索越多样(角色"想起"的东西不重复)')
    print('质量保留越接近 1.0 = 返回结果越相关')
    print('多样性增益/损失 比值越高 = 用越少的相关性换越多的多样性(划算)')
