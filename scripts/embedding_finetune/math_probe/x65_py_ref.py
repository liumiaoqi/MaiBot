# -*- coding: utf-8 -*-
"""x65_py_ref: s5.x 的 python 侧参照（与 x65_diffusion_rank_crosscheck.wl 对拍）"""
import numpy as np

# ① 6 节点路径图热核
n = 6
W = np.zeros((n, n))
for i in range(n - 1):
    W[i, i + 1] = W[i + 1, i] = 1.0
deg = W.sum(1)
L = np.diag(deg) - W
vals, vecs = np.linalg.eigh(L)
p0 = np.zeros(n)
p0[0] = 1.0
coef = vecs.T @ p0
p = vecs @ (np.exp(-vals * 1.0) * coef)
print("p   = " + " ".join(f"{x:.8f}" for x in p))
print(f"sum = {p.sum():.8f}")

# ② nDCG@5
ds = np.array([1.0, 2, 2, 3, 5])
g = 2.0 ** (-ds)
dcg = np.sum(g / np.log2(np.arange(2, 7)))
idcg = np.sum(np.sort(g)[::-1] / np.log2(np.arange(2, 7)))
print(f"DCG = {dcg:.8f}  IDCG = {idcg:.8f}  nDCG = {dcg / idcg:.8f}")
