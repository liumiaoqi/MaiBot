#!/usr/bin/env python3
"""make_data_exp41.py -- exp41b 对拍材料：连接组边列表 + rng 复刻的初始状态。

导出到 data_exp41/：
  edges.csv          (上三角对称边: src, dst, w —— 279 网络)
  rowsum.csv         (W·1 的行和 —— 全 1 状态是否不动点的判据)
  inits.csv          (100 x 279, 复刻 exp41b 第一段循环的 rng 序列)
  behavior_groups.json (行为组 -> 索引)
  sub16_nodes.csv    (度数最高的 16 个节点索引)
  sub16_edges.csv    (子网边列表, 给 Wolfram 全枚举)

跑法: ../.venv/Scripts/python.exe make_data_exp41.py
"""
import json
import os
import sys

import numpy as np

TRADING = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, TRADING)
import exp41b_worm_attractors as E  # noqa: E402

Gs, names = E.load_connectome()
W = E.sym_normalize(Gs)
n = len(names)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_exp41")
os.makedirs(out, exist_ok=True)

# 1) 边列表（上三角）
rows, cols, vals = [], [], []
for i in range(n):
    for j in range(i + 1, n):
        if W[i, j] != 0:
            rows.append(i); cols.append(j); vals.append(W[i, j])
edges = np.column_stack([rows, cols, vals])
np.savetxt(os.path.join(out, "edges.csv"), edges, fmt=["%d", "%d", "%.12f"], delimiter=",")
print("edges:", len(rows))

# 2) 行和
np.savetxt(os.path.join(out, "rowsum.csv"), W.sum(axis=1), fmt="%.12f")
print("rowsum: min %.4f  n_negative %d / %d" % (W.sum(axis=1).min(), (W.sum(axis=1) < 0).sum(), n))

# 3) 复刻 exp41b 的 rng 流 -> 第一段的 100 个初始状态
rng = np.random.RandomState(42)
mask = W != 0
n_edges = int(mask.sum())
idxs = [(i, j) for i in range(n) for j in range(i + 1, n)]
W_rand = np.zeros_like(W)
for t in rng.choice(len(idxs), n_edges // 2, replace=False):
    i, j = idxs[t]
    w = rng.uniform(-1, 1)
    W_rand[i][j] = W_rand[j][i] = w
inits = np.array([rng.choice([-1.0, 1.0], n) for _ in range(100)])
np.savetxt(os.path.join(out, "inits.csv"), inits, fmt="%d", delimiter=",")
print("inits:", inits.shape)

# 4) 行为组索引
name2idx = {nm: i for i, nm in enumerate(names)}
bg = {}
for label, group in E.BEHAVIOR.items():
    bg[label] = [name2idx[nm] for nm in group if nm in name2idx]
with open(os.path.join(out, "behavior_groups.json"), "w", encoding="utf-8") as f:
    json.dump(bg, f, ensure_ascii=False, indent=1)

# 5) 子网（度数最高 16 节点）
deg = (W != 0).sum(axis=1)
top16 = np.argsort(-deg)[:16]
np.savetxt(os.path.join(out, "sub16_nodes.csv"), top16, fmt="%d")
sub_rows, sub_cols, sub_vals = [], [], []
for a, i in enumerate(top16):
    for b, j in enumerate(top16):
        if b > a and W[i, j] != 0:
            sub_rows.append(a); sub_cols.append(b); sub_vals.append(W[i, j])
np.savetxt(os.path.join(out, "sub16_edges.csv"),
           np.column_stack([sub_rows, sub_cols, sub_vals]) if sub_vals else np.zeros((0, 3)),
           fmt=["%d", "%d", "%.12f"], delimiter=",")
print("sub16 edges:", len(sub_rows), "| nodes:", list(top16))
