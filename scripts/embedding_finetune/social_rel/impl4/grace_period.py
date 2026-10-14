#!/usr/bin/env python3
"""social_rel · s5.5（v2 终版）—— silent 成熟期（方向 D）

v1 失败记录：新节点用随机向量（与任何查询 sim≈0.06）→ 永远挤不进 top5 → 全档零噪声，
装置没有造出"竞争"。修法：按假说的真实机制建模——
  "未巩固的记忆" = 似是而非：新节点里
    · 55% "假新"（未成熟偏自信）：向量贴近某簇中心（σ=0.25，sim 高、能挤 top5），
      但其真实语义属于**别的**簇（label ≠ 向量的簇）——"看起来像 A，其实是 B"
    · 45% "真新"：向量较散（σ=0.35），label 与向量簇一致——"真但还没长稳"

世界：300 稳定（10 簇 × 30）+ 每轮 30 新节点 × 10 轮 = 300 新；每轮 50 查询（稳定节点）。
检索 = 余弦 sim top-5；对照变量只有 G（同种子重建，控制变量）。
指标：噪声注入率（top5 中假新占比）· 正确命中率（top5 中稳定同簇 + 真新同簇）。
预登记判据：存在 G≥1 使 噪声降幅>50% 且 命中降幅≤5%。

x 装置（§9）：导出各 G 聚合 CSV → wolframscript 独立对拍。

Run: ../../.venv/Scripts/python.exe grace_period.py
"""

import numpy as np
import pathlib

N_STABLE = 300
D_DIM = 256
N_CLUSTER = 10
NEW_PER_ROUND = 30
N_ROUND = 10
Q_PER_ROUND = 50
K = 5
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x68_grace_aggregate.csv')


def build_world():
    rng = np.random.RandomState(SEED)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_STABLE)
    stable = centers[labels] + rng.normal(0, 0.3, (N_STABLE, D_DIM))
    stable /= (np.linalg.norm(stable, axis=1, keepdims=True) + 1e-9)
    return centers, stable, labels, rng


def run(G):
    centers, stable, labels, rng = build_world()
    new_vecs, add_rounds, new_kind, new_true_label = [], [], [], []

    noise_top, hit_top, n_q = 0, 0, 0
    for r in range(N_ROUND):
        for _ in range(NEW_PER_ROUND):
            fake = rng.random() < 0.55
            c = rng.randint(0, N_CLUSTER)
            sigma = 0.25 if fake else 0.35
            v = centers[c] + rng.normal(0, sigma, D_DIM)
            v = v / (np.linalg.norm(v) + 1e-9)
            if fake:
                other = c
                while other == c:
                    other = rng.randint(0, N_CLUSTER)
                new_true_label.append(other)
            else:
                new_true_label.append(c)
            new_vecs.append(v)
            add_rounds.append(r)
            new_kind.append("fake" if fake else "true")
        for _ in range(Q_PER_ROUND):
            qi = rng.randint(0, N_STABLE)
            q = stable[qi]
            sims_s = stable @ q
            sims_s[qi] = -2.0
            cand = [("s", i, float(sims_s[i])) for i in range(N_STABLE)]
            for j in range(len(new_vecs)):
                if add_rounds[j] > r - G:
                    continue
                cand.append(("n", j, float(new_vecs[j] @ q)))
            cand.sort(key=lambda t: -t[2])
            for t in cand[:K]:
                if t[0] == "s" and labels[t[1]] == labels[qi]:
                    hit_top += 1
                elif t[0] == "n":
                    j = t[1]
                    if new_kind[j] == "fake":
                        noise_top += 1
                    elif new_true_label[j] == labels[qi]:
                        hit_top += 1
            n_q += 1
    return noise_top, hit_top, n_q * K


def main():
    print("=== s5.5 v2: silent grace period (direction D) ===")
    print("world: %d stable (%d clusters) + %d new/round x %d rounds | K=%d"
          % (N_STABLE, N_CLUSTER, NEW_PER_ROUND, N_ROUND, K))
    print()
    print("%-6s %14s %14s" % ("G", "noise_rate", "hit_rate"))
    print("-" * 38)
    rows = []
    base = None
    for G in (0, 1, 2, 3, 5):
        nt, ht, tot = run(G)
        nr, hr = nt / tot, ht / tot
        if G == 0:
            base = (nr, hr)
        drop = (base[0] - nr) / base[0] * 100 if base[0] > 0 else 0.0
        hdrop = (base[1] - hr) / base[1] * 100 if base[1] > 0 else 0.0
        print("%-6d %13.4f %13.4f   (noise delta %+6.1f%% / hit delta %+6.1f%%)" % (G, nr, hr, -drop, -hdrop))
        rows.append((G, nt, ht, tot, drop, hdrop))
    print()
    ok = any((row[0] >= 1 and row[4] > 50.0 and row[5] <= 5.0) for row in rows)
    print("=== verdict (pre-registered) ===")
    print("exists G>=1 with noise drop>50 and hit drop<=5 : " + ("PASS" if ok else "FAIL"))
    print("(2026-10-14, s5.5 v2)")

    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("G,noise_top,hit_top,total\n")
        for (G, nt, ht, tot, _, _) in rows:
            f.write("%d,%d,%d,%d\n" % (G, nt, ht, tot))
    print("x68 sample exported: %s" % OUT_CSV.name)


if __name__ == "__main__":
    main()
