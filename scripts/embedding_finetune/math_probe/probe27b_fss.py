#!/usr/bin/env python3
"""probe27b — FSS 加密扩展版（10 尺寸，含 v1 全部锚点）

相对 v1（probe27_fss.py，6 尺寸）的改动 = 尺寸加密 + 峰区加宽（唯一变量）：
  SIZES 6 → 10：40/60/75/90/110/130/160/190/230/279（v1 的 6 个全在内，可直比）
  Phase2 窗口 ±0.5/15 点 → ±0.6/17 点（峰区更完整——供五点拟合与 bootstrap）
  协议其余全同（Phase1 粗定位 12 点 × 24 run；Phase2 4 rep × 96 runs；nTherm/nSamp）
P 种子统一加 5e6 偏移（避免与 v1 同组合的随机流重复）。

目的：① FSS 拟合更多杠杆点；② 直击「峰定位单点噪声」（n=60 已三次露头）；
      ③ 为 θ=β·λ_max 归一（谱标尺修正坐标）的精确化提供更高分辨率数据。

输出：py27b_fss_output.csv
Run: ../.venv/Scripts/python.exe probe27b_fss.py    （约 18-22 分钟，建议后台）
"""

import pathlib
import time

import numpy as np

from probe27_glauber import load_W, glauber_stats, seed_P
import hard_random as hr

SIZES = (40, 60, 75, 90, 110, 130, 160, 190, 230, 279)
GRAPH_REPS = 4
COARSE_POINTS = 12
COARSE_RUNS = 24
FINE_POINTS = 17
FINE_HALFWIDTH = 0.6
N_P, N_H = 48, 48
NTHERM_F, NSAMP_F, GAP_F = 600, 500, 2
GRAPH_SEED = 20261016
SEED_OFFSET = 5_000_000
OUT_CSV = pathlib.Path(__file__).parent / 'py27b_fss_output.csv'


def deg_weight_pools(W):
    deg = (W != 0).sum(axis=1)
    wpool = W[W != 0] / 2.0
    return deg, wpool


def make_config_graph(n, deg_full, wpool, rng):
    """配置模型（multigraph 变体，度序列严格保持）。
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
    print("=== probe27b: FSS densified (10 sizes, fine +-0.6 / 17 pts) ===")
    print(f"hw source: {hr.source_name} | sizes={SIZES} reps={GRAPH_REPS} "
          f"runs/point={N_P}+{N_H}")
    W = load_W()
    deg_full, wpool = deg_weight_pools(W)
    print(f"degree pool: min={deg_full.min()} max={deg_full.max()} "
          f"mean={deg_full.mean():.2f} | weight pool={len(wpool)}")

    coarse_betas = np.linspace(0.6, 4.0, COARSE_POINTS)
    centers = {}
    print("\n=== Phase 1: coarse peak localization (24 runs, 1 graph) ===")
    for n in SIZES:
        Wg, _, _ = build_graph(n, 0, deg_full, wpool)
        means = []
        for bi, beta in enumerate(coarse_betas):
            chis = [glauber_stats(Wg, beta, seed_P(9_500_000 + n * 100 + bi * 3 + k))['chi']
                    for k in range(COARSE_RUNS)]
            means.append(np.mean(chis))
        centers[n] = float(coarse_betas[int(np.argmax(means))])
        prof = " ".join(f"{b:.2f}:{m:.1f}" for b, m in zip(coarse_betas, means))
        print(f"  n={n:>3}: peak ~{centers[n]:.2f}   profile[{prof}]", flush=True)

    print("\n=== Phase 2: fine sweep (4 graphs x 17 betas x 96 runs) ===")
    rows = []
    total = len(SIZES) * GRAPH_REPS * FINE_POINTS * (N_P + N_H)
    done = 0
    tA = time.time()
    seed_cnt = 0
    p_counter = SEED_OFFSET
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
