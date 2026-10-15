#!/usr/bin/env python3
"""probe29 — 删边扰动与韧性：随机故障 vs 靶向攻击（probe28 的"韧性臂"）

对象：knn_graph_2500（n=2500，边 10634；度 6–29 均值 8.5）
操作：按比例 p 删边，两臂——
  ① **随机删**（硬随机器选边；重复 20 次取中位数）——「随机故障」
  ② **度序删**（按端点度之和降序删；确定性一次）——「靶向攻击」
测量（预登记）：
  A 连通：最大连通分量占比 S(p)
  B 扩散：t90 = 从源集出发 TV≤0.1 的中位步数（边列表实现；源集用硬随机选 20 个，固定）
  C 谱隙：p ∈ {0, 20, 40}% 的 1-|λ₂|（贵 → 随机臂 3 重复 / 度序 1 次）
预登记判据（方向性，先写后跑）：
  M1 「随机 10% 仍强连通」：S(10%) ≥ 0.8 —— 否则记「比预期脆弱」
  M2 「靶向更脆弱」：度序臂的 p½（S 跌破 0.5 的插值点）< 随机臂的 p½
  M3 「扩散单调放缓」：t90 随 p 单调不降；碎裂点之后 t90 不再有意义（标 n/a）
复算接口：主量（某点的 S 与 t90）交 x 装置独立复算（§9）。
诚实边界：删边=「记忆/关系被清理」的最粗扰动模型；非真库实验。
随机源：hard_random.py（RDSEED/RDRAND）；分层重复：连通 20 / 扩散 10 / 谱隙 3。
"""
import sys
import pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

N = 2500
PGRID = [0, 2, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50]

d = np.load('knn_graph_2500.npz')
E0 = d['edges'].astype(np.int64)
M0 = len(E0)
deg0 = np.bincount(E0.ravel(), minlength=N)
_ = hr.hw_u64()  # warm-up：触发懒初始化（否则 source_name 会显示 init 前的 "unavailable"——首版输出的显示瑕疵）
print("== probe29: edge-drop resilience ==")
print(f"hardware source: {hr.source_name} | n={N} m={M0} kbar={deg0.mean():.2f}")


def pick_drop_random(m, k):
    """硬随机选 k 个不同边索引（rejection sampling，无 modulo bias）。"""
    limit = (2 ** 64 // m) * m
    seen = set()
    while len(seen) < k:
        v = hr.hw_u64()
        if v < limit:
            seen.add(v % m)
    return np.fromiter(seen, dtype=np.int64)


# 度序（初始度）
deg_sum = deg0[E0[:, 0]] + deg0[E0[:, 1]]
order_degree = np.argsort(-deg_sum, kind='stable')

# 源集（硬随机，固定）
srcs = []
seen = set()
while len(srcs) < 20:
    v = hr.hw_u64()
    s = v % N
    if s not in seen:
        seen.add(s)
        srcs.append(s)
srcs = np.array(srcs)


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


def t90(E, tmax=300):
    a = np.concatenate([E[:, 0], E[:, 1]])
    b = np.concatenate([E[:, 1], E[:, 0]])
    deg = np.bincount(a, minlength=N)
    wgt = 1.0 / np.maximum(deg, 1)
    pi = deg / deg.sum()
    tvals = []
    for s in srcs:
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
    # 孤立点（度序删会产生）：行=0（次随机矩阵）；孤立点特征值 0，不干扰 λ₂ 口径
    P = A / np.maximum(deg, 1)[:, None]
    mag = np.sort(np.abs(np.linalg.eigvals(P)))[::-1]
    return float(1.0 - mag[1])


# ---------- A. 连通性 ----------
print("\n## A. largest-component ratio S(p)")
print("p%      random (median [p10,p90])          degree-ordered")
S_rand, S_deg = {}, {}
for p in PGRID:
    k = int(round(M0 * p / 100))
    if p > 0:
        rats = []
        for rep in range(20):
            E = np.delete(E0, pick_drop_random(M0, k), axis=0)
            rats.append(largest_comp_ratio(E))
        s_r = float(np.median(rats))
        lo, hi = np.percentile(rats, [10, 90])
        S_rand[p] = s_r
    else:
        s_r = largest_comp_ratio(E0)
        lo = hi = s_r
        S_rand[p] = s_r
    E = np.delete(E0, order_degree[:k], axis=0)
    s_d = largest_comp_ratio(E)
    S_deg[p] = s_d
    print(f"{p:>4}    {s_r:.4f}  [{lo:.3f},{hi:.3f}]        {s_d:.4f}")

# ---------- B. 扩散 t90 ----------
print("\n## B. diffusion t90 (median over 20 sources; -1 = not reached in 300)")
for p in PGRID:
    k = int(round(M0 * p / 100))
    if p > 0:
        tv = []
        for rep in range(10):
            E = np.delete(E0, pick_drop_random(M0, k), axis=0)
            tv.append(t90(E))
        m_r = float(np.median(tv))
    else:
        m_r = t90(E0)
    E = np.delete(E0, order_degree[:k], axis=0)
    m_d = t90(E)
    print(f"{p:>4}    random {m_r:>6.1f}      degree {m_d:>6.1f}")

# ---------- C. 谱隙 ----------
print("\n## C. spectral gap 1-|lambda2| (p in 0/20/40)")
for p in (0, 20, 40):
    k = int(round(M0 * p / 100))
    if p > 0:
        gs = []
        for rep in range(3):
            E = np.delete(E0, pick_drop_random(M0, k), axis=0)
            gs.append(gap_of(E))
        g_r = float(np.median(gs))
    else:
        g_r = gap_of(E0)
    E = np.delete(E0, order_degree[:k], axis=0)
    g_d = gap_of(E)
    print(f"{p:>4}    random {g_r:.6f}      degree {g_d:.6f}")

# ---------- 判据核对 ----------
print("\n## verdict (pre-registered)")
print(f"M1 S(10%)>=0.8 : {'PASS' if S_rand[10] >= 0.8 else 'FAIL'} (S={S_rand[10]:.3f})")
print(f"M2 degree p-half < random p-half : see curve above")
print(f"M3 t90 monotone non-decreasing : see curve above")
print("\ndone. (2026-10-15, probe29)")
