#!/usr/bin/env python3
"""social_rel · s6.1（v5）—— 生长曲线：诱惑节点世界（x72/x73 双处方）

设计（M-first：x72 判冷启动、x73 定诱惑强度）：
  世界：100 真实节点（10 簇）+ 20 诱惑节点（各盯一个簇：向量 = 该簇中心 + 噪声，
        使其对"该簇的 query" sim ≈ 0.66，能挤 top5 但属于别的簇（label ≠ 该簇））。
  query：取某簇中心（该簇的 2 个诱惑节点是干扰源）。
  反馈：系统给 top1；正确 = 真实节点且同主簇；诱惑节点永远算错。
  反馈率：正确候选 √率 0.8 / 错误候选 √率 0.3（κ 调）。
  conf：未评默认 1.0（x72 处方：不惩罚未知）；被评收敛到 √率。

预登记判据：
  P1  κ=0.8：曲线单调升，且末点 ≥ 起点 +10%（生长！）
  P2  κ=0.3（脏）：走平或负
  P3  bad-order：负生长

x71：批次 CSV（wl 复核）。
Run: ../../.venv/Scripts/python.exe growth_curve.py
"""

import numpy as np
import pathlib

N_NODES = 100
N_TEMP = 20
D_DIM = 32
N_CLUSTER = 10
Q_PER_BATCH = 60
K = 5
BATCHES = (0, 50, 200, 500)
P_HIT_GOOD = 0.8
P_HIT_BAD = 0.3
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x71_growth_batches.csv')


def build():
    rng = np.random.RandomState(SEED)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_NODES)
    nodes = centers[labels] + rng.normal(0, 0.35, (N_NODES, D_DIM))
    nodes /= (np.linalg.norm(nodes, axis=1, keepdims=True) + 1e-9)
    # 诱惑节点：盯簇 targets[k]，向量 = 该簇中心 + 噪声（sim ≈ 0.66 左右）
    temp_target = rng.randint(0, N_CLUSTER, N_TEMP)
    temps = []
    for t in temp_target:
        v = centers[t] + rng.normal(0, 0.45, D_DIM)
        v /= (np.linalg.norm(v) + 1e-9)
        temps.append(v)
    temps = np.array(temps)
    # 每个诱惑节点的真实 label = 别的簇
    temp_label = (temp_target + 1 + rng.randint(0, N_CLUSTER - 1, N_TEMP)) % N_CLUSTER
    all_nodes = np.vstack([nodes, temps])
    all_labels = np.concatenate([labels, temp_label])
    return centers, all_nodes, all_labels, N_NODES, rng


def run(kappa, order="good"):
    centers, all_nodes, all_labels, n_real, rng = build()
    n_all = len(all_nodes)
    pos = np.zeros(n_all)
    tot = np.zeros(n_all)
    curve = []
    prev = 0
    # 固定查询集（跨批次一致）
    qs = []
    for k in range(Q_PER_BATCH):
        a = k % N_CLUSTER
        q = centers[a] / (np.linalg.norm(centers[a]) + 1e-9)
        qs.append((q, a))
    for b in BATCHES:
        for _ in range(b - prev):
            q, main = qs[rng.randint(len(qs))]
            sims = all_nodes @ q
            conf = (pos + 2.0) / (tot + 2.0)          # 未评 = 1.0（x72 处方）
            top1 = int(np.argmax(sims * conf))
            correct = (all_labels[top1] == main)
            p = P_HIT_GOOD if correct else P_HIT_BAD
            if kappa < 1.0:
                p = p * kappa + (1 - kappa) * 0.5
            if order == "bad":
                p = 1.0 - p
            r = rng.random() < p
            tot[top1] += 1
            pos[top1] += 1 if r else 0
        prev = b
        conf = (pos + 2.0) / (tot + 2.0)
        hits = 0
        total = 0
        for (q, main) in qs:
            sims = all_nodes @ q
            rank = np.argsort(-(sims * conf))[:K]
            hits += int((all_labels[rank] == main).sum())
            total += K
        curve.append(hits / total)
    return curve


def main():
    print("=== s6.1 v5: growth curve with temptation nodes (x72+x73 prescriptions) ===")
    print(f"world: {N_NODES} real + {N_TEMP} temptation nodes | batches={BATCHES}")
    print()
    good = run(0.8, "good")
    dirty = run(0.3, "good")
    badorder = run(0.8, "bad")
    print("%-10s %14s %14s %14s" % ("feedback", "kappa=0.8", "kappa=0.3", "bad-order"))
    print("-" * 56)
    for i, b in enumerate(BATCHES):
        print("%-10d %14.4f %14.4f %14.4f" % (b, good[i], dirty[i], badorder[i]))
    print()
    P1 = good[-1] >= good[0] + 0.10 and all(good[i] <= good[i+1] + 1e-9 for i in range(len(good)-1))
    P2 = dirty[-1] <= dirty[0] * 1.02
    P3 = badorder[-1] < badorder[0]
    print("=== verdict (pre-registered) ===")
    print(f"P1 good: monotone up & +10pp: {'PASS' if P1 else 'FAIL'} ({good[0]:.4f} -> {good[-1]:.4f})")
    print(f"P2 dirty: flat/negative: {'PASS' if P2 else 'FAIL'} ({dirty[0]:.4f} -> {dirty[-1]:.4f})")
    print(f"P3 bad order: negative: {'PASS' if P3 else 'FAIL'} ({badorder[0]:.4f} -> {badorder[-1]:.4f})")
    print("(2026-10-14, s6.1 v5)")

    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("feedback,good,dirty,badorder\n")
        for i, b in enumerate(BATCHES):
            f.write("%d,%.6f,%.6f,%.6f\n" % (b, good[i], dirty[i], badorder[i]))
    print(f"x71 exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
