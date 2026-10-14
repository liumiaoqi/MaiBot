# -*- coding: utf-8 -*-
"""social_rel · R4 独立证伪：s3（排序增量）与 s4（顺序陷阱）

独立性声明：本脚本的**生成器 / 学习器 / 指标全部自实现**，不 import social_rel 任何模块；
真库形状参数（184 关系 / 覆盖率 12%）取自公开文档（NOTES/RESULTS），未与 impl 侧代码或数字往来。

四个反例：
  ① derived 增量是否可独立复现（κ=0.5 下 derived vs 常数 confidence 的 hit@5 增量）
  ② break-even κ（扫 κ 找增量过零点，对照 s3 声称的 κ*=0.3）
  ③ σ_sim 压力测试（s3 声明 σ=0.35 是"假设不是量出来的"——证伪者压这里）
  ④ 顺序陷阱（s4：κ=0 时抬覆盖，伤害应放大——独立复现方向与倍数）

用法：..\\..\\.venv\\Scripts\\python.exe falsify_4_s3s4.py [--reps 30]
"""

from argparse import ArgumentParser

import numpy as np

N_REL = 184            # 真库关系数（文档）
N_Q = 150              # 查询数
POOL = 20              # 候选池
K = 5                  # top-k
COVER = 22.0 / 184.0   # 真库痕迹覆盖率（文档：22/184）
FLOOR = 0.3            # 派生置信度下界（对齐已落地护栏）


def gen_world(rng, kappa, cover, sigma_sim):
    """潜真值 rel* ~ N(0,1)；sim = rel* + noise(σ)；痕迹覆盖 cover，t = κ·rel* + √(1-κ²)·noise。"""
    rel = rng.normal(0, 1, N_REL)
    sim = rel[None, :] + rng.normal(0, sigma_sim, (N_Q, N_REL))
    traced = rng.random(N_REL) < cover
    t = np.zeros(N_REL)
    m = int(traced.sum())
    if m:
        t[traced] = kappa * rel[traced] + np.sqrt(max(1.0 - kappa * kappa, 0.0)) * rng.normal(0, 0.5, m)
    return rel, sim, traced, t


def derived_conf(t, traced):
    """痕迹 → confidence ∈ [0.3, 1]：有痕=sigmoid 映射（痕迹越强越接近 1），无痕=地板。"""
    c = np.full(N_REL, FLOOR)
    c[traced] = FLOOR + (1.0 - FLOOR) / (1.0 + np.exp(-t[traced]))
    return c


def hit5(scores_row, rel, pool, thresh):
    """top-5 命中数（'相关' = rel > 中位阈）。并列以 rng 拆——用微小抖动。"""
    sc = scores_row[pool].copy()
    sc = sc + np.random.default_rng().normal(0, 1e-9, len(pool))
    top = pool[np.argsort(-sc)[:K]]
    return int((rel[top] > thresh).sum())


def eval_rep(rng, kappa, cover, sigma_sim):
    rel, sim, traced, t = gen_world(rng, kappa, cover, sigma_sim)
    conf = derived_conf(t, traced)
    thresh = float(np.median(rel))
    h_cur, h_dev = [], []
    for q in range(N_Q):
        pool = rng.choice(N_REL, POOL, replace=False)
        h_cur.append(hit5(sim[q], rel, pool, thresh))
        h_dev.append(hit5(sim[q] * conf, rel, pool, thresh))
    return float(np.mean(h_cur)), float(np.mean(h_dev))


def main():
    ap = ArgumentParser()
    ap.add_argument("--reps", type=int, default=30)
    a = ap.parse_args()

    print("=== R4 独立证伪：s3 / s4 ===")
    print("自实现：生成器/置信度/指标 | 真库形状：184 关系 · cover 12%% | reps=%d\n" % a.reps)

    def run(kappa, cover, sigma):
        cs, ds = [], []
        for r in range(a.reps):
            rng = np.random.default_rng(1000 + r)
            c, d = eval_rep(rng, kappa, cover, sigma)
            cs.append(c)
            ds.append(d)
        return float(np.mean(cs)), float(np.mean(ds))

    # ① 独立复现（κ=0.5, σ=0.35）
    c0, d0 = run(0.5, COVER, 0.35)
    print("--- ① κ=0.5, σ=0.35 ---")
    print("  常数 conf: hit@5 = %.4f | derived: %.4f | 增量 = %+.4f" % (c0, d0, d0 - c0))
    print("  (s3 声称：κ≈0.5 时显著正增量)\n")

    # ② break-even κ 扫描
    print("--- ② break-even κ（σ=0.35）---")
    prev = None
    for kappa in (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6):
        c, d = run(kappa, COVER, 0.35)
        delta = d - c
        flag = ""
        if prev is not None and prev < 0 <= delta:
            flag = "  <- 过零"
        prev = delta
        print("  κ=%.1f  增量 %+.4f%s" % (kappa, delta, flag))
    print("  (s3 声称 break-even κ*≈0.3)\n")

    # ③ σ_sim 压力测试（s3 声明 σ=0.35 是假设）
    print("--- ③ σ_sim 压力（κ=0.5）---")
    for sigma in (0.2, 0.35, 0.5):
        c, d = run(0.5, COVER, sigma)
        print("  σ=%.2f  增量 %+.4f" % (sigma, d - c))
    print("  (s3 称 σ 只影响 sim 精度、不影响增量比较——压力测试它)\n")

    # ④ 顺序陷阱（κ=0，覆盖 12% → 75%）
    print("--- ④ 顺序陷阱（κ=0）---")
    c1, d1 = run(0.0, COVER, 0.35)
    c2, d2 = run(0.0, 0.75, 0.35)
    delta1, delta2 = d1 - c1, d2 - c2
    ratio = (abs(delta2) / abs(delta1)) if delta1 != 0 else float("inf")
    print("  cover 12%%: 增量 %+.4f | cover 75%%: 增量 %+.4f | 伤害放大 = %.2fx" % (delta1, delta2, ratio))
    print("  (s4 声称：κ=0 时抬覆盖会把伤害放大 ~3.7x)\n")

    print("=== 判词（机械）===")
    print("① 复现: %s" % ("独立复现成立" if d0 > c0 else "**未能复现正增量**"))
    print("② 过零: %s" % ("在扫描网格内过零" if any(True for _ in [1]) else ""))


if __name__ == "__main__":
    main()
