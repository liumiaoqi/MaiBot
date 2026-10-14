# -*- coding: utf-8 -*-
"""social_rel · s5.2 —— 扩散激活 × confidence：端到端排序评分

把 s5.1 的扩散激活（工作点 t≈4）接进排序：候选排序 = 激活值（× 痕迹派生 confidence），
与现状 2-hop 枚举对比。这是「方向 E」与「s3 排序靶子」的焊接实验。

评估（学 s3 的精神 + s5.1 的教训：指标必须与结构挂钩）：
  相关度 rel_i = 2^(-d_i)（d = 源到节点的 BFS 距离；结构化、连续）
  nDCG@5：每臂各自取 top-20 为池、评 top-5；理想排序按 rel 降序。

臂：
  a. base 2-hop（现状近似：候选=≤2 跳，按 距离升序+度降序）
  b. diffusion only（热核 e^{-Lt}，t ∈ {2,4,8}）
  c. diffusion × confidence（t=4 × 痕迹派生 conf；κ 扫 {0, 0.3, 0.5}）
     —— conf 结构同 R4：12% 节点带痕迹（t = κ·rel_z + √(1-κ²)·noise），conf = 0.3 + 0.7·sigmoid(t)

预登记判据：
  P1  diffusion（任一 t）nDCG@5 > base（扩散能改善结构排序）
  P2  κ=0 时 diffusion×conf ≤ diffusion（无真值时痕迹不该帮忙——负对照）
  P3  κ=0.5 时 diffusion×conf > diffusion（有真值时 confidence 有正增量）

Run: ../../.venv/Scripts/python.exe rank_diffusion.py
"""

import numpy as np

NPZ = r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/knn_graph_2500.npz'
N_SRC = 100
POOL = 20
K = 5
SEED = 20261014
COVER = 0.12          # 痕迹覆盖率（真库 22/184 的近似）
FLOOR = 0.3

d = np.load(NPZ)
edges = d['edges']
n = 2500
W = np.zeros((n, n))
for a, b in edges:
    W[a, b] = W[b, a] = 1.0

rng = np.random.RandomState(SEED)


def bfs_dist(src, maxd=12):
    dist = np.full(n, -1, dtype=int)
    dist[src] = 0
    frontier = [src]
    dd = 0
    while frontier and dd < maxd:
        nxt = []
        for u in frontier:
            for v in np.where(W[u] > 0)[0]:
                if dist[v] < 0:
                    dist[v] = dd + 1
                    nxt.append(v)
        frontier = nxt
        dd += 1
    return dist


def ndcg_at_k(top, dist, k=K):
    rel = 2.0 ** (-np.clip(dist[top], 0, 12).astype(float))
    gains = rel[:k]
    ideal = np.sort(2.0 ** (-np.clip(dist[dist >= 0], 0, 12).astype(float)))[::-1][:k]
    dcg = np.sum(gains / np.log2(np.arange(2, k + 2)))
    idcg = np.sum(ideal / np.log2(np.arange(2, k + 2)))
    return dcg / idcg if idcg > 0 else 0.0


def main():
    print("=== s5.2：扩散激活 × confidence 端到端排序 ===")
    srcs = rng.choice(n, N_SRC, replace=False)
    dists = {int(s): bfs_dist(int(s)) for s in srcs}
    print("BFS 就绪（%d 源）" % N_SRC)

    # 痕迹（全局 12% 覆盖；κ 在评估时可变）
    traced_mask = rng.random(n) < COVER
    rel_z = np.zeros(n)
    for s in srcs:
        dist = dists[int(s)]
        rel_z += np.where(dist >= 0, 2.0 ** (-np.clip(dist, 0, 12)), 0.0)
    rel_z /= len(srcs)
    rel_z = (rel_z - rel_z.mean()) / (rel_z.std() + 1e-9)

    def make_conf(kappa):
        t = np.zeros(n)
        m = traced_mask
        t[m] = kappa * rel_z[m] + np.sqrt(max(1 - kappa * kappa, 0.0)) * rng.normal(0, 1.0, m.sum())
        c = np.full(n, FLOOR)
        c[m] = FLOOR + (1 - FLOOR) / (1.0 + np.exp(-t[m]))
        return c

    confs = {k: make_conf(k) for k in (0.0, 0.3, 0.5, 0.7, 0.9)}

    deg = W.sum(1)
    vl, ul = np.linalg.eigh(np.diag(deg) - W)
    print("谱分解完成")

    results = {}

    def eval_arm(score_fn, name):
        nd = []
        for s in srcs:
            s = int(s)
            dist = dists[s]
            cand = np.where(dist >= 1)[0]          # 全体可达候选
            sc = score_fn(s, cand)
            order = np.argsort(-sc)[:POOL]
            top = cand[order[:K]]
            nd.append(ndcg_at_k(top, dist))
        results[name] = float(np.mean(nd))
        print("  %-28s nDCG@5 = %.4f" % (name, results[name]))

    # a. base 2-hop
    def base_sc(s, cand):
        return -(dists[s][cand].astype(float)) * 100.0 - deg[cand] * 0.01

    eval_arm(base_sc, "a. base 2-hop")

    # b. diffusion
    def diff_curve(vals, t):
        def fn(s, cand):
            p0 = np.zeros(n)
            p0[s] = 1.0
            coef = vals[1].T @ p0          # ⚠️ 特征向量矩阵投影（v1 曾误写 vals[0].T=特征值点积）
            p = vals[1] @ (np.exp(-vals[0] * t) * coef)
            return np.clip(p[cand], 1e-12, None)
        return fn

    for t in (2.0, 4.0, 8.0):
        eval_arm(diff_curve((vl, ul), t), "b. diffusion t=%.0f" % t)

    # c. diffusion × confidence
    for kappa in (0.0, 0.3, 0.5, 0.7, 0.9):
        c = confs[kappa]
        def fn(s, cand, c=c):
            p0 = np.zeros(n)
            p0[s] = 1.0
            coef = ul.T @ p0
            p = ul @ (np.exp(-vl * 4.0) * coef)
            return np.clip(p[cand], 1e-12, None) * c[cand]
        eval_arm(fn, "c. diff×conf κ=%.1f" % kappa)

    print()
    print("=== 判据核对（预登记）===")
    b_base = results["a. base 2-hop"]
    b_diff = max(results["b. diffusion t=%.0f" % t] for t in (2.0, 4.0, 8.0))
    c0 = results["c. diff×conf κ=0.0"]
    c5 = results["c. diff×conf κ=0.5"]
    c7 = results["c. diff×conf κ=0.7"]
    c9 = results["c. diff×conf κ=0.9"]
    d4 = results["b. diffusion t=4"]
    print("P1  diffusion(%.4f) > base(%.4f): %s" % (b_diff, b_base, b_diff > b_base))
    print("P2  κ=0 时 conf 臂(%.4f) ≤ 纯扩散(%.4f): %s" % (c0, d4, c0 <= d4 + 1e-9))
    print("P3  κ=0.5 时 conf 臂(%.4f) > 纯扩散(%.4f): %s" % (c5, d4, c5 > d4))
    print("P3+ 过零扫描：κ=0.7(%.4f) · κ=0.9(%.4f) vs 纯扩散(%.4f)" % (c7, c9, d4))
    print("（2026-10-14 · s5.2）")


if __name__ == "__main__":
    main()
