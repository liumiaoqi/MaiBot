#!/usr/bin/env python3
"""probe29b — 删边极端档（50–99%）：相变点追踪（probe29 的续）

对象/操作/随机源/重复：同 probe29（knn_graph_2500；随机删用硬随机、20 重复；度序 1 次确定）
网格：p ∈ {50, 60, 70, 75, 80, 85, 90, 95, 97, 99}（衔接 probe29 的 50% 点）
测量：S(p) 最大分量占比 + t90（TV≤0.1 的中位步数；-1 = 300 步未达）
预登记判据：
  M4 随机臂 p½ ∈ (50, 99]：**预期 ≈80–90%**（剩余平均度逼近 1 时发生碎裂）
  M5 若 99% 仍未跌破 0.5 → 记「极端删除下都不碎」（冗余度上限结论）
注：跳过谱隙（贵且极端档意义弱）；warm-up 已修（照 probe29 教训）。
"""
import sys
import pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

N = 2500
PGRID = [50, 60, 70, 75, 80, 85, 90, 95, 97, 99]

d = np.load('knn_graph_2500.npz')
E0 = d['edges'].astype(np.int64)
M0 = len(E0)
deg0 = np.bincount(E0.ravel(), minlength=N)
_ = hr.hw_u64()  # warm-up：触发懒初始化（否则 source_name 显示 init 前默认值）
print("== probe29b: extreme edge-drop (50-99%) ==")
print(f"hardware source: {hr.source_name} | n={N} m={M0} kbar={deg0.mean():.2f}")


def pick_drop_random(m, k):
    limit = (2 ** 64 // m) * m
    seen = set()
    while len(seen) < k:
        v = hr.hw_u64()
        if v < limit:
            seen.add(v % m)
    return np.fromiter(seen, dtype=np.int64)


deg_sum = deg0[E0[:, 0]] + deg0[E0[:, 1]]
order_degree = np.argsort(-deg_sum, kind='stable')

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


print("\np%      S random (median [p10,p90])        S degree      t90 rand / deg")
S_rand, S_deg = {}, {}
for p in PGRID:
    k = int(round(M0 * p / 100))
    rats = []
    for rep in range(20):
        E = np.delete(E0, pick_drop_random(M0, k), axis=0)
        rats.append(largest_comp_ratio(E))
    s_r = float(np.median(rats))
    lo, hi = np.percentile(rats, [10, 90])
    S_rand[p] = s_r
    E = np.delete(E0, order_degree[:k], axis=0)
    s_d = largest_comp_ratio(E)
    S_deg[p] = s_d
    # 扩散：随机臂取 5 重复中位（省），度序 1 次
    tv = []
    for rep in range(5):
        E2 = np.delete(E0, pick_drop_random(M0, k), axis=0)
        tv.append(t90(E2))
    m_r = float(np.median(tv))
    m_d = t90(E)
    print(f"{p:>4}    {s_r:.4f}  [{lo:.3f},{hi:.3f}]      {s_d:.4f}      {m_r:>5.1f} / {m_d:>5.1f}")

print("\n## verdict (pre-registered)")
hits_r = [p for p in PGRID if S_rand[p] < 0.5]
hits_d = [p for p in PGRID if S_deg[p] < 0.5]
print(f"M4 random p-half in (50,99]: {'FOUND ' + str(hits_r[0]) + '%' if hits_r else 'NOT FOUND'}"
      f" | degree p-half: {'FOUND ' + str(hits_d[0]) + '%' if hits_d else 'NOT FOUND'}")
print(f"M5 no-collapse-at-99%: {'YES (robust)' if not hits_r and not hits_d else 'see above'}")
print("\ndone. (2026-10-15, probe29b)")
