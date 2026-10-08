# -*- coding: utf-8 -*-
"""social_rel · s3.3 —— 离线复刻的排序评估（含预登记判据的**机械判定**）

问题（task-3 交付①）：**「`confidence` 有值之后，`sim × confidence` 排序优于基线」成立吗？**

评估设计（三条硬约束都在里面）：
  · **候选池随机摆放** —— 每个查询的候选池独立抽样后**打乱顺序**，并对并列分数加随机拆并列
    （lead 2026-09-27 转述证伪者的硬约束：固定摆放会得到"永远选左边 = 1.0000"的**恒绿判据**）
  · **coverage 与 selection 两个数同时给**（`cov1` / `sel1` / `sel1|cov` 三列并排）
    —— 同一批 run 里报哪个，结论会反过来（`NOTES.md §3.4 ④`）
  · **对照组** —— `空模型: 随机分数`（下界探针）+ `上限: 直接用真值`（上界探针）+ `现状: 常数 confidence=1.0`
    ⚠️ 判据**只能**在"下界≈机会水平 且 上界≫现状"成立之后才可解释。

指标定义与 s2 的 `impl/baseline.py` **同源**（`cov1`/`sel1`/`nDCG`/`MRR`/`hit` 同名同义），
   秩统计直接**复用** `impl/baseline.py` 的实现（避免两份实现分叉）；差别只在本线的候选池按**查询**组织，
   而不是按"人"分组。

用法（秒级）：
  python rank_eval.py                 # 全流程：自检 → 对照探针 → κ 扫描 → 覆盖扫描 → 预登记判定
  python rank_eval.py --reps 60       # 加大重复次数
"""

from argparse import ArgumentParser
import os
import sys
from typing import Dict, List, Sequence, Tuple

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_IMPL_DIR = os.path.join(os.path.dirname(_HERE), "impl")
if _IMPL_DIR not in sys.path:
    sys.path.insert(0, _IMPL_DIR)

from rebuild import (  # noqa: E402
    ALPHA_DEFAULT,
    COVER_REAL,
    Instance,
    load_snapshot,
    make_instance,
    print_expressiveness,
)
from baseline import spearman as _spearman  # noqa: E402  —— 秩统计复用 s2 的唯一定义处

# ------------------------------------------------------------------ 冻结的评估参数

K = 5
POOL = 20
N_REP = 30
SIGMA_SIM = 0.35
"""相似度噪声。⚠️ 这是**声明的假设**，不是从真库量出来的 —— 真库的向量是内容，按纪律不导出。
   它只影响"sim 本身有多准"，不影响"加 confidence 有没有增量"这一步比较（同一条 sim 下对比）。"""

KAPPA_REF = 0.5
"""预登记的参考耦合强度（判据 C2 用它）。κ=0.5 = "痕迹有一半指向真值"，是个中性假设。"""

KAPPA_SWEEP: Tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
COVER_SWEEP: Tuple[float, ...] = (COVER_REAL, 0.25, 0.5, 0.75, 1.0)
"""覆盖率扫描：真库当下 12% ⇒ 如果 `record_access` 接线后覆盖率上升，增益会怎样。"""

METHOD_CUR = "现状: 常数 confidence=1.0"
METHOD_NULL = "空模型: 随机分数"
METHOD_ORACLE = "上限: 直接用真值"
METHOD_DERIVED = "派生规则(交付②)"


# ------------------------------------------------------------------ 指标（与 impl/baseline.py 同源）

def _pools(n: int, q: int, p: int, rng: np.random.Generator) -> List[np.ndarray]:
    """q 个查询，每个一个 p 元候选池，**顺序随机摆放**。"""
    out = []
    for _ in range(q):
        out.append(rng.permutation(rng.choice(n, size=p, replace=False)))
    return out


def pool_metrics(score: np.ndarray, rel: np.ndarray, pools: Sequence[np.ndarray],
                 k: int, rng: np.random.Generator) -> Dict[str, float]:
    """按查询取平均。`cov1`/`sel1` 与 s2 同义：

      cov1 = P(真值第 1 名 ∈ 方法 top-k)      —— 「有没有把它生成/召回出来」
      sel1 = P(方法第 1 名 == 真值第 1 名)     —— 「选中的是不是它」
    ⚠️ 两个数必须同时报：只报一个会把结论报反。
    """
    disc = 1.0 / np.log2(np.arange(2, k + 2))
    ndcgs, rrs, hits, cov1s, sel1s, sel1_cov = [], [], [], [], [], []
    for pool in pools:
        s = score[pool] + rng.random(pool.size) * 1e-12   # 随机拆并列（摆放随机化的一部分）
        r = rel[pool]
        order = np.argsort(-s, kind="stable")
        top = order[:k]
        best = int(np.argmax(r))

        gains = np.power(2.0, r[top]) - 1.0
        dcg = float((gains * disc[: top.size]).sum())
        ideal = np.sort(r)[::-1][:k]
        idcg = float(((np.power(2.0, ideal) - 1.0) * disc[: ideal.size]).sum())
        ndcgs.append(dcg / idcg if idcg > 0 else float("nan"))

        rrs.append(1.0 / (int(np.flatnonzero(order == best)[0]) + 1))
        true_top = set(np.argsort(-r, kind="stable")[:k].tolist())
        hits.append(len(true_top & set(top.tolist())) / float(k))

        covered = best in set(top.tolist())
        cov1s.append(1.0 if covered else 0.0)
        sel1s.append(1.0 if int(order[0]) == best else 0.0)
        if covered:
            sel1_cov.append(1.0 if int(order[0]) == best else 0.0)

    return {
        "ndcg": float(np.mean(ndcgs)), "mrr": float(np.mean(rrs)), "hit": float(np.mean(hits)),
        "cov1": float(np.mean(cov1s)), "sel1": float(np.mean(sel1s)),
        "sel1_cov": float(np.mean(sel1_cov)) if sel1_cov else float("nan"),
    }


def run_reps(snap: Dict[str, object], kappa: float, cover: float, n_rep: int = N_REP,
             seed0: int = 0, sigma_sim: float = SIGMA_SIM
             ) -> Tuple[Dict[str, Dict[str, float]], Dict[str, Dict[str, List[float]]]]:
    """n_rep 次重复（每次换样本种子与摆放种子）。

    返回 (逐方法均值, 逐方法逐次原始值)。**原始值必须一起返回** —— 配对检验要用它，
    而且分辨率必须按"重复次数"算，不能按查询条数算（同一 rep 内 184 个查询共用同一条分数向量，
    彼此高度相关；把 184 当独立样本会把分辨带算小 4 倍）。
    """
    per: Dict[str, Dict[str, List[float]]] = {}
    for rep in range(n_rep):
        inst: Instance = make_instance(snap, seed=seed0 + rep, kappa=kappa, cover=cover,
                                       sigma_sim=sigma_sim)
        rng = np.random.default_rng(10_000 + rep)
        pools = _pools(inst.n, inst.n, POOL, rng)
        for name, sc in inst.scores.items():
            m = pool_metrics(np.asarray(sc, dtype=np.float64), inst.rel_star, pools, K, rng)
            slot = per.setdefault(name, {kk: [] for kk in m})
            for kk, vv in m.items():
                slot[kk].append(vv)
    return {name: {kk: float(np.mean(vv)) for kk, vv in d.items()} for name, d in per.items()}, per


def _ms(vals: Sequence[float]) -> Tuple[float, float]:
    a = np.asarray([v for v in vals if v == v], dtype=np.float64)
    if a.size == 0:
        return float("nan"), float("nan")
    return float(a.mean()), float(a.std(ddof=1)) if a.size > 1 else 0.0


def sign_test_p(diffs: Sequence[float]) -> float:
    """配对符号检验（精确、无分布假设）：双侧 p。

    为什么不用 t 检验：重复次数只有几十，且差值分布未知；符号检验只用到"方向"，最保守也最稳。
    ⚠️ 它**不看幅度** —— 所以幅度（均值差）必须一起报。
    """
    from math import comb
    d = [x for x in diffs if x == x and x != 0.0]
    n = len(d)
    if n == 0:
        return 1.0
    pos = sum(1 for x in d if x > 0)
    k = max(pos, n - pos)
    tail = sum(comb(n, i) for i in range(k, n + 1)) / (2 ** n)
    return float(min(1.0, 2.0 * tail))


def paired(per: Dict[str, Dict[str, List[float]]], a: str, b: str,
           metric: str) -> Tuple[float, float, float]:
    """配对差 (a − b)：返回 (均值差, 差值 sd, 符号检验 p)。"""
    da = per[a][metric]
    db = per[b][metric]
    diffs = [x - y for x, y in zip(da, db) if x == x and y == y]
    mean, sd = _ms(diffs)
    return mean, sd, sign_test_p(diffs)


# ------------------------------------------------------------------ 预登记判据

CRITERIA: Dict[str, str] = {
    "C1": "对照探针成立（判据可解释的前提）：`空模型: 随机分数` 落在机会水平（cov1≈k/P, sel1≈1/P），"
          "且 `上限: 直接用真值` 显著高于 `现状`",
    "C2": "靶子：在预登记 κ=0.5 下，`派生规则` 的 hit@5 / cov1 显著优于 `现状`（配对符号检验 p<0.05）",
    "C3": "反恒真：κ=0（痕迹与真值无关 = 真库当下的可辩护假设）时，`派生规则` 相对 `现状` **必须无显著增益**",
    "C4": "break-even：找出使 `派生规则` 首次显著优于 `现状` 的最小 κ，并报出它相对真库覆盖率的位置",
    "C5": "覆盖率是关键变量：在 κ=KAPPA_REF 下扫覆盖 12%→100%，报出增益显著所需的最小覆盖",
    "C6": "coverage 与 selection 两个数**同时**给，并报各自在 n 下的分辨力（SE）",
    "C7": "摆放随机化：`空模型: 随机分数` 与解析机会水平一致（无「永远选左边」式恒绿）",
}

FALSIFY: Dict[str, str] = {
    "C2": "若 κ=1（痕迹完美编码真值）下 `派生规则` 仍不优于 `现状` ⇒ 派生规则/乘法形式本身有问题，靶子不成立",
    "C3": "若 κ=0 下 `派生规则` 就显著优于 `现状` ⇒ 评估有泄漏（恒绿判据），本轮所有结论作废",
}


def verdicts(per_ref: Dict[str, Dict[str, List[float]]], reps: int,
             kappa_sweep: Dict[float, Tuple[float, float, float]],
             cover_sweep: Dict[float, Tuple[float, float, float]]) -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    chance_cov, chance_sel = K / POOL, 1.0 / POOL

    # C1
    null_cov = per_ref[METHOD_NULL]["cov1"]
    oracle_cov = per_ref[METHOD_ORACLE]["cov1"]
    cur_cov = per_ref[METHOD_CUR]["cov1"]
    d_o, _, p_o = paired(per_ref, METHOD_ORACLE, METHOD_CUR, "hit")
    ok_null = abs(np.mean(null_cov) - chance_cov) < 0.03
    ok_c1 = bool(ok_null and p_o < 0.05 and d_o > 0)
    out.append(("C1", "通过" if ok_c1 else "未通过",
                f"随机探针 cov1={np.mean(null_cov):.4f}（机会={chance_cov:.4f}）{'✓' if ok_null else '✗'}"
                f" | 上限−现状 hit 差={d_o:+.4f} p={p_o:.4g} {'✓' if p_o < 0.05 else '✗'}"))

    # C2 / C3
    d_hit, sd_hit, p_hit = paired(per_ref, METHOD_DERIVED, METHOD_CUR, "hit")
    d_cov, _, p_cov = paired(per_ref, METHOD_DERIVED, METHOD_CUR, "cov1")
    ok2 = bool(p_hit < 0.05 and d_hit > 0 and p_cov < 0.05 and d_cov > 0)
    out.append(("C2", "通过" if ok2 else "未通过",
                f"κ={KAPPA_REF}: Δhit={d_hit:+.4f}±{sd_hit:.4f} p={p_hit:.4g}"
                f" | Δcov1={d_cov:+.4f} p={p_cov:.4g}"))
    out.append(("C3", "见 κ=0 行" if 0.0 in kappa_sweep else "未判",
                "κ=0 的配对差见下表（须不显著）"))

    # C4
    be = None
    for kap in sorted(kappa_sweep):
        m, _s, p = kappa_sweep[kap]
        if p < 0.05 and m > 0:
            be = kap
            break
    out.append(("C4", "已测" if be is not None else "未测到",
                f"break-even κ* = {be if be is not None else '扫描区间内无（κ≤1 都不显著）'}"
                f" | 真库覆盖 {COVER_REAL:.4f}"))

    # C5
    be_c = None
    for cv in sorted(cover_sweep):
        m, _s, p = cover_sweep[cv]
        if p < 0.05 and m > 0:
            be_c = cv
            break
    out.append(("C5", "已测" if be_c is not None else "未测到",
                f"覆盖 break-even = {be_c if be_c is not None else '扫描区间内无'}"
                f"（真库当下 = {COVER_REAL:.4f}）"))

    # C6
    sel_vals = per_ref[METHOD_DERIVED]["sel1"]
    cov_vals = per_ref[METHOD_DERIVED]["cov1"]
    _, se_sel = _ms(sel_vals)
    _, se_cov = _ms(cov_vals)
    n_rep = len([v for v in cov_vals if v == v])
    band_cov = 1.96 * se_cov / max(1.0, np.sqrt(n_rep))
    band_sel = 1.96 * se_sel / max(1.0, np.sqrt(n_rep))
    out.append(("C6", "通过",
                f"派生规则 cov1={np.mean(cov_vals):.4f} 与 sel1={np.mean(sel_vals):.4f} 并排给出；"
                f"重复 {n_rep} 次 ⇒ 95% 分辨带（按**重复次数**算，不按查询条数）："
                f"cov1 ±{band_cov:.4f}、sel1 ±{band_sel:.4f}"))

    # C7
    null_sel = np.mean(per_ref[METHOD_NULL]["sel1"])
    ok7 = abs(null_sel - chance_sel) < 0.02
    out.append(("C7", "通过" if ok7 else "未通过",
                f"随机探针 sel1={null_sel:.4f}（机会={chance_sel:.4f}）{'✓' if ok7 else '✗'}"))
    return out


# ------------------------------------------------------------------ CLI

def main() -> None:
    ap = ArgumentParser(description="s3.3 离线复刻排序评估")
    ap.add_argument("--reps", type=int, default=N_REP)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    snap = load_snapshot()
    print("=" * 104)
    print(f"social_rel · s3 离线复刻 | 真库形状 {snap['n_relations']} 关系 / {snap['n_subjects']} 主体"
          f" | k={K} 池={POOL} 重复={args.reps} | σ_sim={SIGMA_SIM} | α={ALPHA_DEFAULT}")
    print("=" * 104)
    print_expressiveness(snap)

    print()
    print(f"【参考点 κ={KAPPA_REF} · 覆盖=真库 {COVER_REAL:.4f}】"
          f"（候选池随机摆放；cov1 与 sel1 必须同时看）")
    hdr = (f"  {'方法':<26} {'nDCG@5':>8} {'MRR':>7} {'hit@5':>7} {'cov1':>7} {'sel1':>7} {'sel1|cov':>9}")
    print(hdr)
    means, per_ref = run_reps(snap, KAPPA_REF, COVER_REAL, n_rep=args.reps, seed0=args.seed)
    for name in (METHOD_CUR, METHOD_NULL, "支撑度 only", "last_reinforced only",
                 METHOD_DERIVED, METHOD_ORACLE):
        m = means[name]
        print(f"  {name:<26} {m['ndcg']:>8.4f} {m['mrr']:>7.4f} {m['hit']:>7.4f} "
              f"{m['cov1']:>7.4f} {m['sel1']:>7.4f} {m['sel1_cov']:>9.4f}")
    print(f"  机会水平（解析）：cov1 = k/P = {K / POOL:.4f} · sel1 = 1/P = {1 / POOL:.4f}")

    print()
    print("【通道归因】派生规则用了两条通道（时效 + 支撑度）—— 合起来到底有没有超过**较好的那一条**？")
    print(f"  {'对比':<34} {'Δhit@5':>10} {'p':>10}   {'Δcov1':>10} {'p':>10}")
    for a, b in ((METHOD_DERIVED, "支撑度 only"), (METHOD_DERIVED, "last_reinforced only"),
                 ("支撑度 only", METHOD_CUR), ("last_reinforced only", METHOD_CUR)):
        dh, _, ph = paired(per_ref, a, b, "hit")
        dc, _, pc = paired(per_ref, a, b, "cov1")
        print(f"  {a + ' − ' + b:<34} {dh:>+10.4f} {ph:>10.4g}   {dc:>+10.4f} {pc:>10.4g}")
    print("  读法：前两行**不显著** ⇒ 「把两个信号合起来」没有实测增益，简单规则（单通道）就够。")

    print()
    print("【配对差：派生规则 − 现状】(同一批样本与候选池 ⇒ 配对；符号检验为精确双侧)")
    print(f"  {'指标':<10} {'均值差':>10} {'差值 sd':>10} {'符号检验 p':>12}")
    for metric in ("ndcg", "mrr", "hit", "cov1", "sel1"):
        d, s, p = paired(per_ref, METHOD_DERIVED, METHOD_CUR, metric)
        print(f"  {metric:<10} {d:>+10.4f} {s:>10.4f} {p:>12.4g}")

    print()
    print("【κ 扫描】痕迹与真值的耦合 ⇒ 派生规则相对现状的增益（配对 hit@5 差）")
    print("  ⚠️ κ 本身不直观 —— 同时给出它的**可解释等价**：ρ(痕迹通道, 真值)（8 个种子的均值）")
    print(f"  {'κ':>6} {'ρ(痕迹,真值)':>13} {'Δhit@5':>10} {'p':>10}   {'Δcov1':>10} {'p':>10}")
    kappa_sweep: Dict[float, Tuple[float, float, float]] = {}
    per_k0: Dict[str, Dict[str, List[float]]] = {}
    for kap in KAPPA_SWEEP:
        _m, pk = run_reps(snap, kap, COVER_REAL, n_rep=args.reps, seed0=args.seed)
        rho_k = float(np.mean([_spearman(make_instance(snap, seed=args.seed + j, kappa=kap).t_rec,
                                         make_instance(snap, seed=args.seed + j, kappa=kap).rel_star)
                               for j in range(8)]))
        dh, _, ph = paired(pk, METHOD_DERIVED, METHOD_CUR, "hit")
        dc, _, pc = paired(pk, METHOD_DERIVED, METHOD_CUR, "cov1")
        kappa_sweep[kap] = (dh, 0.0, ph)
        print(f"  {kap:>6.2f} {rho_k:>+13.3f} {dh:>+10.4f} {ph:>10.4g}   {dc:>+10.4f} {pc:>10.4g}")
        if abs(kap) < 1e-12:
            per_k0 = pk

    print()
    print(f"【覆盖扫描】κ={KAPPA_REF} 固定，痕迹覆盖率 12% → 100%（模拟 `record_access` 接线后的情形）")
    print(f"  {'覆盖':>8} {'条数':>6} {'Δhit@5':>10} {'p':>10}   {'Δcov1':>10} {'p':>10}")
    cover_sweep: Dict[float, Tuple[float, float, float]] = {}
    for cv in COVER_SWEEP:
        _m, pcv = run_reps(snap, KAPPA_REF, cv, n_rep=args.reps, seed0=args.seed)
        dh, _, ph = paired(pcv, METHOD_DERIVED, METHOD_CUR, "hit")
        dc, _, pcc = paired(pcv, METHOD_DERIVED, METHOD_CUR, "cov1")
        cover_sweep[cv] = (dh, 0.0, ph)
        print(f"  {cv:>8.4f} {int(round(cv * snap['n_relations'])):>6} {dh:>+10.4f} {ph:>10.4g}"
              f"   {dc:>+10.4f} {pcc:>10.4g}")

    print()
    print("=" * 104)
    print("【预登记判据 · 机械判定】")
    for cid, text in CRITERIA.items():
        print(f"  {cid}  {text}")
    for key, text in FALSIFY.items():
        print(f"  证伪 {key}：{text}")
    print("-" * 104)
    # C3 用 κ=0 那一行单独判 —— "无增益"与"**有害**"是两种不同的结果，都要能报出来
    d0, s0, p0 = paired(per_k0, METHOD_DERIVED, METHOD_CUR, "hit")
    for cid, status, ev in verdicts(per_ref, args.reps, kappa_sweep, cover_sweep):
        if cid == "C3":
            if p0 < 0.05 and d0 > 0:
                status = "未通过"
                ev = f"κ=0: Δhit={d0:+.4f} p={p0:.4g} ⇒ 竟然有增益 ✗（指标泄漏，本轮结论作废）"
            elif p0 < 0.05 and d0 < 0:
                status = "通过"
                ev = (f"κ=0: Δhit={d0:+.4f}±{s0:.4f} p={p0:.4g} ⇒ **显著有害**"
                      f"（痕迹无信息时接线会**主动降低**排序质量）✓")
            else:
                status = "通过"
                ev = f"κ=0: Δhit={d0:+.4f}±{s0:.4f} p={p0:.4g} ⇒ 无显著差异 ✓"
        mark = ("✓" if status == "通过" else
                ("—" if status in ("已测", "未判", "未测到") else "✗"))
        print(f"  {cid:<4} {mark} {status}    {ev}")


if __name__ == "__main__":
    main()
