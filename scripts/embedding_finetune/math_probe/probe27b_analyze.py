#!/usr/bin/env python3
"""probe27b 分析器：双口径 FSS（名义 β vs θ=β·λ_max）+ 峰定位降噪

对每 (size, rep)：
  · 剖面 mean chi(β) → 五点二次拟合（argmax ±2 窗）→ β_peak、χ_peak
  · bootstrap（96 runs 重采样 B=300，向量化）→ 峰位分布
  · θ_peak = β_peak × λ_max(size, rep)（λ 现场重建，与建图同种子）
跨 rep 汇总：点估计 = rep 均值；CI = 池化 bootstrap 的 [2.5%, 97.5%]
拟合（网格扫描法）：名义 1/ν · θ 口径 1/ν_θ · χ/β ~ λ^a

用法：
  python probe27b_analyze.py          # 默认 py27b_fss_output.csv（10 尺寸）
  python probe27b_analyze.py --v1    # 对旧 py27_fss_output.csv 跑同一分析（自测/对照）
"""

import sys

import numpy as np

from probe27_glauber import load_W
from probe27b_fss import (build_graph as build_graph_b, deg_weight_pools,
                          SIZES as SIZES_V2)
from probe27c_fss import build_graph as build_graph_c, SIZES as SIZES_V3

V1_SIZES = (40, 60, 90, 130, 190, 279)
B = 300


def peak5(xs, ys):
    """argmax ±2 窗内的二次拟合峰；失败回落 argmax。"""
    i = int(np.argmax(ys))
    lo = max(0, i - 2)
    hi = min(len(xs), i + 3)
    if hi - lo >= 3:
        coef = np.polyfit(xs[lo:hi], ys[lo:hi], 2)
        if coef[0] < 0:
            xv = -coef[1] / (2 * coef[0])
            if xs[lo] <= xv <= xs[hi - 1]:
                return float(xv)
    return float(xs[i])


def analyze(csv_names, sizes, rng_seed=42):
    if isinstance(csv_names, str):
        csv_names = [csv_names]
    d = np.vstack([np.loadtxt(c, delimiter=',', skiprows=1, usecols=(0, 1, 2, 7))
                   for c in csv_names])
    W = load_W()
    deg, wp = deg_weight_pools(W)
    lmax = {}
    for n in sizes:
        bg = build_graph_b if n in SIZES_V2 else build_graph_c
        reps_here = sorted(set(d[d[:, 0] == n][:, 1].astype(int)))
        for rep in reps_here:
            Wg, _, _ = bg(n, rep, deg, wp)
            lmax[(n, rep)] = np.linalg.eigvalsh(Wg).max()

    rng = np.random.RandomState(rng_seed)
    print(f"=== analysis: {', '.join(csv_names)} ({len(sizes)} sizes, B={B}) ===")
    print(f"{'n':>4} {'beta_c':>8} {'theta_c':>8} {'chi_pk':>7} {'chi/beta':>9} "
          f"{'lam_max':>8} | theta_c 95% CI")
    res = []
    pools = {}
    for n in sizes:
        pt_beta, pt_theta, pt_chi = [], [], []
        pool_theta = []
        pool_beta = []
        lams = []
        reps_here = sorted(set(d[d[:, 0] == n][:, 1].astype(int)))
        for rep in reps_here:
            sub = d[(d[:, 0] == n) & (d[:, 1] == rep)]
            betas = np.array(sorted(set(sub[:, 2])))
            runs = {b: sub[sub[:, 2] == b][:, 3] for b in betas}
            lam = lmax[(n, rep)]
            lams.append(lam)
            means = np.array([runs[b].mean() for b in betas])
            bp = peak5(betas, means)
            pt_beta.append(bp)
            pt_theta.append(bp * lam)
            pt_chi.append(means[int(np.argmax(means))])
            bm = {b: rng.choice(runs[b], size=(B, len(runs[b])),
                                replace=True).mean(axis=1) for b in betas}
            for j in range(B):
                ys = np.array([bm[b][j] for b in betas])
                xv = peak5(betas, ys)
                pool_theta.append(xv * lam)
                pool_beta.append(xv)

        beta_c = float(np.mean(pt_beta))
        theta_c = float(np.mean(pt_theta))
        chi_pk = float(np.mean(pt_chi))
        lam_m = float(np.mean(lams))
        pools[n] = (np.array(pool_beta), np.array(pool_theta))
        lo, hi = np.percentile(np.array(pool_theta), [2.5, 97.5])
        res.append((n, beta_c, theta_c, chi_pk, chi_pk / beta_c, lam_m))
        print(f"{n:>4} {beta_c:8.4f} {theta_c:8.4f} {chi_pk:7.2f} {chi_pk/beta_c:9.2f} "
              f"{lam_m:8.4f} | [{lo:.3f}, {hi:.3f}]")
    return res, pools


def fit_scan(sizes, vals, s_range=(0.05, 2.5)):
    ns = np.array(sizes, float)
    vals = np.array(vals, float)
    best = None
    for s in np.arange(s_range[0], s_range[1], 0.002):
        x = ns ** (-s)
        A = np.vstack([np.ones_like(x), x]).T
        coef, *_ = np.linalg.lstsq(A, vals, rcond=None)
        r2 = 1 - ((vals - A @ coef) ** 2).sum() / ((vals - vals.mean()) ** 2).sum()
        if best is None or r2 > best[0]:
            best = (r2, s, coef[0])
    return best  # (r2, 1/nu, asymptote)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "--v1":
        res, pools = analyze('py27_fss_output.csv', V1_SIZES)
    elif mode == "--combined":
        res, pools = analyze(['py27b_fss_output.csv', 'py27c_fss_output.csv'],
                             tuple(SIZES_V2) + tuple(SIZES_V3))
    else:
        res, pools = analyze('py27b_fss_output.csv', SIZES_V2)
    sizes = [r[0] for r in res]
    r2b, snb, binf = fit_scan(sizes, [r[1] for r in res])
    r2t, snt, tinf = fit_scan(sizes, [r[2] for r in res])

    # NOTE on uncertainty: the R2-scan objective is nonconvex and its bootstrap is
    # degenerate (samples hop branches / pin to window edges), and curve fits on
    # N=6..10 points have unreliable asymptotic errors. We therefore report a
    # SENSITIVITY band: leave-one-out refits (+ per-size theta_c CI from the
    # run-level bootstrap above, which is within-graph only).
    loo_b, loo_t = [], []
    for k in range(len(sizes)):
        sk = [s for j, s in enumerate(sizes) if j != k]
        vb = [r[1] for j, r in enumerate(res) if j != k]
        vt = [r[2] for j, r in enumerate(res) if j != k]
        loo_b.append(fit_scan(sk, vb)[1])
        loo_t.append(fit_scan(sk, vt)[1])

    print()
    print(f"nominal beta_c drift: 1/nu = {snb:.3f}  R2={r2b:.4f}  "
          f"LOO range [{min(loo_b):.3f}, {max(loo_b):.3f}]  beta_inf = {binf:.4f}")
    print(f"theta_c drift       : 1/nu_theta = {snt:.3f}  R2={r2t:.4f}  "
          f"LOO range [{min(loo_t):.3f}, {max(loo_t):.3f}]  theta_inf = {tinf:.4f}")
    kb0, kb1 = int(np.argmin(loo_b)), int(np.argmax(loo_b))
    kt0, kt1 = int(np.argmin(loo_t)), int(np.argmax(loo_t))
    print(f"  [sensitivity] nominal driven by n={sizes[kb0]}(->{min(loo_b):.2f}) / "
          f"n={sizes[kb1]}(->{max(loo_b):.2f}); theta by n={sizes[kt0]}(->{min(loo_t):.2f}) / "
          f"n={sizes[kt1]}(->{max(loo_t):.2f})")
    lm = np.array([r[5] for r in res])
    cb = np.array([r[4] for r in res])
    a = np.polyfit(np.log(lm), np.log(cb), 1)
    # log-space R2 (matches the R-side convention: summary(lm(log y ~ log x)))
    pred_log = np.polyval(a, np.log(lm))
    r2a = 1 - ((np.log(cb) - pred_log) ** 2).sum() / \
        ((np.log(cb) - np.log(cb).mean()) ** 2).sum()
    print(f"chi/beta ~ lam_max^a : a = {a[0]:.3f}  R2(log-space)={r2a:.4f}")


if __name__ == "__main__":
    main()
