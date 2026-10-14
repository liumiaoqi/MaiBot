#!/usr/bin/env python3
"""probe14 — FSS 普适性分析的内核（Glauber × numba × 硬随机）

背景：probe12 的 χ 峰（β_c≈0.5，279 节点连接组）受「有限尺寸抹圆」之限。
本 probe 用有限尺寸标度（FSS）严格化：嵌套子图序列 × β 密扫 × 多实现平均。
随机实现种子双源对照：
  P（伪随机，固定基 SeedSequence）
  H（硬件随机源 RDSEED/RDRAND，见 hard_random.py；种子全程记录）
统计与拟合移交 R（probe14_fss.R）。

统计口径与 probe12 对齐（同 χ 定义、同采样结构）：
  χ = n·β·(⟨m²⟩ − ⟨m⟩²)，m = mean(x)；nTherm=400, nSamp=300, gap=2。

本文件勘察模式：
  ① 数据 sanity（对称性/nnz/度)
  ② 嵌套子图序列（固定 permutation → 最大连通分量）
  ③ numba 编译 + 单 run 速度实测
  ④ 粗 β 扫（复现 probe12 峰位）

Run: ../.venv/Scripts/python.exe probe14_glauber.py
"""

import pathlib
import time

import numpy as np
from numba import njit

from hard_random import hw_u64, source_name

D_DIR = pathlib.Path(__file__).parent / 'data_exp41'
N_FULL = 279
NTHERM, NSAMP, GAP = 400, 300, 2
SUB_SEQ_SEED = 20261014          # 嵌套子图 permutation（固定，记录）
P_BASE_SEED = 20261015           # P 组伪随机基


@njit(cache=True)
def _glauber_run(Wt, n, beta, nTherm, nSamp, gap, seed):
    """单实现 Glauber 顺序更新。Wt = W.T（行连续列访问）。返回 (absm, chi, q, m2)。"""
    np.random.seed(seed)
    x = np.empty(n, np.float64)
    for i in range(n):
        x[i] = 1.0 if np.random.rand() < 0.5 else -1.0
    # h = W x
    h = np.zeros(n, np.float64)
    for i in range(n):
        acc = 0.0
        for j in range(n):
            acc += Wt[j, i] * x[j]
        h[i] = acc
    # 热化（nTherm sweeps 不采样）
    for sw in range(nTherm):
        order = np.random.permutation(n)
        for k in range(n):
            i = order[k]
            p = 1.0 / (1.0 + np.exp(-2.0 * beta * h[i]))
            nx = 1.0 if np.random.rand() < p else -1.0
            if nx != x[i]:
                d = nx - x[i]
                for j in range(n):
                    h[j] += d * Wt[i, j]
                x[i] = nx
    # 采样（nSamp 点，间隔 gap sweeps）
    ms = np.empty(nSamp, np.float64)
    for s in range(nSamp):
        for sw in range(gap):
            order = np.random.permutation(n)
            for k in range(n):
                i = order[k]
                p = 1.0 / (1.0 + np.exp(-2.0 * beta * h[i]))
                nx = 1.0 if np.random.rand() < p else -1.0
                if nx != x[i]:
                    d = nx - x[i]
                    for j in range(n):
                        h[j] += d * Wt[i, j]
                    x[i] = nx
        acc = 0.0
        for i in range(n):
            acc += x[i]
        ms[s] = acc / n
    m2 = 0.0
    ab = 0.0
    for s in range(nSamp):
        m2 += ms[s] * ms[s]
        ab += abs(ms[s])
    m2 /= nSamp
    ab /= nSamp
    mm = 0.0
    for s in range(nSamp):
        mm += ms[s]
    mm /= nSamp
    chi = n * beta * (m2 - mm * mm)
    return ab, chi, m2, mm


def glauber_stats(W, beta, seed, ntherm=NTHERM, nsamp=NSAMP, gap=GAP):
    """Python 包装：numba 内核 + 转置矩阵缓存。"""
    n = W.shape[0]
    Wt = np.ascontiguousarray(W.T)
    ab, chi, m2, mm = _glauber_run(Wt, n, beta, ntherm, nsamp, gap, seed & 0xFFFFFFFF)
    return dict(absm=ab, chi=chi, q=m2, m2=m2, mmean=mm)


def load_W():
    E = np.loadtxt(D_DIR / 'edges.csv', delimiter=',')
    n = N_FULL
    W = np.zeros((n, n))
    for k in range(E.shape[0]):
        i, j, w = int(E[k, 0]), int(E[k, 1]), E[k, 2]
        W[i, j] = w
        W[j, i] = w
    return W


def build_nested_subgraphs(W, n_cuts, seed=SUB_SEQ_SEED):
    """固定 permutation 的嵌套节点子集 → 各取最大连通分量。"""
    n = W.shape[0]
    rng = np.random.RandomState(seed)
    perm = rng.permutation(n)
    out = []
    for cut in n_cuts:
        nodes = perm[:cut]
        # 诱导子图的连通分量（BFS on dense bool adjacency）
        adj = W[np.ix_(nodes, nodes)] != 0
        seen = np.zeros(cut, dtype=bool)
        best = []
        for st in range(cut):
            if seen[st]:
                continue
            comp = []
            stack = [st]
            seen[st] = True
            while stack:
                v = stack.pop()
                comp.append(v)
                nxt = np.where(adj[v] & ~seen)[0]
                for u in nxt:
                    seen[u] = True
                    stack.append(int(u))
            if len(comp) > len(best):
                best = comp
        sub_nodes = nodes[best]
        out.append((cut, len(sub_nodes), W[np.ix_(sub_nodes, sub_nodes)]))
    return out, perm


def seed_P(k):
    ss = np.random.SeedSequence([P_BASE_SEED, k])
    return int(ss.generate_state(1)[0]) & 0xFFFFFFFF


SEED_LOG = []


def seed_H(k):
    s = hw_u64() & 0xFFFFFFFF
    SEED_LOG.append((k, s))
    return s


def main():
    t_all = time.time()
    W = load_W()
    n = W.shape[0]
    sym = np.allclose(W, W.T)
    nnz = int((W != 0).sum())
    nz = W[W != 0]
    print(f"=== probe14 reconnaissance ===")
    print(f"connectome: n={n} nnz={nnz} symmetric={sym} "
          f"weights |min|={abs(nz).min():.4f} |max|={abs(nz).max():.4f}")
    print(f"hard_random source: {source_name}")
    print()

    # ② nested subgraphs
    cuts = [60, 90, 130, 180, 220, 279]
    subs, perm = build_nested_subgraphs(W, cuts)
    print("nested subgraphs (fixed perm seed %d):" % SUB_SEQ_SEED)
    for cut, neff, Ws in subs:
        print(f"  cut {cut:>3} -> largest component n_eff = {neff}")
    print()

    # ③ speed: one run at full size
    Wfull = subs[-1][2]
    t0 = time.perf_counter()
    r = glauber_stats(Wfull, 0.5, seed_H(0))
    t1 = time.perf_counter()   # includes JIT compile
    r = glauber_stats(Wfull, 0.5, seed_H(1))
    t2 = time.perf_counter()   # warm
    print(f"first call (with JIT): {t1-t0:.2f}s | warm single run: {t2-t1:.3f}s "
          f"(n={Wfull.shape[0]})")
    print(f"example run @beta=0.5: absm={r['absm']:.4f} chi={r['chi']:.3f} q={r['q']:.4f}")
    print()

    # ④ coarse beta sweep (reproduce probe12), 5 runs each, P-seed
    print("coarse beta sweep (5 runs, P-source) -- compare probe12 chi:")
    probe12_ref = {0.4: 1.47, 0.5: 3.61, 0.7: 1.66, 1.0: 1.02}
    for beta in (0.30, 0.40, 0.50, 0.60, 0.70, 0.85, 1.00):
        chis = []
        ms = []
        for k in range(5):
            res = glauber_stats(Wfull, beta, seed_P(k))
            chis.append(res['chi'])
            ms.append(res['absm'])
        ref = f"  (probe12: {probe12_ref[beta]:.2f})" if beta in probe12_ref else ""
        print(f"  beta={beta:.2f}  chi={np.mean(chis):8.3f} +- {np.std(chis):.3f}"
              f"  |m|={np.mean(ms):.4f}{ref}")
    print()
    print(f"total recon time: {time.time()-t_all:.1f}s")
    # record hardware seeds for audit
    if SEED_LOG:
        out = pathlib.Path(__file__).parent / 'probe14_recon_seeds.csv'
        with open(out, 'w', encoding='utf-8', newline='') as f:
            f.write("k,hw_seed32\n")
            for k, s in SEED_LOG:
                f.write(f"{k},{s}\n")
        print(f"hardware seeds logged: {out.name} ({len(SEED_LOG)} seeds)")


if __name__ == "__main__":
    main()
