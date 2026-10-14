#!/usr/bin/env python3
"""social_rel · s5.3 —— 检索元决策：margin 阈值（方向 C）

假说（提案 C）：低 margin 的检索（top1 与 top2 激活差小）错误率偏高 ⇒
「低 margin 时拒检索」比「硬信 top1」划算——减少把错误记忆注入上下文的次数。

装置：kNN 真图（2500）+ 扩散激活（t=4，s5.1 工作点）。
主量（§9 定）：base 错误率 · 各 θ 的（错误拦截率, 保留率）· θ* 工作点。
x 装置：x66（同数据 CSV 导出 → wolframscript 独立重算曲线点对拍）。

定义：
  "正确" = top1 节点到查询源的 BFS 距离 ≤ 2（近邻=相关）
  margin = (p1 - p2) / p1 （top1 相对领先度）
  规则：margin < θ ⇒ 拒检索（不注入）；否则采信 top1
  错误拦截率 = 被拒查询中的错误数 / 全体错误数
  保留率 = 1 - 拒率

预登记判据：存在 θ 使 错误拦截率 ≥ 30% 且 保留率 ≥ 90%。

Run: ../../.venv/Scripts/python.exe margin_decision.py
"""

import numpy as np
import pathlib

NPZ = r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/knn_graph_2500.npz'
N_SRC = 200
T_DIFF = 4.0
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x66_margin_sample.csv')

d = np.load(NPZ)
edges = d['edges']
n = 2500
W = np.zeros((n, n))
for a, b in edges:
    W[a, b] = W[b, a] = 1.0

rng = np.random.RandomState(SEED)


def bfs_dist(src, maxd=12):
    dist = np.full(n, -1, dtype=int)
    dist[src] = 0
    frontier = [src]
    dd = 0
    while frontier and dd < maxd:
        nxt = []
        for u in frontier:
            for v in np.where(W[u] > 0)[0]:
                if dist[v] < 0:
                    dist[v] = dd + 1
                    nxt.append(v)
        frontier = nxt
        dd += 1
    return dist


def main():
    print("=== s5.3：检索元决策——margin 阈值（方向 C）===")
    srcs = rng.choice(n, N_SRC, replace=False)
    dists = {int(s): bfs_dist(int(s)) for s in srcs}
    deg = W.sum(1)
    vl, ul = np.linalg.eigh(np.diag(deg) - W)
    print("谱就绪（%d 源）" % N_SRC)

    rows = []  # (src_i, p1, p2, margin, correct)
    for s in srcs:
        s = int(s)
        p0 = np.zeros(n)
        p0[s] = 1.0
        coef = ul.T @ p0
        p = ul @ (np.exp(-vl * T_DIFF) * coef)
        p[s] = -1
        top2 = np.argsort(-p)[:2]
        p1, p2 = float(p[top2[0]]), float(p[top2[1]])
        margin = (p1 - p2) / (p1 + 1e-12)
        correct = 1 if dists[s][top2[0]] <= 2 else 0
        rows.append((s, p1, p2, margin, correct))

    margins = np.array([r[3] for r in rows])
    correct = np.array([r[4] for r in rows])
    base_err = 1.0 - correct.mean()
    total_err = int((1 - correct).sum())
    print("base：错误率 %.3f（%d/%d）· margin 中位 %.3f" % (base_err, total_err, N_SRC, float(np.median(margins))))
    print()

    print("%-10s %12s %10s %12s" % ("θ", "错误拦截率", "保留率", "保留集准确率"))
    print("-" * 52)
    best = None
    grid = [0.0] + [float(np.quantile(margins, q)) for q in np.arange(0.1, 1.0, 0.1)]
    for theta in grid:
        reject = margins < theta
        kept = ~reject
        errs_rejected = int(((1 - correct) * reject).sum())
        intercept = errs_rejected / total_err if total_err else 0.0
        keep_rate = kept.mean()
        acc_kept = correct[kept].mean() if kept.sum() else float("nan")
        flag = ""
        if intercept >= 0.30 and keep_rate >= 0.90:
            flag = "  ← 判据成立"
            if best is None:
                best = theta
        print("%-8.1f %11.1f%% %9.1f%% %11.3f%s" % (theta, 100 * intercept, 100 * keep_rate, acc_kept, flag))

    print()
    print("=== 判据（预登记）===")
    msg = ("成立（最小 θ = %.4f）" % best) if best is not None else "不成立"
    print("存在 θ 使 错误拦截率≥30% 且 保留率≥90%: " + msg)
    print("（2026-10-14 · s5.3）")

    # 导出 x66 对拍样本（全量 200 行）
    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("margin,correct\n")
        for (_, _, _, m, c) in rows:
            f.write("%.8f,%d\n" % (m, c))
    print("已导出 x66 对拍样本：%s（%d 行）" % (OUT_CSV.name, len(rows)))


if __name__ == "__main__":
    main()
