# -*- coding: utf-8 -*-
"""social_rel · s2.2 —— 最小学习循环（两路对照 + 归因）

机制**照抄 WB 那条线的定案**（`snn_behavior/NOTES.md` 的 exp3e 两节，只读引用）：
  ⭐ 「加强**该动的那位**（+1）」= **发动机**（决定能否学会）
  ⭐ 「per-边 cap / 稳态」      = **守门人**（决定"整体推高"压不压得住）
  ⭐ 「只知对错、不知该往哪边」= **学不动**（纯奖励型更新在临界点自锁）

⚠️ 但"哪条是发动机"的**分界线已被改判**（lead 2026-09-27 通报，证伪者独立复跑）：
   **分界线不是"用不用标签"，而是"信号里有没有方向信息"**。
   ⇒ 本文件的臂按这个改判重排（见 `MODES` 与 `CRITERIA`）；两路对照保留，
     它的价值变成「**方向信息 vs 自选择偏差**」的对照。

世界的两路（学习者能看见什么）：
    freq  = 只看得见「这条边被互动了几次」（与 w* 无关）
    pref  = 看得见每次互动的 valence（±1，唯一携带 w* 的通道）

更新规则（每条对应一种"信号来源"）：
    hebbian   —— 强化**外部记录到的那条**（无标签、无方向）        ← freq_passive 族
    freq_self —— 强化**自己选中的那条**（无标签、自选择偏差）      ← freq_active 族
    boostonly —— 只加强**标签说该动的那条**（标签=方向）
    contrast  —— 加强该动的、削弱不该动的（标签=方向）
    selected  —— 只用**标量对错**：削弱自己的头号选择（用标签，但**没有方向**）

守门人（homeo，三臂归因）：
    off  = 纯累积，不每步处理（终态按现实约束裁到 [0, cap]）
    cap  = 只每步硬封顶（拆开来看"封顶"自己能不能当守门人）
    leak = 每步泄漏回基线 + 硬封顶（稳态；**申报值 LEAK_DEFAULT**，扫描见归因表）

⚠️ 第四维：**增量 `lr`**。WB 的「+1」是**无量纲**的说法，其含义取决于权重量程。
   本世界量程 = [w0, cap]（宽 0.7），而一条边的累积量可达 ±max(n_e)。
   ⇒ 默认按**数据导出的唯一规则**缩放：`lr = (cap − w0) / max(n_e)`（见 `resolve_lr`）。
   照搬字面 `+1` 的后果见 `--literal-plus-one`：那是量纲事故，不是实验结论。

用法（全部秒级）：
  python learn.py                 # 全流程：自检 → 零带 → 上限 → 主网格 → 归因 → 预登记判定
  python learn.py --no-extra      # 只跑主网格（跳过归因扫描与 anti 对照臂）
  python learn.py --seeds 5       # 追加多种子稳健性
  python learn.py --literal-plus-one   # 追加"字面 +1"那一档（量纲事故，附命令可复现）
"""

from argparse import ArgumentParser
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from gen_synth import N_EDGES_DEFAULT, N_PEOPLE_DEFAULT, World, event_stream, make_world, spearman
from baseline import (
    BASELINES,
    K_DEFAULT,
    N_PERM_DEFAULT,
    baseline_score,
    ceiling_rows,
    data_check,
    format_header,
    format_row,
    metric_row,
    pad_display,
)

# ------------------------------------------------------------------ 冻结的超参

ROUTES: Tuple[str, ...] = ("freq", "pref")
MODES: Tuple[str, ...] = ("hebbian", "freq_self", "boostonly", "contrast", "selected")
HOMEOS: Tuple[str, ...] = ("off", "cap", "leak")

ROUTE_MODES: Dict[str, Tuple[str, ...]] = {
    # freq 路不暴露 valence ⇒ 用得上标签的三条（boostonly / contrast / selected）在这条路上不可用
    "freq": ("hebbian", "freq_self"),
    "pref": ("hebbian", "freq_self", "boostonly", "contrast", "selected"),
}

NO_DIRECTION_MODES: Tuple[str, ...] = ("hebbian", "freq_self", "selected")
"""**没有方向信息**的三条臂：hebbian 只数次数；freq_self 带自选择偏差；selected 只有标量对错。"""

WITH_DIRECTION_MODES: Tuple[str, ...] = ("boostonly", "contrast")
"""**有方向信息**的两条臂：标签指明了"该动的是哪位"。"""

LEAK_DEFAULT = 24.0
"""稳态强度（**申报值**）：整条流上累计泄漏 e^{−LEAK}；每条边的稳态偏移 ≈ (净 +1 次数)/LEAK。

⚠️ 预先写定，不是从结果里挑的。敏感性见归因表（扫描区间 leak ∈ 6..1200，跨 200×）。
"""

CAP_DEFAULT = 1.0
"""硬封顶 = 现实现实约束：`unified_profile_service.py:115` 是 `min(1.0, max(0.0, edge.weight))`。"""

LEAK_SWEEP: Tuple[float, ...] = (6.0, 24.0, 60.0, 120.0, 300.0, 600.0, 1200.0)

ALPHA = 0.05


def resolve_lr(world: World, cap: float = CAP_DEFAULT,
               override: Optional[float] = None) -> float:
    """数据导出、**零自由度**的增量：`lr = (cap − w0) / max(n_e)`。

    让"某条边在整条流上每一次都是 +1"这种最极端的情况**刚好**落进量程
    ⇒ 给定世界，lr 唯一确定，没有任何可调空间。

    ⚠️ 为什么必须缩放（2026-09-27 实测，一次真实的**设计缺陷**，不是结论）：
       照搬字面 `+1` 时，量程宽只有 0.7，而一条边累积可达 ±16
       ⇒ **第一条事件就把权重打顶**，此后 `leak` 再强也来不及把它拉回来。
       实测后果：`leak` 臂的 ρ ≡ 0.3227，且与 leak 强度**完全无关**
       （leak=6/12/24/48 之间 ρ(w) = **1.000000**，排序逐元素相同）——
       因为权重被钉死在"首/末一次事件"的价上，**跨事件累积从未发生**。
       那是量纲事故；标定正确的 lr 下同一批数字完全不同（见 RESULTS.md 对照表）。
    """
    if override is not None:
        return float(override)
    return (cap - world.w0) / float(max(1, int(world.n_events.max())))


# ------------------------------------------------------------------ 学习循环

@dataclass
class RunResult:
    mode: str
    route: str
    homeo: str
    weights: np.ndarray
    mean_preclip: float
    """封顶**之前**的均值偏移 —— 用来分辨"整体推高"是真的发生了还是被裁掉了。"""
    n_updates: int = 0
    """真正改动了权重的步数（`boostonly` 遇到负标签时不动 ⇒ 会 < T）。"""

    def label(self) -> str:
        return f"{self.route}/{self.mode}/{self.homeo}"


def run_learner(world: World, mode: str, route: str = "pref", homeo: str = "leak",
                seed: int = 0, *, lr: Optional[float] = None, leak: float = LEAK_DEFAULT,
                cap: float = CAP_DEFAULT, stream_seed: int = 0,
                init_tie_seed: Optional[int] = None) -> RunResult:
    """跑一条学习循环。同一个 (seed, stream_seed, 超参) ⇒ 逐字节可复现。

    `init_tie_seed` 非 None 时给初始权重加 1e-9 抖动，**只用来随机化 argmax 的初始并列**
    （`freq_self` / `selected` 的起点）——自选择臂的稳定性要靠它才能测。
    """
    if route not in ROUTES:
        raise ValueError(f"route 必须是 {ROUTES} 之一，收到 {route!r}")
    if mode not in MODES:
        raise ValueError(f"mode 必须是 {MODES} 之一，收到 {mode!r}")
    if homeo not in HOMEOS:
        raise ValueError(f"homeo 必须是 {HOMEOS} 之一，收到 {homeo!r}")
    if mode not in ROUTE_MODES[route]:
        raise ValueError(
            f"路 {route!r} 不暴露 valence ⇒ 更新规则 {mode!r} 不可用（可用：{ROUTE_MODES[route]}）"
        )

    edge_idx, valence = event_stream(world, seed=stream_seed)
    if route == "freq":
        valence = None  # ← 这就是"两路"的全部差别：freq 路看不见标签

    lr_eff = resolve_lr(world, cap=cap, override=lr)
    n_steps = int(edge_idx.size)
    lam = (leak / n_steps) if homeo == "leak" else 0.0

    w = np.full(world.n_edges, world.w0, dtype=np.float64)
    if init_tie_seed is not None:
        w = w + np.random.default_rng(init_tie_seed).random(world.n_edges) * 1e-9

    n_updates = 0
    for t in range(n_steps):
        e = int(edge_idx[t])
        if mode == "hebbian":
            # 强化**外部记录到的那条** —— 不看 valence，也没有方向
            w[e] += lr_eff
            n_updates += 1
        elif mode == "freq_self":
            # 【自选择偏差臂】强化**自己选中的那条**：频次记录的是自己的动作
            u = int(world.edges[e, 0])
            cand = world.incidence[u]
            chosen = int(cand[int(np.argmax(w[cand]))])
            w[chosen] += lr_eff
            n_updates += 1
        elif mode == "boostonly":
            # 只加强**标签说该动的那条**（标签 = 方向）
            if valence[t] > 0:
                w[e] += lr_eff
                n_updates += 1
        elif mode == "contrast":
            w[e] += lr_eff if valence[t] > 0 else -lr_eff
            n_updates += 1
        else:  # selected —— 只有标量对错，没有"该给谁 +1"
            u = int(world.edges[e, 0])
            cand = world.incidence[u]
            chosen = int(cand[int(np.argmax(w[cand]))])
            if valence[t] < 0:
                w[chosen] -= lr_eff
                n_updates += 1

        if lam:
            w -= lam * (w - world.w0)  # 稳态：每步把每条边拉回基线（与自身事件无关）
        if homeo in ("cap", "leak"):
            np.clip(w, 0.0, cap, out=w)

    mean_preclip = float(w.mean())
    np.clip(w, 0.0, cap, out=w)  # off 臂：不每步裁，但现实使用前一定裁（见 CAP_DEFAULT）
    return RunResult(mode=mode, route=route, homeo=homeo, weights=w,
                     mean_preclip=mean_preclip, n_updates=n_updates)


# ------------------------------------------------------------------ 学到的权重体检

def delta_profile(w: np.ndarray, world: World, q: float = 0.25,
                  cap: float = CAP_DEFAULT) -> Dict[str, float]:
    """区分度体检：高 w* 边 vs 低 w* 边的权重位移。

    `margin` 是 WB 那条线「无关 Δ 不减」在本世界的可证伪等价物：
      · 不区分（"反正都涨"）⇒ margin ≈ 0（两条边一起被推高）
      · 真的学会了区分       ⇒ margin 明显 > 0（强的上、弱的下）
    """
    arr = np.asarray(w, dtype=np.float64)
    d = arr - world.w0
    ws = world.w_star
    hi = ws >= np.quantile(ws, 1.0 - q)
    lo = ws <= np.quantile(ws, q)
    d_hi = float(d[hi].mean())
    d_lo = float(d[lo].mean())
    return {
        "d_hi": d_hi,
        "d_lo": d_lo,
        "margin": d_hi - d_lo,
        "inflation": float(arr.mean() - world.w0),
        "sat_frac": float(np.mean(arr >= cap - 1e-9)),
    }


def evaluate(result: RunResult, world: World, k: int = K_DEFAULT,
             n_perm: int = N_PERM_DEFAULT, perm_seed: int = 0) -> Dict[str, float]:
    row = metric_row(result.weights, world, k=k, n_perm=n_perm, perm_seed=perm_seed)
    row.update(delta_profile(result.weights, world))
    row["mean_preclip"] = result.mean_preclip
    row["n_updates"] = float(result.n_updates)
    row["uniq"] = float(np.unique(result.weights).size)
    return row


# ------------------------------------------------------------------ 零带（未干预基线的经验分布）

BAND_METRICS: Tuple[str, ...] = ("rho", "ndcg", "mrr", "hit", "cov1", "sel1")


def _mean_sd(vals: Sequence[float]) -> Tuple[float, float]:
    arr = np.asarray([v for v in vals if v == v], dtype=np.float64)
    if arr.size == 0:
        return float("nan"), float("nan")
    sd = float(arr.std(ddof=1)) if arr.size > 1 else 0.0
    return float(arr.mean()), sd


def null_band(world: World, n_ens: int = 200, k: int = K_DEFAULT,
              seed0: int = 0) -> Dict[str, Dict[str, float]]:
    """把"内禀随机"的基线跑 n_ens 次 ⇒ 均值 ± 标准差（= 经验零带）。

    ⚠️ 单次抽样不够：240 边时实测 `random` 的 MRR = 0.2733，
       而 `recency` = 0.3244 —— 0.05 的差**全部来自抽样**，不是方法。
       没有零带，"比基线好"就没有判据（`coding-discipline` §42）。
    """
    out: Dict[str, Dict[str, float]] = {}
    for name in BASELINES:
        per: Dict[str, List[float]] = {m: [] for m in BAND_METRICS}
        for s in range(n_ens):
            row = metric_row(baseline_score(name, world, seed0 + s), world,
                             k=k, n_perm=0, perm_seed=0, tie_seeds=(seed0 + s,))
            for m in BAND_METRICS:
                per[m].append(row[m])
        flat: Dict[str, float] = {}
        for m in BAND_METRICS:
            mean, sd = _mean_sd(per[m])
            flat[f"{m}_mean"], flat[f"{m}_sd"] = mean, sd
        out[name] = flat
    return out


def format_band_row(name: str, b: Dict[str, float]) -> str:
    def ms(key: str, spec: str) -> str:
        mean, sd = b[f"{key}_mean"], b[f"{key}_sd"]
        if mean != mean:
            return "n/a"
        return f"{format(mean, spec)}±{format(sd, spec)}"

    return " ".join((
        pad_display(name, 26),
        pad_display(ms("rho", "+.3f"), 14, "r"),
        pad_display(ms("ndcg", ".3f"), 12, "r"),
        pad_display(ms("mrr", ".3f"), 12, "r"),
        pad_display(ms("hit", ".3f"), 12, "r"),
        pad_display(ms("cov1", ".3f"), 12, "r"),
        pad_display(ms("sel1", ".3f"), 12, "r"),
    ))


# ------------------------------------------------------------------ 网格

def grid(world: World, k: int = K_DEFAULT, n_perm: int = N_PERM_DEFAULT,
         perm_seed: int = 0, leak: float = LEAK_DEFAULT, lr: Optional[float] = None,
         homeos: Sequence[str] = HOMEOS) -> Dict[str, Dict[str, float]]:
    rows: Dict[str, Dict[str, float]] = {}
    for route in ROUTES:
        for mode in ROUTE_MODES[route]:
            for homeo in homeos:
                res = run_learner(world, mode=mode, route=route, homeo=homeo,
                                  leak=leak, lr=lr, stream_seed=0)
                rows[res.label()] = evaluate(res, world, k=k, n_perm=n_perm,
                                             perm_seed=perm_seed)
    return rows


def unlabeled_pair_consistency(world: World, leak: float = LEAK_DEFAULT,
                               lr: Optional[float] = None) -> bool:
    """自检：`hebbian` / `freq_self` 都不看 valence ⇒ 两路上必须**逐元素相同**。"""
    ok = True
    for mode in ("hebbian", "freq_self"):
        a = run_learner(world, mode, "freq", "leak", leak=leak, lr=lr).weights
        b = run_learner(world, mode, "pref", "leak", leak=leak, lr=lr).weights
        ok &= bool(np.array_equal(a, b))
    return ok


# ------------------------------------------------------------------ 预登记判据（机械判定）

CRITERIA: Dict[str, str] = {
    "H1a": "显式路 + 有方向的标签型更新（boostonly / contrast，homeo=leak）的 ρ 置换 p < 0.05 且 ρ > 基线带 q95",
    "H1b": "稳态守门人（WB 原话的两半）：(i) 压住整体推高 —— hebbian 的封顶前均值位移 leak ≤ 0.5×off；"
           "(ii) 不影响学会与否 —— contrast / boostonly 的 ρ_leak ≥ ρ_off − 0.05",
    "H1c": "区分度：contrast 的 margin（Δ高w* − Δ低w*）> boostonly 的 margin",
    "H2a": "⭐ **分界线是「信号里有没有方向信息」，不是「用不用标签」**："
           "有方向的 2 臂（boostonly / contrast）ρ 显著 > 0；无方向的 3 臂（hebbian / freq_self / selected）p > 0.05",
    "H2b": "证伪「标签是分界线」：`selected` **用了标签**（标量对错）却学不动 ⇒ 用标签不足以学会",
    "H2c": "证伪「纯频次一律学不动」：`freq_link=anti` 下 hebbian 的 ρ **显著**（方向反了也算用得上方向信息）",
    "H2d": "自选择臂 `freq_self` 学不动，且结果**跨初始并列种子不稳定**（自选择偏差的签名）",
    "E1":  "评估硬约束一（lead 2026-09-27）：coverage 与 selection **必须同时报**（本表 cov1 / sel1 / sel1|cov 三列并排）",
    "E2":  "评估硬约束二：候选摆放必须随机化 ⇒ 恒定分数探针（`fixed` 基线）必须落在**机会水平**，"
           "而不是「永远选左边 = 1.0000」",
}

FALSIFY: Dict[str, str] = {
    "H1": "若标签型更新的 ρ 与无方向臂无显著差 ⇒ WB 的机制组合不迁移 ⇒ H1 不成立",
    "H2": "若 freq_self 或 selected 的 ρ 显著 > 0（它们没有方向信息）⇒ H2 被证伪；"
          "或若 boostonly/contrast 与 hebbian 无差异 ⇒「方向信息」也解释不了",
}


def verdicts(rows: Dict[str, Dict[str, float]], anti_rows: Dict[str, Dict[str, float]],
             band: Dict[str, Dict[str, float]], self_rho: Sequence[float]) -> List[Tuple[str, str, str]]:
    """按预登记判据机械判定，返回 [(判据, 通过?, 证据串)]。"""
    out: List[Tuple[str, str, str]] = []
    q95 = _g(rows, "pref/contrast/leak", "q95")
    chance_hit = band["random"]["hit_mean"]

    # H1a
    ev, ok_a = [], True
    for m in WITH_DIRECTION_MODES:
        rho, p = _g(rows, f"pref/{m}/leak", "rho"), _g(rows, f"pref/{m}/leak", "p")
        good = (p < ALPHA) and (rho > q95)
        ok_a &= good
        ev.append(f"{m}: ρ={rho:+.4f} p={p:.4f} {'>' if rho > q95 else '≤'} q95={q95:.4f} {'✓' if good else '✗'}")
    out.append(("H1a", "通过" if ok_a else "未通过", " | ".join(ev)))

    # H1b —— WB 原话的两半
    inf_off = _g(rows, "pref/hebbian/off", "mean_preclip") - 0.3
    inf_lk = _g(rows, "pref/hebbian/leak", "mean_preclip") - 0.3
    ok_i = inf_lk <= 0.5 * inf_off
    rho_ev, ok_ii = [], True
    for m in WITH_DIRECTION_MODES:
        ro, rl = _g(rows, f"pref/{m}/off", "rho"), _g(rows, f"pref/{m}/leak", "rho")
        good = rl >= ro - 0.05
        ok_ii &= good
        rho_ev.append(f"{m} ρ off={ro:+.4f}→leak={rl:+.4f} {'✓' if good else '✗'}")
    ok_b = bool(ok_i and ok_ii)
    out.append(("H1b", "通过" if ok_b else "未通过",
                f"(i) 整体推高 hebbian off={inf_off:+.4f} → leak={inf_lk:+.4f}"
                f"（需 ≤ {0.5 * inf_off:+.4f}）{'✓' if ok_i else '✗'}"
                f" | (ii) " + "; ".join(rho_ev)))

    # H1c
    mg_c, mg_b = _g(rows, "pref/contrast/leak", "margin"), _g(rows, "pref/boostonly/leak", "margin")
    out.append(("H1c", "通过" if mg_c > mg_b else "未通过",
                f"margin: contrast={mg_c:+.4f} vs boostonly={mg_b:+.4f}"))

    # H2a
    ev, ok_2a = [], True
    for m in WITH_DIRECTION_MODES:
        p = _g(rows, f"pref/{m}/leak", "p")
        ok_2a &= p < ALPHA
        ev.append(f"有方向 {m}: p={p:.4f}{'✓' if p < ALPHA else '✗'}")
    for key in ("pref/hebbian/leak", "freq/freq_self/leak", "pref/selected/leak"):
        p = _g(rows, key, "p")
        ok_2a &= p > ALPHA
        ev.append(f"无方向 {key.split('/')[1]}: p={p:.4f}{'✓' if p > ALPHA else '✗'}")
    out.append(("H2a", "通过" if ok_2a else "未通过", " | ".join(ev)))

    # H2b
    sp = _g(rows, "pref/selected/leak", "p")
    out.append(("H2b", "通过" if sp > ALPHA else "未通过",
                f"selected 用了标签（标量对错）却 ρ p={sp:.4f} ⇒ "
                f"{'用标签不足以学会 ⇒ 标签不是分界线 ✓' if sp > ALPHA else '竟然学动了 ✗'}"))

    # H2c
    if anti_rows:
        ar, ap = _g(anti_rows, "freq/hebbian/leak", "rho"), _g(anti_rows, "freq/hebbian/leak", "p")
        ok_2c = ap < ALPHA
        out.append(("H2c", "通过" if ok_2c else "未通过",
                    f"anti 世界 hebbian: ρ={ar:+.4f} p={ap:.4f} ⇒ "
                    f"{'频次一旦带方向，同一套更新就能用（哪怕方向是反的）✓' if ok_2c else '仍然不显著 ✗'}"))
    else:
        out.append(("H2c", "未判", "（需要 --no-extra 关闭时无 anti 臂）"))

    # H2d
    if self_rho:
        sd = float(np.std(self_rho, ddof=1)) if len(self_rho) > 1 else 0.0
        ok_2d = abs(float(np.mean(self_rho))) < 0.2 and sd > 0.02
        out.append(("H2d", "通过" if ok_2d else "未通过",
                    f"freq_self 跨初始并列种子: ρ 均值={np.mean(self_rho):+.4f} sd={sd:.4f} "
                    f"（n={len(self_rho)}）⇒ "
                    f"{'学不动且随初始条件漂移（自选择偏差签名）✓' if ok_2d else '看具体数值 ✗'}"))
    else:
        out.append(("H2d", "未判", "（需要 --self-seeds > 1）"))

    # E1 / E2
    sel_lk = _g(rows, "pref/contrast/leak", "sel1")
    cov_lk = _g(rows, "pref/contrast/leak", "cov1")
    out.append(("E1", "通过", f"contrast/leak: cov1={cov_lk:.4f} 与 sel1={sel_lk:.4f} 同时给出"
                             f"（sel1|cov={_g(rows, 'pref/contrast/leak', 'sel1_cov'):.4f}）"))
    fixed_hit = band["fixed"]["hit_mean"]
    ok_e2 = abs(fixed_hit - chance_hit) < 0.05
    out.append(("E2", "通过" if ok_e2 else "未通过",
                f"恒定分数探针（fixed）hit@k={fixed_hit:.4f} vs 机会水平(random)={chance_hit:.4f}"
                f" ⇒ {'没有「永远选左边」式的恒绿判据 ✓' if ok_e2 else '疑似摆放泄漏 ✗'}"))
    return out


def _g(rows: Dict[str, Dict[str, float]], key: str, field: str) -> float:
    return rows[key][field]


# ------------------------------------------------------------------ CLI

def print_rows(title: str, rows: Dict[str, Dict[str, float]]) -> None:
    if title:
        print(title)
    print(format_header())
    for name, row in rows.items():
        print(format_row(name, row))


def print_extra_rows(title: str, rows: Dict[str, Dict[str, float]]) -> None:
    print(title)
    print(" ".join((pad_display("方法", 26), pad_display("margin", 10, "r"),
                    pad_display("Δ高w*", 10, "r"), pad_display("Δ低w*", 10, "r"),
                    pad_display("inflation", 11, "r"), pad_display("封顶前位移", 12, "r"),
                    pad_display("封顶率", 8, "r"), pad_display("不同值", 8, "r"))))
    for name, row in rows.items():
        print(" ".join((pad_display(name, 26),
                        pad_display(f"{row['margin']:+.4f}", 10, "r"),
                        pad_display(f"{row['d_hi']:+.4f}", 10, "r"),
                        pad_display(f"{row['d_lo']:+.4f}", 10, "r"),
                        pad_display(f"{row['inflation']:+.4f}", 11, "r"),
                        pad_display(f"{row['mean_preclip'] - 0.3:+.4f}", 12, "r"),
                        pad_display(f"{row['sat_frac']:.3f}", 8, "r"),
                        pad_display(f"{row['uniq']:.0f}", 8, "r"))))


def main() -> None:
    ap = ArgumentParser(description="social_rel s2.2 最小学习循环")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--people", type=int, default=N_PEOPLE_DEFAULT)
    ap.add_argument("--edges", type=int, default=N_EDGES_DEFAULT)
    ap.add_argument("--k", type=int, default=K_DEFAULT)
    ap.add_argument("--n-perm", type=int, default=N_PERM_DEFAULT)
    ap.add_argument("--leak", type=float, default=LEAK_DEFAULT)
    ap.add_argument("--lr", type=float, default=None, help="默认 None ⇒ 按 resolve_lr 的规则缩放")
    ap.add_argument("--ens", type=int, default=200, help="零带集成次数")
    ap.add_argument("--self-seeds", type=int, default=12, help="自选择臂的初始并列种子数")
    ap.add_argument("--seeds", type=int, default=0, help=">0 时追加多种子稳健性")
    ap.add_argument("--no-extra", action="store_true", help="只跑主网格")
    ap.add_argument("--literal-plus-one", action="store_true",
                    help="追加「字面 +1」那一档（量纲事故，附命令可复现）")
    args = ap.parse_args()

    world = make_world(seed=args.seed, n_people=args.people, n_edges=args.edges)
    lr = resolve_lr(world, override=args.lr)
    print("=" * 108)
    print(f"social_rel · s2 合成对照实验 | seed={args.seed} | {world.n_people} 人 / "
          f"{world.n_edges} 边 / T={world.n_interactions} 事件 | k={args.k} | "
          f"lr={lr:.5f} | leak={args.leak} | n_perm={args.n_perm}")
    print("=" * 108)

    data_check(world, n_perm=args.n_perm, seed=args.seed)
    print()
    print(f"  [自检] hebbian / freq_self 在两路上逐元素相同（都不用标签）⇒ "
          f"{unlabeled_pair_consistency(world, leak=args.leak, lr=args.lr)}")

    print()
    band = null_band(world, n_ens=args.ens, k=args.k, seed0=args.seed)
    print(f"【未干预基线 · 经验零带】跑 {args.ens} 次（均值±标准差）——"
          f"单次抽样不足以判定「比基线好」")
    print(" ".join((pad_display("基线", 26), pad_display("ρ 均值±sd", 14, "r"),
                    pad_display("nDCG@k", 12, "r"), pad_display("MRR", 12, "r"),
                    pad_display("hit@k", 12, "r"), pad_display("cov1", 12, "r"),
                    pad_display("sel1", 12, "r"))))
    for name, b in band.items():
        print(format_band_row(f"基线: {name}", b))

    print()
    print_rows("【信息上限】每个学习者各自的天花板（同一批指标、同一条数据）",
               ceiling_rows(world, k=args.k, n_perm=args.n_perm, perm_seed=args.seed))

    print()
    rows = grid(world, k=args.k, n_perm=args.n_perm, perm_seed=args.seed,
                leak=args.leak, lr=args.lr)
    print_rows("【主网格】路 × 信号来源 × 守门人（对照：同路的 hebbian / 同臂的 off）", rows)

    print()
    print_extra_rows("【区分度体检】Δ = 学习后权重 − 初始 0.3；「封顶前位移」= 整体推高的实测量", rows)

    # 自选择臂的稳定性（H2d）
    self_rho: List[float] = []
    for s in range(args.self_seeds):
        res = run_learner(world, mode="freq_self", route="freq", homeo="leak",
                          leak=args.leak, lr=args.lr, stream_seed=0, init_tie_seed=s)
        self_rho.append(spearman(res.weights, world.w_star))
    print()
    print(f"【自选择臂稳定性】freq_self 换 {args.self_seeds} 个初始并列种子（其余全同）：")
    print("   ρ = " + " ".join(f"{v:+.4f}" for v in self_rho)
          + f"   ⇒ 均值 {np.mean(self_rho):+.4f} sd {np.std(self_rho, ddof=1):.4f}")

    anti_rows: Dict[str, Dict[str, float]] = {}
    if not args.no_extra:
        print()
        sweep: Dict[str, Dict[str, float]] = {}
        for mode in WITH_DIRECTION_MODES + ("hebbian",):
            for lk in LEAK_SWEEP:
                res = run_learner(world, mode=mode, route="pref", homeo="leak",
                                  leak=lk, lr=args.lr, stream_seed=0)
                sweep[f"{mode}/leak={lk:g}"] = evaluate(res, world, k=args.k,
                                                        n_perm=args.n_perm,
                                                        perm_seed=args.seed)
        print_rows("【归因：leak 强度扫描】跨 200× 的稳态强度（对照 = 该臂的 off）", sweep)
        print_extra_rows("【归因：leak 强度扫描 · 区分度】", sweep)

        print()
        anti = make_world(seed=args.seed, n_people=args.people, n_edges=args.edges,
                          freq_link="anti")
        print("【对照臂 freq_link=anti】频次与 w* **完美负秩相关**、标签不变 —— "
              "用来证伪「纯频次一律学不动」")
        data_check(anti, n_perm=args.n_perm, seed=args.seed)
        for route in ROUTES:
            for mode in ROUTE_MODES[route]:
                res = run_learner(anti, mode=mode, route=route, homeo="leak",
                                  leak=args.leak, lr=args.lr, stream_seed=0)
                anti_rows[res.label()] = evaluate(res, anti, k=args.k,
                                                  n_perm=args.n_perm, perm_seed=args.seed)
        print_rows("", anti_rows)

    if args.literal_plus_one:
        print()
        print("【量纲事故档 · 字面 +1（lr=1.0）】⚠️ 不是实验结论，是「增量与量程不匹配」的证据")
        lit: Dict[str, Dict[str, float]] = {}
        for homeo in HOMEOS:
            for mode in ("contrast", "hebbian"):
                res = run_learner(world, mode=mode, route="pref", homeo=homeo,
                                  leak=args.leak, lr=1.0, stream_seed=0)
                lit[f"{mode}/{homeo}(lr=1)"] = evaluate(res, world, k=args.k,
                                                        n_perm=args.n_perm, perm_seed=args.seed)
        print_rows("", lit)
        # 无标度性：字面 +1 下 leak 强度几乎不影响 ρ
        probe = []
        for lk in (6.0, 12.0, 24.0, 48.0):
            res = run_learner(world, mode="contrast", route="pref", homeo="leak",
                              leak=lk, lr=1.0, stream_seed=0)
            probe.append((lk, spearman(res.weights, world.w_star)))
        print("  字面 +1 下 ρ 与 leak 强度无关：" +
              "  ".join(f"leak={lk:g}→ρ={v:+.4f}" for lk, v in probe))

    print()
    print("=" * 108)
    print("【预登记判据 · 机械判定】")
    for cid, text in CRITERIA.items():
        print(f"  {cid:<5s} 判据：{text}")
    for key, text in FALSIFY.items():
        print(f"  {key} 证伪条件：{text}")
    print("-" * 108)
    for cid, status, ev in verdicts(rows, anti_rows, band, self_rho):
        mark = "✓" if status == "通过" else ("—" if status == "未判" else "✗")
        print(f"  {cid:<5s} {mark} {status}    {ev}")

    if args.seeds > 0:
        print()
        print(f"【多种子稳健性】seed = {args.seed} .. {args.seed + args.seeds - 1}")
        tracks = [("pref", "hebbian"), ("freq", "freq_self"), ("pref", "boostonly"),
                  ("pref", "contrast"), ("pref", "selected")]
        head = [pad_display("cell", 20), pad_display("方向信息", 9)]
        head += [pad_display(f"ρ(s={args.seed + i})", 13, "r") for i in range(args.seeds)]
        head += [pad_display("均值±sd", 17, "r")]
        print(" ".join(head))
        for route, mode in tracks:
            vals = []
            for i in range(args.seeds):
                w_i = make_world(seed=args.seed + i, n_people=args.people, n_edges=args.edges)
                res = run_learner(w_i, mode=mode, route=route, homeo="leak",
                                  leak=args.leak, lr=args.lr, stream_seed=0)
                vals.append(spearman(res.weights, w_i.w_star))
            mean, sd = _mean_sd(vals)
            row = [pad_display(f"{route}/{mode}", 20),
                   pad_display("有" if mode in WITH_DIRECTION_MODES else "无", 9)]
            row += [pad_display(f"{v:+.4f}", 13, "r") for v in vals]
            row += [pad_display(f"{mean:+.4f}±{sd:.4f}", 17, "r")]
            print(" ".join(row))


if __name__ == "__main__":
    main()
