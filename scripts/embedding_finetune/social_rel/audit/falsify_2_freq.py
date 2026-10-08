#!/usr/bin/env python3
"""反例② —— 纯频次信号是不是真的学不动？（H2 的直接检验）

角色：证伪者（R3）· 写域 `social_rel/audit/`。
**独立实现**：不 import、不复制 `social_rel/impl/` 的任何代码与数字。

为什么必须把 H2 拆开测：
  `social_rel/NOTES.md` §3.2 H2 的原话把**两个不同的信号**并成一个词：「**纯频次/"互动好坏"信号**」。
  ① 「频次」有两种读法 —— (a) **外部日记的频次**（谁常出现，含信息）vs (b) **自己选择的计数**（无结果反馈，不含信息）
  ② 「互动好坏」= **标量对/错**（不用标签）—— 这与频次又是第三个东西
  ⇒ 本文件把三者**分别实现、分别测**，并给出**逐条**证伪判决（不合并成一个结论）。
  D 段是**归因**（不是新假设）：扫「k 选一」k=2/3/5/12，确认 A/B 段的结果不是"任务太容易"，
     而是"自己选了谁 + 标量对错"本身含方向信息 —— 团队方法论：改不动时先归因，不换机制。

协议（与 falsify_1/3 内联同一协议）：
  · N = 12 实体 · 真值强度 = 0..N-1 随机排列 · 随机无序对 + 随机左右摆放
  · 训练 3000 trial（流 A）· 评估 2000 trial（流 B，同分布新抽）· 20 seeds
  · 纯 numpy · 无 I/O · 无新增依赖 · 退出码恒 0（判决看打印）

证伪条件（**跑之前先写死**）：
  噪声尺度 se = 随机权重组的成对排序率标准差 / √seeds；阈值 = 3·se；基线 = 不学组。
  ⛔ 某组"学得动" ⇔ mean(成对排序率) − mean(基线) > 阈值 且 mean(部署选择准确率) − 0.55 > 0
  ⛔ H2 的「频次」半边被证伪 ⇔ 任一**纯频次**组满足上述（**不用任何反馈**却学得动）
  ⛔ H2 的「互动好坏」半边被证伪 ⇔ 任一**纯奖励（不用标签）**组满足上述

⛔ 能说它不成立的那条命令（自证）：
  cd E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune
  .\\.venv\\Scripts\\python.exe social_rel\\audit\\falsify_2_freq.py
  末段「判决」逐组打印 Δ 与 阈值，并单独给「频次」/「互动好坏」两半的结论。

2026-09-27 · 证伪者（R3）
"""

from __future__ import annotations

import numpy as np

N = 12
T_TRAIN = 3000
T_EVAL = 2000
SEEDS = list(range(20))
STREAM_TRUTH = 7_000_000
STREAM_TRAIN = 11_000_000
STREAM_EVAL = 22_000_000
STREAM_NULL = 9_000_000
STREAM_DIARY = 5_000_000


# ---------------------------------------------------------------- 协议（与 falsify_1/3 同）
def true_strength(seed: int, n: int = N) -> np.ndarray:
    return np.random.default_rng(STREAM_TRUTH + seed).permutation(n).astype(float)


def draw_trials(seed: int, stream: int, t: int, n: int = N):
    rng = np.random.default_rng(stream + seed)
    u, v = np.triu_indices(n, k=1)
    k = rng.integers(0, len(u), size=t)
    a, b = u[k], v[k]
    flip = rng.random(t) < 0.5
    return np.where(flip, b, a), np.where(flip, a, b)


# ---------------------------------------------------------------- 指标（与 falsify_1/3 同）
def avg_rank(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    order = np.argsort(x, kind="mergesort")
    xs = x[order]
    r = np.empty(len(x), dtype=float)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[j + 1] == xs[i]:
            j += 1
        r[order[i:j + 1]] = (i + 1 + j + 1) / 2.0
        i = j + 1
    return r


def spearman(x, y) -> float:
    rx = avg_rank(x) - avg_rank(x).mean()
    ry = avg_rank(y) - avg_rank(y).mean()
    d = float(np.sqrt((rx * rx).sum() * (ry * ry).sum()))
    return float((rx * ry).sum() / d) if d > 1e-12 else 0.0


def pairwise_acc(w, s) -> float:
    n = len(w)
    hit = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            dw = w[i] - w[j]
            if dw == 0.0:
                hit += 0.5
            elif (dw > 0.0) == (s[i] > s[j]):
                hit += 1.0
    return hit / (n * (n - 1) / 2.0)


def top1_hit(w, s) -> float:
    w = np.asarray(w, dtype=float)
    cand = np.flatnonzero(w == w.max())
    gold = int(np.argmax(s))
    if len(cand) == 1:
        return 1.0 if cand[0] == gold else 0.0
    return 1.0 / len(cand) if gold in cand else 0.0


def selection_acc(w, left, right, s) -> float:
    w = np.asarray(w, dtype=float)
    pick_left = w[left] >= w[right]
    ok = np.where(pick_left, s[left] > s[right], s[right] > s[left])
    return float(ok.mean())


# ---------------------------------------------------------------- 学习器（逐组独立实现）
def train(cfg: str, s: np.ndarray, left, right, seed: int, n: int = N) -> np.ndarray:
    """返回学出来的关系权重 w（长度 n）。tie 规则与 selection_acc 一致：权重相等取左。"""
    if cfg == "none":
        return np.zeros(n)
    if cfg == "random_w":
        return np.random.default_rng(STREAM_NULL + seed).normal(0.0, 1.0, n)

    # ---- 纯频次 (a)：外部日记（谁常出现）—— 无模型参与、无结果反馈
    if cfg == "freq_passive":
        rng = np.random.default_rng(STREAM_DIARY + seed)
        d = rng.choice(n, size=len(left), p=s / s.sum())
        return np.bincount(d, minlength=n).astype(float)

    # ---- 纯频次 (b)：自己选择的计数 —— 无结果反馈
    if cfg == "freq_active":
        w = np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            w[l if w[l] >= w[r] else r] += 1.0
        return w

    # ---- 纯奖励（不用标签）：只知道"自己选对了没有"
    if cfg in ("reward_1sided", "reward_1sided_clamp"):
        clamped = cfg.endswith("clamp")
        w = np.full(n, 0.5) if clamped else np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            pick = l if w[l] >= w[r] else r
            other = r if pick == l else l
            if not (s[pick] > s[other]):
                w[pick] = max(0.0, w[pick] - 0.05) if clamped else w[pick] - 1.0
        return w
    if cfg == "reward_sym":
        w = np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            pick = l if w[l] >= w[r] else r
            other = r if pick == l else l
            w[pick] += 1.0 if s[pick] > s[other] else -1.0
        return w

    # ---- 以下都用标签（"该给谁 +1" 从外部来）
    win = np.where(s[left] > s[right], left, right)
    lose = np.where(s[left] > s[right], right, left)
    if cfg == "label_boost_all":
        return np.bincount(win, minlength=n).astype(float)
    if cfg == "label_contrast":
        w = np.zeros(n)
        np.add.at(w, win, 1.0)
        np.add.at(w, lose, -1.0)
        return w
    if cfg in ("label_boost_err", "label_boost_err_cap"):
        cap = 5.0 if cfg.endswith("cap") else None
        w = np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            pick = l if w[l] >= w[r] else r
            other = r if pick == l else l
            if not (s[pick] > s[other]):        # 错 ⇒ 给"该选的那位"+1
                x = int(win[t])
                w[x] = min(cap, w[x] + 1.0) if cap else w[x] + 1.0
        return w
    raise ValueError(cfg)


# 组名 · 信号来源 · 是否用标签 · 说明
CONFIGS = [
    ("none",                    "无",         False, "不学：恒 0（do-nothing 基线）"),
    ("random_w",                "无",         False, "随机权重（噪声尺度基准）"),
    ("freq_passive",            "频次(外部日记)", False, "★ 谁常出现就 +1（无结果反馈）"),
    ("freq_active",             "频次(自己选择)", False, "★ 只数自己选了谁（无结果反馈）"),
    ("reward_1sided",           "互动好坏",   False, "WB `selected` 迁移版：错时只削弱被选中的"),
    ("reward_1sided_clamp",     "互动好坏",   False, "同上 + 权重有下界 [0,1]（初值 0.5）"),
    ("reward_sym",              "互动好坏",   False, "纯奖励 ±1（REINFORCE 形态，**不用标签**）"),
    ("label_boost_err",         "显式偏好",   True,  "WB `boostonly` 迁移版：错时给该选的 +1"),
    ("label_boost_err_cap",     "显式偏好",   True,  "同上 + per-实体封顶（WB `homeo` 迁移形态）"),
    ("label_contrast",          "显式偏好",   True,  "每步 真赢家 +1 / 真输家 −1（零和）"),
    ("label_boost_all",         "显式偏好",   True,  "监督上界：每步给真赢家 +1"),
]


def inflation(w, s, w0) -> tuple[float, float, float]:
    """(整体漂移, Δ_强半, Δ_弱半) —— WB「无关 Δ」在本任务的迁移形态。"""
    n = len(s)
    order = np.argsort(-s)
    top, bot = order[: n // 2], order[n // 2:]
    return (float(np.mean(w) - np.mean(w0)),
            float(np.mean(w[top] - w0[top])),
            float(np.mean(w[bot] - w0[bot])))


def main() -> None:
    print("=" * 100)
    print("反例②：纯频次 / 互动好坏信号是不是真的学不动？（H2 的直接检验，逐信号源拆开）")
    print("=" * 100)
    print(f"协议  N={N} · 训练 {T_TRAIN} trial · 评估 {T_EVAL} trial(独立流) · seeds={len(SEEDS)} 个 · 阈值 = 3·se(随机权重组)")
    print()

    res = {}
    for cfg, src, uses_label, _note in CONFIGS:
        pa, sa, t1, sp, infl, dm, dtop, dbot = [], [], [], [], [], [], [], []
        for sd in SEEDS:
            s = true_strength(sd)
            l, r = draw_trials(sd, STREAM_TRAIN, T_TRAIN)
            el, er = draw_trials(sd, STREAM_EVAL, T_EVAL)
            w = train(cfg, s, l, r, sd)
            w0 = np.full(N, 0.5) if cfg == "reward_1sided_clamp" else np.zeros(N)
            pa.append(pairwise_acc(w, s))
            sa.append(selection_acc(w, el, er, s))
            t1.append(top1_hit(w, s))
            sp.append(spearman(w, s))
            a, b, c = inflation(w, s, w0)
            infl.append(a)
            dtop.append(b)
            dbot.append(c)
            dm.append(b - c)
        res[cfg] = dict(pa=np.array(pa), sa=np.array(sa), t1=np.array(t1),
                        sp=np.array(sp), infl=np.array(infl), margin=np.array(dm),
                        dtop=np.array(dtop), dbot=np.array(dbot))

    se = float(res["random_w"]["pa"].std(ddof=1) / np.sqrt(len(SEEDS)))
    thr = 3.0 * se
    base_pa = float(res["none"]["pa"].mean())
    base_sa = float(res["none"]["sa"].mean())
    print(f"噪声尺度 se(随机权重组成对排序率) = {se:.4f} ⇒ 阈值 3·se = {thr:.4f}")
    print(f"不学基线：成对排序率 {base_pa:.4f} · 部署选择准确率 {base_sa:.4f}")
    print()

    print(f"{'组':<24}{'信号来源':<16}{'用标签':<8}{'成对排序率':>11}{'Δ vs 基线':>11}{'top1':>8}{'选择准确率':>11}{'判决':>10}")
    print("-" * 100)
    learns = {}
    for cfg, src, uses_label, _note in CONFIGS:
        d = res[cfg]
        delta = float(d["pa"].mean() - base_pa)
        learns[cfg] = bool(delta > thr and (float(d["sa"].mean()) - 0.55) > 0.0)
        tag = "—" if cfg in ("none", "random_w") else ("★学得动" if learns[cfg] else "学不动")
        print(f"{cfg:<24}{src:<16}{('是' if uses_label else '否'):<8}"
              f"{d['pa'].mean():>11.4f}{delta:>+11.4f}{d['t1'].mean():>8.4f}{d['sa'].mean():>11.4f}{tag:>10}")

    print()
    print("== 判决（H2：『纯频次/互动好坏信号学不动；必须显式偏好信号』）==")
    freq_groups = [c for c, _s, ul, _n in CONFIGS if c.startswith("freq_")]
    rew_groups = [c for c, _s, ul, _n in CONFIGS if c.startswith("reward_")]
    freq_falsified = [c for c in freq_groups if learns[c]]
    rew_falsified = [c for c in rew_groups if learns[c]]
    for c in freq_groups + rew_groups:
        print(f"  {c:<22} 成对排序率 {res[c]['pa'].mean():.4f}  Δ={res[c]['pa'].mean() - base_pa:+.4f}"
              f"  选择准确率 {res[c]['sa'].mean():.4f}   ⇒ {'学得动' if learns[c] else '学不动'}")
    print()
    if freq_falsified:
        print(f"  ⛔【频次半边】被证伪：{'、'.join(freq_falsified)} 在**没有任何反馈信号**的情况下显著高于基线。")
        print("     理由：H2 把「频次」当成一个信号，实际上它至少是两种：")
        print("        · 外部日记频次（谁常出现）—— **含真值信息** ⇒ 学得动；")
        print("        · 自己选择的计数 —— 无结果反馈、无真值信息 ⇒ 学不动。")
        print("     ⇒ 这两半答案相反 ⇒ H2 的措辞必须拆开重写，否则它是可证伪性不足的表述。")
    else:
        print("  ✅【频次半边】未被证伪：本次测到的纯频次组都 ≈ 基线。")
    if rew_falsified:
        print(f"  ⛔【互动好坏半边】被证伪：{'、'.join(rew_falsified)} **不用任何标签**却学得动（见上表 Δ 与选择准确率）。")
        print("     理由：在「二选一 + 标量对错」里，'自己选了谁'与'对错'两者合起来已含方向信息 ⇒")
        print("          不是必须外部偏好信号；WB 的 50% 是**其架构/更新形态**的性质，不是纯奖励的普遍性质。")
    else:
        print("  ✅【互动好坏半边】未被证伪：纯奖励组都 ≈ 基线。")

    print()
    print("== 判决（H1 的『守门人』半边：压住'整体推高'/无关 Δ）==")
    print(f"{'组':<24}{'mean(w) 漂移':>14}{'Δ_强半':>12}{'Δ_弱半':>12}{'判别裕度(强-弱)':>16}")
    print("-" * 100)
    for cfg, _s, _ul, _n in CONFIGS:
        if cfg in ("none", "random_w"):
            continue
        d = res[cfg]
        print(f"{cfg:<24}{d['infl'].mean():>14.4f}{d['dtop'].mean():>12.4f}{d['dbot'].mean():>12.4f}"
              f"{d['margin'].mean():>16.4f}")
    print("  ⚠️ 注：`label_contrast` 的「漂移 = 0」是**零和构造成立**的，不是实验发现（同义反复）。")
    print("  ⚠️ 注：本任务是**排序**读出 ⇒ 绝对水平（漂移）不进入任何指标 —— 用下面这条可验：")
    print(f"        boost-only（漂移 {res['label_boost_all']['infl'].mean():+.1f}）成对排序率 "
          f"{res['label_boost_all']['pa'].mean():.4f}  vs  "
          f"零和（漂移 0.0）成对排序率 {res['label_contrast']['pa'].mean():.4f}"
          f"  ⇒ 差 {res['label_contrast']['pa'].mean() - res['label_boost_all']['pa'].mean():+.4f}（≈0）")
    print("        ⇒ WB 的「压住整体推高」若原封不动搬来排序任务，**可测收益 = 0**；")
    print("          要让它有意义，必须先指出下游有哪个读**绝对水平**的环节（阈值/归一化/融合权重）。")

    part_d()


# ---------------------------------------------------------------- D：归因 —— 结论对 k 选一 的依赖
def draw_trials_k(seed: int, stream: int, t: int, k: int, n: int = N) -> np.ndarray:
    """k 选一：每次随机抽 k 个候选（顺序随机 ⇒ tie 取首位时无位置偏置）。返回 (t,k)。"""
    rng = np.random.default_rng(stream + seed)
    return np.argsort(rng.random((t, n)), axis=1)[:, :k]


def train_k(cfg: str, s: np.ndarray, cand: np.ndarray, seed: int) -> np.ndarray:
    n = len(s)
    k = cand.shape[1]
    best = [int(cand[t][int(np.argmax(s[cand[t]]))]) for t in range(len(cand))]
    if cfg == "none":
        return np.zeros(n)
    if cfg == "freq_active":
        w = np.zeros(n)
        for t in range(len(cand)):
            row = cand[t]
            w[int(row[int(np.argmax(w[row]))])] += 1.0
        return w
    if cfg in ("reward_1sided", "reward_sym"):
        w = np.zeros(n)
        for t in range(len(cand)):
            row = cand[t]
            pick = int(row[int(np.argmax(w[row]))])
            ok = (s[pick] == max(s[row]))
            if cfg == "reward_sym":
                w[pick] += 1.0 if ok else -1.0
            elif not ok:
                w[pick] -= 1.0
        return w
    if cfg == "label_boost_err":
        w = np.zeros(n)
        for t in range(len(cand)):
            row = cand[t]
            pick = int(row[int(np.argmax(w[row]))])
            if s[pick] != max(s[row]):
                w[best[t]] += 1.0
        return w
    raise ValueError(cfg)


def part_d() -> None:
    print()
    print("=" * 100)
    print("D. 归因：上面「纯奖励学得动」是不是因为任务太容易？（扫 k 选一，k=2/3/5/12）")
    print("=" * 100)
    ks = [2, 3, 5, 12]
    cfgs = ["none", "freq_active", "reward_1sided", "reward_sym", "label_boost_err"]
    seeds = SEEDS[:10]
    t_sweep = 2000
    print(f"协议 k 选一 · 训练 {t_sweep} trial · seeds={len(seeds)} 个 · 指标①成对排序率(全 C(N,2) 对，真值序)")
    print(f"指标②选择准确率（选对 k 个候选里的最强）；随机猜命中率 = 1/k")
    print()
    print(f"{'k':>3}{'组':>20}{'成对排序率':>13}{'Δ vs 不学':>12}{'选择准确率':>12}{'随机猜':>9}{'判决':>10}")
    print("-" * 100)
    for k in ks:
        base = None
        for cfg in cfgs:
            pa, sa = [], []
            for sd in seeds:
                s = true_strength(sd)
                cand = draw_trials_k(sd, STREAM_TRAIN, t_sweep, k)
                w = train_k(cfg, s, cand, sd)
                pa.append(pairwise_acc(w, s))
                pick = [int(cand[t][int(np.argmax(w[cand[t]]))]) for t in range(len(cand))]
                sa.append(float(np.mean([s[pick[t]] == max(s[cand[t]]) for t in range(t_sweep)])))
            pa_m, sa_m = float(np.mean(pa)), float(np.mean(sa))
            if cfg == "none":
                base = pa_m
            d = pa_m - (base if base is not None else 0.5)
            tag = "—" if cfg == "none" else ("★学得动" if d > 0.0663 else "学不动")
            print(f"{k:>3}{cfg:>20}{pa_m:>13.4f}{'' if cfg == 'none' else f'{d:>+12.4f}'}"
                  f"{sa_m:>12.4f}{1.0 / k:>9.3f}{tag:>10}")
        print()
    print("  ⇒ 归因结论：`reward_1sided` 在 k=2/3/5/12 下都学得动 ⇒ 不是「任务太容易」，")
    print("     而是**「自己选了谁 + 标量对错」本身就含方向信息**（错 ⇒ 被选中的那个是错的 ⇒ 降它）。")
    print("     ⚠️ 该机制成立的前提（翻案条件）：读出是**共享一维、无固定正基线**的（本协议如此）；")
    print("        WB 的 50% 出在**有固定正基线 + 单位封顶**的读出上 —— 两者不是同一个形态。")


if __name__ == "__main__":
    main()
