#!/usr/bin/env python3
"""probe38 — 真库图体检首跑（「照会 §二·动作 3」兑现 · 只读）

对象：metadata.db 真库（05-07→07-22 运行史）——
  图 A 关系图：relations 端点（~71 节点 / 184 边）
  图 B 共现图：paragraph_entities（27587 实体；段内 pairwise 上限 264464 → 去重）
预登记：
  C1 图 A 全套（S / gap / t90）
  C2 图 B 全图（唯一边 / k̄ / 最大分量 S / gap / t90）——**判定"真库图是否已就绪"**
  C3 与合成 kNN 图（probe28：k̄ 8.51 / gap 0.0441 / t90 26–28）对照——方向不预设
口径注明：大图的 gap 用**对称归一化邻接的 λ2'**（eigsh 'LM' 快路径）——报告为 **L-gap = 1−λ2'**，
与 probe28 的 P-口径为同族非同数（仅作对照）。
"""
import sys
import time
import pathlib
import sqlite3

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'
con = sqlite3.connect(MD, uri=True)
cur = con.cursor()
_ = hr.hw_u64()
print(f"== probe38 真库图体检 (source: {hr.source_name}) ==")


def largest_comp(N, E):
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
    sizes = np.bincount(roots)
    return float(sizes.max() / N), int((sizes > 0).sum())


def gap_sym(N, E):
    a = np.array([x for x, _ in E])
    b = np.array([y for _, y in E])
    aa = np.concatenate([a, b])
    bb = np.concatenate([b, a])
    deg = np.bincount(aa, minlength=N)
    di = 1.0 / np.sqrt(np.maximum(deg, 1))
    data = di[aa] * di[bb]
    Anorm = csr_matrix((data, (aa, bb)), shape=(N, N))
    vals = eigsh(Anorm, k=2, which='LM', maxiter=10000)[0]
    vals = np.sort(vals)[::-1]
    return float(vals[0]), float(1.0 - vals[1])


def t90(N, E, nsrc=30, tmax=300):
    a = np.array([x for x, _ in E])
    b = np.array([y for _, y in E])
    aa = np.concatenate([a, b])
    bb = np.concatenate([b, a])
    deg = np.bincount(aa, minlength=N)
    wgt = 1.0 / np.maximum(deg, 1)
    pi = deg / deg.sum()
    srcs = [hr.hw_u64() % N for _ in range(nsrc)]
    outs = []
    for s in srcs:
        if deg[s] == 0:
            outs.append(-1)
            continue
        p = np.zeros(N)
        p[s] = 1.0
        t = 0
        while t <= tmax:
            tv = 0.5 * np.abs(p - pi).sum()
            if tv <= 0.1:
                break
            p = np.bincount(bb, weights=p[aa] * wgt[aa], minlength=N)
            t += 1
        outs.append(t if t <= tmax else -1)
    return float(np.median(outs))


# ---------- 图 A ----------
print("\n### 图 A：关系图")
pairs = cur.execute('SELECT subject, object FROM relations').fetchall()
nodes = sorted({x for p in pairs for x in p})
idxA = {n: i for i, n in enumerate(nodes)}
EA = [(idxA[s], idxA[o]) for s, o in pairs]
NA = len(nodes)
print(f"  nodes {NA} | edges {len(EA)} | kbar {2*len(EA)/max(1,NA):.2f}")
SA, nA = largest_comp(NA, EA)
l1, gA = gap_sym(NA, EA)
tA = t90(NA, EA)
print(f"  S={SA:.4f} comps={nA} | L-gap={gA:.6f} (λ1={l1:.4f}) | t90={tA:.1f}")

# ---------- 图 B ----------
print("\n### 图 B：共现图（建边中…）")
t0 = time.time()
grp = {}
for p, e in cur.execute('SELECT paragraph_hash, entity_hash FROM paragraph_entities'):
    grp.setdefault(p, []).append(e)
edges = set()
for e_list in grp.values():
    m = len(e_list)
    for i in range(m):
        for j in range(i + 1, m):
            x, y = e_list[i], e_list[j]
            edges.add((x, y) if x < y else (y, x))
print(f"  unique edges: {len(edges)}  ({time.time()-t0:.1f}s)")
ents = sorted({x for e in edges for x in e})
idxB = {n: i for i, n in enumerate(ents)}
EB = [(idxB[x], idxB[y]) for x, y in edges]
NB = len(ents)
print(f"  nodes {NB} | edges {len(EB)} | kbar {2*len(EB)/NB:.2f}")
SB, nB = largest_comp(NB, EB)
print(f"  S={SB:.4f} comps={nB}")
l1b, gB = gap_sym(NB, EB)
print(f"  L-gap={gB:.6f} (λ1={l1b:.4f})")
tB = t90(NB, EB)
print(f"  t90={tB:.1f}")

con.close()
print("\n== 对照（合成 kNN 图 probe28）: kbar 8.51 | gap(P口径) 0.0441 | t90 26–28 ==")
print("done (probe38).")
