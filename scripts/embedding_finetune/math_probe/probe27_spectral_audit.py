#!/usr/bin/env python3
"""probe27 附加诊断：χ_max 异常的「谱标尺假说」检验

背景：py27 FSS 首跑里 χ_max 几乎不随 n 增长（a≈0，mean/median 均如此），
而 β_c 漂移干净（1/ν=1.56）。mean/median 对照已证伪「median 压峰」。
线索：χ = n·β·Var(m) 里的 β_peak 随 n 下降（2.72→1.36，×2），
χ/β ≈ n·Var(m) 从 10.9 涨到 21.5（×2），而配置模型图 λ_max 也从 ~0.6 到 ~1.2（×2）。

假说：峰高由谱尺度 λ_max（mean-field 的 T_c = 1/λ_max 精神）而非节点数控制——
  χ_max/β_peak ~ c · λ_max^α（待检 α = 1 or 2 or 3）。
做法：与 py27 同种子重建 6×4 张图，算 λ_max 与度矩，与 χ 峰对照。

Run: ../.venv/Scripts/python.exe probe27_spectral_audit.py
"""

import numpy as np

from probe27_fss import make_config_graph, deg_weight_pools, SIZES, GRAPH_REPS, GRAPH_SEED
from probe27_glauber import load_W

W = load_W()
deg, wp = deg_weight_pools(W)

lmax_all = {}
k2_over_k = {}
for n in SIZES:
    for rep in range(GRAPH_REPS):
        gseed = GRAPH_SEED + 1000 * n + rep
        rng = np.random.RandomState(gseed)
        Wg, pm, sl = make_config_graph(n, deg, wp, rng)
        ev = np.linalg.eigvalsh(Wg)
        lmax_all[(n, rep)] = ev.max()
        dvec = (Wg != 0).sum(axis=1).astype(float)
        k2_over_k[(n, rep)] = (dvec ** 2).sum() / dvec.sum()

d = np.loadtxt('py27_fss_output.csv', delimiter=',', skiprows=1, usecols=(0, 2, 7))
print("size |  lam_max (mean±sd) | chi_max(mean) | beta_pk |  chi/beta | lam^2  | <k^2>/<k>")
rows = []
for n in SIZES:
    lms = np.array([lmax_all[(n, r)] for r in range(GRAPH_REPS)])
    kks = np.array([k2_over_k[(n, r)] for r in range(GRAPH_REPS)])
    sub = d[d[:, 0] == n]
    betas = sorted(set(sub[:, 1]))
    means = np.array([sub[sub[:, 1] == b][:, 2].mean() for b in betas])
    im = int(np.argmax(means))
    chi_m = means[im]; b_pk = betas[im]
    rows.append((n, lms.mean(), lms.std(), chi_m, b_pk, chi_m / b_pk, lms.mean() ** 2, kks.mean()))
    print(f"{n:5d} | {lms.mean():8.4f} ± {lms.std():.3f} | {chi_m:12.2f} | {b_pk:7.3f} | {chi_m/b_pk:8.2f} | {lms.mean()**2:6.3f} | {kks.mean():6.2f}")

ns = np.array([r[0] for r in rows], float)
lm = np.array([r[1] for r in rows])
chi_b = np.array([r[5] for r in rows])
l2 = np.array([r[6] for r in rows])
kk = np.array([r[7] for r in rows])

print()
print("log-log slopes of chi/beta vs each scale candidate:")
for label, x in (("n", ns), ("lam_max", lm), ("lam_max^2", l2), ("<k2>/<k>", kk)):
    a = np.polyfit(np.log(x), np.log(chi_b), 1)[0]
    print(f"  chi/beta ~ {label:>10s}^a :  a = {a:6.3f}")
print()
print("(interpretation: a ~ 1.0-2.0 with lam_max would mean peak height is set")
print(" by the spectral scale, not by node count -- the 'effective size' is lambda)")

# ---------- part 2: export lambda table + per-rep theta-space peak analysis ----------
with open('r27_lmax_by_rep.csv', 'w', encoding='utf-8', newline='') as f:
    f.write("size,rep,lmax,k2_over_k\n")
    for n in SIZES:
        for rep in range(GRAPH_REPS):
            f.write(f"{n},{rep},{lmax_all[(n, rep)]:.6f},{k2_over_k[(n, rep)]:.4f}\n")
print()
print("exported r27_lmax_by_rep.csv")

print()
print("=== part 2: per-rep theta-space (theta = beta * lam_max) peak analysis ===")
d2 = np.loadtxt('py27_fss_output.csv', delimiter=',', skiprows=1, usecols=(0, 1, 2, 7))
theta_peaks = {}
chi_peaks = {}
for n in SIZES:
    tcs, cms = [], []
    for rep in range(GRAPH_REPS):
        sub = d2[(d2[:, 0] == n) & (d2[:, 1] == rep)]
        betas = np.array(sorted(set(sub[:, 2])))
        means = np.array([sub[sub[:, 2] == b][:, 3].mean() for b in betas])
        i = int(np.argmax(means))
        lam = lmax_all[(n, rep)]
        tc = betas[i] * lam
        if 0 < i < len(betas) - 1:
            xs = betas[i - 1:i + 2] * lam
            ys = means[i - 1:i + 2]
            coef = np.polyfit(xs, ys, 2)
            if coef[0] < 0:
                xv = -coef[1] / (2 * coef[0])
                if xs[0] <= xv <= xs[2]:
                    tc = xv
        tcs.append(tc)
        cms.append(means[i])
    theta_peaks[n] = float(np.mean(tcs))
    chi_peaks[n] = float(np.mean(cms))
    print(f"n={n:>3}: theta_c = {np.mean(tcs):.4f} +- {np.std(tcs):.4f} | chi_max = {np.mean(cms):7.2f}")

ns = np.array(SIZES, float)
th = np.array([theta_peaks[n] for n in SIZES])
best = None
for s in np.arange(0.05, 2.5, 0.002):
    x = ns ** (-s)
    A = np.vstack([np.ones_like(x), x]).T
    coef, *_ = np.linalg.lstsq(A, th, rcond=None)
    r2 = 1 - ((th - A @ coef) ** 2).sum() / ((th - th.mean()) ** 2).sum()
    if best is None or r2 > best[0]:
        best = (r2, s, coef[0], coef[1])
print()
print("theta_c drift: 1/nu_theta = %.3f  R2=%.4f  theta_inf = %.4f" % (best[1], best[0], best[2]))
print("(compare nominal-beta 1/nu = 1.56 -- the difference is the lambda-scale drift)")
