#!/usr/bin/env python3
"""probe28 — 「我们图的松弛谱系」探针（T7b 提案首跑）

对象：`knn_graph_2500.npz`（语义 kNN 图：n=2500、边 10634、度 6–29、均值 8.5）
对照：ER 随机图（同 n / 同平均度）· 50×50 周期格（度 4）

预登记判据（先写后跑 —— 线纪律）：
  E1 谱隙：随机游走转移 P = D^-1 A 的 λ₂；gap = 1-|λ₂|（读数——松弛速度的数）
  E2 混合曲线：单点扩散 TV(t)（对稳态 π = deg/2m）；30 个随机源取中位数曲线；
     记 t10 / t50 / t90（TV 首次 ≤ 0.9 / 0.5 / 0.1）；
     cut 比率 = (t90 - t10) / t50：< 1 记「急变型」，> 2 记「渐进型」（本次口径）
  E3 谱统计：邻接矩阵 bulk 谱（去两端各 10%）的 spacing ratio r；
     对照值 GOE ≈ 0.5307 · Poisson ≈ 0.386（±0.03 内记「接近」）
  E4 对照臂同管线：ER（GOE 端候选）· 周期格（revival 端）

诚实边界：knn 图是几何/语义图——预期既非纯 GOE 也非 Poisson；本实验回答「偏哪边、多远」。
"""
import numpy as np

rng = np.random.default_rng(20261015)


# ---------- 构造 ----------
def build_knn(n=2500):
    d = np.load('knn_graph_2500.npz')
    e = d['edges']
    A = np.zeros((n, n))
    A[e[:, 0], e[:, 1]] = 1.0
    A[e[:, 1], e[:, 0]] = 1.0
    return A


def build_er(n=2500, kbar=8.5):
    p = kbar / (n - 1)
    U = (rng.random((n, n)) < p)
    U = np.triu(U, 1)
    A = U + U.T
    return A.astype(float)


def build_lattice(L=50):
    n = L * L
    A = np.zeros((n, n))
    for i in range(L):
        for j in range(L):
            a = i * L + j
            for di, dj in ((0, 1), (1, 0)):
                b = ((i + di) % L) * L + ((j + dj) % L)
                A[a, b] = A[b, a] = 1.0
    return A


# ---------- 指标 ----------
def spec_gap(A):
    deg = A.sum(1)
    P = A / deg[:, None]
    vals = np.linalg.eigvals(P)
    mag = np.sort(np.abs(vals))[::-1]
    return mag[0], mag[1], 1.0 - mag[1]


def mixing_curve(A, nsrc=30, tmax=300):
    n = len(A)
    deg = A.sum(1)
    pi = deg / deg.sum()
    P = A / deg[:, None]
    srcs = rng.choice(n, nsrc, replace=False)
    curves = np.zeros((nsrc, tmax + 1))
    for si, s in enumerate(srcs):
        p = np.zeros(n)
        p[s] = 1.0
        for t in range(tmax + 1):
            curves[si, t] = 0.5 * np.abs(p - pi).sum()
            if t < tmax:
                p = p @ P
    med = np.median(curves, axis=0)
    def hit(level):
        idx = np.where(med <= level)[0]
        return int(idx[0]) if len(idx) else -1
    return med, hit(0.9), hit(0.5), hit(0.1)


def spacing_ratio(A):
    w = np.linalg.eigvalsh(A)
    w = np.sort(w)
    k = int(0.1 * len(w))
    core = w[k:-k]
    s = np.diff(core)
    s = s[s > 1e-12]
    r = np.minimum(s[:-1], s[1:]) / np.maximum(s[:-1], s[1:])
    return float(np.mean(r))


# ---------- 主流程 ----------
print("=" * 72)
print("probe28 · 松弛谱系（预登记判据见 docstring）")
print("=" * 72)

for name, A in (("knn_graph_2500", build_knn()),
                ("ER (kbar=8.5)", build_er()),
                ("50x50 torus", build_lattice())):
    print(f"\n### {name}  (n={len(A)}, edges={int(A.sum()//2)}, K={A.sum()/len(A):.2f})")
    l1, l2, gap = spec_gap(A)
    print(f"  E1 λ₁={l1:.6f}  λ₂={l2:.6f}  gap=1-|λ₂|={gap:.6f}")
    med, t10, t50, t90 = mixing_curve(A)
    if t10 >= 0 and t50 > 0:
        ratio = (t90 - t10) / t50 if t90 >= 0 else float('nan')
        shape = "急变型" if ratio < 1 else ("渐进型" if ratio > 2 else "中间型")
        print(f"  E2 t10≈{t10}  t50≈{t50}  t90≈{t90}  (t90-t10)/t50={ratio:.2f} → {shape}")
    else:
        print(f"  E2 未达阈值（t10={t10}, t50={t50}, t90={t90}）——可能样本不够或图太慢")
    print(f"     TV(0)={med[0]:.4f}  TV(10)={med[10]:.4f}  TV(50)={med[50]:.4f}  TV(150)={med[150]:.4f}")
    r = spacing_ratio(A)
    tag = "≈GOE" if abs(r - 0.5307) < 0.03 else ("≈Poisson" if abs(r - 0.386) < 0.03 else "两者之间")
    print(f"  E3 spacing ratio r={r:.4f}  (GOE 0.5307 | Poisson 0.386) → {tag}")

print("\ndone. (2026-10-15, probe28)")
