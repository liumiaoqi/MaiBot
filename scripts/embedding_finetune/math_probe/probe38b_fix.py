#!/usr/bin/env python3
"""probe38b — 真库图体检·修正补算（最大分量内口径 · 只读）

修 probe38 的口径坑：「L-gap 用 eigsh 'LM'」在不连通/二分/简并图上会取到 λ=-1（输出伪值 2.0）。
正确做法：① 非连通图 L-gap=0（由分量数直接判定）；② 主读数改用**最大分量内部**的
gap（'LA' 口径——最大代数，避开 -1）与 t90。对象同 probe38。
"""
import sys, pathlib, sqlite3
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.linalg import eigsh
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'
con = sqlite3.connect(MD, uri=True); cur = con.cursor()
_ = hr.hw_u64()
print(f"== probe38b 修正补算 (source: {hr.source_name}) ==")


def maxcomp(N, E):
    parent = np.arange(N)
    def find(x):
        r = x
        while parent[r] != r: r = parent[r]
        while parent[x] != r: parent[x], x = r, parent[x]
        return r
    for a, b in E:
        ra, rb = find(a), find(b)
        if ra != rb: parent[ra] = rb
    roots = np.array([find(i) for i in range(N)])
    sizes = np.bincount(roots)
    big = int(np.argmax(sizes))
    mem = np.where(roots == big)[0]
    remap = {v: i for i, v in enumerate(mem)}
    E2 = [(remap[a], remap[b]) for a, b in E if a in remap and b in remap]
    return len(mem), E2, sizes.max() / N


def gap_LA(N, E):
    a = np.array([x for x, _ in E]); b = np.array([y for _, y in E])
    aa = np.concatenate([a, b]); bb = np.concatenate([b, a])
    deg = np.bincount(aa, minlength=N)
    di = 1.0 / np.sqrt(np.maximum(deg, 1))
    Anorm = csr_matrix((di[aa] * di[bb], (aa, bb)), shape=(N, N))
    vals = eigsh(Anorm, k=2, which='LA', maxiter=10000)[0]
    vals = np.sort(vals)[::-1]
    return float(vals[0]), float(1.0 - vals[1])


def t90(N, E, nsrc=30, tmax=400):
    a = np.array([x for x, _ in E]); b = np.array([y for _, y in E])
    aa = np.concatenate([a, b]); bb = np.concatenate([b, a])
    deg = np.bincount(aa, minlength=N)
    wgt = 1.0 / np.maximum(deg, 1); pi = deg / deg.sum()
    outs = []
    for _ in range(nsrc):
        s = hr.hw_u64() % N
        p = np.zeros(N); p[s] = 1.0; t = 0
        while t <= tmax:
            tv = 0.5 * np.abs(p - pi).sum()
            if tv <= 0.1: break
            p = np.bincount(bb, weights=p[aa] * wgt[aa], minlength=N); t += 1
        outs.append(t if t <= tmax else -1)
    return float(np.median(outs))


# 图 A
pairs = cur.execute('SELECT subject, object FROM relations').fetchall()
nodes = sorted({x for p in pairs for x in p}); idxA = {n: i for i, n in enumerate(nodes)}
EA = [(idxA[s], idxA[o]) for s, o in pairs]
NA = len(nodes)
MA, EA2, SA = maxcomp(NA, EA)
l1, gA = gap_LA(MA, EA2)
tA = t90(MA, EA2)
print(f"图A 最大分量: {MA}/{NA} (S={SA:.4f}) | LA λ1={l1:.4f} L-gap={gA:.6f} | t90={tA:.1f}")

# 图 B
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
ents = sorted({x for e in edges for x in e}); idxB = {n: i for i, n in enumerate(ents)}
EB = [(idxB[x], idxB[y]) for x, y in edges]
NB = len(ents)
MB, EB2, SB = maxcomp(NB, EB)
l1b, gB = gap_LA(MB, EB2)
tB = t90(MB, EB2)
print(f"图B 最大分量: {MB}/{NB} (S={SB:.4f}) | LA λ1={l1b:.4f} L-gap={gB:.6f} | t90={tB:.1f}")
con.close()
print("对照: 合成 kNN(Pgap 0.0441 · t90 26-28) | done (probe38b).")
