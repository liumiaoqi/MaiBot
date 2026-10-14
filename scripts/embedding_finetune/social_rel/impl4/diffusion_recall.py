# -*- coding: utf-8 -*-
"""social_rel · s5.1（v2）—— 激活扩散版检索：结构指标版

v1 的教训（30 分钟前的自己）：用"随机 3 个目标"的 recall@5 做指标——池子太大，
top5 命中随机目标的概率 ≈ 0，连基线都测不出来。**召回实验的指标必须与结构挂钩。**

v2 指标（全部连续、不依赖随机目标）：
  A  平均图距离：top5 成员到源的平均 BFS 距离（基线被结构锁在 ≤2）
  B  远端触达率：top5 中 d≥3 的占比 %（基线结构上恒为 0——扩散的靶区）
  C  近端占比：top5 中 d≤2 的占比 %（权衡的另一端）

预登记判据：
  C1' 扩散臂的远端触达率 > 0 且随 t 单调上升；
  C2' 近端占比随 t 单调下降（权衡曲线存在）；
  C3' 存在工作点：远端触达 ≥40% 且近端占比 ≥50%（两者同时要）。

Run: ../../.venv/Scripts/python.exe diffusion_recall.py
"""

import numpy as np

NPZ = r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/knn_graph_2500.npz'
N_SRC = 100
K_TOP = 5
SEED = 20261014

d = np.load(NPZ)
edges = d['edges']
n = 2500
W = np.zeros((n, n))
for a, b in edges:
    W[a, b] = W[b, a] = 1.0

rng = np.random.RandomState(SEED)


def bfs_dist(src, maxd=8):
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


def main():
    print("=== s5.1 v2：激活扩散版检索（结构指标）===")
    print("图 knn_2500 | %d 源 | K=%d | 指标：top5 的 d 分布" % (N_SRC, K_TOP))
    srcs = rng.choice(n, N_SRC, replace=False)
    dists = {int(s): bfs_dist(int(s)) for s in srcs}
    print("BFS 距离表就绪")
    print()

    # 基线：2-hop 枚举（按 距离升序 + 度降序）
    mean_d, far_pct, near_pct = 0.0, 0.0, 0.0
    for s in srcs:
        s = int(s)
        dist = dists[s]
        cand = np.where((dist >= 1) & (dist <= 2))[0]
        order = np.lexsort((-W[cand].sum(1), dist[cand]))
        top = cand[order[:K_TOP]]
        dd = dist[top]
        mean_d += dd.mean()
        far_pct += 100.0 * (dd >= 3).mean()
        near_pct += 100.0 * (dd <= 2).mean()
    mean_d /= N_SRC; far_pct /= N_SRC; near_pct /= N_SRC

    print("%-14s %-6s %10s %10s %10s" % ("臂", "t", "mean_d", "far%", "near%"))
    print("-" * 56)
    print("%-14s %-6s %10.3f %9.1f%% %9.1f%%" % ("base 2-hop", "-", mean_d, far_pct, near_pct))
    print()

    deg = W.sum(1)
    vl, ul = np.linalg.eigh(np.diag(deg) - W)
    vq, uq = np.linalg.eigh(W)
    print("谱分解完成（L 与 A）")
    print()

    def arm_metrics(vals, vecs, quantum, t):
        md, fp, npc = 0.0, 0.0, 0.0
        for s in srcs:
            s = int(s)
            p0 = np.zeros(n)
            p0[s] = 1.0
            coef = vecs.T @ p0
            if quantum:
                psi = vecs @ (np.exp(-1j * vals * t) * coef)
                p = np.abs(psi) ** 2
            else:
                p = vecs @ (np.exp(-vals * t) * coef)
                p = np.clip(p, 0, None)
                p = p / p.sum()
            p[s] = -1
            top = np.argsort(-p)[:K_TOP]
            dd = dists[s][top]
            md += dd.mean()
            fp += 100.0 * (dd >= 3).mean()
            npc += 100.0 * (dd <= 2).mean()
        return md / N_SRC, fp / N_SRC, npc / N_SRC

    for t in (0.5, 1.0, 2.0, 4.0, 8.0):
        md, fp, npc = arm_metrics(vl, ul, False, t)
        print("%-14s %-6.1f %10.3f %9.1f%% %9.1f%%" % ("diffusion", t, md, fp, npc))
    for t in (0.5, 1.0, 2.0, 4.0):
        md, fp, npc = arm_metrics(vq, uq, True, t)
        print("%-14s %-6.1f %10.3f %9.1f%% %9.1f%%" % ("quantum walk", t, md, fp, npc))
    print()
    print("=== 判据（预登记）===")
    print("C1' 扩散远端触达率>0 且随 t 上升 | C2' 近端占比随 t 下降 | C3' 存在 t: far≥40% 且 near≥50%")
    print("（2026-10-14 · s5.1 v2 · 指标已修正）")


if __name__ == "__main__":
    main()
