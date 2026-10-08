#!/usr/bin/env python3
"""make_data_exp30.py -- exp30 对拍材料：词袋对数据集 + Python 基准度量。

导出到 data_exp30/：
  redundant.csv / independent.csv     (200 x 30, int 词 id 0..199, 前15=x 后15=y)
  syn00/10/30/50.csv                   (同上, 四档同义词率)
  constrained.csv                      (新增: 同主题低重合对——修正测试)
  sample_pair.csv                      (1 x 30, Wolfram 闭式对拍样例)
  py_metrics.csv                       (7 数据集 x [100 jaccard | 100 cosine | 100 mi])

跑法: ../.venv/Scripts/python.exe make_data_exp30.py
"""
import os
import sys

import numpy as np

TRADING = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, TRADING)
import exp30_entanglement_dedup as E  # noqa: E402

# --- 复刻 exp30 main 的构造顺序（同一 rng 流）---
redundant = []
for _ in range(100):
    t = E.rng.randint(E.N_TOPICS)
    redundant.append((E.sample_memory(t), E.sample_memory(t, syn_ratio=0.3)))

independent = []
for _ in range(100):
    t1, t2 = E.rng.choice(E.N_TOPICS, 2, replace=False)
    independent.append((E.sample_memory(t1), E.sample_memory(t2)))

syn = {}
for ratio in [0.0, 0.1, 0.3, 0.5]:
    pairs = []
    for _ in range(100):
        t = E.rng.randint(E.N_TOPICS)
        pairs.append((E.sample_memory(t), E.sample_memory(t, syn_ratio=ratio)))
    syn[ratio] = pairs


def sample_constrained(topic, avoid, n_words=15):
    """同主题低重合: 从主题分布采样但排除 avoid 词 (模拟'用不同的词说同一件事')。"""
    p = E.TOPICS[topic].copy()
    p[list(avoid)] = 0.0
    s = p.sum()
    if s <= 0:
        p = E.TOPICS[topic] / E.TOPICS[topic].sum()
    else:
        p = p / s
    return E.rng.choice(E.VOCAB, n_words, p=p)


constrained = []
for _ in range(100):
    t = E.rng.randint(E.N_TOPICS)
    m1 = E.sample_memory(t)
    m2 = sample_constrained(t, set(m1))
    constrained.append((m1, m2))

# --- 导出 ---
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_exp30")
os.makedirs(out, exist_ok=True)


def flatten(pairs):
    return np.array([list(x) + list(y) for x, y in pairs], dtype=int)


datasets = {"redundant": redundant, "independent": independent,
            "syn00": syn[0.0], "syn10": syn[0.1], "syn30": syn[0.3], "syn50": syn[0.5],
            "constrained": constrained}

for name, pairs in datasets.items():
    np.savetxt(os.path.join(out, name + ".csv"), flatten(pairs), fmt="%d", delimiter=",")

# Python 基准度量（用 exp30 原函数）
names = list(datasets.keys())
mat = np.zeros((len(names), 300))
for i, name in enumerate(names):
    ps = datasets[name]
    mat[i, :100] = [E.jaccard(x, y) for x, y in ps]
    mat[i, 100:200] = [E.cosine(x, y) for x, y in ps]
    mat[i, 200:] = [E.mutual_info(x, y) for x, y in ps]
np.savetxt(os.path.join(out, "py_metrics.csv"), mat, fmt="%.10f", delimiter=",")
with open(os.path.join(out, "py_metrics_names.txt"), "w", encoding="utf-8") as f:
    f.write("\n".join(names) + "\n")

# Wolfram 闭式对拍样例
xp, yp = redundant[0]
np.savetxt(os.path.join(out, "sample_pair.csv"), np.array([list(xp) + list(yp)]), fmt="%d", delimiter=",")
print("sample x:", list(xp))
print("sample y:", list(yp))
print("sample mi (python, exp30 impl): %.12f" % E.mutual_info(list(xp), list(yp)))
