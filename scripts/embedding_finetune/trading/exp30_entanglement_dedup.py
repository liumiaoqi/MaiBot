#!/usr/bin/env python3
"""exp30: 纠缠熵记忆去重——量子互信息 vs 文本相似度(信息论冗余度)

问题(ZH ⑲):⑪ 实验发现"只追加 88% 冗余"——现状用文本相似度(Jaccard/cosine)
做确定性去重,但"语义等价字面不同"的表述(琳姐今天生日 vs 她生日是今天)
文本相似度低,去重漏掉。量子信息论提供新度量:互信息 I(X;Y)=S(X)+S(Y)-S(X,Y)
(量子互信息 I(A;B)=S(A)+S(B)-S(AB) 的经典模拟)——度量"两条记忆共享多少
信息",不依赖字面:共现的罕见词(高IDF)贡献大 = 语义冗余,而非字符重叠。

实现:记忆 = 词袋;对记忆对构建 2×2 列联表(a=双现词/b=仅x/c=仅y/d=全无)
→ 互信息;对比 Jaccard / cosine / 互信息 在"冗余对 vs 独立对"上的区分能力。
关键测试:语义等价字面不同对(同义词替换)——文本相似度低但互信息高?
"""

import math
import numpy as np

rng = np.random.RandomState(42)

VOCAB = 200          # 词表大小
N_TOPICS = 8         # 主题数


def topic_dist(k):
    """第 k 个主题的词分布(集中在若干词上)。"""
    d = np.full(VOCAB, 0.001)
    core = np.random.RandomState(100 + k).choice(VOCAB, 12, replace=False)
    d[core] = np.random.RandomState(200 + k).dirichlet(np.ones(12)) * 0.85
    return d


TOPICS = [topic_dist(k) for k in range(N_TOPICS)]


def sample_memory(topic, n_words=15, syn_ratio=0.0):
    """从主题采样一条记忆;syn_ratio 时用同义词替换部分词(语义等价字面不同)。"""
    words = rng.choice(VOCAB, n_words, p=TOPICS[topic] / TOPICS[topic].sum())
    if syn_ratio > 0:
        # 同义词替换:把部分词换成"同义词"(映射到同主题的其他词)
        n_syn = int(n_words * syn_ratio)
        syns = rng.choice(VOCAB, n_syn, p=TOPICS[topic] / TOPICS[topic].sum())
        words[:n_syn] = syns
    return words


def jaccard(x, y):
    return len(set(x) & set(y)) / len(set(x) | set(y))


def cosine(x, y):
    vx = np.zeros(VOCAB); vy = np.zeros(VOCAB)
    for w in x: vx[w] += 1
    for w in y: vy[w] += 1
    n = np.linalg.norm(vx) * np.linalg.norm(vy)
    return float(vx @ vy / n) if n > 0 else 0.0


def mutual_info(x, y):
    """2×2 列联表互信息:双现词 a / 仅x b / 仅y c / 全无 d。
    共现的罕见词贡献大(词频低→p 小→-log p 大)——语义冗余的信号。"""
    sx, sy = set(x), set(y)
    a = len(sx & sy)   # 双现
    b = len(sx - sy)
    c = len(sy - sx)
    d = VOCAB - a - b - c
    N = a + b + c + d
    if N == 0:
        return 0.0
    # 词频加权:双现词的稀有度(用记忆内词频近似 IDF)
    mi = 0.0
    for w in sx & sy:
        fx = sum(1 for v in x if v == w) / len(x)
        fy = sum(1 for v in y if v == w) / len(y)
        # 联合 = 双现;边缘 = 各自词频——互信息项 = p·log(p/(px·py))
        p = 1.0 / N
        px = (fx * len(x) + 1) / (N + VOCAB)
        py = (fy * len(y) + 1) / (N + VOCAB)
        if p > 0 and px > 0 and py > 0:
            mi += p * math.log(p / (px * py))
    return mi


if __name__ == '__main__':
    print('=== exp30: 纠缠熵(互信息)记忆去重——信息论冗余 vs 文本相似度 ===')
    print('词表 200,8 主题;对比 Jaccard/cosine/互信息 在冗余对 vs 独立对上的区分\n')

    # 构造数据集:100 对冗余(同主题不同采样,含同义词替换)+ 100 对独立(不同主题)
    redundant = []
    independent = []
    for _ in range(100):
        t = rng.randint(N_TOPICS)
        m1 = sample_memory(t)
        # 冗余对:同主题,同义词替换 30%
        m2 = sample_memory(t, syn_ratio=0.3)
        redundant.append((m1, m2))
    for _ in range(100):
        t1, t2 = rng.choice(N_TOPICS, 2, replace=False)
        independent.append((sample_memory(t1), sample_memory(t2)))

    # 每种度量:冗余对 vs 独立对的均值 + 区分度(d 分数)
    print('%-14s %12s %12s %12s' % ('度量', '冗余对均值', '独立对均值', '区分度'))
    print('-' * 52)
    for name, fn in [('Jaccard', jaccard), ('cosine', cosine),
                     ('互信息(纠缠熵)', mutual_info)]:
        rv = [fn(x, y) for x, y in redundant]
        iv = [fn(x, y) for x, y in independent]
        mr, mi_ = np.mean(rv), np.mean(iv)
        sr, si = np.std(rv), np.std(iv)
        d = (mr - mi_) / np.sqrt((sr ** 2 + si ** 2) / 2) if (sr + si) > 0 else 0
        print('%-14s %12.4f %12.4f %12.2f' % (name, mr, mi_, d))

    # 阈值判定:用"各自均值中点"做阈值,算准确率
    print()
    print('--- 阈值判定准确率(区分冗余/独立) ---')
    for name, fn in [('Jaccard', jaccard), ('cosine', cosine),
                     ('互信息(纠缠熵)', mutual_info)]:
        rv = [fn(x, y) for x, y in redundant]
        iv = [fn(x, y) for x, y in independent]
        thr = (np.mean(rv) + np.mean(iv)) / 2
        acc = (sum(1 for v in rv if v > thr) + sum(1 for v in iv if v <= thr)) / 200
        print('%-14s 阈值 %.4f 准确率 %.1f%%' % (name, thr, acc * 100))

    print()
    print('=== 关键测试:语义等价字面不同(同义词替换 0/10/30/50%) ===')
    for ratio in [0.0, 0.1, 0.3, 0.5]:
        pairs = []
        for _ in range(100):
            t = rng.randint(N_TOPICS)
            pairs.append((sample_memory(t), sample_memory(t, syn_ratio=ratio)))
        js = np.mean([jaccard(x, y) for x, y in pairs])
        cs = np.mean([cosine(x, y) for x, y in pairs])
        mi = np.mean([mutual_info(x, y) for x, y in pairs])
        print('同义词率 %2d%%: Jaccard %.3f  cosine %.3f  互信息 %.6f' % (
            int(ratio * 100), js, cs, mi))

    print()
    print('=== 结论观察 ===')
    print('互信息(纠缠熵)是否在"语义等价字面不同"下保持高值(去重不漏)?')
    print('区分度 d 是否优于 Jaccard/cosine?')
