# -*- coding: utf-8 -*-
"""social_rel · s3.2 —— 用**真库聚合特征**重建离线样本（含潜真值 + 痕迹耦合 κ）

为什么必须有"潜真值"：真库**没有相关性标注** ⇒ 无法直接量"排序好不好"。
所以本文件把问题**翻译成一个可证伪的命题**：
  「痕迹里的信息量 κ 要到多大，派生出的 `confidence` 才值得接」——κ 是**假设**，不是发现，必须扫。

三件事：
  ① `exact_expressiveness()` —— **纯计数、零模型假设**：真库的痕迹到底能区分多少「关系对」。
     这一节是**硬事实**，它给出了任何派生规则在真实数据上的表达力上限。
  ② `make_instance()` —— 按真实形状（184 关系 / 36 主体 / 支撑度 1..6 / last_reinforced 的 15 个值）
     重建一个样本，并注入：潜真值 `rel*` · 相似度 `sim` · 痕迹（由 `κ` 控制它与 `rel*` 的耦合）。
  ③ `derived_confidence()` —— 待验证的**派生规则**（本轮的交付②）。

⚠️ κ 的含义（读结果前必须记住）：κ = **痕迹与真实关系强度的耦合强度**。
   κ=0 ⇒ 痕迹与真值无关（= 真库当下的情形，因为我们**没有任何证据**说强化过的关系更重要）；
   κ=1 ⇒ 痕迹完美编码真值（上界）。**真库自己选不出 κ** —— 所以本文只报"break-even 在哪"。

用法：
  python rebuild.py                 # 打印真实侧表达力上限（+ 与真快照的一致性自检）
  python rebuild.py --kappa 0.5     # 看某个 κ 下生成的样本长什么样
"""

from argparse import ArgumentParser
from dataclasses import dataclass
import json
import os
import sys
from typing import Dict, List, Sequence, Tuple

import numpy as np

# 秩统计的**唯一定义处** = `impl/gen_synth.py`（s2 已定案，且带并列平均秩）。
# ⚠️ 不在这里重写一份：2026-09-27 我第一版写了个"按排序位置给秩"的 `_rank01`，
#    它**会拆开并列** —— 而真库里 163/184 条关系的支撑度都是 1（88.6% 并列）、
#    22 条痕迹只有 15 个不同时刻。拆并列等于**凭空造出分辨力**，会把表达力上限算高一个量级。
_HERE = os.path.dirname(os.path.abspath(__file__))
_IMPL_DIR = os.path.join(os.path.dirname(_HERE), "impl")
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

from gen_synth import average_ranks  # noqa: E402  —— 路径插在最前，故意放在第三方之后

HERE = os.path.dirname(os.path.abspath(__file__))
SNAPSHOT_PATH = os.path.join(HERE, "real_sample.json")

CONF_FLOOR = 0.3
"""派生 confidence 的下界。对齐已落地的护栏：`confidence_guard.py` 的 floor `0.3`。"""

CONF_CEIL = 1.0
"""上界 = 现状值（全 1.0）。派生规则只解释 `[floor, 1.0]` 这一段。"""

ALPHA_DEFAULT = 0.5
"""派生规则里"时效"与"支撑度"的权重（**预登记值**，敏感性见 `rank_eval.py` 的扫描）。"""

COVER_REAL = 22.0 / 184.0
"""真库当下的**痕迹覆盖率** = 22/184 = 11.96%。"""


# ------------------------------------------------------------------ 真快照

def load_snapshot(path: str = SNAPSHOT_PATH) -> Dict[str, object]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"缺少真库快照：{path}\n请先跑：python snapshot.py")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# ------------------------------------------------------------------ ① 真实侧表达力上限（纯计数）

def exact_expressiveness(snap: Dict[str, object]) -> List[Tuple[str, int, int, float]]:
    """对每个候选特征，精确数出它**能区分**多少「关系对」（并列算不能区分）。

    返回 [(特征, 覆盖条数, 可区分对子数, 占比)]。
    ⚠️ 零模型假设 —— 这是真库本身的表达力上限，不是实验结果。
    """
    rels: List[Dict[str, object]] = snap["relations"]  # type: ignore[assignment]
    n = len(rels)
    total = n * (n - 1) // 2

    sup_keys = [r["sup"] for r in rels]
    # 无痕迹的一律取同一个值 ⇒ 彼此并列
    reinf_keys = [r["reinf_sec"] if r["reinf_sec"] is not None else -1 for r in rels]
    both_keys = [(r["reinf_sec"] if r["reinf_sec"] is not None else -1, r["sup"]) for r in rels]
    access_keys = [0] * n  # access_count 全 0

    rows: List[Tuple[str, int, int, float]] = []
    for name, keys, cover in (
        ("last_reinforced（时效）", reinf_keys, sum(1 for r in rels if r["reinf_sec"] is not None)),
        ("access_count（访问次数）", access_keys, 0),
        ("支撑度（段落数）", sup_keys, n),
        ("支撑度 × last_reinforced", both_keys, n),
    ):
        d = _distinguishable_pairs(keys)
        rows.append((name, cover, d, d / total))
    return rows


def print_expressiveness(snap: Dict[str, object]) -> None:
    rels: List[Dict[str, object]] = snap["relations"]  # type: ignore[assignment]
    n = len(rels)
    total = n * (n - 1) // 2
    print(f"【真实侧表达力上限 · 纯计数，零模型假设】（关系 {n} 条 ⇒ 关系对 {total:,} 个）")
    print(f"  {'特征':<26} {'覆盖':>10} {'可区分对子':>10} {'占比':>9}")
    for name, cover, d, frac in exact_expressiveness(snap):
        print(f"  {name:<26} {cover:>4}/{n:<5} {d:>10,} {frac:>8.2%}")
    print("  ⚠️ 「可区分」≠「有信息」：它只说**权重值不同**。这些差异指向真值还是指向噪声，")
    print("     取决于痕迹与真值的耦合 κ —— **真库自己给不出 κ**（没有相关性标注），只能扫（见 `rank_eval.py`）。")


# ------------------------------------------------------------------ ② 样本

@dataclass
class Instance:
    """一次离线样本。所有数组长度 = 关系数 n。"""

    seed: int
    kappa: float
    cover: float
    sigma_sim: float
    alpha: float
    n: int
    rel_star: np.ndarray      # 潜真值：真实关系强度（真库没有它 —— 这是"注入的判据"）
    sim: np.ndarray           # 相似度（现状排序用的就是它，因为 confidence ≡ 1）
    sup_norm: np.ndarray      # 支撑度归一化到 [0,1]
    rec_norm: np.ndarray      # 时效归一化到 [0,1]（无痕迹 = 0）
    traced: np.ndarray        # bool：这条关系是否有可用痕迹
    scores: Dict[str, np.ndarray]   # 各方法的排序分数
    t_rec: np.ndarray         # 时效通道的"信号强度"（建模内部量，用于报 κ 的可解释等价）
    t_sup: np.ndarray         # 支撑度通道的"信号强度"


def _rank01(x: np.ndarray) -> np.ndarray:
    """归一化到 [0,1] 的**平均秩**（并列取平均 ⇒ **不拆并列**）。"""
    x = np.asarray(x, dtype=np.float64)
    if x.size <= 1:
        return np.zeros_like(x)
    return (average_ranks(x) - 1.0) / (x.size - 1.0)


def _distinguishable_pairs(keys: Sequence[object]) -> int:
    """**能区分**的关系对数 = 总数 − 同值（并列）对数。

    ⚠️ 别写成 `Σ C(v,2)`：那是**并列**对数，语义正好相反。
       2026-09-27 我第一版就写反了，把 `access_count`（全 0 ⇒ 一对都分不出）
       算成了 100% 可区分 —— 数字看起来还挺"漂亮"，全靠交叉核对才抓住。
    """
    from collections import Counter
    c = Counter(keys)
    n = sum(c.values())
    within = sum(v * (v - 1) // 2 for v in c.values())
    return n * (n - 1) // 2 - within


def real_level_sizes(snap: Dict[str, object]) -> Dict[str, List[int]]:
    """真库里两个特征的**并列结构**（按时效/支撑度降序，每档多少条）。

    这是必须保真的东西：真库 22 条痕迹只落在 **15 个时刻**上（不是 22 个），
       支撑度只有 **6 档**且 163/184 挤在第 1 档。
       建模时若把并列拆开，等于**凭空造出分辨力**，会把表达力上限算高一个量级。
    """
    rels: List[Dict[str, object]] = snap["relations"]  # type: ignore[assignment]
    from collections import Counter
    rec = Counter(r["reinf_sec"] for r in rels if r["reinf_sec"] is not None)
    sup = Counter(int(r["sup"]) for r in rels)
    return {
        "rec_levels": [c for _v, c in sorted(rec.items(), key=lambda kv: -kv[0])],
        "sup_levels": [c for _v, c in sorted(sup.items(), key=lambda kv: -kv[0])],
    }


def _scale_sizes(sizes: Sequence[int], total: int) -> List[int]:
    """把档位人数按比例缩放到 total（最大余数法），保序且各档 ≥0。"""
    s = np.asarray(sizes, dtype=np.float64)
    raw = s / s.sum() * total
    base = np.floor(raw).astype(int)
    rem = total - int(base.sum())
    if rem > 0:
        for i in np.argsort(-(raw - base))[:rem]:
            base[i] += 1
    elif rem < 0:
        for i in np.argsort(raw - base)[: -rem]:
            if base[i] > 0:
                base[i] -= 1
    return [int(x) for x in base]


def _levelize(t: np.ndarray, idx: np.ndarray, sizes: Sequence[int]) -> np.ndarray:
    """把 `idx`（按 `t` 降序）分成 len(sizes) 档，第 0 档 = `t` 最大。

    返回长度 = len(idx)、取值 ∈ [0,1] 的档位归一化值（**同档完全并列** ⇒ 保真库的并列结构）。
    """
    order = idx[np.argsort(-t[idx], kind="stable")]
    out = np.zeros(order.size, dtype=np.float64)
    pos = 0
    levels = len(sizes)
    for lv, cnt in enumerate(sizes):
        out[pos:pos + cnt] = 1.0 - (lv / max(1, levels - 1))
        pos += cnt
    res = np.zeros(t.size, dtype=np.float64)
    res[order] = out
    return res




def derived_confidence(traced: np.ndarray, rec_norm: np.ndarray, sup_norm: np.ndarray,
                       alpha: float = ALPHA_DEFAULT) -> np.ndarray:
    """**待验证的派生规则**（交付②）：

        conf = FLOOR + (CEIL − FLOOR) · w
        w    = alpha · 时效分 + (1 − alpha) · 支撑度分        （有痕迹）
        w    = 0                                             （无痕迹 ⇒ 取 floor）

    三个输入都是**真库现成可取的**：`last_reinforced`（时效）· `paragraph_relations` 计数（支撑度）。
    ⚠️ **增量按量程缩放**（s2 的坑）：两个分量都先归一化到 `[0,1]` 再进 `[FLOOR, CEIL]`，
       绝不直接拿"次数 / 天数"当权重 —— 那会让第一条/最新一条把权重顶到天花板。
    """
    w = alpha * rec_norm + (1.0 - alpha) * sup_norm
    w = np.where(traced, w, 0.0)
    return CONF_FLOOR + (CONF_CEIL - CONF_FLOOR) * np.clip(w, 0.0, 1.0)


def make_instance(snap: Dict[str, object], seed: int = 0, kappa: float = 0.0,
                  cover: float = COVER_REAL, sigma_sim: float = 0.35,
                  alpha: float = ALPHA_DEFAULT) -> Instance:
    """按真实形状重建样本。

    κ = **每条痕迹通道**与 `rel*` 的耦合强度；κ=0 ⇒ 痕迹与真值无关（真库当下的可辩护假设）。
    两条通道**各自独立**（时效通道 / 支撑度通道），因为现实中它们是两个不同的观察面：
      · `last_reinforced`（时效）—— 只覆盖 cover 那一部分关系
      · `paragraph_relations` 计数（支撑度）—— 覆盖 184/184
    ⇒ "把两个信号合起来" 才是有意义的问题（`derived` 干的就是这件事）。

    ⚠️ **并列结构保真**：真库 22 条痕迹只落在 15 个时刻、支撑度只有 6 档（163 条挤在第 1 档）。
       本函数按真库的档位人数分配信号强度 ⇒ **同档完全并列**，不凭空造分辨力。
       2026-09-27 第一版把档位拆开了（还会循环复用那 15 个值），测出来的"覆盖越高越好"是**假象**。
    """
    rels: List[Dict[str, object]] = snap["relations"]  # type: ignore[assignment]
    n = len(rels)
    rng = np.random.default_rng(seed)

    rel_star = rng.random(n)
    sim = rel_star + rng.normal(0.0, sigma_sim, size=n)

    # 两条通道各自的"信号强度"：κ=0 纯噪声，κ=1 完美指向 rel*
    t_rec = kappa * _rank01(rel_star) + (1.0 - kappa) * rng.random(n)
    t_sup = kappa * _rank01(rel_star) + (1.0 - kappa) * rng.random(n)

    lv = real_level_sizes(snap)

    # --- 通道一：支撑度（真库覆盖 184/184）---
    sup_sizes = lv["sup_levels"]
    sup_norm = _levelize(t_sup, np.arange(n), _scale_sizes(sup_sizes, n))

    # --- 通道二：last_reinforced（真库覆盖 22/184，只有 15 个不同时刻）---
    n_traced = int(round(cover * n))
    order = np.argsort(-t_rec, kind="stable")
    traced = np.zeros(n, dtype=bool)
    traced[order[:n_traced]] = True
    rec_norm = _levelize(t_rec, np.flatnonzero(traced),
                         _scale_sizes(lv["rec_levels"], n_traced))

    conf_const = np.full(n, CONF_CEIL)                                   # 现状：全 1.0
    conf_support = CONF_FLOOR + (CONF_CEIL - CONF_FLOOR) * sup_norm      # 全coverage
    conf_reinf = derived_confidence(traced, rec_norm, np.zeros(n), alpha=1.0)
    conf_derived = derived_confidence(traced, rec_norm, sup_norm, alpha=alpha)

    scores = {
        "现状: 常数 confidence=1.0": sim,                 # = sim × 1.0，恒等变换
        "空模型: 随机分数": rng.random(n),
        "支撑度 only": sim * conf_support,
        "last_reinforced only": sim * conf_reinf,
        "派生规则(交付②)": sim * conf_derived,
        "上限: 直接用真值": rel_star,
    }
    return Instance(seed=seed, kappa=kappa, cover=cover, sigma_sim=sigma_sim, alpha=alpha,
                    n=n, rel_star=rel_star, sim=sim, sup_norm=sup_norm, rec_norm=rec_norm,
                    traced=traced, scores=scores, t_rec=t_rec, t_sup=t_sup)


def main() -> None:
    ap = ArgumentParser(description="s3.2 离线样本重建")
    ap.add_argument("--kappa", type=float, default=None)
    ap.add_argument("--cover", type=float, default=COVER_REAL)
    args = ap.parse_args()

    snap = load_snapshot()
    rels: List[Dict[str, object]] = snap["relations"]  # type: ignore[assignment]
    print(f"真快照：{snap['n_relations']} 关系 / {snap['n_subjects']} 主体 / "
          f"内容字段 = {'有' if any('subject' in r for r in rels) else '无（只聚合量）'} ✓")
    print()
    print_expressiveness(snap)

    if args.kappa is not None:
        inst = make_instance(snap, seed=0, kappa=args.kappa, cover=args.cover)
        sup_counts = {}
        for r in rels:
            sup_counts[int(r["sup"])] = sup_counts.get(int(r["sup"]), 0) + 1
        print()
        print(f"【样本预览】κ={args.kappa} · cover={args.cover:.4f}（{int(inst.traced.sum())}/{inst.n} 条有痕迹）"
              f" · σ_sim={inst.sigma_sim} · α={inst.alpha}")
        print(f"  支撑度分布 = {sorted(sup_counts.items())}")
        print(f"  时效不同取值 = {len(np.unique(inst.rec_norm[inst.traced]))}（真库 = 15）")
        print("  （分数质量对比在 `rank_eval.py` —— 指标只在那一个地方定义）")


if __name__ == "__main__":
    main()
