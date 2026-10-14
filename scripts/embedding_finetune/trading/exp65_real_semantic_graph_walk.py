#!/usr/bin/env python3
"""exp65: 真实语义图上的量子游走 vs 经典扩散（A 线深化）

数据：A_memorix graph 向量（1024d · 29260 条 · float16）→ 2500 节点 kNN 语义图
（k=6 无向化：10634 边 · 度均值 8.5 · 全连通）。
判据（对照 exp61 合成图族 + probe23 口径）：
  ① 首达 α：量子 vs 经典——真实图方向是否同合成图（量子<经典）
  ② 双源分解：纯干涉项 vs 动力学差——真实图更像 ER/BA（混合）还是对称图（零干涉）
  ③ 集中度对照（量子 revival 倾向）
流程遵循 AUDIT-CHECKLIST：源抽样（300/2500 · 固定种子 · 声明）· 谱宽声明 · 连通性已验。
Run: ../.venv/Scripts/python.exe exp65_real_semantic_graph_walk.py
"""

import numpy as np

NPZ = r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/knn_graph_2500.npz'
d = np.load(NPZ)
edges = d['edges']
n = 2500
W = np.zeros((n, n))
for a, b in edges:
    W[a, b] = W[b, a] = 1.0

TS = np.linspace(0.2, 24.0, 80)
rng = np.random.RandomState(20261014)
N_SRC = 300
srcs = rng.choice(n, N_SRC, replace=False)


def graph_dist_sample(W, src, maxd=12):
    """从 src 出发 BFS 距离（采样版）。"""
    dist = np.full(W.shape[0], -1, dtype=int)
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
    print("=== exp65: 真实语义图（A_memorix kNN · 2500 节点）上的量子游走 vs 经典扩散 ===")
    print("图: 10634 边 · 全连通 · 度均值 8.5 | 源抽样 %d/%d（固定种子）" % (N_SRC, n))
    deg = W.sum(1)
    vq, uq = np.linalg.eigh(W)                 # 量子：H = A
    vl, ul = np.linalg.eigh(np.diag(deg) - W)  # 经典：L
    print("谱宽: A %.2f (min %.3f max %.3f) | L %.2f" % (vq.max()-vq.min(), vq.min(), vq.max(), vl.max()-vl.min()))
    print()

    def psi_all(vals, vecs, src, quantum=True):
        n_ = len(vals)
        p0 = np.zeros(n_)
        p0[src] = 1.0
        coef = vecs.T @ p0
        out = np.empty((len(TS), n_))
        if quantum:
            for i, t in enumerate(TS):
                psi = vecs @ (np.exp(-1j * vals * t) * coef)
                out[i] = np.abs(psi) ** 2
        else:
            for i, t in enumerate(TS):
                p = vecs @ (np.exp(-vals * t) * coef)
                p = np.clip(p, 0, None)
                out[i] = p / p.sum()
        return out

    # ① 首达 α（按 BFS 距离，源抽样）
    print("--- ① 首达时间标度 α（抽样源，按图距离）---")
    alphas = {}
    for name, vals, vecs, quant in (("quantum", vq, uq, True), ("classical", vl, ul, False)):
        ds_all, th_all = [], []
        for sidx, s in enumerate(srcs):
            dist = graph_dist_sample(W, s)
            P = psi_all(vals, vecs, s, quantum=quant)
            for dd in range(1, 8):
                nodes = np.where(dist == dd)[0]
                if len(nodes) == 0:
                    continue
                curve = P[:, nodes].mean(axis=1)
                ds_all.append(dd)
                th_all.append(TS[int(np.argmax(curve))])
        ds_all = np.array(ds_all); th_all = np.array(th_all)
        med = {}
        for dd in sorted(set(ds_all)):
            med[dd] = float(np.median(th_all[ds_all == dd]))
        dsx = np.array(sorted(med.keys()))
        thy = np.array([med[k] for k in dsx])
        alpha = float(np.polyfit(np.log(dsx), np.log(thy), 1)[0])
        alphas[name] = alpha
        print("  %-10s α = %.3f   (d→t_med: %s)" % (name, alpha, {k: round(v, 1) for k, v in med.items()}))
    print("  => 方向对照 exp61（量子<经典 为预期）: %s" % ("成立" if alphas["quantum"] < alphas["classical"] else "**反转**"))
    print()

    # ② 双源分解（probe23 口径：纯干涉 vs 动力学差），抽样 30 对
    print("--- ② 双源分解（t=6，抽样 30 对，邻接源）---")
    inter_max, dyn_max = [], []
    for _ in range(30):
        a = int(rng.choice(n))
        nb = np.where(W[a] > 0)[0]
        b = int(rng.choice(nb))
        t = TS[int(np.argmin(np.abs(TS - 6.0)))]
        # 量子单源/双源
        p0a = np.zeros(n); p0a[a] = 1.0
        p0b = np.zeros(n); p0b[b] = 1.0
        ca = uq.T @ p0a; cb = uq.T @ p0b
        psia = uq @ (np.exp(-1j * vq * t) * ca)
        psib = uq @ (np.exp(-1j * vq * t) * cb)
        pq = np.abs((psia + psib) / np.sqrt(2)) ** 2
        p_inc = (np.abs(psia) ** 2 + np.abs(psib) ** 2) / 2
        p_inter = pq - p_inc
        cl_a = ul.T @ p0a; cl_b = ul.T @ p0b
        pc_a = ul @ (np.exp(-vl * t) * cl_a); pc_a = np.clip(pc_a, 0, None); pc_a /= pc_a.sum()
        pc_b = ul @ (np.exp(-vl * t) * cl_b); pc_b = np.clip(pc_b, 0, None); pc_b /= pc_b.sum()
        pc = (pc_a + pc_b) / 2
        p_dyn = p_inc - pc
        inter_max.append(float(np.abs(p_inter).max()))
        dyn_max.append(float(np.abs(p_dyn).max()))
    print("  |interference| max: mean %.4f (max %.4f)" % (np.mean(inter_max), np.max(inter_max)))
    print("  |dyn-diff|     max: mean %.4f (max %.4f)" % (np.mean(dyn_max), np.max(dyn_max)))
    print("  => 真实图更像: %s" % ("相干与动力学差混合（类 ER/BA）" if np.mean(inter_max) > 0.2 * np.mean(dyn_max) else "零干涉（类对称图）"))
    print()

    # ③ 集中度
    print("--- ③ 集中度（单源最大单点概率，抽样 50 源）---")
    cmax_q, cmax_c = 0.0, 0.0
    for s in rng.choice(n, 50, replace=False):
        s = int(s)
        Pq = psi_all(vq, uq, s, True)
        Pc = psi_all(vl, ul, s, False)
        cmax_q = max(cmax_q, float(Pq.max()))
        cmax_c = max(cmax_c, float(Pc.max()))
    print("  量子 %.4f vs 经典 %.4f" % (cmax_q, cmax_c))
    print()
    print("=== 判词 ===")
    print("真实语义图上的对照表（与 exp61 合成图族并排）：量子<经典 是否成立 / 干涉身份 / 集中度差")
    print("（2026-10-14 · A 线真实图版）")


if __name__ == "__main__":
    main()
