#!/usr/bin/env python3
"""s6.1 附属审计：bad 臂末点低因（v8 遗留异常）

v8 中 bad 臂（pu=0，all 口径）3-seed 末点 [0.58, 0.50, 0.42]（均值 0.50）。
崩坏成因审计：假设 H「未评池浮起」——所有被评价的本地节点 conf 被打崩，
而从未进过 top5、conf 恒 1.0 的异簇节点用 sim 噪声高尾占位。

本审计（与 v8 完全同流：rng 消费逐点对齐）打印：
  A. 每簇诱惑数分布（检验「分配不均」假设 → 期望上不成立，均匀摊）
  B. 末态 top5 构成：same-true / targeted-tempter / other-tempter / other-true
  C. 未评池的 sim 高尾对比：异簇真实 (n=90) vs 其他诱惑 (n≈18)
     —— 检验「为什么是其他诱惑占位而不是异簇真实」

Run: ../../.venv/Scripts/python.exe growth_bad_audit.py
"""

import numpy as np

N_NODES = 100
N_TEMP = 20
D_DIM = 32
N_CLUSTER = 10
Q_PER_BATCH = 60
K = 5
ROUNDS = 500
SIGMA_REAL = 0.35
SIGMA_TEMP = 0.25
SEEDS = (20261014, 20261015, 20261016)


def build(rng):
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_NODES)
    nodes = centers[labels] + rng.normal(0, SIGMA_REAL, (N_NODES, D_DIM))
    nodes /= (np.linalg.norm(nodes, axis=1, keepdims=True) + 1e-9)
    temp_target = rng.randint(0, N_CLUSTER, N_TEMP)
    temps = []
    for t in temp_target:
        v = centers[t] + rng.normal(0, SIGMA_TEMP, D_DIM)
        v /= (np.linalg.norm(v) + 1e-9)
        temps.append(v)
    temps = np.array(temps)
    temp_label = (temp_target + 1 + rng.randint(0, N_CLUSTER - 1, N_TEMP)) % N_CLUSTER
    all_nodes = np.vstack([nodes, temps])
    all_labels = np.concatenate([labels, temp_label])
    return centers, all_nodes, all_labels, temp_target


def replay_bad(seed):
    rng = np.random.RandomState(seed)
    centers, all_nodes, all_labels, temp_target = build(rng)
    n_all = len(all_nodes)
    pos = np.zeros(n_all)
    tot = np.zeros(n_all)
    qs = []
    for k in range(Q_PER_BATCH):
        a = k % N_CLUSTER
        q = centers[a] / (np.linalg.norm(centers[a]) + 1e-9)
        qs.append((q, a))
    for _ in range(ROUNDS):
        q, main = qs[rng.randint(len(qs))]
        conf = (pos + 2.0) / (tot + 2.0)
        scores = (all_nodes @ q) * conf
        top = np.argsort(-scores)[:K]
        true_hit = all_labels[top] == main
        true_idx = top[true_hit]
        # 与 v8 完全同流：pu=0 时 rng.random() 仍被消费（true_idx 非空时）
        if len(true_idx) > 0 and rng.random() < 0.0:
            pick = int(rng.choice(true_idx))   # 不可达，仅为同流
        else:
            non = top[~true_hit]
            pick = int(non[0]) if len(non) > 0 else int(top[0])
        pick_pos = int(np.where(top == pick)[0][0])
        for j in np.delete(top, pick_pos):
            tot[j] += 1
        tot[pick] += 1
        pos[pick] += 1

    # --- A: tempter distribution per cluster ---
    temp_count = np.bincount(temp_target, minlength=N_CLUSTER)
    # --- B: end-state top5 composition ---
    conf = (pos + 2.0) / (tot + 2.0)
    comp = np.zeros(4)   # [same-true, targeted-tempter, other-true, other-tempter]
    hit = 0
    # --- C: unrated-pool sim head comparison ---
    c_other_true, c_other_temp = [], []
    for (q, main) in qs:
        scores = (all_nodes @ q) * conf
        top = np.argsort(-scores)[:K]
        for idx in top:
            if idx < N_NODES and all_labels[idx] == main:
                comp[0] += 1
            elif idx >= N_NODES and temp_target[idx - N_NODES] == main:
                comp[1] += 1
            elif idx < N_NODES:
                comp[2] += 1
            else:
                comp[3] += 1
        hit += int((all_labels[top] == main).sum())
        sims = all_nodes @ q
        ot = sims[:N_NODES][all_labels[:N_NODES] != main]
        oth = [(sims[N_NODES + j], j) for j in range(N_TEMP)
               if temp_target[j] != main]
        c_other_true.append(ot.max())
        c_other_temp.append(max(s for s, _ in oth))
    comp /= len(qs)
    hit /= len(qs) * K
    return temp_count, comp, hit, np.mean(c_other_true), np.mean(c_other_temp)


def main():
    print("=== s6.1 bad-arm audit: root cause of terminal hit < naive floor ===")
    print()
    for seed in SEEDS:
        tc, comp, hit, mt, mth = replay_bad(seed)
        print(f"seed {seed}:")
        print(f"  tempters/cluster: {list(tc)}")
        print(f"  end-state hit: {hit:.4f}   (v8 reported this seed's tail)")
        print(f"  top5 composition: same-true {comp[0]:.2f} | targeted-temp {comp[1]:.2f}"
              f" | other-true {comp[2]:.2f} | other-temp {comp[3]:.2f}")
        print(f"  unrated-pool sim head: other-true max {mt:.3f} vs other-temp max {mth:.3f}")
        print()
    print("(2026-10-14, s6.1 bad-arm audit)")


if __name__ == "__main__":
    main()
