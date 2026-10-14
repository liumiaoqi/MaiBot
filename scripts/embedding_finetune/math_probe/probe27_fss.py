#!/usr/bin/env python3
"""probe27 正式版 v2 — FSS 普适性分析：配置模型系综 × 双随机源（P/H）

装置演化记录（2026-10-14 勘察）：
  ① 母图「节点诱导子图」✗：切节点连带切边——平均度 14.26→3.19、λ_max 2.83→0.90
     → 峰位漂移 6×（0.58→>3.4），度/谱归一化均不能完全吸收 ⇒ 弃用；
  ② 简单图配置模型 ✗：整图拒绝重试——小尺寸重边率高 ⇒ 度损耗 33%（且随尺寸变）；
  ③ multigraph 配置模型 ✓：重边=权重相加（并行边=更强耦合）、自环丢弃
     （损耗 ~2%）⇒ 度序列严格保持，温度标尺跨尺寸统一。

设计（两阶段，per-size 窗口）：
  Phase 1  每尺寸粗扫 beta ∈ linspace(0.6, 4.0, 12) × 24 run × 1 图 → 峰位中心
  Phase 2  每尺寸 [峰-0.5, 峰+0.5] 15 点 × 4 图实现 × 48(P)+48(H) runs → 主数据
  统计口径与 probe12 对齐：χ = n·β·(⟨m²⟩−⟨m⟩²)；nTherm=600, nSamp=500, gap=2
  动力学种子双源：P 固定（可复现）| H 硬件（RDSEED/RDRAND，全记录）
  图实现种子固定（GRAPH_SEED），记录度审计（自环损耗）。

输出：py27_fss_output.csv（每 run 一行）+ 控制台摘要
Run: ../.venv/Scripts/python.exe probe27_fss.py    （约 12-15 分钟）
"""

import pathlib
import time

import numpy as np

from probe27_glauber import load_W, glauber_stats, seed_P
import hard_random as hr

SIZES = (40, 60, 90, 130, 190, 279)
GRAPH_REPS = 4
COARSE_POINTS = 12
COARSE_RUNS = 24
FINE_POINTS = 15
FINE_HALFWIDTH = 0.5
N_P, N_H = 48, 48
NTHERM_F, NSAMP_F, GAP_F = 600, 500, 2
GRAPH_SEED = 20261016
OUT_CSV = pathlib.Path(__file__).parent / 'py27_fss_output.csv'


def deg_weight_pools(W):
    deg = (W != 0).sum(axis=1)
    wpool = W[W != 0] / 2.0
    return deg, wpool


def make_config_graph(n, deg_full, wpool, rng):
    """配置模型（multigraph 变体，度序列严格保持）：
    stub 配对；重边 ⇒ 权重相加；自环丢弃。返回 (W, pairs, selfloops)。"""
    degs = rng.choice(deg_full, size=n, replace=False).astype(int)
    stubs = np.repeat(np.arange(n), degs)
    rng.shuffle(stubs)
    m = len(stubs) // 2
    pair_counts = {}
    selfloops = 0
    for k in range(m):
        i, j = int(stubs[2 * k]), int(stubs[2 * k + 1])
        if i == j:
            selfloops += 1
            continue
        a, b = (i, j) if i < j else (j, i)
        pair_counts[(a, b)] = pair_counts.get((a, b), 0) + 1
    Wm = np.zeros((n, n))
    keys = list(pair_counts.keys())
    wvals = rng.choice(wpool, size=len(keys), replace=True)
    for (a, b), w in zip(keys, wvals):
        Wm[a, b] = w
        Wm[b, a] = w
    return Wm, m, selfloops


def build_graph(n, rep, deg_full, wpool):
    gseed = GRAPH_SEED + 1000 * n + rep
    rng = np.random.RandomState(gseed)
    Wg, pairs, sl = make_config_graph(n, deg_full, wpool, rng)
    return Wg, pairs, sl


def main():
    t0 = time.time()
    hr._init()
    print("=== probe27 FSS v2 (config-model ensemble x dual source) ===")
    print(f"hw source: {hr.source_name} | sizes={SIZES} reps={GRAPH_REPS} "
          f"fine points={FINE_POINTS} runs/point={N_P}+{N_H}")
    W = load_W()
    deg_full, wpool = deg_weight_pools(W)
    print(f"degree pool: min={deg_full.min()} max={deg_full.max()} "
          f"mean={deg_full.mean():.2f} | weight pool={len(wpool)}")

    # degree audit for the ensemble (rep 0..3)
    print("\ndegree audit (self-loop loss; coupling mass per node = 2*pairs*wbar/n):")
    for n in SIZES:
        for rep in range(GRAPH_REPS):
            _, pairs, sl = build_graph(n, rep, deg_full, wpool)
            print(f"  n={n:>3} rep={rep} pairs={pairs:>4} selfloop={sl:>3}"
                  f" ({100*sl/pairs:.1f}%)")

    # ---- Phase 1: coarse localization ----
    coarse_betas = np.linspace(0.6, 4.0, COARSE_POINTS)
    centers = {}
    print("\n=== Phase 1: coarse peak localization (24 runs, 1 graph) ===")
    for n in SIZES:
        Wg, _, _ = build_graph(n, 0, deg_full, wpool)
        means = []
        for bi, beta in enumerate(coarse_betas):
            chis = [glauber_stats(Wg, beta, seed_P(900_000 + n * 100 + bi * 3 + k))['chi']
                    for k in range(COARSE_RUNS)]
            means.append(np.mean(chis))
        ibest = int(np.argmax(means))
        centers[n] = float(coarse_betas[ibest])
        prof = " ".join(f"{b:.2f}:{m:.1f}" for b, m in zip(coarse_betas, means))
        print(f"  n={n:>3}: peak ~{centers[n]:.2f}   profile[{prof}]", flush=True)

    # ---- Phase 2: fine sweep per size ----
    print("\n=== Phase 2: fine sweep (4 graphs x 15 betas x 96 runs) ===")
    rows = []
    total = len(SIZES) * GRAPH_REPS * FINE_POINTS * (N_P + N_H)
    done = 0
    tA = time.time()
    seed_cnt = 0
    p_counter = 0
    for n in SIZES:
        grid = np.round(np.linspace(centers[n] - FINE_HALFWIDTH,
                                    centers[n] + FINE_HALFWIDTH, FINE_POINTS), 3)
        for rep in range(GRAPH_REPS):
            Wg, _, _ = build_graph(n, rep, deg_full, wpool)
            for bi, beta in enumerate(grid):
                for k in range(N_P):
                    s = seed_P(p_counter) & 0xFFFFFFFF
                    p_counter += 1
                    r = glauber_stats(Wg, beta, s, NTHERM_F, NSAMP_F, GAP_F)
                    rows.append((n, rep, beta, 'P', k, s, r['absm'], r['chi'], r['q']))
                    done += 1
                for k in range(N_H):
                    s = hr.hw_u64() & 0xFFFFFFFF
                    seed_cnt += 1
                    r = glauber_stats(Wg, beta, s, NTHERM_F, NSAMP_F, GAP_F)
                    rows.append((n, rep, beta, 'H', k, s, r['absm'], r['chi'], r['q']))
                    done += 1
                if done % 1920 == 0:
                    el = time.time() - tA
                    print(f"  {done}/{total} ({100*done/total:.0f}%) {el:.0f}s "
                          f"elapsed, ~{el/done*(total-done):.0f}s left", flush=True)

    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
        f.write("size,rep,beta,source,run,seed,absm,chi,q\n")
        for t in rows:
            f.write(f"{t[0]},{t[1]},{t[2]:.3f},{t[3]},{t[4]},{t[5]},"
                    f"{t[6]:.6f},{t[7]:.6f},{t[8]:.6f}\n")
    print(f"\ndone in {time.time()-t0:.0f}s | rows={len(rows)} -> {OUT_CSV.name}")
    print(f"hardware seeds used: {seed_cnt}")

    # quick per-size peak summary (mean over everything)
    arr = np.array([(r[0], r[2], r[7]) for r in rows])
    print("\nquick fine-summary (mean chi):")
    for n in SIZES:
        sub = arr[arr[:, 0] == n]
        betas = np.unique(sub[:, 1])
        prof = [(b, sub[sub[:, 1] == b][:, 2].mean()) for b in betas]
        bmax, cmax = max(prof, key=lambda t: t[1])
        print(f"  n={n:>3}  peak beta~{bmax:.3f}  chi~{cmax:.2f}")


if __name__ == "__main__":
    main()
