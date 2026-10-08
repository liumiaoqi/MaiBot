#!/usr/bin/env python3
"""反例① —— 随机权重在同一指标上是不是也一样好？

角色：证伪者（R3）· 写域 `social_rel/audit/`。
**独立实现**：本文件不 import、不复制 `social_rel/impl/` 的任何代码与数字（否则"同一份错"会被复制两遍）。

协议（三份脚本各自内联同一协议 —— 便于单文件复跑，且互为交叉核对）：
  · N = 12 个实体（关系候选），真值强度 = 0..N-1 的**随机排列**（无并列 ⇒ 排序有唯一正解）
  · 每个 trial 随机取一个无序对，并**随机左右摆放** ⇒「永远选左」的期望准确率 = 0.500
  · 训练 3000 trial（流 A）· 评估 2000 trial（流 B：同分布**新抽**的对，不是分布外泛化）
  · 纯 numpy · 无文件 I/O · 无新增依赖 · 退出码恒 0（判决看打印，不看 rc）

证伪条件（**跑之前先写死**，跑完不许改）：
  ⛔ 反例①成立 ⇔ |mean(成对排序率｜监督上界) − mean(成对排序率｜随机权重)| ≤ 3·se(随机权重)
     ⇒ 指标分不开「学到」与「没学到」⇒ 本线所有"变好了"的结论作废。
  ✅ 否则反例①不成立：指标有分辨力，「随机也赢」不成立。

⛔ 能说它不成立的那条命令（自证）：
  cd E:\\Users\\lmq\\MaiBot\\scripts\\embedding_finetune
  .\\.venv\\Scripts\\python.exe social_rel\\audit\\falsify_1_random.py
  末段「判决」直接打印 差值 / 阈值 / 三个锚点。

2026-09-27 · 证伪者（R3）
"""

from __future__ import annotations

import numpy as np

N = 12              # 实体（关系候选）数
T_TRAIN = 3000      # 训练 trial 数
T_EVAL = 2000       # 评估 trial 数（独立抽样流）
SEEDS = list(range(20))
STREAM_TRUTH = 7_000_000
STREAM_TRAIN = 11_000_000
STREAM_EVAL = 22_000_000
STREAM_NULL = 9_000_000


# ---------------------------------------------------------------- 协议
def true_strength(seed: int, n: int = N) -> np.ndarray:
    """真值强度：0..n-1 的随机排列（无并列）。"""
    return np.random.default_rng(STREAM_TRUTH + seed).permutation(n).astype(float)


def draw_trials(seed: int, stream: int, t: int, n: int = N):
    """抽 t 个 trial：随机无序对 + 随机左右顺序（位置与真值无关）。返回 (left, right)。"""
    rng = np.random.default_rng(stream + seed)
    u, v = np.triu_indices(n, k=1)
    k = rng.integers(0, len(u), size=t)
    a, b = u[k], v[k]
    flip = rng.random(t) < 0.5
    return np.where(flip, b, a), np.where(flip, a, b)


# ---------------------------------------------------------------- 指标（自实现，不依赖 scipy）
def avg_rank(x: np.ndarray) -> np.ndarray:
    """平均秩（并列取平均）。"""
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
    """学出来的权重 vs 真值强度的秩相关（①层指标）。"""
    rx = avg_rank(x)
    ry = avg_rank(y)
    rx = rx - rx.mean()
    ry = ry - ry.mean()
    d = float(np.sqrt((rx * rx).sum() * (ry * ry).sum()))
    return float((rx * ry).sum() / d) if d > 1e-12 else 0.0


def pairwise_acc(w, s) -> float:
    """成对排序率：C(N,2) 对里 w 的相对序与 s 一致的比例（并列计 0.5）。"""
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
    """学出来的 top-1 是否就是真值最强（并列按比例给分）。"""
    w = np.asarray(w, dtype=float)
    cand = np.flatnonzero(w == w.max())
    gold = int(np.argmax(s))
    if len(cand) == 1:
        return 1.0 if cand[0] == gold else 0.0
    return 1.0 / len(cand) if gold in cand else 0.0


def selection_acc(w, left, right, s) -> float:
    """部署选择准确率：每个 trial 取 w 较大的一侧（并列取左，与训练策略同一 tie 规则）。"""
    w = np.asarray(w, dtype=float)
    pick_left = w[left] >= w[right]
    ok = np.where(pick_left, s[left] > s[right], s[right] > s[left])
    return float(ok.mean())


def left_bias_acc(left, right, s) -> float:
    """结构默认偏向：永远选左。随机摆放时应 = 0.5。"""
    return float((s[left] > s[right]).mean())


# ---------------------------------------------------------------- 三组权重
def w_none(n: int = N) -> np.ndarray:
    """不学：恒 0（do-nothing 对照 ⇒ 结构默认偏向）。"""
    return np.zeros(n, dtype=float)


def w_random(seed: int, n: int = N) -> np.ndarray:
    """随机权重（反例①的对照）：与任务无关的正态噪声。"""
    return np.random.default_rng(STREAM_NULL + seed).normal(0.0, 1.0, n)


def w_label_all(left, right, s) -> np.ndarray:
    """监督上界（正对照）：每步给该对的真赢家 +1 ⇒ 纯 Win-Count 估计。"""
    win = np.where(s[left] > s[right], left, right)
    return np.bincount(win, minlength=len(s)).astype(float)


# ---------------------------------------------------------------- 跑
def main() -> None:
    print("=" * 78)
    print("反例①：随机权重在同一指标上是不是也一样好？")
    print("=" * 78)
    print(f"协议  N={N} · 训练 {T_TRAIN} trial · 评估 {T_EVAL} trial(独立流) · seeds={len(SEEDS)} 个")
    print("真值强度 = 0..N-1 的随机排列（无并列）· 左右顺序随机 ⇒ 期望「永远选左」= 0.500")
    print()

    rows = {}
    for name, fn in (
        ("none(不学)", lambda sd, l, r, s: w_none()),
        ("random_w(随机权重)", lambda sd, l, r, s: w_random(sd)),
        ("label_boost_all(监督上界)", lambda sd, l, r, s: w_label_all(l, r, s)),
    ):
        sp, pa, t1, sa = [], [], [], []
        for sd in SEEDS:
            s = true_strength(sd)
            l, r = draw_trials(sd, STREAM_TRAIN, T_TRAIN)
            el, er = draw_trials(sd, STREAM_EVAL, T_EVAL)
            w = fn(sd, l, r, s)
            sp.append(spearman(w, s))
            pa.append(pairwise_acc(w, s))
            t1.append(top1_hit(w, s))
            sa.append(selection_acc(w, el, er, s))
        rows[name] = (np.array(sp), np.array(pa), np.array(t1), np.array(sa))

    # 「永远选左」这条策略没有权重向量 ⇒ 只有选择准确率一列
    bias = np.array([left_bias_acc(*draw_trials(sd, STREAM_EVAL, T_EVAL), true_strength(sd)) for sd in SEEDS])

    print(f"{'组':<26}{'Spearman':>16}{'成对排序率':>18}{'top1命中':>16}{'部署选择准确率':>18}")
    print("-" * 78)
    for name, (sp, pa, t1, sa) in rows.items():
        print(f"{name:<26}{sp.mean():>8.4f}±{sp.std():<7.4f}{pa.mean():>10.4f}±{pa.std():<7.4f}"
              f"{t1.mean():>8.4f}±{t1.std():<7.4f}{sa.mean():>10.4f}±{sa.std():<7.4f}")
    print(f"{'pos_left(永远选左)':<26}{'—':>16}{'—':>18}{'—':>16}{bias.mean():>10.4f}±{bias.std():<7.4f}")

    print()
    print("== 对照组：位置偏置有没有被我随机化掉 ==")
    sd0 = SEEDS[0]
    s0 = true_strength(sd0)
    el, er = draw_trials(sd0, STREAM_EVAL, T_EVAL)
    strong_left = np.where(s0[el] > s0[er], el, er)      # 固定把强者摆在左边
    strong_right = np.where(s0[el] > s0[er], er, el)
    sorted_left_bias = float(np.mean(s0[strong_left] > s0[strong_right]))
    print(f"  随机左右摆放   : 永远选左 = {bias.mean():.4f}   ← 本协议（位置与真值无关）")
    print(f"  固定'强者在左' : 永远选左 = {sorted_left_bias:.4f}   ← 若评估不随机摆放：什么都不学也满分")

    print()
    print("== 判决（反例①）==")
    pa_rand = rows["random_w(随机权重)"][1]
    pa_anch = rows["label_boost_all(监督上界)"][1]
    se_rand = float(pa_rand.std(ddof=1) / np.sqrt(len(SEEDS)))
    diff = float(pa_anch.mean() - pa_rand.mean())
    thr = 3.0 * se_rand
    print(f"  监督上界 成对排序率 = {pa_anch.mean():.4f} ± {pa_anch.std():.4f}")
    print(f"  随机权重 成对排序率 = {pa_rand.mean():.4f} ± {pa_rand.std():.4f}  (se = {se_rand:.4f})")
    print(f"  差值 = {diff:.4f}   阈值 3·se = {thr:.4f}   （{diff / thr if thr > 0 else float('inf'):.1f} × 阈值）")
    print(f"  不学(do-nothing) 部署选择准确率 = {rows['none(不学)'][3].mean():.4f} "
          f"（= 永远是左的结构偏向，随机摆放后 = 0.5）")
    if diff <= thr:
        print("  ⇒ ⛔ 反例①成立：随机权重与监督上界不可分辨 ⇒ 指标无分辨力，机制主张作废。")
    else:
        print("  ⇒ ✅ 反例①不成立：指标能把「学到」与「没学到」分开，且 do-nothing 落在结构偏向处。")


if __name__ == "__main__":
    main()
