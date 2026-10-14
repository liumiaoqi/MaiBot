#!/usr/bin/env python3
"""审计：s5.7 扩散探索位是否把查询节点自身（qi）捞回（口径瑕疵核查）

s5.7 报告「扩散席位命中率 ~100%」（b 臂 500/500、c 臂 996/1000）。
疑点：s5.7 的 diff_top 只排除「已在 sim 席位的节点」，**不排除 qi 自身**——
qi 被 sim 压至 -2.0 因而从不进入 exclude，但它在图上与 seed（通常同簇、
高相似）近邻相连，扩散概率 p[qi] 可能很高 → 可能被探索位捞回并记「命中」
（qi 的 label 必然 == target，自返=完美作弊）。

本审计重放 s5.7 世界（同 seed/同图/同 diff 逻辑，无 qi 排除），统计：
  ① b/c 臂扩散席位的 qi 自返率
  ② 扣除自返后的实际「扩散席位命中率」（修正口径）

Run: ../../.venv/Scripts/python.exe audit_s57_diff_selfreturn.py
"""

import numpy as np

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


def gen_world():
    rng = np.random.RandomState(SEED)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_STABLE)
    stable = centers[labels] + rng.normal(0, 0.3, (N_STABLE, D_DIM))
    stable /= (np.linalg.norm(stable, axis=1, keepdims=True) + 1e-9)
    new_vecs, add_rounds, is_fake, new_true_label = [], [], [], []
    queries = []
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
            is_fake.append(fake)
        for _ in range(Q_PER_ROUND):
            queries.append((rng.randint(0, N_STABLE), r))
    return (stable, labels, np.array(new_vecs), np.array(add_rounds),
            np.array(is_fake), np.array(new_true_label), queries)


def main():
    (stable, labels, new_vecs, add_rounds, is_fake, new_true_label, queries) = gen_world()
    n_all = N_STABLE + len(new_vecs)
    nodes = np.vstack([stable, new_vecs])
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
    print(f"replay s5.7: {n_nodes} nodes | queries={len(queries)}")

    def is_true(gi, target):
        if gi < N_STABLE:
            return labels[gi] == target
        j = gi - N_STABLE
        return (not is_fake[j]) and new_true_label[j] == target

    def diff_scan(p, m, exclude, r):
        out = []
        for gi in np.argsort(-p):
            if len(out) >= m:
                break
            gi = int(gi)
            if gi in exclude:
                continue
            if gi >= N_STABLE:
                j = gi - N_STABLE
                if add_rounds[j] > r - GRACE:
                    continue
            out.append(gi)
        return out

    stats = {"b": dict(total=0, self_ret=0, hit=0, hit_noself=0, slots=0, slots_noself=0),
             "c": dict(total=0, self_ret=0, hit=0, hit_noself=0, slots=0, slots_noself=0)}
    for (qi, r) in queries:
        q = stable[qi]
        target = labels[qi]
        sims_s = stable @ q
        sims_s[qi] = -2.0
        s_all = np.concatenate([sims_s, new_vecs @ q])
        mask = np.concatenate([np.ones(N_STABLE, dtype=bool), add_rounds <= r - GRACE])
        score = np.where(mask, s_all, -np.inf)
        order = [int(g) for g in np.argsort(-score)[:K]]
        # s5.7 生成扩散概率（seed = sim top1；b/c 两臂同 seed，一次计算共享）
        p0 = np.zeros(n_nodes)
        p0[order[0]] = 1.0
        p = ul @ (np.exp(-vl * DIFF_T) * (ul.T @ p0))
        for arm, m in (("b", 1), ("c", 2)):
            exclude = set(order[:K - m])
            dpart = diff_scan(p, m, exclude, r)
            stats[arm]["total"] += 1
            if qi in dpart:
                stats[arm]["self_ret"] += 1
            for gi in dpart:
                h = is_true(gi, target)
                stats[arm]["hit"] += h
                stats[arm]["slots"] += 1
                if gi != qi:
                    stats[arm]["hit_noself"] += h
                    stats[arm]["slots_noself"] += 1

    print()
    print("=== qi self-return audit (s5.7 diffusion slots) ===")
    for arm, m in (("b", 1), ("c", 2)):
        s = stats[arm]
        print(f"arm {arm} (m={m}): queries with qi self-returned:"
              f" {s['self_ret']}/{s['total']}  ({100.0*s['self_ret']/s['total']:.1f}%)")
        print(f"  slot hit-rate as-reported : {s['hit']}/{s['slots']}"
              f" = {s['hit']/s['slots']:.4f}")
        print(f"  slot hit-rate w/o qi-self : {s['hit_noself']}/{s['slots_noself']}"
              f" = {s['hit_noself']/s['slots_noself']:.4f}")
    print()
    print("note: s5.7's b/c arms did NOT exclude qi; s7.1's c arm does")
    print("(growth_integrated.py adds `or gi == qi`), so s7.1 numbers are clean.")
    print("(2026-10-14, audit for s5.7)")
    print("x70 CSV self-return estimate vs recompute:")
    print("  x70 reported b: 500/500, c: 996/1000 slot hits -- compare above")


if __name__ == "__main__":
    main()
