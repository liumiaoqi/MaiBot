#!/usr/bin/env python3
"""exp63: 记忆衰减的形状辨识——指数/双指数/幂律/拉伸指数的可分辨性（D 线）

问题：A_memorix granular_decay 是「指数+地板」（马尔可夫）；exp29 双指数拟合领先；
但认知文献里「幂律 vs 指数」是经典争论。非马尔可夫的标志 = 长尾（幂律，见 x63 符号推导）。
实验：
① 可分辨矩阵：四形状合成数据（采样点=Ebbinghaus 8 点密度）→ 四模型拟合 → AIC 选对率
② Ebbinghaus 真实 8 点：四模型 AIC 裁判
③ 采样预算：8 点 vs 24 点（对数均匀）对「幂律 vs 双指数」分辨力的影响（未来数据采集判据）

模型集：
  exp      m = a*exp(-t/tau)
  biexp    m = a*exp(-t/tau1) + b*exp(-t/tau2)
  power    m = m0*(1+t/tau)^(-alpha)        （Wixted 形，长尾）
  stretch  m = m0*exp(-(t/tau)^beta)        （Weibull）
"""

import numpy as np
from scipy.optimize import curve_fit

rng = np.random.RandomState(20261014)

# Ebbinghaus 8 点（小时→天）
EBB_H = np.array([0.33, 1, 9, 24, 48, 144, 744]) / 24.0
EBB_Y = np.array([0.58, 0.44, 0.36, 0.33, 0.28, 0.25, 0.21])
T8 = np.concatenate([[0.0], EBB_H])       # 8 点（含 t=0 的 1.0）
Y8 = np.concatenate([[1.0], EBB_Y])
T24 = np.concatenate([[0.0], np.geomspace(0.02, 31.0, 23)])  # 24 点（对数均匀）


def m_exp(t, a, tau):
    return a * np.exp(-t / tau)


def m_biexp(t, a, tau1, b, tau2):
    return a * np.exp(-t / tau1) + b * np.exp(-t / tau2)


def m_power(t, m0, tau, alpha):
    return m0 * (1.0 + t / tau) ** (-alpha)


def m_stretch(t, m0, tau, beta):
    return m0 * np.exp(-((t / tau) ** beta))


MODELS = {"exp": (m_exp, 2), "biexp": (m_biexp, 4), "power": (m_power, 3), "stretch": (m_stretch, 3)}


def fit_aic(model_fn, p0, t, y, sigma_floor=0.01):
    try:
        popt, _ = curve_fit(model_fn, t, y, p0=p0, maxfev=20000)
        resid = y - model_fn(t, *popt)
        rss = np.sum(resid ** 2)
        n = len(t)
        k = len(p0)
        aic = n * np.log(max(rss / n, 1e-12)) + 2 * k
        return aic, popt
    except Exception:
        return np.inf, None


def aic_all(t, y):
    out = {}
    out["exp"] = fit_aic(m_exp, [1.0, 5.0], t, y)
    out["biexp"] = fit_aic(m_biexp, [0.7, 1.0, 0.3, 100.0], t, y)
    out["power"] = fit_aic(m_power, [1.0, 1.0, 0.5], t, y)
    out["stretch"] = fit_aic(m_stretch, [1.0, 3.0, 0.5], t, y)
    return out


def gen_shape(kind, t, params):
    if kind == "exp":
        a, tau = params
        return m_exp(t, a, tau)
    if kind == "biexp":
        return m_biexp(t, *params)
    if kind == "power":
        return m_power(t, *params)
    if kind == "stretch":
        return m_stretch(t, *params)
    raise ValueError(kind)


def sample_params(kind):
    if kind == "exp":
        return [1.0, rng.uniform(1.0, 30.0)]
    if kind == "biexp":
        return [rng.uniform(0.5, 0.9), rng.uniform(0.3, 2.0), rng.uniform(0.1, 0.5), rng.uniform(50.0, 400.0)]
    if kind == "power":
        return [1.0, rng.uniform(0.3, 10.0), rng.uniform(0.15, 0.7)]
    if kind == "stretch":
        return [1.0, rng.uniform(1.0, 10.0), rng.uniform(0.4, 0.9)]


def main():
    print("=== exp63: 记忆衰减形状辨识（指数/双指数/幂律/拉伸指数） ===")
    print()

    # ① 可分辨矩阵（8 点采样）
    print("--- ① 可分辨矩阵 @ 8 点（Ebbinghaus 密度，噪声 sigma=0.01） ---")
    kinds = ["exp", "biexp", "power", "stretch"]
    n_rep = 120
    matrix = {k: {m: 0 for m in kinds} for k in kinds}
    for kind in kinds:
        for _ in range(n_rep):
            p = sample_params(kind)
            y = gen_shape(kind, T8, p)
            y = np.clip(y + rng.normal(0, 0.01, len(T8)), 0, 1)
            res = aic_all(T8, y)
            winner = min(res, key=lambda m: res[m][0])
            matrix[kind][winner] += 1
    print("%-10s %s" % ("真值\\选出", "  ".join("%-9s" % k for k in kinds)))
    for k in kinds:
        row = "  ".join("%-8.1f%%" % (100.0 * matrix[k][m] / n_rep) for m in kinds)
        print("%-10s %s" % (k, row))
    print()

    # ② Ebbinghaus 真实 8 点裁判
    print("--- ② Ebbinghaus 真实数据点：四模型 AIC 裁判 ---")
    res = aic_all(T8, Y8)
    aics = {m: res[m][0] for m in kinds}
    best = min(aics, key=aics.get)
    for m in kinds:
        aic, popt = res[m]
        ps = " ".join("%.3f" % v for v in popt) if popt is not None else "-"
        print("  %-8s AIC=%8.2f  参数: %s%s" % (m, aic, ps, "   ← min" if m == best else ""))
    print()

    # ③ 采样预算：8 点 vs 24 点 对 power vs biexp 的分辨
    print("--- ③ 采样预算对「power vs biexp」分辨力的影响（真值 power 与 biexp 各 120 次） ---")
    for name, T in (("8 点", T8), ("24 点(对数均匀)", T24)):
        conf = {k: {m: 0 for m in kinds} for k in ["power", "biexp"]}
        for kind in ("power", "biexp"):
            for _ in range(n_rep):
                p = sample_params(kind)
                y = np.clip(gen_shape(kind, T, p) + rng.normal(0, 0.01, len(T)), 0, 1)
                res2 = aic_all(T, y)
                winner = min(res2, key=lambda m: res2[m][0])
                conf[kind][winner] += 1
        p_say = 100.0 * conf["power"]["power"] / n_rep
        b_say = 100.0 * conf["biexp"]["biexp"] / n_rep
        cross = 100.0 * (conf["power"]["biexp"] + conf["biexp"]["power"]) / (2 * n_rep)
        print("  %-18s power 选对 %.1f%% · biexp 选对 %.1f%% · 互混 %.1f%%" % (name, p_say, b_say, cross))
    print()

    print("=== 判词 ===")
    print("① 8 点密度下的可分辨矩阵：哪些形状互混（尤其 power<->biexp、power<->stretch）；")
    print("② Ebbinghaus 数据上 AIC 赢家 = 该数据支持的形状（对照 exp29 的 MAE 结论）；")
    print("③ 若 power vs biexp 在 8 点下互混显著、24 点显著改善 ⇒ 给未来真实数据采集的采样判据。")
    print("④ 非马尔可夫（幂律核）的可测特征 = 长尾（x63 符号 ⇔ 本表数值）；指数核无此尾。")
    print("（2026-10-14 · D 线）")


if __name__ == "__main__":
    main()
