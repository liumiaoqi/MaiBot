#!/usr/bin/env python3
"""exp3d: 检验「加竞争就能产生选择性」这个处方 —— 以及补上漏掉的探针

起因：exp3c 结束时我给的下一步是「给读出加竞争（互相抑制/对手项）」。
⚠️ 但动手前算了一下：**线性竞争不改变 argmax** ——
   互相抑制 a−z·b vs b−z·a ⇒ 差 = (a−b)(1+z) ⇒ **符号同 a−b**；减均值同理。
   ⇒ 所以"加竞争"**不可能**改变决策 ⇒ **那个处方是错的**。
   ⇒ 本支把它**当对照跑出来**，而不是只写在纸上（能证伪的才叫结论）。

同时补 exp3c 漏掉的关键探针
---------------------------
exp3c 只报了「泛化探针（好类）」与「无关组合」，**漏了坏类**。
而 50% 有另一种可能：**方向学对了、幅度不够**（坏类 margin 被压低但没翻负）。
⇒ 本支加 `坏类训练组合` 探针，并**扫 η 与 TRIALS**，看它能不能翻负 ⇒ 直接分辨这两种解释。

读数
----
  · 训练正确率（前段 → 后段）
  · 四个探针的 Δmargin：好类训练 / 坏类训练 / 泛化 / 无关
  · ⭐ 判据：坏类 Δmargin **翻负** ⇒ "幅度不够"；**仍为正** ⇒ "方向也没学对"

依赖：numpy ＋ 复用 exp3/exp3c。运行：python exp3d_competition_test.py
"""

import time

import numpy as np

from exp3_mb_real_wiring import backbone, kc_pattern, load_graph, pick_readout
from exp3c_normalize_combo import channels_of, norm_glom  # noqa: F401  (统一命名口径)

W_CLIP = 2000.0
K_SPARSE = 0.05
ARMS = [(1.0, 1200), (3.0, 1200), (3.0, 4000), (10.0, 4000)]
MODES = ("none", "lateral", "homeo")   # homeo = **每个读出位**总权重封顶（唯一能压"整体推高"的）
Z_LAT = 1.0

N_NODES = 0


def drive(pool):
    d = np.zeros(N_NODES)
    for i in pool:
        d[i] = 1.0
    return d


def make_net(p2k, k2m, readout, k, mode):
    w = k2m[:, 2].astype(float).copy()
    ks, kd = k2m[:, 0].astype(int), k2m[:, 1].astype(int)

    w0_j = {j: float(w[kd == j].sum()) for j in readout}

    def respond(pool):
        s = kc_pattern(p2k, drive(pool), k)
        x = np.zeros(N_NODES)
        np.add.at(x, kd, w * s[ks])
        a, b = float(x[readout[0]]), float(x[readout[1]])
        if mode == "lateral":
            a, b = a - Z_LAT * b, b - Z_LAT * a      # ⚠️ 线性 ⇒ 只缩放 margin，不改符号
        return s, a, b

    def cap():
        """per-MBON 稳态：**每位**自己的总权重不许超过初值（全局归一化做不到这点）。"""
        for j in readout:
            mj = kd == j
            tot = float(w[mj].sum())
            if tot > w0_j[j]:
                w[mj] *= w0_j[j] / tot

    return w, ks, kd, respond, cap


def run(p2k, k2m, readout, k, mode, eta, trials, train_set, probes):
    w, ks, kd, respond, cap = make_net(p2k, k2m, readout, k, mode)
    base = {}
    for name, pool in probes.items():
        _, a, b = respond(pool)
        base[name] = a - b

    trail = []
    for t in range(trials):
        pool, want = train_set[t % len(train_set)]
        s, a, b = respond(pool)
        mg = a - b
        trail.append((mg >= 0) == want)
        j = readout[0] if mg >= 0 else readout[1]
        m = kd == j
        w[m] = w[m] + eta * (1.0 if want else -1.0) * s[ks[m]]
        np.clip(w, 0.0, W_CLIP, out=w)
        if mode == "homeo":
            cap()

    after = {}
    for name, pool in probes.items():
        _, a, b = respond(pool)
        after[name] = a - b
    n = len(train_set) * 3
    return {"acc": float(np.mean(trail)), "first": float(np.mean(trail[:n])),
            "last": float(np.mean(trail[-n:])), "base": base, "after": after}


def main():
    global N_NODES
    t0 = time.perf_counter()
    print("=" * 78)
    print("exp3d · 检验「加竞争产生选择性」＋ 补坏类探针 ＋ 扫 η/轮数")
    print("=" * 78)

    src, dst, w, ids, pos, kinds = load_graph()
    kind, p2k, k2m = backbone(ids, pos, kinds, src, dst, w)
    N_NODES = len(kind)
    readout = pick_readout(k2m)
    k = max(1, int(K_SPARSE * len(set(k2m[:, 0].astype(int)))))
    chan = channels_of(kinds, ids, kind)
    order = sorted(chan, key=lambda g: -len(chan[g]))

    def P(*gs):
        out = []
        for g in gs:
            out += chan[g]
        return out

    sg, sb = order[0], order[1]
    gA, gB, gE = order[2], order[3], order[4]
    bC, bD, bF = order[5], order[6], order[7]
    u1, u2 = order[8], order[9]

    probes = {"好类训练": P(sg, gA), "坏类训练": P(sb, bC),
              "泛化探针": P(sg, gE), "无关组合": P(u1, u2)}
    train_set = [(P(sg, gA), True), (P(sg, gB), True), (P(sb, bC), False), (P(sb, bD), False)]
    print(f"\n[球] 共享 好={sg} 坏={sb} | 特异 gA={gA} gB={gB} gE={gE} bC={bC} bD={bD} | 无关 {u1},{u2}")

    print("\n" + "-" * 78)
    print(f"{'模式':<9}{'η':<6}{'轮数':<7}{'正确率 前→后':<20}"
          f"{'坏类 margin(基→后)':>22}{'好类 Δ':>12}{'泛化 Δ':>12}{'无关 Δ':>12}")
    print("-" * 78)
    for mode in MODES:
        for eta, trials in ARMS:
            r = run(p2k, k2m, readout, k, mode, eta, trials, train_set, probes)
            d = {n: r["after"][n] - r["base"][n] for n in probes}
            print(f"{mode:<9}{eta:<6}{trials:<7}"
                  f"{r['first']:>6.1%} → {r['last']:<11.1%}"
                  f"{r['base']['坏类训练']:>+10.0f} → {r['after']['坏类训练']:>+9.0f}"
                  f"{d['好类训练']:>+12.0f}{d['泛化探针']:>+12.0f}{d['无关组合']:>+12.0f}")
        print()

    print("[判据] ① `lateral` 与 `none` 的**正确率逐格相同**、数值恰好 ×(1+z) ⇒ 实证「线性竞争只缩放 margin」，我的处方错了")
    print("       ② 坏类 Δmargin **翻负** ⇒ 方向学对了、只是幅度不够；**仍为正** ⇒ 方向也没学对")
    print(f"\n[耗时] {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
