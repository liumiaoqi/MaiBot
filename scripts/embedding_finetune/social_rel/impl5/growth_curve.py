#!/usr/bin/env python3
"""social_rel · s6.1（v8）—— 生长曲线：反馈质量响应曲线（all 口径）

v7 判决（已提交）：
  - all 口径胜出（good 末点 0.873 vs before 0.833，seed 收敛更好）；
  - 三臂平台按信号质量单调：pu0.8 → 0.873 | pu0.59 → 0.800 | pu0.0 → 0.500；
  - bad 臂在 all 口径下负生长 -12pp（before 口径无信息、静止）。

v8 的数学问题：平台 0.873 是机制缺陷还是数学必然？
  「信号摊薄对称点」推导：top5 里 4 个正确者时，正确者被选率 = 0.8/4 = 0.2；
  诱惑（1 个在展示里）独吞失误信号 = 0.2/1 = 0.2 —— 恰好打平，
  conf 收敛到同值、分辨力归零，排序退化为 sim 决胜 → 平台 ≈ 0.87。
  推论（可检验预言）：**平台高度是信号纯度的函数**——
    pu0.9 → 0.225 vs 0.1，正确者显著胜 → 平台应升至 ~0.95；
    pu0.7 → 0.175 vs 0.3，诱惑胜 → 平台应降至 ~0.75。
  若 v8 数据与预言一致 → 「平台 = f(信号质量)」成立，平台 0.87 是必然而非缺陷。

v8 设计（单变量：信号质量矩阵，all 口径）：
  曲线五条：pu ∈ {0.9, 0.8, 0.7, 0.59(dirty), 0.0(bad)}

预登记判据：
  P4（主）平台随信号质量单调：late(0.9) ≥ late(0.8) ≥ late(0.7) ≥ late(0.59)，
          且 late(0.0) 最低（容差 0.02）
  P1（0.8 档仍 +10pp）
  记录：bad 崩坏度

x71：宽表 CSV。3 seeds 均值。
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
SIGMA_TEMP = 0.25
PUS = (0.9, 0.8, 0.7, 0.59, 0.0)
SEEDS = (20261014, 20261015, 20261016)
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x71_growth_batches.csv')


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
    return centers, all_nodes, all_labels


def run(pu, seed):
    rng = np.random.RandomState(seed)
    centers, all_nodes, all_labels = build(rng)
    n_all = len(all_nodes)
    pos = np.zeros(n_all)
    tot = np.zeros(n_all)
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
            conf = (pos + 2.0) / (tot + 2.0)
            scores = (all_nodes @ q) * conf
            top = np.argsort(-scores)[:K]
            true_hit = all_labels[top] == main
            true_idx = top[true_hit]
            if len(true_idx) > 0 and rng.random() < pu:
                pick = int(rng.choice(true_idx))
            else:
                non = top[~true_hit]
                pick = int(non[0]) if len(non) > 0 else int(top[0])
            pick_pos = int(np.where(top == pick)[0][0])
            # all 口径：展示未选全记拒（位置无关）
            for j in np.delete(top, pick_pos):
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
    arr = np.array([run(pu, sd) for sd in SEEDS])
    return arr.mean(axis=0), arr


def main():
    print("=== s6.1 v8: feedback-quality response curve (all rejection) ===")
    print(f"world: {N_NODES} real + {N_TEMP} temptation (sigma {SIGMA_TEMP}) | batches={BATCHES}")
    print(f"quality sweep pu: {PUS} | seeds={len(SEEDS)}")
    print()
    curves = {}
    for pu in PUS:
        c, rs = run_mean(pu)
        curves[pu] = (c, rs)
        print("pu=%-4.2f : %s  (gain %+0.4f)" % (
            pu, "  ".join("%.3f" % v for v in c), c[-1] - c[0]))
    print()
    late = {pu: curves[pu][0][len(BATCHES)//2:].mean() for pu in PUS}
    print("late-mean (second half avg):")
    for pu in PUS:
        print("  pu=%-4.2f : %.4f" % (pu, late[pu]))
    print()
    print("=== verdict (v8 criteria) ===")
    P4 = (late[0.9] >= late[0.8] - 0.02 and late[0.8] >= late[0.7] - 0.02
          and late[0.7] >= late[0.59] - 0.02
          and late[0.0] <= min(late[0.59], late[0.7]) - 0.02)
    g8 = curves[0.8][0]
    P1 = g8[-1] >= g8[0] + 0.10 and g8[len(g8)//2:].mean() >= g8[0] + 0.10
    print(f"P4 quality-monotone platforms: {'PASS' if P4 else 'FAIL'}"
          f"  (0.9:{late[0.9]:.3f} 0.8:{late[0.8]:.3f} 0.7:{late[0.7]:.3f} 0.59:{late[0.59]:.3f} 0.0:{late[0.0]:.3f})")
    print(f"P1 grow at pu=0.8 (+10pp): {'PASS' if P1 else 'FAIL'} ({g8[0]:.4f} -> {g8[-1]:.4f})")
    print(f"bad-arm collapse (pu=0): 0.620 -> {curves[0.0][0][-1]:.3f}")
    print()
    print("per-seed last points:")
    for pu in PUS:
        print("  pu=%-4.2f : %s" % (pu, ["%.3f" % r[-1] for r in curves[pu][1]]))
    print("(2026-10-14, s6.1 v8)")

    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
        f.write("feedback,pu90,pu80,pu70,pu59,pu00\n")
        for i, b in enumerate(BATCHES):
            f.write("%d," % b + ",".join("%.6f" % curves[pu][0][i] for pu in PUS) + "\n")
    print(f"x71 exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
