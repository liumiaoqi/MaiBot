#!/usr/bin/env python3
"""exp3b: 生物学语义版 —— 「信息素通道」的正负，能不能按类泛化

为什么单独一支（exp3 的缺陷）
-----------------------------
exp3 的"好/坏气味"是**按 PN 数随手挑的 4+4**，没有语义 —— 结果挑中的第一个 `DA1`
恰恰是**负性**的社交信息素通道（cVA/Or67d：抑制求偶、促攻击）。语义正好反了。
所以这一支：**只用已核实的三个通道**，直接问"**按生物学赋语义，任务会不会有类别结构**"。

三个通道（2026-09-27 核）
------------------------
  DA1   Or67d   cVA（雄性信息素）  → 负性 / 警戒
  VA1v  Or47b   处女雌性气味       → 正性
  VL2a  IR84a   PAA（食物发酵味）  → 正性
三者 PN 都投向蘑菇体 + 侧角，通路经 aSP-g → pC1/pCd。

要回答的两个问题
----------------
① **同类在 KC 层更相似吗**：J(VA1v, VL2a)（同类·都正）vs J(DA1, VA1v)、J(DA1, VL2a)（异类）
   —— 这是"类别结构存不存在"的直接读数。
② **能按类泛化吗**：训练只给「DA1→逃避 + VA1v→趋近」，
   然后喂**没见过**的同类 **VL2a** ⇒ 它会不会也趋近？
   （对照组：喂一个**无关的普通气味通道**，预期不趋近）

依赖：numpy ＋ 复用 exp3 的加载/主干/k-WTA。运行：python exp3b_bio_semantics.py
"""

import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from exp3_mb_real_wiring import backbone, kc_pattern, load_graph, pick_readout

K_SPARSE = 0.05
TRIALS = 600
ETA = 1.0
W_CLIP = 2000.0

POS = ["VA1v", "VL2a"]      # 正性（吸引）
NEG = ["DA1"]              # 负性（警戒）


def channels_of(kinds, ids, kind):
    chan = defaultdict(list)
    for i, body_id in enumerate(ids):
        if kind[i] == "PN":
            chan[kinds[int(body_id)].split("_")[0]].append(i)
    return chan


def drive_for(chan, glom, n):
    d = np.zeros(n)
    for i in chan[glom]:
        d[i] = 1.0
    return d


def jaccard(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def make_learner(p2k, k2m, readout, n_nodes, k, rng):
    w = k2m[:, 2].astype(float).copy()
    w0 = w.copy()
    ks, kd = k2m[:, 0].astype(int), k2m[:, 1].astype(int)

    def respond(drive):
        """返回 (KC 模式, **margin** = 趋近位 − 逃避位的输入差)。

        ⚠️ 用连续 margin 而不是布尔：布尔会被**结构默认偏向**支配（见 §③），
        看不出"学习有没有真的推动决策"。
        """
        s = kc_pattern(p2k, drive, k)
        x = np.zeros(n_nodes)
        np.add.at(x, kd, w * s[ks])
        return s, float(x[readout[0]] - x[readout[1]])

    def learn(s, margin, want_approach):
        j = readout[0] if (margin >= 0) else readout[1]
        mask = kd == j
        w[mask] += ETA * (1.0 if want_approach else -1.0) * s[ks[mask]]
        np.clip(w, 0.0, W_CLIP, out=w)
        w[:] *= w0.sum() / max(w.sum(), 1e-9)   # ⚠️ 必须原地（w *= ... 会重绑定名字 ⇒ 闭包里变局部）

    return respond, learn


def main():
    t0 = time.perf_counter()
    rng = np.random.default_rng(20260927)
    print("=" * 70)
    print("exp3b · 生物学语义版 —— 信息素通道的正负 + 按类泛化")
    print("=" * 70)

    src, dst, w, ids, pos, kinds = load_graph()
    kind, p2k, k2m = backbone(ids, pos, kinds, src, dst, w)
    readout = pick_readout(k2m)
    chan = channels_of(kinds, ids, kind)
    n = len(kind)
    k = max(1, int(K_SPARSE * len(set(k2m[:, 0].astype(int)))))
    print(f"\n[主干] PN→KC {len(p2k):,} 边 · KC→MBON {len(k2m):,} 边 · 读出 {readout}")
    print(f"[通道 PN 数] " + " ".join(f"{g}={len(chan[g])}" for g in POS + NEG))

    # ── 问题①：同类在 KC 层更相似吗 ─────────────────────────
    pats = {g: kc_pattern(p2k, drive_for(chan, g, n), k) for g in POS + NEG}
    j_same = jaccard(pats[POS[0]], pats[POS[1]])
    j_diff = [jaccard(pats[g], pats[NEG[0]]) for g in POS]
    print("\n" + "-" * 70)
    print("① KC 模式相似度（Jaccard）")
    print(f"   同类（{POS[0]} vs {POS[1]}，都正性）     = {j_same:.4f}")
    for g, v in zip(POS, j_diff):
        print(f"   异类（{g} vs {NEG[0]}，正 vs 负）  = {v:.4f}")
    verdict = "✅ 类内 > 类间（有类别结构）" if j_same > max(j_diff) else "⚠️ 类内并不高于类间（无类别结构）"
    print(f"   ⇒ {verdict}")

    # ── 问题②：按类泛化 ───────────────────────────────────
    print("\n" + "-" * 70)
    print("② 按类泛化（用**连续 margin**看，不用布尔 —— 布尔被默认偏向支配）")
    print("   未训练基线 margin（正=趋近）:")
    respond0, _ = make_learner(p2k, k2m, readout, n, k, rng)
    base = {g: respond0(drive_for(chan, g, n))[1] for g in POS + NEG + ["DL2d"]}
    for g, v in base.items():
        print(f"     {g:6s} {v:>10.0f}   {'趋近' if v >= 0 else '回避'}")

    rows = []
    for train_pos, test_pos in ((POS[0], POS[1]), (POS[1], POS[0])):
        respond, learn = make_learner(p2k, k2m, readout, n, k, rng)
        odors = [(NEG[0], True), (train_pos, False)]   # (通道, 是否期望「回避」)
        trail = []
        for t_i in range(TRIALS):
            glom, want_avoid = odors[t_i % len(odors)]
            s, margin = respond(drive_for(chan, glom, n))
            trail.append(margin < 0 if want_avoid else margin >= 0)
            learn(s, margin, not want_avoid)
        acc = float(np.mean(trail))
        third = len(trail) // 3
        m_test = respond(drive_for(chan, test_pos, n))[1]
        m_ctrl = respond(drive_for(chan, "DL2d", n))[1]
        rows.append((train_pos, test_pos, acc, m_test, m_ctrl))
        print(f"   训 [{train_pos}→趋近 · DA1→回避]  正确率 前段 {np.mean(trail[:third]):.1%}"
              f" → 后段 {np.mean(trail[-third:]):.1%}（全程 {acc:.1%}）")
        print(f"      ⇒ 测同类 {test_pos}: margin {m_test:>8.0f}"
              f"（基线 {base[test_pos]:>8.0f}，变化 {m_test - base[test_pos]:+.0f}）"
              f" | 测无关 DL2d: {m_ctrl:>8.0f}（基线 {base['DL2d']:>8.0f}，变化 {m_ctrl - base['DL2d']:+.0f}）")

    # ── 问题③：默认偏向是哪来的（结构性？） ────────────────
    tot = {}
    for s_, d_, w_ in k2m:
        tot[int(d_)] = tot.get(int(d_), 0.0) + w_
    print("\n" + "-" * 70)
    print("③ \"默认答趋近\"是哪来的 —— 看两个读出位的**总突触强度**：")
    for r in readout:
        print(f"     MBON {r}: KC→MBON 总权重 {tot.get(r, 0):>9.0f}")
    r0, r1 = tot.get(readout[0], 0.0), tot.get(readout[1], 0.0)
    print(f"     ⇒ 比值 {r0 / max(r1, 1e-9):.2f}× ⇒ "
          f"{'趋近位在**结构上**就更强（= 先天偏向由接线给出）' if r0 > r1 else '（逃避位更强）'}")

    print(f"\n[耗时] {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
