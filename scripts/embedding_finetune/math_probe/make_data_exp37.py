#!/usr/bin/env python3
"""make_data_exp37.py -- 导出 exp37 的确定性对拍材料（CSV）。

复刻 exp37 的生成流程（同一 RNG 状态）：
  X (200x64 会话矩阵), centers (8x64), queries (96x64 + labels)
供 Wolfram / MATLAB 在同一份数据上逐位复现 exp37 的检索表与谱结构。

跑法（在 math_probe/ 下）：
  ../.venv/Scripts/python.exe make_data_exp37.py
"""
import os
import sys

import numpy as np

TRADING = r"E:/Users/lmq/MaiBot/scripts/embedding_finetune/trading"
sys.path.insert(0, TRADING)
import exp37_tensor_network_compression as E  # noqa: E402

X, centers = E.make_session()

# main 里的 queries 生成（rng 状态与 exp37 原版一致）
queries = []
for topic in range(E.N_TOPICS):
    for _ in range(12):
        queries.append((topic, centers[topic] + E.rng.normal(0, 0.3, E.D)))

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data_exp37")
os.makedirs(out, exist_ok=True)

np.savetxt(os.path.join(out, "X.csv"), X, delimiter=",", fmt="%.12f")
np.savetxt(os.path.join(out, "centers.csv"), centers, delimiter=",", fmt="%.12f")
qarr = np.stack([q for _, q in queries])
labs = np.array([t for t, _ in queries])
np.savetxt(os.path.join(out, "queries.csv"), qarr, delimiter=",", fmt="%.12f")
np.savetxt(os.path.join(out, "labels.csv"), labs, delimiter=",", fmt="%d")

sv = np.linalg.svd(X, compute_uv=False)
np.savetxt(os.path.join(out, "sigmas.csv"), sv, fmt="%.12f")

print("X:", X.shape, " queries:", qarr.shape)
print("sigmas[:16]:", " ".join(f"{s:.4f}" for s in sv[:16]))
print("sigma ratio s8/s9:", f"{sv[7]/sv[8]:.3f}")
# Marčenko-Pastur upper edge for the noise band (sigma=0.3, T=200, D=64)
mp = 0.3 * (np.sqrt(200) + np.sqrt(64))
print(f"MP upper edge ~ {mp:.3f}  (sigma*(sqrt(T)+sqrt(D)))")
