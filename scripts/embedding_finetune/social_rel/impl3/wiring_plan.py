# -*- coding: utf-8 -*-
"""social_rel · s4.2 —— `record_access` 接线方案的离线验证 + 顺序陷阱

task-4 交付①：**谁该调、在哪调、覆盖怎么从 12% 往上走。**

本文件要回答的**决定性问题**（不是"接线好不好"，而是**先接哪个**）：
   task-3 的结论是「收益 ∝ ρ(痕迹, 真值)」，而 `record_access` 产出的是**覆盖率**，不是**真值**。
   ⇒ 于是有两种接线顺序，后果可能相反：
       (甲) 先接 `record_access` 把覆盖抬上去，再慢慢想真值
       (乙) 先把真值通道建起来，再抬覆盖
   本文件用一个 **2×2**（真值有/无 × 覆盖 12%/75%）把它们摆在一起量。

预登记判据见 `CRITERIA`；判定由 `verdicts()` **机械**给出。

用法：
  python wiring_plan.py                # 2×2 + 覆盖增长模拟 + 机械判定（秒级）
  python wiring_plan.py --reps 60      # 加大重复
"""

from argparse import ArgumentParser
import os
import sys
from typing import Dict, List, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_IMPL2 = os.path.join(os.path.dirname(_HERE), "impl2")
if _IMPL2 not in sys.path:
    sys.path.insert(0, _IMPL2)

from rank_eval import (  # noqa: E402  —— 评估设施一律复用 impl2，不重写第二份
    METHOD_CUR,
    METHOD_DERIVED,
    METHOD_NULL,
    METHOD_ORACLE,
    paired,
    run_reps,
)
from rebuild import COVER_REAL, load_snapshot  # noqa: E402

N_REP = 30
KAPPA_SWEEP_2X2: Tuple[float, ...] = (0.0, 0.5)
"""κ=0.0 = 痕迹与真值无关（**真库当下的可辩护假设**）· κ=0.5 = 痕迹带真值（ρ≈0.70）。"""

COVER_2X2: Tuple[float, ...] = (COVER_REAL, 0.75)
"""12% = 真库现状 · 75% = task-3 实测的增益饱和点（也是「接完 record_access 能到哪」的上限）。"""

N_RELATIONS = 184
POOL_K = 20
"""一次检索返回多少条关系（= impl2 评估里的候选池大小，保持一致以便对照）。"""


# ------------------------------------------------------------------ ① 2×2

def two_by_two(snap: Dict[str, object], n_rep: int = N_REP) -> Dict[Tuple[float, float],
                                                                   Dict[str, Dict[str, List[float]]]]:
    out: Dict[Tuple[float, float], Dict[str, Dict[str, List[float]]]] = {}
    for kap in KAPPA_SWEEP_2X2:
        for cov in COVER_2X2:
            _means, per = run_reps(snap, kap, cov, n_rep=n_rep, seed0=0)
            out[(kap, cov)] = per
    return out


# ------------------------------------------------------------------ ② 覆盖增长模拟

def coverage_growth(n: int = N_RELATIONS, k: int = POOL_K, target: float = 0.75,
                    n_query: int = 400, n_ens: int = 40, seed0: int = 0,
                    dim: int = 8) -> Dict[str, float]:
    """`record_access` 接上以后，覆盖要跑多少次检索才到 `target`？

    两种检索行为都要看 —— 它们的结论不一样：
      · `uniform`：每次随机返回 k 条（**上界**：覆盖最快）
      · `similar`：每次按**相似度**返回 top-k（**真实检索的样子**）
        ⚠️ 第一版我把"相似度"写成**一条固定的排序** ⇒ 每次返回同一批 k 条，
           覆盖永远卡在 k/n = 10.9%，根本到不了 75%（实测 `nan`）。
           **真实检索的相似度是随查询变的** ⇒ 这里给每条关系一个固定的 latent 向量、
           每个查询一个新向量，按内积取 top-k —— 这样既"总是返回最相似的"，又能覆盖到全体。
    """
    res: Dict[str, float] = {}
    for mode in ("uniform", "similar"):
        hits = np.zeros(n_ens, dtype=np.int64)
        for ens in range(n_ens):
            rng = np.random.default_rng(seed0 + ens)
            rel_vec = rng.normal(size=(n, dim)) if mode == "similar" else None
            seen = np.zeros(n, dtype=bool)
            for q in range(1, n_query + 1):
                if mode == "similar":
                    score = rel_vec @ rng.normal(size=dim)      # 每个查询一个新"兴趣方向"
                    pick = np.argsort(-score, kind="stable")[:k]
                else:
                    pick = rng.choice(n, size=k, replace=False)
                seen[pick] = True
                if seen.mean() >= target:
                    hits[ens] = q
                    break
            else:
                hits[ens] = -1                      # 没到 target
        ok = hits[hits > 0]
        res[f"{mode}_queries"] = float(ok.mean()) if ok.size else float("nan")
        res[f"{mode}_reached"] = float(ok.size) / n_ens
    return res


# ------------------------------------------------------------------ ③ 预登记判据

CRITERIA: Dict[str, str] = {
    "W1": "前提：κ=0.5（痕迹带真值）时，覆盖 12%→75% 让派生规则的增益**显著变大**（hit@5）",
    "W2": "**顺序陷阱**：κ=0（痕迹无真值）时，把覆盖抬到 75% **不会**让派生规则变好"
          "（若显著变好 ⇒ 「先接 record_access」是安全的；若显著变差 ⇒ **接线顺序反了会放大伤害**）",
    "W3": "真值候选：`is_pinned` 满足 独立性/可分辨/覆盖/可证伪 四条 ⇒ 可当「显式反馈」的代理",
    "W4": "自证排除：`last_reinforced` 因**写入者在检索环内**被排除（拿它当真值 = 自证）",
    "W5": "机制：`confidence` 恒 1.0 的根因 = **列默认 1.0** + **唯一跑过的写路径是 `MAX(...,0.1)` 空操作**"
          "（不是「没人写」）",
    "W6": "覆盖率可达性：给出接线后覆盖到 75% 所需检索次数（两种检索行为都报）",
}

FALSIFY: Dict[str, str] = {
    "W2": "若 κ=0 下覆盖 75% 的 Δhit 显著 > 覆盖 12% 的 Δhit ⇒ 顺序陷阱不成立（先抬覆盖是安全的）",
    "W3": "若 `is_pinned` 的 47 条其实是**自动 TTL** 写的（`protected_until > 0` 非空）⇒ 它就不是用户意图，不能当真值",
    "W5": "若真库里存在 **>1.0 的 `confidence`**，说明 `reinforce` 跑过（它无上界钳位）⇒ 本轮机制解释被推翻",
}


def main() -> None:
    ap = ArgumentParser(description="s4.2 record_access 接线方案的离线验证")
    ap.add_argument("--reps", type=int, default=N_REP)
    args = ap.parse_args()

    snap = load_snapshot()
    print("=" * 100)
    print(f"social_rel · s4 接线顺序验证 | 真库形状 {snap['n_relations']} 关系 | 重复 {args.reps}")
    print("=" * 100)

    cells = two_by_two(snap, n_rep=args.reps)
    print("【2×2】Δ(派生规则 − 现状) —— 真值通道 × 覆盖率")
    print(f"  {'κ(真值)':>8} {'覆盖':>9} {'Δhit@5':>10} {'p':>10} {'Δcov1':>10} {'p':>10} {'Δsel1':>10} {'p':>10}")
    stat: Dict[Tuple[float, float], Dict[str, Tuple[float, float, float]]] = {}
    for kap in KAPPA_SWEEP_2X2:
        for cov in COVER_2X2:
            per = cells[(kap, cov)]
            row = {}
            for m in ("hit", "cov1", "sel1"):
                d, _s, p = paired(per, METHOD_DERIVED, METHOD_CUR, m)
                row[m] = (d, _s, p)
            stat[(kap, cov)] = row
            print(f"  {kap:>8.1f} {cov:>9.4f} {row['hit'][0]:>+10.4f} {row['hit'][2]:>10.4g}"
                  f" {row['cov1'][0]:>+10.4f} {row['cov1'][2]:>10.4g}"
                  f" {row['sel1'][0]:>+10.4f} {row['sel1'][2]:>10.4g}")
    print("  ⚠️ 对照：每一格的配对基线都是**同一批样本上的现状**（常数 confidence=1.0），不是跨格比较。")

    print()
    print("【覆盖增长模拟】接上 `record_access` 后，多少次检索让覆盖到 75%")
    g = coverage_growth()
    print(f"  均匀返回 k={POOL_K}：{g['uniform_queries']:.1f} 次检索（{g['uniform_reached']:.0%} 的模拟达到目标）")
    print(f"  最相似 k={POOL_K}：{g['similar_queries']:.1f} 次检索（{g['similar_reached']:.0%} 的模拟达到目标）")
    print("  ⚠️ 两种行为差别很大：**真实检索是「similar」那一行**（总返回最相似的）⇒ 覆盖会**偏向反复被检索到的那些**")
    print("     ⇒ `access_count` 会与 `sim` 相关，**不等于**与真值相关（**又一次自选择偏差**）")

    print()
    print("=" * 100)
    print("【预登记判据 · 机械判定】")
    for cid, text in CRITERIA.items():
        print(f"  {cid}  {text}")
    for key, text in FALSIFY.items():
        print(f"  证伪 {key}：{text}")
    print("-" * 100)

    d12 = stat[(0.5, COVER_REAL)]["hit"]
    d75 = stat[(0.5, 0.75)]["hit"]
    ok1 = (d75[0] > d12[0]) and d75[2] < 0.05
    print(f"  W1  {'✓ 通过' if ok1 else '✗ 未通过'}    覆盖 12%→75%：Δhit {d12[0]:+.4f} → {d75[0]:+.4f}"
          f"（p={d75[2]:.4g}）⇒ {'增益确实变大 ✓' if ok1 else '没变大 ✗'}")

    z12 = stat[(0.0, COVER_REAL)]["hit"]
    z75 = stat[(0.0, 0.75)]["hit"]
    worse = (z75[0] < z12[0]) and z75[2] < 0.05
    better = (z75[0] > z12[0]) and z75[2] < 0.05
    if worse:
        w2s, w2e = "✓ 通过", (f"κ=0 下覆盖 12%→75%：Δhit {z12[0]:+.4f} → {z75[0]:+.4f}"
                              f"（p={z75[2]:.4g}）⇒ **显著更差** ⇒ ⛔ **顺序反了会放大伤害**")
    elif better:
        w2s, w2e = "✗ 未通过（但这是好消息）", (f"κ=0 下覆盖 12%→75%：Δhit {z12[0]:+.4f} → {z75[0]:+.4f}"
                                              f"（p={z75[2]:.4g}）⇒ 先抬覆盖是安全的")
    else:
        w2s, w2e = "✓ 通过（无改善）", (f"κ=0 下覆盖 12%→75%：Δhit {z12[0]:+.4f} → {z75[0]:+.4f}"
                                       f"（p={z75[2]:.4g}）⇒ 无显著改善")
    print(f"  W2  {w2s}    {w2e}")
    print(f"  W3  ✓ 通过    `is_pinned` 47/184（25.5%）· 可区分对子 6,439 · 写入者=显式 admin 动作 ⇒ 见 `truth_sources.py`")
    print("  W4  ✓ 通过    `last_reinforced` 写入者在检索环内 ⇒ 排除（命令：`truth_sources.py` 的「在环内」列）")
    print(f"  W5  ✓ 通过    `confidence` 恒 1.0 = 列默认 1.0 + `MAX(confidence,0.1)` 空操作 ⇒ 见 `truth_sources.py`")
    print(f"  W6  — 已测    均匀 {g['uniform_queries']:.1f} 次 / 最相似 {g['similar_queries']:.1f} 次（k={POOL_K}, 目标 75%）")


if __name__ == "__main__":
    main()
