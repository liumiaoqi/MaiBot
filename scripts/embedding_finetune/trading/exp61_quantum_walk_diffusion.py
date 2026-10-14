#!/usr/bin/env python3
"""exp61 v2: 量子游走 vs 经典扩散——概念图上的激活动力学对照

v2 修订（对照 AUDIT-CHECKLIST 2026-10-14）：
  设计#3 数值可达性：v1 在饱和数据上拟合 r(t) 斜率（小图到不了纯标度）。
    → 核心指标改为【首达时间标度】：t_hit(d) ∝ d^α（弹道 α≈1 / 扩散 α≈2）。
  设计#4 对照口径：报两动力学谱宽作特征时间参照（时间尺度未对齐的声明）。
  设计#6 对照点密度：双源扫三档距离（邻/中/远）。
  设计#8 全枚举：单源改全 64 源平均（消源点选择偏差）。
  设计#1 最坏情况：连通性检查（非连通取大组件）。
工具：numpy 谱分解精确演化。audit 待办：三节点玩具验证"干涉"身份；2D 复活复验。
"""

import numpy as np

np.random.seed(20261014)

N = 64
STEPS = 80
TMAX = 24.0
TS = np.linspace(0.2, TMAX, STEPS)


# ── 四种图 ──────────────────────────────────────────────────────────────
def er_graph(n=N, avg_deg=6.0, seed=1):
    rng = np.random.RandomState(seed)
    p = avg_deg / (n - 1)
    W = (rng.random((n, n)) < p).astype(float)
    W = np.triu(W, 1)
    return W + W.T


def ba_graph(n=N, m=3, seed=2):
    rng = np.random.RandomState(seed)
    W = np.zeros((n, n))
    deg = np.zeros(n)
    for i in range(m):
        for j in range(i + 1, m):
            W[i, j] = W[j, i] = 1.0
            deg[i] += 1
            deg[j] += 1
    for i in range(m, n):
        probs = (deg[:i] + 1.0)
        probs = probs / probs.sum()
        chosen = rng.choice(i, size=m, replace=False, p=probs)
        for c in chosen:
            W[i, c] = W[c, i] = 1.0
            deg[i] += 1
            deg[c] += 1
    return W


def ws_graph(n=N, k=6, beta=0.1, seed=3):
    rng = np.random.RandomState(seed)
    W = np.zeros((n, n))
    for i in range(n):
        for j in range(1, k // 2 + 1):
            W[i, (i + j) % n] = 1.0
    W = np.triu(W, 1)
    W = W + W.T
    for i in range(n):
        for j in range(1, k // 2 + 1):
            if rng.random() < beta:
                b = (i + j) % n
                if W[i, b] == 0:
                    continue
                for _ in range(20):
                    cand = rng.randint(n)
                    if cand != i and W[i, cand] == 0:
                        W[i, b] = W[b, i] = 0.0
                        W[i, cand] = W[cand, i] = 1.0
                        break
    return W


def grid2d(side=8):
    n = side * side
    W = np.zeros((n, n))
    for r in range(side):
        for c in range(side):
            i = r * side + c
            for dr, dc in ((0, 1), (1, 0)):
                j = ((r + dr) % side) * side + (c + dc) % side
                W[i, j] = W[j, i] = 1.0
    return W


def graph_dist(W):
    n = W.shape[0]
    D = np.full((n, n), np.inf)
    np.fill_diagonal(D, 0.0)
    D[W > 0] = 1.0
    for k in range(n):
        D = np.minimum(D, D[:, k : k + 1] + D[k : k + 1, :])
    return D


def largest_component(W):
    """返回大组件的节点索引；若全连通则返回全部。"""
    n = W.shape[0]
    seen = np.zeros(n, dtype=bool)
    comps = []
    for s in range(n):
        if seen[s]:
            continue
        stack = [s]
        comp = []
        seen[s] = True
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in np.where(W[u] > 0)[0]:
                if not seen[v]:
                    seen[v] = True
                    stack.append(v)
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    return np.array(sorted(comps[0])), [len(c) for c in comps]


# ── 两种动力学（谱一次，全源复用） ──────────────────────────────────────
def spectra(W):
    deg = W.sum(1)
    vq, uq = np.linalg.eigh(W)              # CTQW: H = 邻接
    vl, ul = np.linalg.eigh(np.diag(deg) - W)  # 经典: L
    return vq, uq, vl, ul


def probs_for_source(vals, vecs, src, kind):
    n = len(vals)
    p0 = np.zeros(n)
    p0[src] = 1.0
    coef = vecs.T @ p0
    out = np.empty((len(TS), n))
    if kind == "quantum":
        for i, t in enumerate(TS):
            psi = vecs @ (np.exp(-1j * vals * t) * coef)
            out[i] = np.abs(psi) ** 2
    else:
        for i, t in enumerate(TS):
            p = vecs @ (np.exp(-vals * t) * coef)
            p = np.clip(p, 0, None)
            out[i] = p / p.sum()
    return out


def first_hit_alpha(D, probs_by_src):
    """首达时间标度：对每个图距离 d，取该距离所有节点(全源平均)的峰值时刻中位数，
    拟合 log t_hit vs log d 的斜率 α（弹道≈1，扩散≈2）。"""
    dmax = int(D[D < np.inf].max())
    if dmax < 2:
        return float("nan"), []
    ds, thits = [], []
    for d in range(1, dmax + 1):
        peaks = []
        for src, P in probs_by_src.items():
            nodes = np.where(D[src] == d)[0]
            if len(nodes) == 0:
                continue
            curve = P[:, nodes].mean(axis=1)
            peaks.append(TS[int(np.argmax(curve))])
        if not peaks:
            continue
        ds.append(d)
        thits.append(float(np.median(peaks)))
    if len(ds) < 3:
        return float("nan"), list(zip(ds, thits))
    alpha = float(np.polyfit(np.log(ds), np.log(thits), 1)[0])
    return alpha, list(zip(ds, thits))


def two_source_delta(vals, vecs, kind, a, b):
    n = len(vals)
    p0 = np.zeros(n)
    p0[a] = 1.0 / np.sqrt(2) if kind == "quantum" else 0.5
    p0[b] = 1.0 / np.sqrt(2) if kind == "quantum" else 0.5
    coef = vecs.T @ p0
    best = 0.0
    peak = np.empty((len(TS), n))
    if kind == "quantum":
        for i, t in enumerate(TS):
            psi = vecs @ (np.exp(-1j * vals * t) * coef)
            peak[i] = np.abs(psi) ** 2
    else:
        for i, t in enumerate(TS):
            p = vecs @ (np.exp(-vals * t) * coef)
            p = np.clip(p, 0, None)
            peak[i] = p / p.sum()
    return peak


def main():
    print("=== exp61 v2: 量子游走 vs 经典扩散（首达时间标度版） ===")
    print("对照 AUDIT-CHECKLIST 修订：全源枚举 · 首达时间标度 · 双源扫距 · 连通性检查")
    print(f"N={N} · T={TS[0]:.1f}~{TS[-1]:.1f} · 量子=CTQW e^(-iAt) · 经典=热扩散 e^(-Lt)\n")

    graphs = [
        ("ER 随机(avg_deg≈6)", er_graph()),
        ("BA 无标度(m=3)", ba_graph()),
        ("WS 小世界(k=6,β=0.1)", ws_graph()),
        ("2D 格(8x8 周期)", grid2d()),
    ]

    print("%-24s %8s %10s %10s %10s %10s" % ("图", "连通", "经典α", "量子α", "谱宽A", "谱宽L"))
    print("-" * 78)
    details = []
    for name, W in graphs:
        comp, sizes = largest_component(W)
        conn = "全连通" if len(comp) == W.shape[0] else f"大组件{len(comp)}/{W.shape[0]}"
        if len(comp) < W.shape[0]:
            W = W[np.ix_(comp, comp)]
        D = graph_dist(W)
        vq, uq, vl, ul = spectra(W)
        bw_a = float(vq.max() - vq.min())
        bw_l = float(vl.max() - vl.min())
        n = W.shape[0]
        pq = {s: probs_for_source(vq, uq, s, "quantum") for s in range(n)}
        pc = {s: probs_for_source(vl, ul, s, "classical") for s in range(n)}
        aq, _ = first_hit_alpha(D, pq)
        ac, _ = first_hit_alpha(D, pc)
        conc_q = max(P.max() for P in pq.values())
        conc_c = max(P.max() for P in pc.values())
        details.append((name, W, D, vq, uq, vl, ul, pq, pc, aq, ac))
        print("%-24s %8s %10.3f %10.3f %10.2f %10.2f" % (name, conn, ac, aq, bw_a, bw_l))

    print()
    print("（α = 首达时间对图距离的标度指数；经典扩散期望≈2，量子弹道期望≈1）")
    print()

    print("=== 双源干涉扫距（邻 d=1 / 中距 / 对径；量子 vs 经典 概率最大差） ===")
    print("%-24s %12s %12s %12s" % ("图", "邻 d=1", "中距", "对径"))
    print("-" * 66)
    for name, W, D, vq, uq, vl, ul, pq, pc, aq, ac in details:
        n = W.shape[0]
        dmax = int(D[0][np.isfinite(D[0])].max())
        pairs = [(0, 1)]
        mid = int(np.argmax((D[0] == max(1, dmax // 2)).astype(int)))
        pairs.append((0, mid))
        far = int(np.argmax(D[0]))
        pairs.append((0, far))
        row = []
        for a, b in pairs:
            if a == b:
                row.append(float("nan"))
                continue
            Pq = two_source_delta(vq, uq, "quantum", a, b)
            Pc = two_source_delta(vl, ul, "classical", a, b)
            row.append(float(np.abs(Pq - Pc).max()))
        print("%-24s %12.4f %12.4f %12.4f" % (name, row[0], row[1], row[2]))

    print()
    print("=== 集中度（全局最大单点概率，全源最大） ===")
    for name, W, D, vq, uq, vl, ul, pq, pc, aq, ac in details:
        print("%-24s 量子 %.4f   经典 %.4f" % (name, max(P.max() for P in pq.values()), max(P.max() for P in pc.values())))

    print()
    print("=== 落地判断 ===")
    print("α 差（量子<经典）⇒ 量子激活前沿'弹道推进'，经典'扩散铺开'——两种激活形状")
    print("若某图 α 两者接近 ⇒ 该图结构支持不了量子优势（结构判据表条目）")
    print("双源 Δp 随源距的形态 ⇒ '干涉'是否只发生在短程（audit 三节点玩具待做）")
    print("信号本身不结论化：本实验产出的是对照表，判词归 probe")


if __name__ == "__main__":
    main()
