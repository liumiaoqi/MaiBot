#!/usr/bin/env python3
"""social_rel · s6.1（重构版）—— 生长曲线：反馈→conf 的直连设计

v1/v2 失败的教训：反馈“±0.1 微调”对排序影响力太弱、链条断两截。
重构：**反馈直接定义 conf**——
  每次“检索反馈”：系统对某 query 给出 top1 候选，用户打 √（正确）/×（错误）。
  node 的 conf = 它的“被打 √ 的历史比例”（拉普拉斯平滑）。
  √/× 与节点质量绑定：正确候选 √率 0.8 / 错误候选 √率 0.3（信噪由 κ 调）。
  排序 = sim × conf。曲线应随反馈积累单调上升（conf 从 1.0 → 真值水平）。

预登记判据：
  P1  κ=0.8：曲线单调升，500 反馈内较无反馈基线 ≥ +10%
  P2  κ=0.3（脏）：走平或负
  P3  bad-order（前期错误反馈主导，s4 式）：出现负生长

x71：批次曲线 CSV 导出（wl 复核）。
Run: ../../.venv/Scripts/python.exe growth_curve.py
"""

import numpy as np
import pathlib

N_NODES = 100
D_DIM = 32
N_CLUSTER = 10
Q_PER_BATCH = 60
K = 5
BATCHES = (0, 50, 200, 500)
P_HIT_GOOD_AVG = 0.8   # 正确（同簇）候选的 √ 概率
P_HIT_BAD_AVG = 0.3    # 错误（异簇）候选的 √ 概率
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x71_growth_batches.csv')


def build():
    rng = np.random.RandomState(SEED)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_NODES)
    nodes = centers[labels] + rng.normal(0, 0.35, (N_NODES, D_DIM))
    nodes /= (np.linalg.norm(nodes, axis=1, keepdims=True) + 1e-9)
    # 跨簇查询：q = 0.62*A + 0.38*B（正确答案 = 主簇 A；B 簇节点是干扰）
    qs = []
    for k in range(Q_PER_BATCH):
        a, b = rng.choice(N_CLUSTER, 2, replace=False)
        q = 0.62 * centers[a] + 0.38 * centers[b]
        q /= np.linalg.norm(q) + 1e-9
        qs.append((q, a))
    return nodes, labels, qs, rng


def run(kappa, order="good"):
    nodes, labels, qs, rng = build()
    pos = np.zeros(N_NODES)   # √ 次数
    tot = np.zeros(N_NODES)   # 被评次数
    curve = []
    prev = 0
    for b in BATCHES:
        for _ in range(b - prev):
            qi = int(rng.randint(len(qs)))
            q, main = qs[qi]
            sims = nodes @ q
            conf = (pos + 1.0) / (tot + 2.0)
            top1 = int(np.argmax(sims * conf))
            correct = (labels[top1] == main)
            p_hit = P_HIT_GOOD_AVG if correct else P_HIT_BAD_AVG
            if kappa < 1.0:
                p_hit = p_hit * kappa + (1 - kappa) * 0.5
            if order == "bad":
                p_hit = 1.0 - p_hit
            r = rng.random() < p_hit
            tot[top1] += 1
            if r:
                pos[top1] += 1
        prev = b
        # 评估：全部跨簇查询（干净读取，命中 = top5 中主簇节点数）
        conf = (pos + 1.0) / (tot + 2.0)
        hits = 0
        total = 0
        for (q, main) in qs:
            sims = nodes @ q
            rank = np.argsort(-(sims * conf))[:K]
            hits += int((labels[rank] == main).sum())
            total += K
        curve.append(hits / total)
    return curve


def main():
    print("=== s6.1 (rewrite): growth curve with feedback-defined conf ===")
    print(f"world: {N_NODES} nodes / {N_CLUSTER} clusters | batches={BATCHES} | "
          f"p_hit: correct={P_HIT_GOOD_AVG} wrong={P_HIT_BAD_AVG}")
    print()
    good = run(0.8, "good")
    dirty = run(0.3, "good")
    badorder = run(0.8, "bad")
    print("%-10s %14s %14s %14s" % ("feedback", "kappa=0.8", "kappa=0.3", "bad-order"))
    print("-" * 56)
    for i, b in enumerate(BATCHES):
        print("%-10d %14.4f %14.4f %14.4f" % (b, good[i], dirty[i], badorder[i]))
    print()
    P1 = good[-1] >= good[0] * 1.10 and all(good[i] <= good[i + 1] + 1e-9 for i in range(len(good) - 1))
    P2 = dirty[-1] <= dirty[0] * 1.02
    P3 = badorder[-1] < badorder[0]
    print("=== verdict (pre-registered) ===")
    print(f"P1 good: monotone up & >=+10%%: {'PASS' if P1 else 'FAIL'} ({good[0]:.4f} -> {good[-1]:.4f})")
    print(f"P2 dirty: flat/negative: {'PASS' if P2 else 'FAIL'} ({dirty[0]:.4f} -> {dirty[-1]:.4f})")
    print(f"P3 bad order: negative growth: {'PASS' if P3 else 'FAIL'} ({badorder[0]:.4f} -> {badorder[-1]:.4f})")
    print("(2026-10-14, s6.1 rewrite)")

    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("feedback,good,dirty,badorder\n")
        for i, b in enumerate(BATCHES):
            f.write("%d,%.6f,%.6f,%.6f\n" % (b, good[i], dirty[i], badorder[i]))
    print(f"x71 exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
