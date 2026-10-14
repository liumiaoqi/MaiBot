#!/usr/bin/env python3
"""social_rel · s6.1（v6）—— 生长曲线：展示-选择反馈（x74 三处方）

v5 双诊断（2026-10-14）：
  ① 天花板：诱惑 σ=0.45（sim≈0.91）进不了 top5 → 纯 sim 已 0.98，无生长空间；
  ② 反馈失衡：只评 top1 → 正确节点被评后 conf→0.74，诱惑从未被评 conf=1.0
     → 已评正确节点被未评诱惑反超 → 全臂下降（0.98→0.88）。

x74 处方（M-first，math_probe/x74_v6_design.wl）：
  ① 世界：σ_temp=0.25 → 初始 hit≈0.6（诱惑占 top5 两席，生长有空间）；
  ② 反馈形态：「展示 top5 + 选择」——选中者记正；选中者之前的展示位记拒
     （before 口径，x74 模拟 0.67→1.00；all 口径不稳，正确节点被误伤，否）；
  ③ pu 稳健（0.6-0.9 均生长），取 0.8。

三臂（对齐 v5 语义）：
  good  pu=0.8；dirty pu=0.8*0.3+0.7*0.5=0.59（信号压向随机）；bad pu=0（永远选错）。

预登记判据：
  P1 good ：后半段均值 ≥ 起点 +10pp 且 末点 ≥ 起点 +10pp（生长！）
  P2 dirty：走平或负（后半段均值 ≤ 起点 +3pp）
  P3 bad  ：末点 < 起点（负生长）

x71：批次 CSV（wl 复核）。3 seeds 均值。
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
BATCHES = (0, 25, 50, 100, 200, 350, 500)
SIGMA_REAL = 0.35
SIGMA_TEMP = 0.25          # x74 处方①：初始 hit≈0.6
PU_GOOD = 0.8
PU_DIRTY = 0.8 * 0.3 + 0.7 * 0.5   # = 0.59，信号压向随机（v5 kappa=0.3 语义）
PU_BAD = 0.0               # 永远选错
SEEDS = (20261014, 20261015, 20261016)
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x71_growth_batches.csv')


def build(rng):
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_NODES)
    nodes = centers[labels] + rng.normal(0, SIGMA_REAL, (N_NODES, D_DIM))
    nodes /= (np.linalg.norm(nodes, axis=1, keepdims=True) + 1e-9)
    # 诱惑节点：盯簇 temp_target，向量 = 该簇中心 + N(0, SIGMA_TEMP)
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
    return centers, all_nodes, all_labels


def run(pu, seed):
    rng = np.random.RandomState(seed)
    centers, all_nodes, all_labels = build(rng)
    n_all = len(all_nodes)
    pos = np.zeros(n_all)
    tot = np.zeros(n_all)
    # 固定查询集（跨批次一致）
    qs = []
    for k in range(Q_PER_BATCH):
        a = k % N_CLUSTER
        q = centers[a] / (np.linalg.norm(centers[a]) + 1e-9)
        qs.append((q, a))
    curve = []
    prev = 0
    for b in BATCHES:
        for _ in range(b - prev):
            q, main = qs[rng.randint(len(qs))]
            conf = (pos + 2.0) / (tot + 2.0)          # 未评 = 1.0（x72 处方）
            scores = (all_nodes @ q) * conf
            top = np.argsort(-scores)[:K]
            true_hit = all_labels[top] == main
            true_idx = top[true_hit]
            if len(true_idx) > 0 and rng.random() < pu:
                pick = int(rng.choice(true_idx))       # 用户选正确
            else:
                non = top[~true_hit]
                pick = int(non[0]) if len(non) > 0 else int(top[0])  # 选最前非正确（或兜底）
            pick_pos = int(np.where(top == pick)[0][0])
            for j in top[:pick_pos]:                   # before 口径：选中者之前记拒
                tot[j] += 1
            tot[pick] += 1
            pos[pick] += 1
        prev = b
        conf = (pos + 2.0) / (tot + 2.0)
        hits = 0
        total = 0
        for (q, main) in qs:
            scores = (all_nodes @ q) * conf
            top = np.argsort(-scores)[:K]
            hits += int((all_labels[top] == main).sum())
            total += K
        curve.append(hits / total)
    return curve


def run_mean(pu):
    rs = [run(pu, sd) for sd in SEEDS]
    arr = np.array(rs)
    return arr.mean(axis=0), arr


def main():
    print("=== s6.1 v6: growth curve, show-top5 + choose feedback (x74 prescriptions) ===")
    print(f"world: {N_NODES} real + {N_TEMP} temptation (sigma {SIGMA_TEMP}) | batches={BATCHES}")
    print(f"arms: good pu={PU_GOOD} | dirty pu={PU_DIRTY:.2f} | bad pu={PU_BAD} | seeds={len(SEEDS)}")
    print()
    good, good_rs = run_mean(PU_GOOD)
    dirty, dirty_rs = run_mean(PU_DIRTY)
    badorder, bad_rs = run_mean(PU_BAD)
    print("%-8s %14s %14s %14s" % ("feedback", "good", "dirty", "bad-order"))
    print("-" * 52)
    for i, b in enumerate(BATCHES):
        print("%-8d %14.4f %14.4f %14.4f" % (b, good[i], dirty[i], badorder[i]))
    print()
    print("per-seed last point (good arm):", ["%.3f" % r[-1] for r in good_rs])
    print()
    P1 = good[-1] >= good[0] + 0.10 and good[len(good)//2:].mean() >= good[0] + 0.10
    P2 = dirty[-1] <= dirty[0] + 0.03 and dirty[len(dirty)//2:].mean() <= dirty[0] + 0.03
    P3 = badorder[-1] < badorder[0]
    print("=== verdict (pre-registered) ===")
    print(f"P1 good: grow(+10pp, late-mean): {'PASS' if P1 else 'FAIL'} ({good[0]:.4f} -> {good[-1]:.4f})")
    print(f"P2 dirty: flat/neg: {'PASS' if P2 else 'FAIL'} ({dirty[0]:.4f} -> {dirty[-1]:.4f})")
    print(f"P3 bad order: negative: {'PASS' if P3 else 'FAIL'} ({badorder[0]:.4f} -> {badorder[-1]:.4f})")
    print("(2026-10-14, s6.1 v6)")

    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
        f.write("feedback,good,dirty,badorder\n")
        for i, b in enumerate(BATCHES):
            f.write("%d,%.6f,%.6f,%.6f\n" % (b, good[i], dirty[i], badorder[i]))
    print(f"x71 exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
