#!/usr/bin/env python3
"""probe27 附加分析：χ/β 峰高的标度审计（a 的理论落点候选）

背景：χ/β ~ λ_max^1.59（16 点数据集，见 NOTES probe27 节）。本脚本做三组检验：

  ① 双变量分解  log(χ/β) ~ log(n) + log(λ_max)
     → 判定 n 与 λ 的独立贡献（两者共线：λ~n^0.24，分解结果解读需谨慎）
  ② 三变量      + log(⟨k⁴⟩) 或 + log(k_max)
     → 高阶矩（重尾的直接表征）是否有增量贡献
  ③ 单变量对照  ~ (⟨k²⟩/⟨k⟩)^b（配置模型 T_c 的控制量）+ LOO

结论（2026-10-14 实测）：
  · n/λ 分解对称（0.26/0.27）但不能稳健分离（共线）；
  · ⟨k⁴⟩/k_max 无增量（R² 仅 +0.001）——不是独立驱动力；
  · (⟨k²⟩/⟨k⟩)^1.70（R²=0.86，LOO [1.62,1.97]）——「平方」是候选落点，
    数据限定在 1.7~2.0 带；与 λ_max^1.76 同带（两标度量强相关）。

Run: ../.venv/Scripts/python.exe probe27_a_theory_audit.py
"""

import numpy as np

from probe27_glauber import load_W
from probe27b_fss import build_graph as bg_b, deg_weight_pools, SIZES as SIZES_B
from probe27c_fss import build_graph as bg_c, SIZES as SIZES_C
import hard_random  # noqa: F401  (keep import list consistent with siblings)


def load_peaks():
    """每尺寸的 χ/β 峰值（跨 rep 混合 mean，与分析器主口径同源）。"""
    cb = {}
    for f in ('py27b_fss_output.csv', 'py27c_fss_output.csv'):
        d = np.loadtxt(f, delimiter=',', skiprows=1, usecols=(0, 1, 2, 7))
        for n in sorted(set(d[:, 0].astype(int))):
            betas = sorted(set(d[d[:, 0] == n][:, 2]))
            cb[n] = max(np.mean(d[(d[:, 0] == n) & (d[:, 2] == b)][:, 3]) / b
                        for b in betas)
    return cb


def graph_moments():
    """每尺寸的 (λ_max, ⟨k⁴⟩, k_max, ⟨k²⟩/⟨k⟩)（跨 rep 均值，与建图同种子）。"""
    W = load_W()
    deg, wp = deg_weight_pools(W)
    out = {}
    for n in tuple(SIZES_B) + tuple(SIZES_C):
        bg = bg_b if n in SIZES_B else bg_c
        reps = range(4) if n in SIZES_B else range(3)
        lm, k4, km, k2k = [], [], [], []
        for rep in reps:
            Wg, _, _ = bg(n, rep, deg, wp)
            dv = (Wg != 0).sum(axis=1).astype(float)
            lm.append(np.linalg.eigvalsh(Wg).max())
            k4.append((dv ** 4).mean())
            km.append(dv.max())
            k2k.append((dv ** 2).sum() / dv.sum())
        out[n] = (np.mean(lm), np.mean(k4), np.mean(km), np.mean(k2k))
    return out


def fit(names, xs, y):
    X = np.vstack([np.ones_like(y)] + [np.log(x) for x in xs]).T
    coef, *_ = np.linalg.lstsq(X, np.log(y), rcond=None)
    pred = X @ coef
    r2 = 1 - ((np.log(y) - pred) ** 2).sum() / ((np.log(y) - np.log(y).mean()) ** 2).sum()
    print('  log(chi/beta) = %.3f + %s   R2=%.4f'
          % (coef[0], ' + '.join('%.3f*log(%s)' % (c, l) for c, l in zip(coef[1:], names)), r2))
    return coef, r2


def load_betas():
    """每尺寸的 β_c（峰位，跨 rep 平均）。"""
    bc = {}
    for f in ('py27b_fss_output.csv', 'py27c_fss_output.csv'):
        d = np.loadtxt(f, delimiter=',', skiprows=1, usecols=(0, 1, 2, 7))
        for n in sorted(set(d[:, 0].astype(int))):
            reps = sorted(set(d[d[:, 0] == n][:, 1].astype(int)))
            bcs = []
            for r in reps:
                sub = d[(d[:, 0] == n) & (d[:, 1] == r)]
                betas = sorted(set(sub[:, 2]))
                means = np.array([np.mean(sub[sub[:, 2] == b][:, 3]) for b in betas])
                bcs.append(betas[int(np.argmax(means))])
            bc[n] = float(np.mean(bcs))
    return bc


def dgm_quantitative():
    """DGM 定量对账：Eq.1（用每尺寸截断矩）→ T_c(n) 预测 vs 实测；1/Tc ∝ λ 检验。"""
    lb_ = np.loadtxt('r27b_lmax_by_rep.csv', delimiter=',', skiprows=1, usecols=(0, 1, 2, 3))
    lc_ = np.loadtxt('r27c_lmax_by_rep.csv', delimiter=',', skiprows=1, usecols=(0, 1, 2, 3))
    k2k, lams = {}, {}
    for row in np.vstack([lb_, lc_]):
        k2k.setdefault(int(row[0]), []).append(row[3])
        lams.setdefault(int(row[0]), []).append(row[2])
    bc = load_betas()
    ns = sorted(bc.keys())
    invT = np.array([np.arctanh(1.0 / (np.mean(k2k[n]) - 1.0)) for n in ns])
    invb = np.array([1.0 / bc[n] for n in ns])
    lm = np.array([np.mean(lams[n]) for n in ns])
    print("=== (4) DGM quantitative check (Eq.1 with per-size truncated moments) ===")
    print(f"{'n':>4} {'k2k':>6} {'1/beta':>7} {'1/Tc_DGM':>9} {'lam':>7} {'1/Tc*lam':>9}")
    for i, n in enumerate(ns):
        print(f"{n:>4} {np.mean(k2k[n]):6.2f} {invb[i]:7.3f} {invT[i]:9.5f} "
              f"{lm[i]:7.4f} {invT[i]*lm[i]:9.5f}")

    def spread(x):
        return 100 * (x.max() / x.min() - 1)

    print(f"relative spread: 1/beta {spread(invb):.1f}%  |  1/Tc_DGM {spread(invT):.1f}%  |"
          f"  (1/Tc)*lam {spread(invT * lm):.1f}%")
    print("  -> lambda normalization absorbs ~80% of the Tc(n) variation (T_c ~ 1/lambda)")
    ratio = invb / (invT * lm)
    print(f"  ratio (1/beta)/((1/Tc)*lam): {ratio.min():.1f} .. {ratio.max():.1f} "
          f"({100 * (ratio.max() / ratio.min() - 1):.0f}% drift -- weight/unit convention)")


def main():
    cb = load_peaks()
    gm = graph_moments()
    ns = sorted(cb.keys())
    y = np.array([cb[n] for n in ns])
    lam = np.array([gm[n][0] for n in ns])
    k4 = np.array([gm[n][1] for n in ns])
    km = np.array([gm[n][2] for n in ns])
    k2k = np.array([gm[n][3] for n in ns])

    print("=== (1) bivariate: n vs lambda ===")
    fit(['n', 'lam'], [np.array(ns, float), lam], y)

    print("=== (2) adding higher moments ===")
    fit(['n', 'lam', 'k4'], [np.array(ns, float), lam, k4], y)
    fit(['n', 'lam', 'kmax'], [np.array(ns, float), lam, km], y)

    print("=== (3) single-variable candidates ===")
    fit(['lam'], [lam], y)
    fit(['k2k'], [k2k], y)
    a = np.polyfit(np.log(k2k), np.log(y), 1)
    loo = []
    for k in range(len(ns)):
        m = np.ones(len(ns), bool); m[k] = False
        loo.append(np.polyfit(np.log(k2k[m]), np.log(y[m]), 1)[0])
    print('  chi/beta ~ (k2k)^%.3f  LOO [%.3f, %.3f]  (candidate clean value: 2)'
          % (a[0], min(loo), max(loo)))
    print()
    dgm_quantitative()


if __name__ == "__main__":
    main()
