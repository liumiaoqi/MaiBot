#!/usr/bin/env python3
"""probe30 — 断崖区反转的机制解剖（85% 删除的剩余图分析）

背景：probe29b 在 85% 删除处发现反转——随机臂最大分量 0.148 [0.08,0.25]，度序臂 0.415。
本探针解剖两臂的**剩余图**，找机制线索（不预设结论）。

对象：knn_graph_2500 的 85% 删边二臂（随机 6 重复 + 度序 1 次；硬随机同源）。
指标（预登记）：
  a) 剩余度：零度点占比 / 剩余平均度
  b) 分量结构：最大分量占比 / 前 5 分量 / 分量总数
  c) 剩余边的「原图度」特征：端点 min 度均值 / 低-低边占比（两端原度 ≤ 8）
  d) 最大分量成员的「原图度」均值（大分量保住的是谁）
预期（H，先写后跑）：
  H1 度序臂剩余边显著偏「低-低」（高-高边被优先删光）；
  H2 度序臂孤立点更少（低度点被保护）；随机臂大分量跨重复方差大（临界区波动）；
  H3 反转机制初步判据 = 两臂在 c/d 两项上的差异。
"""
import sys
import pathlib
import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

N = 2500
P = 85

d = np.load('knn_graph_2500.npz')
E0 = d['edges'].astype(np.int64)
M0 = len(E0)
deg0 = np.bincount(E0.ravel(), minlength=N)
_ = hr.hw_u64()  # warm-up
print("== probe30: mechanism dissection @ 85% edge-drop ==")
print(f"hardware source: {hr.source_name} | n={N} m={M0} kbar={deg0.mean():.2f}")

K = int(round(M0 * P / 100))


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


def analyze(E):
    a, b = E[:, 0], E[:, 1]
    deg_rem = np.bincount(np.concatenate([a, b]) if len(E) else np.array([], dtype=int),
                          minlength=N)
    zero = int((deg_rem == 0).sum())
    parent = np.arange(N)

    def find(x):
        r = x
        while parent[r] != r:
            r = parent[r]
        while parent[x] != r:
            parent[x], x = r, parent[x]
        return r

    for x, y in E:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry
    roots = np.array([find(i) for i in range(N)])
    sizes = np.bincount(roots)
    order = np.argsort(-sizes)
    comp_sizes = sizes[order]
    big_members = np.where(roots == order[0])[0]
    lo = np.minimum(deg0[a], deg0[b])
    hi = np.maximum(deg0[a], deg0[b])
    return dict(
        zero=zero,
        kbar_rem=float(deg_rem.mean()),
        comp_top5=[int(x) for x in comp_sizes[:5]],
        ncomp=int((comp_sizes > 0).sum()),
        big_frac=float(comp_sizes[0] / N),
        big_deg0_mean=float(deg0[big_members].mean()),
        lo_mean=float(lo.mean()),
        hi_mean=float(hi.mean()),
        lowlow=float((hi <= 8).mean()),
    )


print("\n## 随机臂（6 重复）")
rand_rows = []
for rep in range(6):
    E = np.delete(E0, pick_drop_random(M0, K), axis=0)
    r = analyze(E)
    rand_rows.append(r)
    print(f"  #{rep}: 零度 {r['zero']:>4} | 残余k̄ {r['kbar_rem']:.3f} | 分量数 {r['ncomp']:>4} | "
          f"最大 {r['big_frac']:.4f} | 前5 {r['comp_top5']} | 大分量原均度 {r['big_deg0_mean']:.2f} | "
          f"剩余边 lo/hi {r['lo_mean']:.2f}/{r['hi_mean']:.2f} | 低-低 {r['lowlow']:.3f}")

E = np.delete(E0, order_degree[:K], axis=0)
r = analyze(E)
print(f"## 度序臂: 零度 {r['zero']:>4} | 残余k̄ {r['kbar_rem']:.3f} | 分量数 {r['ncomp']:>4} | "
      f"最大 {r['big_frac']:.4f} | 前5 {r['comp_top5']} | 大分量原均度 {r['big_deg0_mean']:.2f} | "
      f"剩余边 lo/hi {r['lo_mean']:.2f}/{r['hi_mean']:.2f} | 低-低 {r['lowlow']:.3f}")

print("\n## 预期核对（H1/H2/H3）")
rl = np.mean([x['lowlow'] for x in rand_rows])
print(f"H1 低-低边占比: 随机 {rl:.3f} vs 度序 {r['lowlow']:.3f} "
      f"→ {'度序更偏低-低 ✓' if r['lowlow'] > rl + 0.05 else '差异不显著'}")
rz = np.mean([x['zero'] for x in rand_rows])
print(f"H2 零度点: 随机 {rz:.0f} vs 度序 {r['zero']} "
      f"→ {'度序更少 ✓' if r['zero'] < rz else '否'}")
rv = np.std([x['big_frac'] for x in rand_rows])
print(f"H2b 随机臂大分量跨重复 std = {rv:.4f}（[0.08,0.25] 级波动？）")
rb = np.mean([x['big_deg0_mean'] for x in rand_rows])
print(f"H3 大分量成员原均度: 随机 {rb:.2f} vs 度序 {r['big_deg0_mean']:.2f}")
print("\ndone. (2026-10-15, probe30)")
