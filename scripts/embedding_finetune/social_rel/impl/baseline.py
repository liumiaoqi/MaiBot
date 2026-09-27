# -*- coding: utf-8 -*-
"""social_rel · s2.3 —— 测量：指标 + 现状等价基线 + 信息上限

本文件是**本项目指标的唯一定义处**（`learn.py` 从这里 import；指标不在别处再实现一份）。

三块内容：
  ① 指标 —— Spearman ρ（含置换检验）/ nDCG@k / MRR / hit@k
  ② 基线 —— 现状等价（全等 confidence · created_at 排序）＋ 空模型
  ③ 上限 —— 每个学习者**各自的信息天花板**（同一批指标、同一批数据）
            ⚠️ 没有上限行，"ρ = 0.6" 无法解释：是学得好，还是信息本来就只有这么多？

用法：
  python baseline.py --data-check        # 数据设计不变量自检（ρ + 置换 p）
  python baseline.py                     # 基线表 + 信息上限
  python baseline.py --freq-link anti    # 听劝对照：频次与 w* 反着来
"""

from argparse import ArgumentParser
from typing import Dict, List, Optional, Sequence, Tuple
import unicodedata

import numpy as np

from gen_synth import (
    N_EDGES_DEFAULT,
    N_PEOPLE_DEFAULT,
    World,
    average_ranks,
    event_stream,
    freq_signal,
    make_world,
    spearman,
)

K_DEFAULT = 5
N_PERM_DEFAULT = 2000
TIE_SEEDS_DEFAULT: Tuple[int, ...] = tuple(range(20))
"""并列（饱和）时随机的拆并列种子——**只用于并列存在时**的稳健化，不引入额外假设。"""


# ================================================================== ① 指标
# 真值对照统计（average_ranks / pearson / spearman）唯一定义处 = gen_synth.py（随真值定义，生成期也在用）
# 本文件负责：置换检验 + 检索类指标（nDCG / MRR / hit），不重复实现上面三个。

def perm_test(a: np.ndarray, b: np.ndarray, n_perm: int = N_PERM_DEFAULT,
              seed: int = 0) -> Tuple[float, float, float]:
    """双侧置换检验，返回 (rho, p, q95)。

      p   = (1 + #{|ρ_perm| ≥ |ρ_obs|}) / (1 + n_perm)
      q95 = |ρ_perm| 的 95 分位 —— 即"基线带"（超过它才算真的做过点什么）

    ⚠️ 置换算的是**相关**的零分布，不是"随机权重基线"的近似——两者在本文件里都给。
    """
    a = np.asarray(a, dtype=np.float64)
    b = np.asarray(b, dtype=np.float64)
    ra = average_ranks(a)
    rb = average_ranks(b)
    rac = ra - ra.mean()
    rbc = rb - rb.mean()
    den0 = np.sqrt(float((rac * rac).sum()) * float((rbc * rbc).sum()))
    if den0 == 0.0:
        return float("nan"), float("nan"), float("nan")
    rho = float((rac * rbc).sum() / den0)

    n = b.size
    rng = np.random.default_rng(seed)
    perms = rng.permuted(np.tile(np.arange(n, dtype=np.int64), (n_perm, 1)), axis=1)
    rbc_perm = rbc[perms]
    rbc_perm = rbc_perm - rbc_perm.mean(axis=1, keepdims=True)
    rho_perm = (rbc_perm @ rac) / np.sqrt((rbc_perm ** 2).sum(axis=1) * float((rac * rac).sum()))

    abs_perm = np.abs(rho_perm)
    p = float((1 + int(np.count_nonzero(abs_perm >= abs(rho) - 1e-12))) / (1 + n_perm))
    return rho, p, float(np.quantile(abs_perm, 0.95))


def person_rank_metrics(score: np.ndarray, world: World, k: int = K_DEFAULT,
                        tie_rng: Optional[np.random.Generator] = None,
                        min_candidates: Optional[int] = None) -> Dict[str, float]:
    """按人分组的检索质量。

    候选集 = 该人的全部关联边（= 图召回 `graph_relation_recall` 的候选池）；
    真值排序 = w* 降序。指标与 `NOTES.md` §3.1 ②层同名，便于接入层直接对照。

      nDCG@k ：graded relevance = w*（连续量，不用布尔），gain = 2^rel − 1
      MRR    ：真值第 1 名在 score 排序里的倒数排名
      hit@k  ：|score top-k ∩ 真值 top-k| / k（本世界候选数 ≥ k ⇒ 与 Precision@k 相同）
    """
    if min_candidates is None:
        min_candidates = k
    score = np.asarray(score, dtype=np.float64)
    if tie_rng is not None:
        # 并列 = "没有区分度"；拆并列只为让指标可算，不改变方法的排序信息
        score = score + tie_rng.random(score.size) * 1e-9

    disc = 1.0 / np.log2(np.arange(2, k + 2))
    ndcgs: List[float] = []
    rrs: List[float] = []
    hits: List[float] = []
    cov1s: List[float] = []
    sel1s: List[float] = []
    sel1_cov: List[float] = []

    for cand in world.incidence:
        if cand.size < min_candidates:
            continue
        rel = world.w_star[cand]
        order = np.argsort(-score[cand], kind="stable")
        top = cand[order[:k]]

        gains = np.power(2.0, world.w_star[top]) - 1.0
        dcg = float((gains * disc[: top.size]).sum())
        ideal = np.sort(rel)[::-1][:k]
        idcg = float(((np.power(2.0, ideal) - 1.0) * disc[: ideal.size]).sum())
        ndcgs.append(dcg / idcg if idcg > 0.0 else float("nan"))

        best = int(cand[int(np.argmax(rel))])
        rank_of_best = int(np.flatnonzero(cand[order] == best)[0]) + 1
        rrs.append(1.0 / rank_of_best)

        top_set = set(top.tolist())
        true_top = set(cand[np.argsort(-rel, kind="stable")[:k]].tolist())
        hits.append(len(true_top & top_set) / float(k))

        # ⭐ 生成 ≠ 选择：两个数必须**同时**给，只报一个会把结论报反
        covered = best in top_set
        cov1s.append(1.0 if covered else 0.0)
        sel1s.append(1.0 if int(cand[order[0]]) == best else 0.0)
        if covered:
            sel1_cov.append(1.0 if int(cand[order[0]]) == best else 0.0)

    if not ndcgs:
        raise ValueError(f"没有一个人的关联边数 ≥ {min_candidates}（k={k} 无法计算）")
    return {
        "ndcg": float(np.mean(ndcgs)),
        "mrr": float(np.mean(rrs)),
        "hit": float(np.mean(hits)),
        "cov1": float(np.mean(cov1s)),
        "sel1": float(np.mean(sel1s)),
        "sel1_cov": float(np.mean(sel1_cov)) if sel1_cov else float("nan"),
        "n_people": float(len(ndcgs)),
    }


def metric_row(score: np.ndarray, world: World, k: int = K_DEFAULT,
               n_perm: int = N_PERM_DEFAULT, perm_seed: int = 0,
               tie_seeds: Optional[Sequence[int]] = TIE_SEEDS_DEFAULT) -> Dict[str, float]:
    """一行完整指标：ρ + p + q95 + nDCG@k + MRR + hit@k。

    有并列（`np.unique(score).size < M`）时，对多个随机拆并列种子取平均——
    否则"饱和"这类结果会被某一次任意的拆法支配。

    `n_perm=0` ⇒ 只算点估计 ρ、不算置换检验（集成扫描时用来省时间）。
    """
    score = np.asarray(score, dtype=np.float64)
    if np.unique(score).size <= 1:
        rho, p, q95 = float("nan"), float("nan"), float("nan")
    elif n_perm > 0:
        rho, p, q95 = perm_test(score, world.w_star, n_perm=n_perm, seed=perm_seed)
    else:
        rho, p, q95 = spearman(score, world.w_star), float("nan"), float("nan")

    has_ties = np.unique(score).size < score.size
    seeds: Sequence[Optional[int]] = list(tie_seeds) if (has_ties and tie_seeds) else [None]
    rows = [
        person_rank_metrics(
            score, world, k=k,
            tie_rng=None if ts is None else np.random.default_rng(int(ts)),
        )
        for ts in seeds
    ]
    out = {
        "rho": rho, "p": p, "q95": q95,
        "ndcg": float(np.mean([r["ndcg"] for r in rows])),
        "mrr": float(np.mean([r["mrr"] for r in rows])),
        "hit": float(np.mean([r["hit"] for r in rows])),
        "cov1": float(np.mean([r["cov1"] for r in rows])),
        "sel1": float(np.mean([r["sel1"] for r in rows])),
        "sel1_cov": float(np.nanmean([r["sel1_cov"] for r in rows])),
        "n_people": rows[0]["n_people"],
        "ties": float(score.size - np.unique(score).size),
    }
    return out


# ================================================================== ② 现状等价基线

BASELINES: Tuple[str, ...] = ("fixed", "recency", "frequency", "random")


def baseline_score(name: str, world: World, seed: int = 0) -> np.ndarray:
    """三个"现状等价" + 一个空模型。"""
    if name == "fixed":
        # 现状：所有边 confidence 都是同一个默认值（cognitive_store DEFAULT 0.3）⇒ 零区分度
        return np.full(world.n_edges, world.w0, dtype=np.float64)
    if name == "recency":
        # 现状排序键：relation_store 的查询只见 created_at / last_activated_at
        # 构造上与 w* 无关 ⇒ 等价于一个独立随机置换（**这正是要证明的现状弱点**）
        return np.random.default_rng(seed).random(world.n_edges)
    if name == "frequency":
        # 纯频次权重：= freq 路的全部信息
        return freq_signal(world)
    if name == "random":
        # 空模型（未干预基线）：与 recency 同分布 ⇒ 两者应当给出一致的分数量级
        return np.random.default_rng(seed + 99991).random(world.n_edges)
    raise ValueError(f"未知基线 {name!r}，可用：{BASELINES}")


def baseline_rows(world: World, k: int = K_DEFAULT, n_perm: int = N_PERM_DEFAULT,
                  perm_seed: int = 0) -> Dict[str, Dict[str, float]]:
    rows: Dict[str, Dict[str, float]] = {}
    for name in BASELINES:
        rows[f"基线: {name}"] = metric_row(baseline_score(name, world), world,
                                          k=k, n_perm=n_perm, perm_seed=perm_seed)
    return rows


# ================================================================== ③ 信息上限

def ceiling_rows(world: World, k: int = K_DEFAULT, n_perm: int = N_PERM_DEFAULT,
                 perm_seed: int = 0) -> Dict[str, Dict[str, float]]:
    """每个学习者各自的**信息天花板**——同一批指标、同一条数据上的最优可用估计。

    ⚠️ 没有这一行，任何 ρ 都无法解释：是学得差，还是信息本来就只有这么多？
    """
    n_pos = world.n_pos.astype(np.float64)
    net = (world.n_pos - (world.n_events - world.n_pos)).astype(np.float64)
    return {
        "上限: 频次 n_e（hebbian 支）": metric_row(freq_signal(world), world, k=k,
                                                  n_perm=n_perm, perm_seed=perm_seed),
        "上限: 正标签 n₊（boostonly 支）": metric_row(n_pos, world, k=k,
                                                     n_perm=n_perm, perm_seed=perm_seed),
        "上限: 净标签 n₊−n₋（contrast 支）": metric_row(net, world, k=k,
                                                       n_perm=n_perm, perm_seed=perm_seed),
    }


# ================================================================== 打印

def _disp_width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1 for ch in s)


def pad_display(s: str, width: int, align: str = "l") -> str:
    """按**显示宽度**补齐（中日韩字符占 2 列）——`learn.py` 也用它排版。"""
    gap = max(0, width - _disp_width(s))
    return s + " " * gap if align == "l" else " " * gap + s


HEADER = (pad_display("方法", 26), pad_display("ρ(ŵ,w*)", 9, "r"), pad_display("p", 8, "r"),
          pad_display("q95", 7, "r"), pad_display("nDCG@5", 8, "r"), pad_display("MRR", 7, "r"),
          pad_display("hit@5", 7, "r"), pad_display("cov1", 6, "r"), pad_display("sel1", 6, "r"),
          pad_display("sel1|cov", 9, "r"), pad_display("并列", 6, "r"))


def format_header() -> str:
    return " ".join(HEADER)


def format_row(name: str, r: Dict[str, float]) -> str:
    def f(x: float, spec: str) -> str:
        return "n/a" if x != x else format(x, spec)

    return " ".join((
        pad_display(name, 26),
        pad_display(f(r["rho"], "+.4f"), 9, "r"),
        pad_display(f(r["p"], ".4f"), 8, "r"),
        pad_display(f(r["q95"], ".4f"), 7, "r"),
        pad_display(f(r["ndcg"], ".4f"), 8, "r"),
        pad_display(f(r["mrr"], ".4f"), 7, "r"),
        pad_display(f(r["hit"], ".4f"), 7, "r"),
        pad_display(f(r["cov1"], ".4f"), 6, "r"),
        pad_display(f(r["sel1"], ".4f"), 6, "r"),
        pad_display(f(r["sel1_cov"], ".4f"), 9, "r"),
        pad_display(f(r["ties"], ".0f"), 6, "r"),
    ))


# ================================================================== 数据设计不变量自检

def data_check(world: World, n_perm: int = N_PERM_DEFAULT, seed: int = 0) -> bool:
    """I1 频次 ∥ w*；I2 标签依赖 w*；I3 两路共用同一条日程。返回是否全部通过。"""
    print("【数据设计不变量自检】")
    ok = True

    rho1, p1, q1 = perm_test(freq_signal(world), world.w_star, n_perm=n_perm, seed=seed)
    sig1 = p1 < 0.05
    if world.freq_link == "none":
        good1 = not sig1
        ok &= good1
        verdict1 = "✓ 不显著异于 0（设计使然：频次不携带 w* 信息）" if good1 \
            else "✗ 频次竟然与 w* 显著相关"
    else:
        good1 = sig1 and rho1 < 0
        ok &= good1
        verdict1 = "✓ 与 w* 完美负秩相关（对照臂：响但反着）" if good1 \
            else "✗ 对照臂的负相关没做出来"
    print(f"  I1 ρ(纯频次次数 n_e, w*) = {rho1:+.4f}  p = {p1:.4f}  q95 = {q1:.4f}"
          f"   {verdict1}")

    # I2：构造式 p_pos = POS_FLOOR + POS_SPAN·w* ⇒ 单调 ⇒ ρ ≡ 1（这里验证"信息确实进了标签"）
    p_pos_emp = world.n_pos / np.maximum(1, world.n_events)
    rho2, p2, _ = perm_test(p_pos_emp, world.w_star, n_perm=n_perm, seed=seed + 1)
    good2 = p2 < 0.05 and rho2 > 0
    ok &= good2
    print(f"  I2 ρ(实测 +1 占比, w*) = {rho2:+.4f}  p = {p2:.4f}"
          f"   {'✓ 显式偏好信号确实携带 w* 信息' if good2 else '✗ 标签与 w* 无关！'}")

    # I3：两路必须共用同一条互动日程（对照只差"标签可见性"）
    edge_idx, _ = event_stream(world, seed=seed)
    hist = np.bincount(edge_idx, minlength=world.n_edges).astype(np.int64)
    same = bool(np.array_equal(hist, world.n_events))
    ok &= same
    print(f"  I3 两路共用同一条日程：freq 直方图 == pref 直方图 ⇒ {same}"
          f"   {'✓ 对照只差一个变量' if same else '✗ 两路日程不一致！'}")

    print(f"  规模：{world.n_people} 人 / {world.n_edges} 边 / T = {world.n_interactions} 事件"
          f" / 可评估人数（度 ≥ {K_DEFAULT}）= "
          f"{int(sum(1 for c in world.incidence if c.size >= K_DEFAULT))}")
    return ok


# ================================================================== CLI

def main() -> None:
    ap = ArgumentParser(description="social_rel s2.3 基线 / 指标 / 上限")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--people", type=int, default=N_PEOPLE_DEFAULT)
    ap.add_argument("--edges", type=int, default=N_EDGES_DEFAULT)
    ap.add_argument("--freq-link", choices=("none", "anti"), default="none")
    ap.add_argument("--k", type=int, default=K_DEFAULT)
    ap.add_argument("--n-perm", type=int, default=N_PERM_DEFAULT)
    ap.add_argument("--data-check", action="store_true", help="只跑设计不变量自检")
    args = ap.parse_args()

    world = make_world(seed=args.seed, n_people=args.people, n_edges=args.edges,
                       freq_link=args.freq_link)

    ok = data_check(world, n_perm=args.n_perm, seed=args.seed)
    if args.data_check:
        raise SystemExit(0 if ok else 1)

    print()
    print("【未干预基线】（对照：现状等价 + 空模型）")
    print(format_header())
    for name, row in baseline_rows(world, k=args.k, n_perm=args.n_perm,
                                   perm_seed=args.seed).items():
        print(format_row(name, row))

    print()
    print("【信息上限】（每个学习者各自的天花板——同一批指标、同一条数据）")
    print(format_header())
    for name, row in ceiling_rows(world, k=args.k, n_perm=args.n_perm,
                                  perm_seed=args.seed).items():
        print(format_row(name, row))


if __name__ == "__main__":
    main()
