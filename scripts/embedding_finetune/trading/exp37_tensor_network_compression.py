#!/usr/bin/env python3
"""exp37: 张量网络压缩会话历史——低秩结构 vs 截断(对标 dsh compaction)

WB 调研首选:张量网络压缩(KARIPAP 93% 内存削减/2-3% 损失)——"量子纠缠有界"
思想:高维数据实际有低秩结构,用少量参数捕获主要相关性,纯经典可实现。

MaiBot 场景:会话历史压缩。会话 = T 条消息嵌入矩阵 X(T×D)。
- 截断(现状 compaction 式):只保留最近 K 条——老话题全丢
- 张量网络(低秩/SVD,MPO 的数学基础):X ≈ U_r Σ_r V_r^T——全历史结构
  压缩成 r 维(低秩子空间),老话题的相关性仍在低秩坐标里

指标:同压缩率下 检索准确率(按话题年龄分层——老话题是不是只有张量网络能找回)+ 重构误差
"""

import math
import numpy as np

rng = np.random.RandomState(20260818)

T = 200            # 会话消息数
D = 64             # 嵌入维度
N_TOPICS = 8       # 话题数


def make_session():
    """模拟会话:T 条消息嵌入,8 个话题阶段漂移。"""
    # 话题中心(8 个,两两正交部分)
    centers = rng.normal(0, 1, (N_TOPICS, D))
    X = np.zeros((T, D))
    for t in range(T):
        topic = min(N_TOPICS - 1, t * N_TOPICS // T)  # 话题随会话推进
        X[t] = centers[topic] + rng.normal(0, 0.3, D)
    return X, centers


def truncate_compress(X, K):
    """截断:保留最近 K 条(现状 compaction 式)。"""
    return X[-K:].copy()


def tn_compress(X, r):
    """张量网络(低秩 SVD)压缩:保留前 r 个奇异值,返回低秩坐标。"""
    U, S, Vt = np.linalg.svd(X, full_matrices=False)
    Ur = U[:, :r]
    Sr = S[:r]
    # 低秩坐标:消息在 r 维子空间的投影(全历史的结构压缩)
    return Ur * Sr  # T×r


def retrieval_acc(query, candidates, exact=None):
    """在候选集里找与 query 最相似的一条,判断是否正确话题(用 exact 话题检查)。"""
    scores = candidates @ query
    best = int(np.argmax(scores))
    return best


def topic_of(idx, T=T, N=N_TOPICS):
    return min(N - 1, idx * N // T)


if __name__ == '__main__':
    print('=== exp37: 张量网络压缩会话历史——低秩 vs 截断 ===')
    print('T=200 消息 × D=64 嵌入,8 话题阶段;对比同压缩率下的检索准确率\n')

    X, centers = make_session()

    # 压缩率对照:K=50 → 保留 25%;SVD r 选择使参数量相当
    # 截断参数量 = K×D;张量网络参数量 = (T+r)×r + r(约 2Tr)
    configs = [
        ('原始(不压缩)', 'full', None),
        ('截断 K=100(50%)', 'trunc', 100),
        ('张量网络 r=15(≈50%)', 'tn', 15),
        ('截断 K=40(20%)', 'trunc', 40),
        ('张量网络 r=6(≈20%)', 'tn', 6),
    ]

    print('--- 检索准确率(按话题年龄分层:新=近3话题/中=中间/老=前2话题) ---')
    print('%-24s %10s %10s %10s' % ('压缩方案', '新话题', '中话题', '老话题'))
    print('-' * 58)
    # 100 个 query:每个话题均匀采样
    queries = []
    for topic in range(N_TOPICS):
        for _ in range(12):
            queries.append((topic, centers[topic] + rng.normal(0, 0.3, D)))

    for name, kind, param in configs:
        if kind == 'full':
            cand = X
            r_eff = D
        elif kind == 'trunc':
            cand = truncate_compress(X, param)
        else:
            cand = tn_compress(X, param)
        acc_new = acc_mid = acc_old = 0
        n_new = n_mid = n_old = 0
        for topic, q in queries:
            if topic >= N_TOPICS - 3:
                bucket = 'new'
            elif topic >= 2:
                bucket = 'mid'
            else:
                bucket = 'old'
            # 找最近消息
            if kind == 'tn':
                # 低秩坐标检索:query 也投影
                U, S, Vt = np.linalg.svd(X, full_matrices=False)
                q_proj = (q @ Vt[:param].T)  # 投影到前 r 个右奇异向量
                # 检索低秩坐标中的最近消息
                best = int(np.argmax(cand @ q_proj))
            else:
                best = int(np.argmax(cand @ q))
            # 正确 = 命中消息属于 query 的话题
            if kind == 'trunc':
                best_topic = topic_of(len(X) - len(cand) + best)
            else:
                best_topic = topic_of(best)
            ok = (best_topic == topic)
            if bucket == 'new':
                acc_new += ok; n_new += 1
            elif bucket == 'mid':
                acc_mid += ok; n_mid += 1
            else:
                acc_old += ok; n_old += 1
        print('%-24s %10.0f%% %10.0f%% %10.0f%%' % (
            name, acc_new / n_new * 100, acc_mid / n_mid * 100,
            acc_old / n_old * 100))

    # 重构误差(张量网络信息保留)
    print()
    print('--- 张量网络重构误差(信息保留度) ---')
    for r in [3, 6, 15, 30]:
        U, S, Vt = np.linalg.svd(X, full_matrices=False)
        Xr = (U[:, :r] * S[:r]) @ Vt[:r]
        err = np.linalg.norm(X - Xr) / np.linalg.norm(X)
        print('r=%2d: 重构误差 %.3f(参数量 %.1f%%)' % (
            r, err, (T * r + r) / (T * D) * 100))

    print()
    print('=== 结论观察 ===')
    print('老话题:截断是否丢光 vs 张量网络是否保住(低秩全局结构)?')
    print('同压缩率下检索准确率对比——张量网络值得替换截断吗?')
