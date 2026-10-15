#!/usr/bin/env python3
"""probe31 — 恢复与滞后：删-恢复的代数（「疤痕」实验）

背景：probe29/29b/30 测的是「删」（抵抗力）。本探针补「恢复力」：
**同密度、不同历史的图，行为一样吗？**——即：删了再补回来，能不能回到没删过的状态？

设计（预登记）：
  基线            : 原图
  参照 A          : 直接度序删 50%
  参照 B          : 直接随机删 50%（10 重复取中位）
  M0【全恢复回归】: 随机删 50% → **全加回** ⇒ 应 = 基线（精确）
  M1【互逆无痕】  : 度序删 85% → **按删除逆序恢复 35%**（剩删=前 50% 高分集）⇒ 应 = 参照 A（精确——验证实现）
  M2【随机恢复】  : 度序删 85% → **随机恢复 35%** ⇒ vs 参照 A 的差 = **疤痕**
  M3【全随机】    : 随机删 85% → 随机恢复 35% ⇒ vs 参照 B 的差 = 疤痕（10 重复中位）
指标：S（最大分量）/ t90（扩散混合）/ gap（谱隙——只在基线·参照A·M2 三点各测一次）
预期（先写后跑）：M0/M1 无差（可逆性由"精确逆操作"保证）；M2/M3 有差——**疤痕的形态是发现，不预设方向**。

随机源：hard_random.py（rdrand）。
"""
import sys
import pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

N = 2500

d = np.load('knn_graph_2500.npz')
E0 = d['edges'].astype(np.int64)
M0n = len(E0)
deg0 = np.bincount(E0.ravel(), minlength=N)
_ = hr.hw_u64()  # warm-up
print(f"== probe31: recovery & hysteresis (source: {hr.source_name}) ==")
print(f"n={N} m={M0n} kbar={deg0.mean():.2f}")

deg_sum = deg0[E0[:, 0]] + deg0[E0[:, 1]]
order_degree = np.argsort(-deg_sum, kind='stable')


def pick_k_idx(m, k):
    """硬随机选 k 个不同索引。"""
    limit = (2 ** 64 // m) * m
    seen = set()
    while len(seen) < k:
        v = hr.hw_u64()
        if v < limit:
            seen.add(v % m)
    return np.fromiter(seen, dtype=np.int64)


def largest_comp_ratio(E):
    parent = np.arange(N)

    def find(x):
        r = x
        while parent[r] != r:
            r = parent[r]
        while parent[x] != r:
            parent[x], x = r, parent[x]
        return r

    for a, b in E:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    roots = np.array([find(i) for i in range(N)])
    return np.bincount(roots).max() / N


srcs = []
seen = set()
while len(srcs) < 20:
    v = hr.hw_u64()
    s = v % N
    if s not in seen:
        seen.add(s)
        srcs.append(s)
srcs = np.array(srcs)


def t90(E, tmax=300):
    a = np.concatenate([E[:, 0], E[:, 1]])
    b = np.concatenate([E[:, 1], E[:, 0]])
    if len(a) == 0:
        return -1.0
    deg = np.bincount(a, minlength=N)
    wgt = 1.0 / np.maximum(deg, 1)
    pi = deg / deg.sum()
    tvals = []
    for s in srcs:
        if deg[s] == 0:
            tvals.append(-1)
            continue
        p = np.zeros(N)
        p[s] = 1.0
        t = 0
        while t <= tmax:
            tv = 0.5 * np.abs(p - pi).sum()
            if tv <= 0.1:
                break
            p = np.bincount(b, weights=p[a] * wgt[a], minlength=N)
            t += 1
        tvals.append(t if t <= tmax else -1)
    return float(np.median(tvals))


def gap_of(E):
    A = np.zeros((N, N))
    np.add.at(A, (E[:, 0], E[:, 1]), 1.0)
    np.add.at(A, (E[:, 1], E[:, 0]), 1.0)
    deg = A.sum(1)
    P = A / np.maximum(deg, 1)[:, None]
    mag = np.sort(np.abs(np.linalg.eigvals(P)))[::-1]
    return float(1.0 - mag[1])


def keep_by_dropset(drop_idx):
    mask = np.ones(M0n, dtype=bool)
    mask[drop_idx] = False
    return E0[mask]


def merge_back(kept_E, add_idx):
    return np.vstack([kept_E, E0[add_idx]])


k50 = int(round(M0n * 0.50))
k85 = int(round(M0n * 0.85))
k35 = k85 - k50  # 85% → 50% 的恢复量

print("\n### 基线")
S_base = largest_comp_ratio(E0)
t_base = t90(E0)
print(f"S={S_base:.4f}  t90={t_base:.1f}")

print("\n### 参照 A：直接度序删 50%")
EA = keep_by_dropset(order_degree[:k50])
S_A = largest_comp_ratio(EA)
t_A = t90(EA)
g_A = gap_of(EA)
print(f"S={S_A:.4f}  t90={t_A:.1f}  gap={g_A:.6f}")

print("\n### 参照 B：直接随机删 50%（10 重复）")
Sb, tb = [], []
for rep in range(10):
    EB = keep_by_dropset(pick_k_idx(M0n, k50))
    Sb.append(largest_comp_ratio(EB))
    tb.append(t90(EB))
S_B, t_B = float(np.median(Sb)), float(np.median(tb))
print(f"S={S_B:.4f} (p10={np.percentile(Sb,10):.4f})  t90={t_B:.1f}  [范围 {min(tb):.0f}–{max(tb):.0f}]")

print("\n### M0：随机删 50% → 全恢复（应=基线）")
drop = pick_k_idx(M0n, k50)
E_kept = keep_by_dropset(drop)
E_M0 = merge_back(E_kept, drop)
S_M0 = largest_comp_ratio(E_M0)
t_M0 = t90(E_M0)
print(f"S={S_M0:.4f}  t90={t_M0:.1f}  → 与基线差: ΔS={S_M0-S_base:+.4f}  Δt={t_M0-t_base:+.1f}")

print("\n### M1：度序删 85% → 逆序恢复 35%（应=参照 A）")
E85 = keep_by_dropset(order_degree[:k85])
E_M1 = merge_back(E85, order_degree[k50:k85])  # 逆序恢复 = 把「最后删的 35%」加回
S_M1 = largest_comp_ratio(E_M1)
t_M1 = t90(E_M1)
print(f"S={S_M1:.4f}  t90={t_M1:.1f}  → 与参照A差: ΔS={S_M1-S_A:+.4f}  Δt={t_M1-t_A:+.1f}")

print("\n### M2：度序删 85% → 随机恢复 35%（vs 参照 A；疤痕）")
E_M2 = merge_back(E85, order_degree[:k85][pick_k_idx(k85, k35)])
S_M2 = largest_comp_ratio(E_M2)
t_M2 = t90(E_M2)
g_M2 = gap_of(E_M2)
print(f"S={S_M2:.4f}  t90={t_M2:.1f}  gap={g_M2:.6f}  → 与参照A差: ΔS={S_M2-S_A:+.4f}  Δt={t_M2-t_A:+.1f}  Δgap={g_M2-g_A:+.6f}")

print("\n### M3：随机删 85% → 随机恢复 35%（vs 参照 B；10 重复）")
Sm, tm = [], []
for rep in range(10):
    D85 = pick_k_idx(M0n, k85)
    E85r = keep_by_dropset(D85)
    E_M3 = merge_back(E85r, D85[pick_k_idx(k85, k35)])
    Sm.append(largest_comp_ratio(E_M3))
    tm.append(t90(E_M3))
S_M3, t_M3 = float(np.median(Sm)), float(np.median(tm))
print(f"S={S_M3:.4f} (p10={np.percentile(Sm,10):.4f})  t90={t_M3:.1f}  → 与参照B差: ΔS={S_M3-S_B:+.4f}  Δt={t_M3-t_B:+.1f}")

print("\n### 判词核对（预登记）")
print(f"M0 全恢复回归: ΔS={S_M0-S_base:+.4f} (期望≈0)")
print(f"M1 互逆无痕:   ΔS={S_M1-S_A:+.4f} (期望=0——由构造保证)")
print(f"M2 疤痕(度序): ΔS={S_M2-S_A:+.4f} Δt={t_M2-t_A:+.1f} Δgap={g_M2-g_A:+.6f}")
print(f"M3 疤痕(随机): ΔS={S_M3-S_B:+.4f} Δt={t_M3-t_B:+.1f}")
print("\ndone. (2026-10-15, probe31)")
