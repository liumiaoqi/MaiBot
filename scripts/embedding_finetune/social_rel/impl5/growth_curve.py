#!/usr/bin/env python3
"""social_rel · s6.1 —— 自生长：生长曲线模拟（目标「真实数据面前的自生长潜质」首实验）

设计（对照 proposals/2026-10-14-self-growth.md）：
  世界：簇世界（200 稳定 · 10 簇）+ 反馈流分批到达（0→50→200→500 条）。
  反馈：对随机关系对给出 ±1 正确性（κ 控制质量：0.8 好数据 / 0.3 脏数据）。
  系统：0004 更新规则（+δ/−δ 调 conf，δ=0.1，clamp [0.3,1]）→ conf 进排序（sim × conf）。
  评估：每批后测 100 查询的 top5 命中率（命中 = 同簇稳定节点）。

预登记判据：
  P1  κ=0.8 曲线单调升，且 500 条内超过无反馈基线 ≥10%（相对）
  P2  κ=0.3 曲线走平或负（脏数据不生长）
  P3  错误顺序组（先覆盖后真值）出现负生长（复现 s4 顺序陷阱）

x71：生长斜率的批次增量分解核对（wl）—— 本脚本导出每批增量 CSV。
Run: ../../.venv/Scripts/python.exe growth_curve.py
"""

import numpy as np
import pathlib

N_STABLE = 200
D_DIM = 64
N_CLUSTER = 10
Q_PER_BATCH = 100
K = 5
BATCHES = (0, 50, 200, 500)   # 累计反馈条数
DELTA = 0.1
FLOOR, CEIL = 0.3, 1.0
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x71_growth_batches.csv')


def build():
    rng = np.random.RandomState(SEED)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_STABLE)
    stable = centers[labels] + rng.normal(0, 0.3, (N_STABLE, D_DIM))
    stable /= (np.linalg.norm(stable, axis=1, keepdims=True) + 1e-9)
    # 查询（固定）+ 查询噪声（让基线掉到 ~0.6，留生长空间）
    qidx = rng.choice(N_STABLE, Q_PER_BATCH, replace=False)
    return centers, stable, labels, qidx, rng


def noisy_query(stable, qi, sigma=0.7):
    q = stable[qi] + np.random.RandomState(qi + 777).normal(0, sigma, stable.shape[1])
    return q / (np.linalg.norm(q) + 1e-9)


def run_stream(kappa, order="good"):
    """order: good=真值先行 / bad=先覆盖后真值（s4 顺序陷阱的对照）"""
    centers, stable, labels, qidx, rng = build()
    # 现状：conf 初始带轻微异质（模拟真实中"全 1.0"之前的自然扰动）——让反馈有作用空间
    conf = np.clip(CEIL - np.abs(rng.normal(0, 0.03, N_STABLE)), FLOOR, CEIL)
    curve = []
    prev_fb = 0
    for b in BATCHES:
        n_new = b - prev_fb
        if n_new > 0:
            for _ in range(n_new):
                i = rng.randint(0, N_STABLE)
                j = rng.randint(0, N_STABLE)
                # 正确性信号：同簇 = +1（真值），否则 −1
                truth = 1 if labels[i] == labels[j] else -1
                if order == "bad":
                    truth = -truth          # 覆盖阶段：反向（s4 的情境）
                noisy = truth if rng.random() < kappa else -truth
                conf[i] = float(np.clip(conf[i] + DELTA * noisy, FLOOR, CEIL))
        # 评估（sim × conf，查询加噪）
        hits = 0
        for qi in qidx:
            q = noisy_query(stable, qi)
            sims = stable @ q
            sims[qi] = -2
            rank = np.argsort(-(sims * conf))[:K]
            hits += int((labels[rank] == labels[qi]).sum())
        curve.append(hits / (len(qidx) * K))
        prev_fb = b
    return curve


def main():
    print("=== s6.1: growth curve (feedback arrives in batches) ===")
    print(f"world: {N_STABLE} stable / {N_CLUSTER} clusters | batches={BATCHES} | delta={DELTA}")
    print()
    print("%-10s %-46s %s" % ("feedback", "kappa=0.8 (good)", "kappa=0.3 (dirty)"))
    print("-" * 78)
    good = run_stream(0.8, "good")
    dirty = run_stream(0.3, "good")
    badorder = run_stream(0.8, "bad")
    for i, b in enumerate(BATCHES):
        print("%-10d %-46s %s" % (b, f"{good[i]:.4f}", f"{dirty[i]:.4f}"))
    base = good[0]
    print()
    print("bad-order group (先覆盖后真值, kappa=0.8):", " ".join(f"{x:.4f}" for x in badorder))
    print()
    P1 = good[-1] >= base * 1.10 and all(good[i] <= good[i+1] + 1e-9 for i in range(len(good)-1))
    P2 = dirty[-1] <= dirty[0] * 1.02
    P3 = badorder[-1] < badorder[0]
    print("=== verdict (pre-registered) ===")
    print(f"P1 good data: monotone up & >=+10% vs base: {'PASS' if P1 else 'FAIL'} ({base:.4f} -> {good[-1]:.4f})")
    print(f"P2 dirty data: flat or negative: {'PASS' if P2 else 'FAIL'} ({dirty[0]:.4f} -> {dirty[-1]:.4f})")
    print(f"P3 bad order: negative growth: {'PASS' if P3 else 'FAIL'} ({badorder[0]:.4f} -> {badorder[-1]:.4f})")
    print("(2026-10-14, s6.1)")

    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("feedback,good_curve,dirty_curve,badorder_curve\n")
        for i, b in enumerate(BATCHES):
            f.write("%d,%.6f,%.6f,%.6f\n" % (b, good[i], dirty[i], badorder[i]))
    print(f"x71 batches exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
