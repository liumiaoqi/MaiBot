# -*- coding: utf-8 -*-
"""social_rel · s2.1 —— 合成社会关系图 + 两路事件流

使命（`social_rel/NOTES.md` §3.1 指标①「机制层」）：
  造一个有 ground truth 的社会关系世界，让「学出来的关系强度 w  vs  注入的真值 w*」
  这件事**可以被算出来**——没有真值，"更好"就没有判据。

世界：N 个人 · M 条边（边 = 一条关系）· 每条边注入真值强度 w* ~ U(0.05, 0.95)

两路事件流（**同一条互动日程，唯一差别 = 是否暴露 valence 标签**）：
  · freq 路（纯频次）  ：只暴露「这条边被互动了几次」。次数**独立于 w***（设计使然）
  · pref 路（显式偏好）：暴露每次互动的 valence（±1），P(+1) = 0.15 + 0.70·w*
                         —— 这是**唯一**携带 w* 信息的通道

  两条路共用同一条日程 ⇒ 对照只差一个变量（标签可见性）——这是本实验对照设计的核心。
  ⚠️ 于是"纯频次学不动"这件事本身是**设计性质**（实证部分见 `RESULTS.md` 的 H2a/H2b 拆分）。

用法：
  python gen_synth.py --seed 0        # 世界描述统计（不含 ρ 检验）
  python baseline.py --data-check     # 设计不变量自检（ρ + 置换 p）
  python learn.py                     # 全流程（网格 + 归因 + 预登记判定）

⚠️ 本文件**不 import 本地模块**（保持 gen_synth → baseline → learn 的单向依赖），
   因此 ρ / nDCG 等指标一律定义在 `baseline.py`，不在这里重复实现。
"""

from argparse import ArgumentParser
from dataclasses import dataclass, field
from typing import List, Tuple

import numpy as np

# ------------------------------------------------------------------ 真值对照统计（唯一定义处）

def average_ranks(x: np.ndarray) -> np.ndarray:
    """平均秩（并列取平均）。不依赖 scipy —— 本线只允许 numpy。

    ⚠️ 本函数与 `pearson` / `spearman` **随真值一起定义在这里**（不是放错位置）：
       它们是「ŵ vs w*」的**真值对照**统计，生成期要用它约束设计不变量，
       报告期 `baseline.py` 直接 import 复用 ⇒ 全项目只有这一份实现，不会分叉。
       检索类指标（nDCG / MRR / hit）与置换检验在 `baseline.py`。
    """
    x = np.asarray(x, dtype=np.float64)
    n = x.size
    order = np.argsort(x, kind="stable")
    xs = x[order]

    is_start = np.ones(n, dtype=bool)
    if n > 1:
        is_start[1:] = xs[1:] != xs[:-1]
    starts = np.flatnonzero(is_start)
    lengths = np.diff(np.append(starts, n))

    # 一个并列块的秩区间是 [starts+1, starts+lengths] ⇒ 平均秩 = 区间中点
    ranks = np.empty(n, dtype=np.float64)
    ranks[order] = np.repeat((starts + 1 + starts + lengths) / 2.0, lengths)
    return ranks


def pearson(a: np.ndarray, b: np.ndarray) -> float:
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ac = a - a.mean()
    bc = b - b.mean()
    den = np.sqrt(float((ac * ac).sum()) * float((bc * bc).sum()))
    if den == 0.0:
        return float("nan")
    return float((ac * bc).sum() / den)


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    return pearson(average_ranks(a), average_ranks(b))


# ------------------------------------------------------------------ 冻结的设计参数

W0 = 0.3
"""初始权重。对齐现状：`src/A_memorix/core/storage/stores/cognitive_store.py` 的
`confidence REAL NOT NULL DEFAULT 0.3`——所有边起步同值，即"现状没有区分度"。"""

POS_FLOOR = 0.15
POS_SPAN = 0.70
"""P(valence=+1 | 边 e) = POS_FLOOR + POS_SPAN · w*_e —— 显式偏好信号与真值的耦合方式。

w* = 0.05 ⇒ P(+1) ≈ 0.185（基本是负反馈）
w* = 0.95 ⇒ P(+1) ≈ 0.815（基本是正反馈）
"""

SEED_DEFAULT = 0
N_PEOPLE_DEFAULT = 60
N_EDGES_DEFAULT = 600
"""**三个文件共用一个默认世界**（`baseline.py` / `learn.py` 的 argparse 都 import 这两个常量）。

⚠️ 曾是 **240**，改 600 是实测决定的：240 边时度中位只有 8，而 k=5，
   "从 8 个里挑 5 个" 让机会水平就高达 nDCG ≈ **0.71** ⇒ 可分辨区间只剩 0.16，指标几乎分不出好坏。
   600 边时度中位 20，机会水平降到 nDCG ≈ **0.56**，可分辨区间拉到 0.27（见 RUNBOOK 里的实测对照）。
   ⚠️ 更要紧的是：三处默认值不一致会让"照着文档跑一遍"得到**另一个世界**的数
   —— 2026-09-27 实测踩到（`gen_synth.py` 默认 240、`learn.py` 默认 600）。
   现在默认值**只有这一份定义**，别的文件 import 它。
"""
WSTAR_LO = 0.05
WSTAR_HI = 0.95

FREQ_LINKS = ("none", "anti")
"""频次与真值的关系：
  "none" —— 次数 ∥ 独立于 w*（默认；"纯频次信号与 w* 无关，只在频次上高"）
  "anti" —— 次数与 w* 完美**负**秩相关（"响但反着"的对照臂：把最大次数派给最弱的边）
"""

FREQ_ORTHO_TOL = 0.02
"""`freq_link="none"` 时的**设计约束**：|ρ(n_e, w*)| ≤ 本值，否则重抽次数。

⚠️ 为什么必须约束而不是"独立抽样就完事"：独立抽样只保证**总体**不相关，
   而**这一次实现**的样本可以有偶然相关。2026-09-27 实测 seed=0 原始抽样拿到
   ρ = +0.1204 / p = 0.0545（M=240 的 95 分位带是 0.1217）——**差一点就显著**。
   那次样本里"纯频次"是**带信息**的，H2 的对照就被污染了。
   ⇒ 把设计不变量**做实在样本上**（不是祈祷它成立），代价 ≈ 4 次重抽。
"""

FREQ_MAX_TRIES = 2000


# ------------------------------------------------------------------ 世界

@dataclass
class World:
    """一个合成社会关系世界（纯数组，无隐藏状态）。"""

    seed: int
    n_people: int
    edges: np.ndarray           # (M, 2) int64 —— 每行的两个人（无向、无自环、无重边）
    w_star: np.ndarray          # (M,)   float64 —— 注入的真值强度
    n_events: np.ndarray        # (M,)   int64 —— 每边的互动次数（两路共用的日程）
    n_pos: np.ndarray           # (M,)   int64 —— 其中 valence=+1 的次数
    freq_link: str
    w0: float = W0
    incidence: List[np.ndarray] = field(default_factory=list)
    """incidence[u] = 第 u 个人关联的边下标（升序）——`selected` 更新要用它取"候选集"。"""

    def __post_init__(self) -> None:
        self.incidence = build_incidence(self.edges, self.n_people)

    @property
    def n_edges(self) -> int:
        return int(self.w_star.size)

    @property
    def n_interactions(self) -> int:
        return int(self.n_events.sum())

    def degrees(self) -> np.ndarray:
        return np.array([c.size for c in self.incidence], dtype=np.int64)


def build_incidence(edges: np.ndarray, n_people: int) -> List[np.ndarray]:
    """人 → 关联边下标（升序）。"""
    buckets: List[List[int]] = [[] for _ in range(n_people)]
    for e in range(edges.shape[0]):
        buckets[int(edges[e, 0])].append(e)
        buckets[int(edges[e, 1])].append(e)
    return [np.asarray(sorted(b), dtype=np.int64) for b in buckets]


def make_world(
    seed: int = SEED_DEFAULT,
    n_people: int = N_PEOPLE_DEFAULT,
    n_edges: int = N_EDGES_DEFAULT,
    freq_link: str = "none",
    w0: float = W0,
) -> World:
    """合成一个世界。同一个 (seed, 参数) ⇒ 逐字节可复现。"""
    if freq_link not in FREQ_LINKS:
        raise ValueError(f"freq_link 必须是 {FREQ_LINKS} 之一，收到 {freq_link!r}")
    n_pairs = n_people * (n_people - 1) // 2
    if not 0 < n_edges <= n_pairs:
        raise ValueError(f"n_edges 必须在 (0, {n_pairs}]，收到 {n_edges}")

    rng = np.random.default_rng(seed)

    # 1) 无向简单图：从 C(n,2) 个二元组里不放回抽 M 条（无自环、无重边）
    pair_idx = rng.choice(n_pairs, size=n_edges, replace=False)
    tri_i, tri_j = np.triu_indices(n_people, k=1)
    edges = np.stack([tri_i[pair_idx], tri_j[pair_idx]], axis=1).astype(np.int64)

    # 2) 注入真值强度
    w_star = rng.uniform(WSTAR_LO, WSTAR_HI, size=n_edges)

    # 3) 互动次数：重尾，且**不依赖 w***
    #    freq_link="none" 时用拒绝抽样把"设计不变量"做实在**这个样本**上：
    #    |ρ(n_e, w*)| ≤ FREQ_ORTHO_TOL，否则重抽（见 FREQ_ORTHO_TOL 的说明）。
    def _draw_counts() -> np.ndarray:
        return (1 + rng.poisson(rng.lognormal(mean=1.0, sigma=0.7, size=n_edges))).astype(np.int64)

    if freq_link == "anti":
        # 完美负秩相关：最大的次数派给 w* 最小的边
        base = _draw_counts()
        order_desc = np.argsort(-base, kind="stable")
        target = np.argsort(w_star, kind="stable")
        n_events = np.empty(n_edges, dtype=np.int64)
        n_events[target] = base[order_desc]
    else:
        n_events = _draw_counts()
        tries = 0
        while abs(spearman(n_events, w_star)) > FREQ_ORTHO_TOL:
            tries += 1
            if tries > FREQ_MAX_TRIES:
                raise RuntimeError(
                    f"频次正交化重抽 {FREQ_MAX_TRIES} 次仍未达到 |ρ| ≤ {FREQ_ORTHO_TOL}"
                    f"（当前 ρ = {spearman(n_events, w_star):+.4f}）——参数或容差需要复核"
                )
            n_events = _draw_counts()

    # 4) valence —— 唯一携带 w* 的通道
    p_pos = POS_FLOOR + POS_SPAN * w_star
    n_pos = rng.binomial(n_events, p_pos).astype(np.int64)

    return World(
        seed=seed,
        n_people=n_people,
        edges=edges,
        w_star=w_star,
        n_events=n_events,
        n_pos=n_pos,
        freq_link=freq_link,
        w0=w0,
    )


# ------------------------------------------------------------------ 两路事件流

def event_stream(world: World, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """把世界展开成一条**时间上打散**的事件流，返回 (edge_idx (T,), valence (T,))。

    ⚠️ 两路共用这一条日程：
        · freq 路只读 edge_idx 的直方图（= `freq_signal`）
        · pref 路读 edge_idx + valence（= `pref_signal`）
        ⇒ 对照只差"标签可见性"这一个变量。
    """
    rng = np.random.default_rng(seed)
    edge_idx = np.repeat(np.arange(world.n_edges), world.n_events)

    # 每条边的前 n_pos 个事件标 +1，其余 −1（顺序在下面被整体打散）
    offsets = np.arange(edge_idx.size) - np.repeat(np.cumsum(world.n_events) - world.n_events,
                                                   world.n_events)
    valence = np.where(offsets < np.repeat(world.n_pos, world.n_events), 1, -1).astype(np.int64)

    perm = rng.permutation(edge_idx.size)
    return edge_idx[perm], valence[perm]


def freq_signal(world: World) -> np.ndarray:
    """【纯频次事件流】的全部信息：每条边被互动了几次（与 w* 无关）。"""
    return world.n_events.astype(np.float64)


def pref_signal(world: World, seed: int = 0) -> Tuple[np.ndarray, np.ndarray]:
    """【显式偏好事件流】的全部信息：每次互动的 (边, valence)。"""
    return event_stream(world, seed)


# ------------------------------------------------------------------ CLI

def describe(world: World) -> str:
    ws = world.w_star
    ne = world.n_events
    deg = world.degrees()
    lines = [
        f"世界：{world.n_people} 人 · {world.n_edges} 边 · 互动总数 T = {world.n_interactions}"
        f" · freq_link = {world.freq_link} · seed = {world.seed}",
        f"  w*       min/中位/max = {ws.min():.3f} / {np.median(ws):.3f} / {ws.max():.3f}"
        f"  均值 {ws.mean():.3f}",
        f"  次数/Min = {ne.min()}  中位 = {np.median(ne):.0f}  max = {ne.max()}"
        f"  均值 {ne.mean():.2f}（重尾 ⇒ 频次「看起来很重要」）",
        f"  P(+1) 构造式 = {POS_FLOOR} + {POS_SPAN}·w*  ⇒ 实际 +1 占比"
        f" {world.n_pos.sum() / max(1, ne.sum()):.3f}",
        f"  度分布  min/中位/max = {deg.min()} / {np.median(deg):.0f} / {deg.max()}"
        f"  ·  度 ≥ 5 的人 = {int((deg >= 5).sum())} / {world.n_people}",
        "  ⚠️ 描述统计不含 ρ 检验；设计不变量自检见：python baseline.py --data-check",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = ArgumentParser(description="social_rel s2.1 合成世界生成器")
    ap.add_argument("--seed", type=int, default=SEED_DEFAULT)
    ap.add_argument("--people", type=int, default=N_PEOPLE_DEFAULT)
    ap.add_argument("--edges", type=int, default=N_EDGES_DEFAULT)
    ap.add_argument("--freq-link", choices=FREQ_LINKS, default="none")
    args = ap.parse_args()

    world = make_world(seed=args.seed, n_people=args.people, n_edges=args.edges,
                       freq_link=args.freq_link)
    print(describe(world))


if __name__ == "__main__":
    main()
