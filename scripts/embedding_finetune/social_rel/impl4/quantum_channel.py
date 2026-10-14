#!/usr/bin/env python3
"""social_rel · s5.7 —— 综合系统 v2：融入扩散通道（量子实验的正式接缝）

背景：s5.6 综合系统 = sim 排序 + grace（两个可移植组件）。扩散在 s5.2 被判定为
「非竞争者、远端补充通道」——但当时只在纯图世界测过。本实验把它真正装进综合系统：
  在语义 kNN 图上跑热核扩散（量子实验 exp61/65 的同一动力学），
  每查询以「探索位」（m 个席位）引入扩散激活的节点，其余席位留给 sim 排序。

臂（共享世界/查询流/grace=2）：
  a. v1        sim + grace（s5.6 基线）
  b. +diff-1   sim 4 席 + 扩散 1 席（探索位 m=1）
  c. +diff-2   sim 3 席 + 扩散 2 席（m=2）

预登记判据：
  P1  b 的命中 ≥ a（探索位不亏；允许 ≤2% 波动）
  P2  扩散席位的命中率 > 随机水平（0.29 基线）——捞到的不是噪声
  P3  b 的噪声 ≤ a 的 1.05 倍

x70（§9）：计数 CSV → wolframscript 独立重算率对拍。

Run: ../../.venv/Scripts/python.exe quantum_channel.py
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
GRACE = 2
DIFF_T = 2.0
KNN_K = 6
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x70_quantum_channel_counts.csv')


def main():
    rng = np.random.RandomState(SEED)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_STABLE)
    stable = centers[labels] + rng.normal(0, 0.3, (N_STABLE, D_DIM))
    stable /= (np.linalg.norm(stable, axis=1, keepdims=True) + 1e-9)

    new_vecs, add_rounds, new_kind, new_true_label = [], [], [], []
    per_q = []

    for r in range(N_ROUND):
        for _ in range(NEW_PER_ROUND):
            fake = rng.random() < 0.55
            c = rng.randint(0, N_CLUSTER)
            sigma = 0.25 if fake else 0.35
            v = centers[c] + rng.normal(0, sigma, D_DIM)
            v /= (np.linalg.norm(v) + 1e-9)
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
                if add_rounds[j] > r - GRACE:
                    continue
                cand.append(("n", j, float(new_vecs[j] @ q)))
            cand.sort(key=lambda t: -t[2])
            per_q.append((cand, qi, r))

    print(f"=== s5.7: integrated v2 with diffusion channel ===")
    print(f"queries={len(per_q)} | grace={GRACE} | diffusion: kNN(k={KNN_K}, t={DIFF_T}) on final snapshot")

    # 建 kNN 图（末期快照近似：全部稳定 + 全部新）
    nodes = np.vstack([stable] + ([np.array(new_vecs)] if new_vecs else []))
    n_nodes = nodes.shape[0]
    Sg = nodes @ nodes.T
    np.fill_diagonal(Sg, -2.0)
    knn = np.argpartition(-Sg, KNN_K, axis=1)[:, :KNN_K]
    Wm = np.zeros((n_nodes, n_nodes))
    for i in range(n_nodes):
        for j in knn[i]:
            Wm[i, int(j)] = Wm[int(j), i] = 1.0
    deg = Wm.sum(1)
    vl, ul = np.linalg.eigh(np.diag(deg) - Wm)
    print(f"graph: {n_nodes} nodes, edges={int(Wm.sum()//2)}")

    idx = {}  # 节点键 -> 图内下标
    for i in range(N_STABLE):
        idx[("s", i)] = i
    for j in range(len(new_vecs)):
        idx[("n", j)] = N_STABLE + j

    def diff_top(seed_key, m, exclude, r):
        seed = idx[seed_key]
        p0 = np.zeros(n_nodes)
        p0[seed] = 1.0
        coef = ul.T @ p0
        p = ul @ (np.exp(-vl * DIFF_T) * coef)
        order = np.argsort(-p)
        out = []
        for gi in order:
            if len(out) >= m:
                break
            key = ("s", gi) if gi < N_STABLE else ("n", gi - N_STABLE)
            if key in exclude:
                continue
            if key[0] == "n" and add_rounds[key[1]] > r - GRACE:
                continue      # 新节点 grace 过滤（与 sim 候选同口径）
            out.append(key)
        return out

    def score(key, qi):
        if key[0] == "s" and labels[key[1]] == labels[qi]:
            return 1, 0
        if key[0] == "n":
            j = key[1]
            if new_kind[j] == "fake":
                return 0, 1
            if new_true_label[j] == labels[qi]:
                return 1, 0
        return 0, 0

    stats = {arm: dict(noise=0, hit=0.0, kept=0, diff_hit=0, diff_total=0) for arm in ("a", "b", "c")}

    for (cand, qi, r) in per_q:
        sim_top = cand[:K]
        # a: v1
        for t in sim_top:
            h, nz = score((t[0], t[1]), qi)
            stats["a"]["hit"] += h; stats["a"]["noise"] += nz
        stats["a"]["kept"] += 1
        # 扩散候选（seed = sim top1 的节点）
        seed_key = (cand[0][0], cand[0][1])
        for arm, m in (("b", 1), ("c", 2)):
            sim_part = cand[: K - m]
            exclude = {(t[0], t[1]) for t in sim_part}
            dpart = diff_top(seed_key, m, exclude, r)
            keys = [(t[0], t[1]) for t in sim_part] + dpart
            for kk in keys:
                h, nz = score(kk, qi)
                stats[arm]["hit"] += h; stats[arm]["noise"] += nz
                if kk in dpart:
                    stats[arm]["diff_hit"] += h
                    stats[arm]["diff_total"] += 1
            stats[arm]["kept"] += 1

    n_q = len(per_q)
    print()
    print(f"{'arm':<6} {'noise_rate':>12} {'hit_rate':>10} {'diff_slot_hit':>14}")
    print("-" * 50)
    rows = {}
    for arm in ("a", "b", "c"):
        s = stats[arm]
        slots = s["kept"] * K
        noise_rate = s["noise"] / slots if slots else 0.0
        hit_rate = s["hit"] / (n_q * K)
        dh = s["diff_hit"] / s["diff_total"] if s["diff_total"] else float("nan")
        rows[arm] = (noise_rate, hit_rate, dh)
        print(f"{arm:<6} {noise_rate:>12.4f} {hit_rate:>10.4f} {dh:>14.4f}")
    print()
    P1 = rows["b"][1] >= rows["a"][1] - 0.02 * rows["a"][1]
    P2 = rows["b"][2] > rows["a"][1]
    P3 = rows["b"][0] <= 1.05 * rows["a"][0]
    print("=== verdict (pre-registered) ===")
    print(f"P1 explore slot not losing (hit>=0.98*a): {'PASS' if P1 else 'FAIL'}")
    print(f"P2 diffusion slot hit-rate > baseline hit: {'PASS' if P2 else 'FAIL'}")
    print(f"P3 noise not worse (<=1.05*a): {'PASS' if P3 else 'FAIL'}")
    print("(2026-10-14, s5.7)")

    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("arm,noise,hit,kept,diff_hit,diff_total,n_q\n")
        for arm in ("a", "b", "c"):
            s = stats[arm]
            f.write(f"{arm},{s['noise']},{s['hit']},{s['kept']},{s['diff_hit']},{s['diff_total']},{n_q}\n")
    print(f"x70 counts exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
