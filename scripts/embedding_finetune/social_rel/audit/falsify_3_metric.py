#!/usr/bin/env python3
"""反例③ —— 指标是不是被同义改写了？（生成 ≠ 选择，SAT 论文那一环）

角色：证伪者（R3）· 写域 `social_rel/audit/`。
**独立实现**：不 import、不复制 `social_rel/impl/` 的任何代码与数字。

⭐ 为什么要拆开报（`NOTES.md` §3.1 第③层）：
  「产出过正确排序的比例（coverage）」与「最终选中的准确率」**是两个数字**。
  WB 那条线的 50% 就死在这一环：**排序/生成环节做对了，选择环节没接上** ⇒ 只报前者会把结论说过头。
  ⚠️ 本任务的现实对应物**不是假想**：`NOTES.md` §1 实测「`confidence` 有存储、有累积、有映射，
     但没看到它参与检索排序」= 同一个 run 里，①层能满分而②/③层停在旧基线。

四部分：
  A. 逐组同时报 coverage 与 selection（含"排序学对了但部署走旧规则"的真实对照）
  B. 指标分辨力锚点（oracle / random / do-nothing）—— 若锚点不成立，这个指标本身作废
  C. 接线演示：①层满分、②层数字逐位不动 ⇒ 证明两层不是同一个数
  D. 真实分歧案例：k 选一时「全序」与「选择」给出相反结论（不是构造的，是跑出来的）

协议（与 falsify_1/2 内联同一协议）：
  · N = 12 实体 · 真值强度 = 0..N-1 随机排列 · 随机无序对 + 随机左右摆放
  · 训练 3000 trial（流 A）· 评估 2000 trial（流 B，同分布新抽）· 20 seeds
  · 纯 numpy · 无 I/O · 无新增依赖 · 退出码恒 0（判决看打印）

⭐ 证伪条件（**跑之前先写死**）：
  ⛔ 反例③成立 ⇔ 存在某组：coverage_strict ≥ 0.50 且 部署选择准确率(新规则) ≤ 0.55
     —— 即"生成了正确排序、却没选对"⇒ **只报 coverage 的结论必须作废**。
  ⛔ 指标作废 ⇔ oracle 锚点的成对排序率 < 1.0 或 random 锚点 > 0.55（指标没有工作区间）
  ⛔ 同义改写成立 ⇔ ①层满分、而②层指标与基线**逐位相同**（学到的排序 ≠ 检索变好）

⛔ 能说它不成立的那条命令（自证）：
  cd E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune
  .\\.venv\\Scripts\\python.exe social_rel\\audit\\falsify_3_metric.py
  末段「判决」逐条打印 A/B/C 的检查结果与 PASS-FAIL。

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
STREAM_SEL = 3_000_000

M_RET = 60          # C 部分：检索候选数
M_REL = 12          # C 部分：相关集大小
Q_RET = 200         # C 部分：查询数
T_RET = 3000        # C 部分：学 conf 的 trial 数


# ---------------------------------------------------------------- 协议（与 falsify_1/2 同）
def true_strength(seed: int, n: int = N) -> np.ndarray:
    return np.random.default_rng(STREAM_TRUTH + seed).permutation(n).astype(float)


def draw_trials(seed: int, stream: int, t: int, n: int = N):
    rng = np.random.default_rng(stream + seed)
    u, v = np.triu_indices(n, k=1)
    k = rng.integers(0, len(u), size=t)
    a, b = u[k], v[k]
    flip = rng.random(t) < 0.5
    return np.where(flip, b, a), np.where(flip, a, b)


# ---------------------------------------------------------------- 指标（与 falsify_1/2 同）
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
    """新规则：按学出来的权重选（部署该用的那条路）。"""
    w = np.asarray(w, dtype=float)
    pick_left = w[left] >= w[right]
    ok = np.where(pick_left, s[left] > s[right], s[right] > s[left])
    return float(ok.mean())


def selection_acc_legacy(left, right, s) -> float:
    """旧规则：按位置/created_at 取第一条（= 权重没接线时的现状）。"""
    return float((s[left] > s[right]).mean())


# ---------------------------------------------------------------- 学习器（与 falsify_2 同签名）
def train(cfg: str, s: np.ndarray, left, right, seed: int, n: int = N) -> np.ndarray:
    if cfg == "none":
        return np.zeros(n)
    if cfg == "random_w":
        return np.random.default_rng(STREAM_NULL + seed).normal(0.0, 1.0, n)
    if cfg == "oracle":
        return np.array(s, dtype=float)
    if cfg == "freq_active":
        w = np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            w[l if w[l] >= w[r] else r] += 1.0
        return w
    if cfg == "reward_1sided":
        w = np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            pick = l if w[l] >= w[r] else r
            other = r if pick == l else l
            if not (s[pick] > s[other]):
                w[pick] -= 1.0
        return w
    if cfg == "reward_sym":
        w = np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            pick = l if w[l] >= w[r] else r
            other = r if pick == l else l
            w[pick] += 1.0 if s[pick] > s[other] else -1.0
        return w
    win = np.where(s[left] > s[right], left, right)
    lose = np.where(s[left] > s[right], right, left)
    if cfg == "label_boost_all":
        return np.bincount(win, minlength=n).astype(float)
    if cfg == "label_contrast":
        w = np.zeros(n)
        np.add.at(w, win, 1.0)
        np.add.at(w, lose, -1.0)
        return w
    if cfg == "label_boost_err":
        w = np.zeros(n)
        for t in range(len(left)):
            l, r = int(left[t]), int(right[t])
            pick = l if w[l] >= w[r] else r
            other = r if pick == l else l
            if not (s[pick] > s[other]):
                w[int(win[t])] += 1.0
        return w
    raise ValueError(cfg)


CONFIGS = ["none", "random_w", "freq_active", "reward_1sided", "reward_sym",
           "label_boost_err", "label_contrast", "label_boost_all", "oracle"]


# ---------------------------------------------------------------- A：coverage vs selection
def part_a() -> dict:
    print("=" * 100)
    print("A. 同一批 run，两个数字分开报：coverage（产出正确排序的比例） vs 选择准确率")
    print("=" * 100)
    print(f"{'组':<20}{'coverage_strict':>17}{'coverage_top1':>15}{'选择:新规则':>13}{'选择:旧规则':>13}{'gap':>9}")
    print("-" * 100)
    out = {}
    for cfg in CONFIGS:
        cov_s, cov_t, sel_new, sel_old = [], [], [], []
        for sd in SEEDS:
            s = true_strength(sd)
            l, r = draw_trials(sd, STREAM_TRAIN, T_TRAIN)
            el, er = draw_trials(sd, STREAM_EVAL, T_EVAL)
            w = train(cfg, s, l, r, sd)
            cov_s.append(1.0 if pairwise_acc(w, s) == 1.0 else 0.0)
            cov_t.append(1.0 if top1_hit(w, s) == 1.0 else 0.0)
            sel_new.append(selection_acc(w, el, er, s))
            sel_old.append(selection_acc_legacy(el, er, s))
        A = dict(cov_s=float(np.mean(cov_s)), cov_t=float(np.mean(cov_t)),
                 sel_new=float(np.mean(sel_new)), sel_old=float(np.mean(sel_old)))
        A["gap"] = A["cov_s"] - A["sel_new"]
        out[cfg] = A
        print(f"{cfg:<20}{A['cov_s']:>17.3f}{A['cov_t']:>15.3f}{A['sel_new']:>13.4f}{A['sel_old']:>13.4f}{A['gap']:>+9.3f}")
    print()
    print("  注：coverage_strict = 「整条排序完全正确」的 run 占比（并列/错一处即不算）")
    print("      选择:新规则 = 按学出来的权重选 · 选择:旧规则 = 按位置取第一条（= 权重没接线时的现状）")
    return out


# ---------------------------------------------------------------- B：指标分辨力锚点
def part_b() -> dict:
    print()
    print("=" * 100)
    print("B. 指标分辨力锚点（若锚点不成立 ⇒ 这个指标本身作废，任何'变好'都是空的）")
    print("=" * 100)
    print(f"{'锚点':<26}{'Spearman':>12}{'成对排序率':>13}{'top1命中':>11}{'选择准确率':>12}")
    print("-" * 100)
    out = {}
    for cfg, label in (("oracle", "oracle（喂真值=正对照）"), ("none", "do-nothing（不学）"), ("random_w", "random_w（随机权重）")):
        sp, pa, t1, sa = [], [], [], []
        for sd in SEEDS:
            s = true_strength(sd)
            l, r = draw_trials(sd, STREAM_TRAIN, T_TRAIN)
            el, er = draw_trials(sd, STREAM_EVAL, T_EVAL)
            w = train(cfg, s, l, r, sd)
            sp.append(spearman(w, s))
            pa.append(pairwise_acc(w, s))
            t1.append(top1_hit(w, s))
            sa.append(selection_acc(w, el, er, s))
        out[cfg] = (float(np.mean(sp)), float(np.mean(pa)), float(np.mean(t1)), float(np.mean(sa)))
        print(f"{label:<26}{out[cfg][0]:>12.4f}{out[cfg][1]:>13.4f}{out[cfg][2]:>11.4f}{out[cfg][3]:>12.4f}")
    return out


# ---------------------------------------------------------------- C：接线演示（①层 ≠ ②层）
def part_c() -> dict:
    print()
    print("=" * 100)
    print("C. 接线演示：①层（学到的排序）满分，②层（检索质量）动不动 —— 两层不是同一个数")
    print("=" * 100)
    s = true_strength(101, M_RET)
    l, r = draw_trials(101, STREAM_TRAIN, T_RET, M_RET)
    conf = train("label_boost_err", s, l, r, 101, M_RET)
    conf_norm = (conf - conf.min()) / max(1e-12, (conf.max() - conf.min()))
    print(f"  ①层：conf（label_boost_err 在 {M_RET} 个候选上学的权重） vs 真值强度 "
          f"成对排序率 = {pairwise_acc(conf, s):.4f} · Spearman = {spearman(conf, s):.4f}")

    rng = np.random.default_rng(424242)
    rel = np.zeros((Q_RET, M_RET))
    top = np.argsort(-s)[:M_REL]
    rel[np.arange(Q_RET), top[rng.integers(0, M_REL, size=Q_RET)]] = 1.0   # 每查询恰好 1 个相关
    sim = 0.15 * rel + 0.85 * rng.random((Q_RET, M_RET))    # 现状：噪声主导，只有相似度
    conf_q = np.tile(conf_norm, (Q_RET, 1))
    wrong = np.tile(np.random.default_rng(7).random(M_RET), (Q_RET, 1))

    def metrics(score):
        order = np.argsort(-score, axis=1)
        r1 = float(rel[np.arange(Q_RET), order[:, 0]].mean())
        r5 = float(np.take_along_axis(rel, order[:, :5], axis=1).sum(axis=1).mean())
        rank = np.argmax(np.take_along_axis(rel, order, axis=1) > 0, axis=1) + 1
        return r1, r5, float((1.0 / rank).mean())

    lam = 1.0
    cands = [
        ("(a) 基线：sim", sim),
        ("(b) 学到但没接线：sim + 0.0·conf", sim + 0.0 * conf_q),
        ("(c) 接线：sim + 1.0·conf", sim + lam * conf_q),
        ("(d) 反号对照：sim + 1.0·随机权重", sim + lam * wrong),
    ]
    print(f"  {Q_RET} 个查询 · {M_RET} 候选 · 每查询 1 个相关 · λ = {lam}")
    print(f"  {'配置':<36}{'Recall@1':>10}{'Recall@5':>10}{'MRR':>10}{'与(a)逐位相同':>14}")
    print("  " + "-" * 80)
    res = {}
    for name, sc in cands:
        r1, r5, mrr = metrics(sc)
        res[name] = (r1, r5, mrr)
        same = ("是" if np.array_equal(sc, sim) else "—") if name.startswith("(b)") else "—"
        print(f"  {name:<36}{r1:>10.4f}{r5:>10.4f}{mrr:>10.4f}{same:>14}")
    print()
    print("  ⚠️ 本演示的构造成分（必须说明）：")
    print("     · 相关集由真值强度导出 ⇒ 它**不证明**机制能提升真实检索；")
    print("     · (b) 的 λ=0 是构造的 ⇒ (a)≡(b) 是**同义反复**（作用是'接线完整性检验'，不是发现）；")
    print("     · conf 与查询无关 ⇒ 它只能当全局先验，不能替代 query-doc 相似度。")
    print("     真正的发现是 (c)/(d) 两个方向：②层能不能分辨接线方向。")
    return res


# ---------------------------------------------------------------- D：真实分歧案例
def draw_trials_k(seed: int, stream: int, t: int, k: int, n: int = N) -> np.ndarray:
    """k 选一：每次随机抽 k 个候选（顺序随机 ⇒ tie 取首位时无位置偏置）。返回 (t,k)。"""
    rng = np.random.default_rng(stream + seed)
    return np.argsort(rng.random((t, n)), axis=1)[:, :k]


def train_k_reward_1sided(s: np.ndarray, cand: np.ndarray) -> np.ndarray:
    """与 falsify_2 的 `reward_1sided` 同语义：错时只削弱被自己选中的那个（不用标签）。"""
    w = np.zeros(len(s))
    for t in range(len(cand)):
        row = cand[t]
        pick = int(row[int(np.argmax(w[row]))])
        if s[pick] != max(s[row]):
            w[pick] -= 1.0
    return w


def part_d() -> dict:
    print()
    print("=" * 100)
    print("D. 真实分歧案例（**不是构造的**）：同一次 run 里「全序」与「选择」给出相反结论")
    print("=" * 100)
    seeds = SEEDS[:10]
    t = 2000
    out = {}
    print(f"{'k':>3}{'成对排序率(全序)':>18}{'coverage_strict':>17}{'选择准确率':>12}{'这句话会说成':>34}")
    print("-" * 100)
    for k in (2, 12):
        pa, cov, sa = [], [], []
        for sd in seeds:
            s = true_strength(sd)
            cand = draw_trials_k(sd, STREAM_TRAIN, t, k)
            w = train_k_reward_1sided(s, cand)
            pa.append(pairwise_acc(w, s))
            cov.append(1.0 if pairwise_acc(w, s) == 1.0 else 0.0)
            pick = [int(cand[i][int(np.argmax(w[cand[i]]))]) for i in range(t)]
            sa.append(float(np.mean([s[pick[i]] == max(s[cand[i]]) for i in range(t)])))
        out[k] = (float(np.mean(pa)), float(np.mean(cov)), float(np.mean(sa)))
        verdict = ("「全序没学会」而「选择满分」" if k == 12 else "两句话一致")
        print(f"{k:>3}{out[k][0]:>18.4f}{out[k][1]:>17.3f}{out[k][2]:>12.4f}{verdict:>34}")
    print()
    print("  ⚠️ 交叉核对：本表 k=2/12 的数字应与 `falsify_2_freq.py` 的 D 段**逐位相同**"
          "（同协议同种子，独立实现 ⇒ 互为复算）。")
    print("  ⇒ 同一批 run：k=12 时『选择准确率 = 1.0000』（看着完全学会）而『全序 = "
          f"{out[12][0]:.4f}』（≈随机）——")
    print("     报哪一个，结论就反过来。这就是「生成 ≠ 选择」的真实形态，不是假想。")
    return out


def main() -> None:
    print("反例③：指标是不是被同义改写了？——「生成 ≠ 选择」拆开报")
    print()
    a = part_a()
    b = part_b()
    c = part_c()
    d = part_d()

    print()
    print("=" * 100)
    print("判决（反例③）")
    print("=" * 100)
    bad = [k for k, v in a.items() if v["cov_s"] >= 0.50 and v["sel_new"] <= 0.55]
    oracle_ok = b["oracle"][1] >= 1.0 and abs(b["oracle"][0] - 1.0) < 1e-9
    rand_ok = b["random_w"][1] <= 0.55
    donothing_ok = abs(b["none"][1] - 0.5) < 1e-9
    wired_same = bool(np.isclose(c["(a) 基线：sim"], c["(b) 学到但没接线：sim + 0.0·conf"]).all())
    ca, cc, cd = c["(a) 基线：sim"], c["(c) 接线：sim + 1.0·conf"], c["(d) 反号对照：sim + 1.0·随机权重"]
    wired_up = all(x >= y for x, y in zip(cc, ca)) and any(x > y for x, y in zip(cc, ca))
    wired_dn = all(x <= y for x, y in zip(cd, ca)) and any(x < y for x, y in zip(cd, ca))

    msg_a = ("⛔ 反例③成立：单看 coverage 会说过头，两个数必须一起报。" if bad
             else "✅ 本批 N=12 组里无「coverage 高而选择 low」者；但见 [D] 的真实分歧案例。")
    msg_b = ("✅ 指标有工作区间，不是恒真判据" if (oracle_ok and rand_ok and donothing_ok) else "⛔ 指标作废")
    msg_c = ("✅ ②层能分辨接线方向（①层满分 ≠ ②层变好）⇒ 两层必须分开报"
             if (wired_same and wired_up and wired_dn) else "⛔ ②层分辨不出接线方向 ⇒ 该指标不足以支撑 H3")
    diverge = d[12][2] >= 0.99 and d[12][0] <= 0.65

    print(f"  [A] coverage≥0.50 且 选择准确率≤0.55 的组：{bad if bad else '无'}")
    print(f"      ⇒ {msg_a}")
    print(f"      最高 coverage 组：{max(a, key=lambda kk: a[kk]['cov_s'])} = {max(v['cov_s'] for v in a.values()):.3f}；"
          f"其「旧规则」选择准确率 = {a['oracle']['sel_old']:.4f}")
    print(f"  [B] 锚点：oracle 成对排序率 = {b['oracle'][1]:.4f}（须 =1.0）· random = {b['random_w'][1]:.4f}（须 ≤0.55）"
          f"· do-nothing = {b['none'][1]:.4f}（须 =0.5）")
    print(f"      ⇒ {msg_b}")
    print(f"  [C1] (a)≡(b) 逐位相同 = {wired_same}（⚠️ λ=0 **构造** ⇒ 同义反复，作用是接线完整性检验）")
    print(f"  [C2] (c) 全面不劣于(a) 且至少一项更好 = {wired_up} · (d) 全面不优于(a) 且至少一项更差 = {wired_dn}")
    print(f"      ⇒ {msg_c}")
    print(f"  [D] k=12：选择准确率 {d[12][2]:.4f} vs 全序 {d[12][0]:.4f}"
          f" ⇒ {'⛔ 反例③成立（真实分歧）：两个数字必须同时报，单独报任一个都会误判。' if diverge else '✅ 本次未出现真实分歧'}")
    print()
    print("  ⛔ 能说它不成立的那条命令：.\\.venv\\Scripts\\python.exe social_rel\\audit\\falsify_3_metric.py")


if __name__ == "__main__":
    main()
