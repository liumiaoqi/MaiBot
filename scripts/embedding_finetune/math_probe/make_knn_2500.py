# -*- coding: utf-8 -*-
"""从 A_memorix graph 向量建 kNN 语义图（子集）并验证连通性
   数据源（只读副本）：a-memorix/vectors/graph/{vectors.bin, vectors_ids.bin}
"""
import numpy as np
import pathlib

T = pathlib.Path(r'C:/Users/lmq/AppData/Local/Temp/cg5')
vec = np.fromfile(T / 'vectors.bin', dtype=np.float16).reshape(-1, 1024).astype(np.float32)
ids = np.fromfile(T / 'vectors_ids.bin', dtype=np.int64)
print('vec:', vec.shape, 'ids:', ids.shape)
assert vec.shape[0] == ids.shape[0] == 29260

# 归一化（余弦）
vec /= (np.linalg.norm(vec, axis=1, keepdims=True) + 1e-9)

rng = np.random.RandomState(20261014)
sel = rng.choice(29260, 2500, replace=False)
V = vec[sel]
ID = ids[sel]

# 暴力 kNN（余弦相似度），分块省内存
n = 2500
k = 6
S = V @ V.T
np.fill_diagonal(S, -2.0)
nn = np.argpartition(-S, k, axis=1)[:, :k]

edges = set()
for i in range(n):
    for j in nn[i]:
        a, b = (i, int(j)) if i < j else (int(j), i)
        edges.add((a, b))
print('symmetrized edges:', len(edges))

deg = np.zeros(n, dtype=int)
adj = [[] for _ in range(n)]
for a, b in edges:
    deg[a] += 1
    deg[b] += 1
    adj[a].append(b)
    adj[b].append(a)
print('degree mean=%.2f max=%d min=%d' % (deg.mean(), deg.max(), deg.min()))

# 连通性（BFS 大组件）
seen = np.zeros(n, dtype=bool)
comps = []
for s in range(n):
    if seen[s]:
        continue
    stack, comp = [s], []
    seen[s] = True
    while stack:
        u = stack.pop()
        comp.append(u)
        for v in adj[u]:
            if not seen[v]:
                seen[v] = True
                stack.append(v)
    comps.append(comp)
comps.sort(key=len, reverse=True)
print('components:', len(comps), '| top5 sizes:', [len(c) for c in comps[:5]])

# 样例（随机节点的近邻相似度）
i0 = int(rng.randint(n))
print('sample node idx %d  top-k nn sims:' % i0, [round(float(S[i0, j]), 3) for j in nn[i0]])

# 存图（给实验用）
np.savez(T / 'knn_graph.npz',
         edges=np.array(sorted(edges), dtype=np.int32),
         sub_idx=sel.astype(np.int32),
         sub_ids=ID)
print('saved knn_graph.npz')
