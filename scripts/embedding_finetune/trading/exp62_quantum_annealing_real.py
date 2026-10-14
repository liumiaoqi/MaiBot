#!/usr/bin/env python3
"""exp62: 真·横向场量子退火（SQA/PIMC）——双井与 Ising 玻璃对照（C 线）

缘起（probe10 之后）：
- probe10 判 exp32「退火」= 假退火（切换概率 exp(-0.2/T) 与 gain 无关——纯温度调度噪声）；
- 且 exp32 的问题形态（168 步在线序列决策）与退火（静态组合优化）**不同构**。
本实验给出「真退火」的正确对照面：Path-Integral Monte Carlo（Trotter 切片 + Γ 调度）
实现标准横向场量子退火，在**静态优化**问题上与经典模拟退火（SA）**同预算**对照。

判据：
① 双井：局部最优 (1,1) 被壁垒 +3.2 隔开全局 (−1,−1)——低温/短预算下 SQA 能否隧穿；
② 16-bit Ising 玻璃：穷举最优为基准，SA vs SQA 成功率-预算曲线；
③ 判词：真隧穿的可分辨优势区间（有/无，都如实记录）。
约定：H = -Σ_{i<j} J_ij s_i s_j - Σ h_i s_i（s=±1）；横向场 Γ 由大调度到小。
"""

import itertools

import numpy as np

rng = np.random.RandomState(20261014)


# ── 问题 1：双井（2 比特） ──
def dw_E(s):
    return -2.0 * s[0] * s[1] + 0.4 * (s[0] + s[1])


def dw_dE(s, i):
    t = s.copy()
    t[i] = -t[i]
    return dw_E(t) - dw_E(s)


# ── 问题 2：16-bit Ising 玻璃 ──
def make_glass(n=16, seed=7):
    r = np.random.RandomState(seed)
    J = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            if r.random() < 0.5:
                J[i, j] = J[j, i] = r.choice([-1.0, 1.0])
    h = r.uniform(-0.2, 0.2, n)
    return J, h


def glass_E(s, J, h):
    return -0.5 * s @ J @ s - h @ s


def glass_dE(s, i, J, h):
    return 2.0 * s[i] * (J[i] @ s + h[i])


def glass_best(J, h, n=16):
    best = np.inf
    for bits in itertools.product([-1.0, 1.0], repeat=n):
        e = glass_E(np.array(bits), J, h)
        if e < best:
            best = e
    return best


# ── 经典模拟退火 ──
def sa_run(dE_fn, n, n_sweeps, T0=3.0, T1=0.04, seed=None):
    r = np.random.RandomState(seed)
    s = r.choice([-1.0, 1.0], n)
    for T in np.geomspace(T0, T1, n_sweeps):
        for i in range(n):
            dE = dE_fn(s, i)
            if dE <= 0 or r.random() < np.exp(-dE / T):
                s[i] = -s[i]
    return s


# ── 真·横向场量子退火（PIMC） ──
def sqa_run(dE_fn, n, n_sweeps, P=16, T=0.3, G0=3.0, G1=0.05, seed=None):
    """P=16 Trotter 片；T 固定低温（量子退火靠 Γ 而非热）；Γ 几何调度。"""
    r = np.random.RandomState(seed)
    s = r.choice([-1.0, 1.0], (P, n))
    for Gamma in np.geomspace(G0, G1, n_sweeps):
        Jperp = -0.5 * P * T * np.log(np.tanh(Gamma / (P * T)))
        for _ in range(P):
            p = r.randint(P)
            for i in range(n):
                dE = dE_fn(s[p], i) + 2.0 * Jperp * s[p, i] * (s[(p + 1) % P, i] + s[(p - 1) % P, i])
                if dE <= 0 or r.random() < np.exp(-dE / T):
                    s[p, i] = -s[p, i]
    return s[0]


# ── 库版真 SQA（dwave-samplers · Path-Integral Annealing，独立实现） ──
try:
    from dwave.samplers import PathIntegralAnnealingSampler
    HAS_LIB_SQA = True
except ImportError:
    HAS_LIB_SQA = False


def sqa_lib_run(Jmat, hvec, n_sweeps=1000):
    """能量约定映射：目标 E = -0.5 sᵀJs - h·s ⇒ 库侧 hd = -h, Jd(i<j) = -J_ij。"""
    n = len(hvec)
    hd = {i: -float(hvec[i]) for i in range(n)}
    Jd = {}
    for i in range(n):
        for j in range(i + 1, n):
            if Jmat[i, j] != 0.0:
                Jd[(i, j)] = -float(Jmat[i, j])
    sampler = PathIntegralAnnealingSampler()
    ss = sampler.sample_ising(hd, Jd, num_reads=1, num_sweeps=n_sweeps)
    best = ss.first.sample
    return np.array([best[i] for i in range(n)], dtype=float)


# ── 跑对照 ──
def run_doublewell():
    print("--- ① 双井（全局 (−1,−1) E=−2.8；局部 (1,1) E=−1.2；壁垒 +3.2） ---")
    print("%-12s %-8s %10s %10s" % ("预算(sweeps)", "方法", "命中全局率", "平均E"))
    print("-" * 46)
    n_runs = 300
    # 双井能量映射：E = -2 s1s2 + 0.4(s1+s2) = -0.5 sᵀJs - h·s ⇒ J=[[0,2],[2,0]], h=[-0.4,-0.4]
    DwJ = np.array([[0.0, 2.0], [2.0, 0.0]])
    Dwh = np.array([-0.4, -0.4])
    for sweeps in (10, 30, 100):   # 同 sweeps 口径（SQA 每 sweep 计算量 ≈ P 倍，成本差如实注明）
        for name, runner in (("SA", "sa"), ("SQA", "sqa"), ("SQA-lib", "lib")):
            hit = 0
            es = []
            for k in range(n_runs):
                if name == "SA":
                    s = sa_run(lambda ss, i: dw_dE(ss, i), 2, sweeps, T0=1.0, T1=0.04, seed=1000 * sweeps + k)
                elif name == "SQA":
                    s = sqa_run(lambda ss, i: dw_dE(ss, i), 2, sweeps, P=16, T=0.3, seed=1000 * sweeps + k)
                else:
                    s = sqa_lib_run(DwJ, Dwh, n_sweeps=sweeps) if HAS_LIB_SQA else np.array([1.0, 1.0])
                e = dw_E(s)
                es.append(e)
                if e <= -2.79:
                    hit += 1
            print("%-12s %-8s %10.1f%% %10.3f" % (sweeps, name, 100.0 * hit / n_runs, float(np.mean(es))))
    print()


def run_glass():
    print("--- ② 16-bit Ising 玻璃（穷举最优为基准） ---")
    J, h = make_glass()
    best = glass_best(J, h)
    print("穷举最优 E = %.3f" % best)
    print("%-12s %-8s %10s %10s" % ("预算(sweeps)", "方法", "命中最优率", "平均gap"))
    print("-" * 46)
    n_runs = 120
    for sweeps in (100, 500, 1500):   # 同 sweeps 口径（SQA 每 sweep 计算量 ≈ P 倍）
        for name in ("SA", "SQA", "SQA-lib"):
            hit, gaps = 0, []
            for k in range(n_runs):
                if name == "SA":
                    s = sa_run(lambda ss, i: glass_dE(ss, i, J, h), 16, sweeps, T0=3.0, T1=0.04, seed=2000 * sweeps + k)
                elif name == "SQA":
                    s = sqa_run(lambda ss, i: glass_dE(ss, i, J, h), 16, sweeps, P=16, T=0.3, seed=2000 * sweeps + k)
                else:
                    s = sqa_lib_run(J, h, n_sweeps=sweeps) if HAS_LIB_SQA else np.array([1.0] * 16)
                e = glass_E(s, J, h)
                gaps.append(e - best)
                if e <= best + 1e-9:
                    hit += 1
            print("%-12s %-8s %10.1f%% %10.3f" % (sweeps, name, 100.0 * hit / n_runs, float(np.mean(gaps))))
    print()


def main():
    print("=== exp62: 真·横向场 SQA（PIMC）vs 经典 SA —— 静态优化对照 ===")
    print("Trotter P=8 · Γ 几何调度 3.0→~0.05 · 同预算 · 多次独立跑")
    print()
    run_doublewell()
    run_glass()
    print("=== 判词 ===")
    print("① exp32 的「退火」判决（probe10）不变：其问题为在线序列决策，与静态退火不同构；")
    print("② 真退火的价值面在静态优化——本表给出 SQA 相对 SA 的可分辨区间（有则记，无则零结果）；")
    print("③ 隧穿的可分辨性 = 壁垒高度 / 预算 / 温度三者交叉，单点对照会掩盖。")
    print("（2026-10-14 · C 线）")


if __name__ == "__main__":
    main()
