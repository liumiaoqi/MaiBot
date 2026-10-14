#!/usr/bin/env python3
"""probe27c — FSS 上端扩展（6 个新尺寸，n > 279）

动机（v2 结论）：θ=β·λ_max 归一的效应显著（降 ~38%），但**小端主导**——
n=40 是全局最敏感点，漂移形态靠它撑 ⇒ 钉死渐近行为需要**大 n 数据**。

设计决定（唯一新变量 = 上端尺寸）：
  SIZES = 300..760 六个（全部 >279）
  ⚠️ 度池只有 279 个值 ⇒ `replace=True`（有放回）抽样：
     度分布的前几阶矩无偏（谱标尺假说依赖矩）⇒ 可用；
     与 v2（replace=False）的点不混跑，分析时合并（标注抽样方式差异）。
  Phase1 粗扫窗口收窄为 [0.5, 2.4]（上端峰更小：β_c 外推 ~1.2-1.35，原 [0.6,4.0] 浪费）
  Phase2：±0.6 / 17 点 × **3 图** × **48 runs（P24+H24）**——大图单 run 慢（n=760 实测 0.16s），
      按预算削减统计（v3 的角色是「上端形态」而非精确指数；分析时统一标注统计更薄）
  seed 段：Phase1 用 9.9e6 段、Phase2 从 7.5e6 起（与 v1/v2 隔离）

输出：py27c_fss_output.csv
Run: ../.venv/Scripts/python.exe probe27c_fss.py   （约 35-40 分钟，后台）
"""

import pathlib
import time

import numpy as np

from probe27_glauber import load_W, glauber_stats, seed_P
import hard_random as hr

SIZES = (300, 360, 430, 520, 630, 760)
GRAPH_REPS = 3
COARSE_POINTS = 12
COARSE_RUNS = 24
FINE_POINTS = 17
FINE_HALFWIDTH = 0.6
N_P, N_H = 24, 24
NTHERM_F, NSAMP_F, GAP_F = 600, 500, 2
GRAPH_SEED = 20261016
SEED_OFFSET = 7_500_000
COARSE_WINDOW = (0.5, 2.4)
OUT_CSV = pathlib.Path(__file__).parent / 'py27c_fss_output.csv'


def deg_weight_pools(W):
    deg = (W != 0).sum(axis=1)
    wpool = W[W != 0] / 2.0
    return deg, wpool


def make_config_graph(n, deg_full, wpool, rng):
    """配置模型（multigraph 变体）——上端扩展版：度值 replace=True（有放回）。
    stub 配对；重边 ⇒ 权重相加；自环丢弃。返回 (W, pairs, selfloops)。"""
    degs = rng.choice(deg_full, size=n, replace=True).astype(int)
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
    print("=== probe27c: FSS upper-end extension (6 sizes > 279, replace=True degrees) ===")
    print(f"hw source: {hr.source_name} | sizes={SIZES} reps={GRAPH_REPS} "
          f"runs/point={N_P}+{N_H} | coarse window {COARSE_WINDOW}")
    W = load_W()
    deg_full, wpool = deg_weight_pools(W)
    print(f"degree pool: min={deg_full.min()} max={deg_full.max()} "
          f"mean={deg_full.mean():.2f} | weight pool={len(wpool)}")

    coarse_betas = np.linspace(COARSE_WINDOW[0], COARSE_WINDOW[1], COARSE_POINTS)
    centers = {}
    print("\n=== Phase 1: coarse peak localization ===")
    for n in SIZES:
        Wg, _, _ = build_graph(n, 0, deg_full, wpool)
        means = []
        for bi, beta in enumerate(coarse_betas):
            chis = [glauber_stats(Wg, beta, seed_P(9_900_000 + n * 100 + bi * 3 + k))['chi']
                    for k in range(COARSE_RUNS)]
            means.append(np.mean(chis))
        centers[n] = float(coarse_betas[int(np.argmax(means))])
        prof = " ".join(f"{b:.2f}:{m:.1f}" for b, m in zip(coarse_betas, means))
        print(f"  n={n:>3}: peak ~{centers[n]:.2f}   profile[{prof}]", flush=True)

    print(f"\n=== Phase 2: fine sweep ({GRAPH_REPS} graphs x {FINE_POINTS} betas "
          f"x {N_P+N_H} runs) ===")
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
