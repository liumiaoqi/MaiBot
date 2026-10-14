#!/usr/bin/env python3
"""probe23_interference_numeric.py -- exp61 audit (numeric part):
   A. Δp decomposition: Δp = interference + dynamics-difference
   B. first-hit α indicator audit (TMAX / definition sensitivity)
   C. 2D-grid revival verification (is the 0.94 peak real, and source-stable?)
   Run: ../.venv/Scripts/python.exe probe23_interference_numeric.py
"""

import numpy as np

np.random.seed(20261014)

N = 64
TS = np.linspace(0.2, 24.0, 80)


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


def spec(W):
    vq, uq = np.linalg.eigh(W)
    deg = W.sum(1)
    vl, ul = np.linalg.eigh(np.diag(deg) - W)
    return (vq, uq), (vl, ul)


def psi_evolve(vals, vecs, src, t):
    n = len(vals)
    psi0 = np.zeros(n, dtype=complex)
    psi0[src] = 1.0
    coef = vecs.T @ psi0
    return vecs @ (np.exp(-1j * vals * t) * coef)


def p_evolve_classical(vals, vecs, src, t):
    n = len(vals)
    p0 = np.zeros(n)
    p0[src] = 1.0
    coef = vecs.T @ p0
    p = vecs @ (np.exp(-vals * t) * coef)
    p = np.clip(p, 0, None)
    return p / p.sum()


# ── A. Δp 分解 ─────────────────────────────────────────────────────────
def delta_decomposition(W, D, a, b, tcheck=6.0):
    """在若干时间点上分解：
       Δp = [p_q(2src) - p_inc(2src)]  +  [p_inc(2src) - p_cl(2src)]
            =    纯干涉项(相干-非相干)       +     动力学差项
    注意 p_inc = (|psi_a|^2 + |psi_b|^2)/2（量子单源的混合）"""
    (vq, uq), (vl, ul) = spec(W)
    ti = int(np.argmin(np.abs(TS - tcheck)))
    t = TS[ti]
    psia = psi_evolve(vq, uq, a, t)
    psib = psi_evolve(vq, uq, b, t)
    pq = np.abs((psia + psib) / np.sqrt(2)) ** 2
    p_inc = (np.abs(psia) ** 2 + np.abs(psib) ** 2) / 2
    p_inter = pq - p_inc                      # 纯干涉（同动力学内）
    pc = (p_evolve_classical(vl, ul, a, t) + p_evolve_classical(vl, ul, b, t)) / 2
    p_dyn = p_inc - pc                        # 动力学差（量子单源 vs 经典单源）
    delta = np.abs(pq - pc)
    return t, float(np.abs(p_inter).max()), float(np.abs(p_dyn).max()), float(delta.max())


# ── B. 首达 α 指标审计 ─────────────────────────────────────────────────
def first_hit_alpha(vals, vecs, D, n_src=16, tmax=24.0, thresh_frac=None):
    ts = np.linspace(0.2, tmax, int(tmax * 80 / 24) + 1)
    dmax = int(D[np.isfinite(D)].max())
    ds, th = [], []
    for d in range(1, dmax + 1):
        peaks = []
        for src in range(0, n_src):
            nodes = np.where(D[src] == d)[0]
            if len(nodes) == 0:
                continue
            if thresh_frac is None:
                curve = np.array([np.abs(psi_evolve(vals, vecs, src, t))[nodes].mean() ** 2 for t in ts])
                peaks.append(ts[int(np.argmax(curve))])
            else:
                # 阈值首达：组平均概率首次达到峰值 x frac 的时刻
                vals_curve = []
                for t in ts:
                    psi = psi_evolve(vals, vecs, src, t)
                    vals_curve.append(np.abs(psi)[nodes].mean() ** 2)
                vals_curve = np.array(vals_curve)
                pk = vals_curve.max()
                idx = np.where(vals_curve >= thresh_frac * pk)[0]
                peaks.append(ts[idx[0]] if len(idx) else tmax)
        if peaks:
            ds.append(d)
            th.append(float(np.median(peaks)))
    if len(ds) < 3:
        return float("nan")
    return float(np.polyfit(np.log(ds), np.log(th), 1)[0])


# ── C. 2D revival 验证 ────────────────────────────────────────────────
def revival_check(W):
    (vq, uq), _ = spec(W)
    n = W.shape[0]
    ts = np.linspace(0.2, 48.0, 480)
    out = {}
    for src in (0, 8, 27):
        pm = []
        for t in ts:
            psi = psi_evolve(vq, uq, src, t)
            pm.append(np.abs(psi).max() ** 2)
        pm = np.array(pm)
        i = int(np.argmax(pm))
        far = int(np.argmax(graph_dist(W)[src]))
        psi_pk = psi_evolve(vq, uq, src, ts[i])
        return_node = int(np.argmax(np.abs(psi_pk)))
        out[src] = (float(pm.max()), float(ts[i]), return_node, far)
    return out


def main():
    print("=== probe23: exp61 audit (numeric) ===")
    print()

    print("--- A. Δp decomposition at t=6: 纯干涉项 vs 动力学差项 ---")
    print("%-22s %10s %14s %12s %10s" % ("图", "t", "|interference|", "|dyn-diff|", "Δp=max"))
    print("-" * 74)
    graphs = [
        ("ER 随机", er_graph()),
        ("BA 无标度", ba_graph()),
        ("WS 小世界", ws_graph()),
        ("2D 格", grid2d()),
    ]
    store = {}
    for name, W in graphs:
        D = graph_dist(W)
        store[name] = (W, D)
        t, pi_max, pd_max, dl_max = delta_decomposition(W, D, 0, 1)
        print("%-22s %10.1f %14.4f %12.4f %10.4f" % (name, t, pi_max, pd_max, dl_max))
    print()
    print("判读：若 |interference| 量级 ≥ |dyn-diff| ⇒ exp61 的 Δp 主要来自相干项（真干涉）；")
    print("      否则主要是单源动力学差（量子 vs 经典本身的差异，不是'干涉'）。")
    print()

    print("--- B. 首达 α 指标审计（量子侧；定义/截断敏感性） ---")
    print("%-22s %12s %12s %12s" % ("图", "α(tmax=12)", "α(tmax=24)", "α(阈值0.5)"))
    print("-" * 62)
    for name, W in graphs:
        D = store[name][1]
        (vq, uq), _ = spec(W)
        a12 = first_hit_alpha(vq, uq, D, tmax=12.0)
        a24 = first_hit_alpha(vq, uq, D, tmax=24.0)
        a_t = first_hit_alpha(vq, uq, D, tmax=24.0, thresh_frac=0.5)
        print("%-22s %12.3f %12.3f %12.3f" % (name, a12, a24, a_t))
    print()
    print("判读：α 对截断/定义敏感 ⇒ 该指标只可作相对对照，不可当绝对标度读。")
    print()

    print("--- C. 2D 格 revival 验证（0.94 峰的真伪与源稳定性） ---")
    W = grid2d()
    out = revival_check(W)
    for src, (pk, tk, rn, far) in out.items():
        print("源 %-3d: max p_i(t) = %.4f @ t=%.1f | 峰值节点=%d | 该源最远节点=%d" % (src, pk, tk, rn, far))
    print()
    print("判读：若峰值节点 = 最远点且多源重现 ⇒ 结构性的 quasi-revival（可作'激活回声'候选）；")
    print("      若只有个别源出现 ⇒ 对称性特例，不进判据表。")


if __name__ == "__main__":
    main()
