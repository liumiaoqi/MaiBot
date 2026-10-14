#!/usr/bin/env python3
"""exp65b: 真实语义图 v2——审计收口与"近邻迟到"深挖

v1（exp65）遗留三点，本版收口：
  ① α 的截断：d≥6 处 t_med 触顶 TMAX（24）—— 扩 TMAX 至 48 并自动剔除触顶点后重拟合
  ② 双源样本 30 对偏小 —— 扩至 100 对（判词给出双阈值：弱/强干涉）
  ③ 新观察"量子近邻首峰迟到"（d=1: 0.5 vs 0.2）—— 前 2.0 时间窗密扫，看首峰微结构
数据：同 exp65 的 kNN 语义图（math_probe/knn_graph_2500.npz，本机）
Run: ../.venv/Scripts/python.exe exp65b_real_graph_audit.py
"""

import numpy as np

NPZ = r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/knn_graph_2500.npz'
d = np.load(NPZ)
edges = d['edges']
n = 2500
W = np.zeros((n, n))
for a, b in edges:
    W[a, b] = W[b, a] = 1.0

rng = np.random.RandomState(20261014)
srcs = rng.choice(n, 300, replace=False)

TMAX = 48.0
TS = np.concatenate([np.geomspace(0.05, 2.0, 40), np.linspace(2.2, TMAX, 80)])
TS_EARLY = np.linspace(0.05, 3.0, 120)   # 早期密扫


def bfs_dist(src, maxd=15):
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


def evolve_curves(vals, vecs, src, ts, quantum):
    p0 = np.zeros(n)
    p0[src] = 1.0
    coef = vecs.T @ p0
    out = np.empty((len(ts), n))
    if quantum:
        for i, t in enumerate(ts):
            psi = vecs @ (np.exp(-1j * vals * t) * coef)
            out[i] = np.abs(psi) ** 2
    else:
        for i, t in enumerate(ts):
            p = vecs @ (np.exp(-vals * t) * coef)
            p = np.clip(p, 0, None)
            out[i] = p / p.sum()
    return out


def main():
    print("=== exp65b: 真实语义图 v2（审计收口）===")
    deg = W.sum(1)
    vq, uq = np.linalg.eigh(W)
    vl, ul = np.linalg.eigh(np.diag(deg) - W)
    print("谱宽: A %.2f | L %.2f | TMAX=%g" % (vq.max() - vq.min(), vl.max() - vl.min(), TMAX))
    print()

    # ① α 重拟合（TMAX=48，剔除触顶点）
    print("--- ① 首达 α（TMAX=48，自动剔除触顶点）---")
    for name, vals, vecs, quant in (("quantum", vq, uq, True), ("classical", vl, ul, False)):
        ds_all, th_all = [], []
        for s in srcs[:150]:
            dist = bfs_dist(s)
            P = evolve_curves(vals, vecs, int(s), TS, quant)
            for dd in range(1, 10):
                nodes = np.where(dist == dd)[0]
                if len(nodes) == 0:
                    continue
                curve = P[:, nodes].mean(axis=1)
                ds_all.append(dd)
                th_all.append(TS[int(np.argmax(curve))])
        ds_all = np.array(ds_all); th_all = np.array(th_all)
        keep = th_all < TMAX * 0.95   # 剔除触顶
        ds_k, th_k = ds_all[keep], th_all[keep]
        med = {}
        for dd in sorted(set(ds_k)):
            med[dd] = float(np.median(th_k[ds_k == dd]))
        dsx = np.array(sorted(med.keys()))
        thy = np.array([med[k] for k in dsx])
        alpha = float(np.polyfit(np.log(dsx), np.log(thy), 1)[0])
        print("  %-10s α = %.3f  (d→med: %s | 剔触顶 %d/%d 点)" % (
            name, alpha, {int(k): round(v, 1) for k, v in med.items()},
            int((~keep).sum()), len(ds_all)))
    print()

    # ② 双源分解（100 对）
    print("--- ② 双源分解（100 对邻接源，t=6）---")
    inter_max, dyn_max = [], []
    for _ in range(100):
        a = int(rng.choice(n))
        nb = np.where(W[a] > 0)[0]
        b = int(rng.choice(nb))
        t = 6.0
        p0a = np.zeros(n); p0b = np.zeros(n)
        p0a[a] = 1.0; p0b[b] = 1.0
        psia = uq @ (np.exp(-1j * vq * t) * (uq.T @ p0a))
        psib = uq @ (np.exp(-1j * vq * t) * (uq.T @ p0b))
        pq = np.abs((psia + psib) / np.sqrt(2)) ** 2
        p_inc = (np.abs(psia) ** 2 + np.abs(psib) ** 2) / 2
        p_inter = pq - p_inc
        pc_a = ul @ (np.exp(-vl * t) * (ul.T @ p0a)); pc_a = np.clip(pc_a, 0, None); pc_a /= pc_a.sum()
        pc_b = ul @ (np.exp(-vl * t) * (ul.T @ p0b)); pc_b = np.clip(pc_b, 0, None); pc_b /= pc_b.sum()
        pc = (pc_a + pc_b) / 2
        p_dyn = p_inc - pc
        inter_max.append(float(np.abs(p_inter).max()))
        dyn_max.append(float(np.abs(p_dyn).max()))
    mi, md = float(np.mean(inter_max)), float(np.mean(dyn_max))
    print("  |interference| mean %.4f (p95 %.4f) | |dyn-diff| mean %.4f (p95 %.4f)" % (
        mi, float(np.percentile(inter_max, 95)), md, float(np.percentile(dyn_max, 95))))
    ratio = mi / (md + 1e-12)
    verdict = ("强干涉（相干主导）" if ratio > 0.8 else ("中等（混合）" if ratio > 0.3 else "弱干涉（动力学差主导）"))
    print("  比值 inter/dyn = %.2f ⇒ %s" % (ratio, verdict))
    print()

    # ③ "近邻迟到"深挖：前 3.0 密扫，看 d=1..2 首峰时间分布
    print("--- ③ 前 3.0 时间窗密扫：d=1/2 首峰位置（50 源）---")
    for name, vals, vecs, quant in (("quantum", vq, uq, True), ("classical", vl, ul, False)):
        peak1, peak2 = [], []
        for s in srcs[:50]:
            dist = bfs_dist(s)
            P = evolve_curves(vals, vecs, int(s), TS_EARLY, quant)
            nodes1 = np.where(dist == 1)[0]
            nodes2 = np.where(dist == 2)[0]
            if len(nodes1):
                peak1.append(TS_EARLY[int(np.argmax(P[:, nodes1].mean(axis=1)))])
            if len(nodes2):
                peak2.append(TS_EARLY[int(np.argmax(P[:, nodes2].mean(axis=1)))])
        print("  %-10s d=1 首峰: med %.2f (p25 %.2f p75 %.2f) | d=2 首峰: med %.2f" % (
            name, float(np.median(peak1)), float(np.percentile(peak1, 25)),
            float(np.percentile(peak1, 75)), float(np.median(peak2))))
    print()
    print("=== 判词 ===")
    print("① 剔截断后 α 是否仍 量子<经典（方向稳健性）② 双源比值定位干涉强度档 ③ 近邻首峰差的形状（真实图上 '量子迟到' 是否系统性）")
    print("（2026-10-14 · A 线 v2）")


if __name__ == "__main__":
    main()
