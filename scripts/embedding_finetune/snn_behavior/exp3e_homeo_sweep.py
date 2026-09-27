#!/usr/bin/env python3
"""exp3e: 在 per-MBON 稳态（homeo）下细扫 η × 轮数 —— 找"能稳定翻负"的窗口

起因（exp3d 的结论）
--------------------
三种机制各测一次，只有 **per-MBON 稳态**有效：
  · 它把「整体推高」消掉了（无关 Δ ≈ 0，而 none 是 +2627）
  · 它把坏类 margin 从 **+830 压到 −24**（翻负，方向对了）
  · 泛化/无关 比值 ≈ **196×**
⚠️ **但正确率仍 50%** —— 原因是 **−24 只是"刚刚过零"**，翻负发生在**训练极末期**，
   对"每一拍"统计的正确率几乎没贡献。
   ⇒ 旁证：η=10 时反而回到 +0（**大 η 与强 cap 打架**）⇒ 中间有窗口。

本支要回答的一个问题
--------------------
**在 homeo 下把 η / 轮数扫开，能不能找到"稳定翻负、并且正确率明显 > 50%"的窗口？**

读数设计（关键：**分段正确率**，才看得出"什么时候开始学会"）
-----------------------------------------------------------
  全程正确率 · **四段正确率**（每 1/4 一段）· 坏类 margin 基→后 · 泛化 Δ · 无关 Δ
  ⭐ 判据：**后段 > 前段** 才算"在学"；**坏类 margin 翻负** 才算"方向对"；
     而且**无关 Δ 必须仍然 ≈ 0**（否则区分性又被整体推高淹掉）。

⚠️ 本流程是**确定性**的（无随机初始化/无采样噪声）⇒ 每格跑一次即可，不需要多 seed。

依赖：numpy ＋ 复用 exp3 / exp3c。运行：python exp3e_homeo_sweep.py
"""

import time

import numpy as np

from exp3_mb_real_wiring import backbone, kc_pattern, load_graph, pick_readout
from exp3c_normalize_combo import channels_of

K_SPARSE = 0.05
W_CLIP = 2000.0
ETAS = (1.0, 3.0, 12.0)
TRIALS = (2000,)

N_NODES = 0


def drive(pool):
    d = np.zeros(N_NODES)
    for i in pool:
        d[i] = 1.0
    return d


def run(p2k, k2m, readout, k, eta, trials, train_set, probes, update="selected", homeo=True,
        eps=0.0, seed=0):
    w = k2m[:, 2].astype(float).copy()
    ks, kd = k2m[:, 0].astype(int), k2m[:, 1].astype(int)
    mask = {j: (kd == j) for j in readout}          # ⭐ 预计算：别每拍重建 30k 布尔数组
    idx = {j: np.flatnonzero(mask[j]) for j in readout}
    w0j = {j: float(w[idx[j]].sum()) for j in readout}
    ks_of = {j: ks[idx[j]] for j in readout}

    def resp(pool):
        s = kc_pattern(p2k, drive(pool), k)
        x = np.zeros(N_NODES)
        np.add.at(x, kd, w * s[ks])
        return s, float(x[readout[0]] - x[readout[1]])

    base = {n: resp(p)[1] for n, p in probes.items()}
    rng = np.random.default_rng(seed)
    acc = []
    for t in range(trials):
        pool, want = train_set[t % len(train_set)]
        s, mg = resp(pool)
        # ⭐ ε-greedy：以 eps 概率**随机执行动作**（探索）；否则按 margin。
        #    更新仍**只动实际执行的那个动作**、sign **只由"这个动作对不对"(=奖励)** 给
        #    ⇒ 这是**纯奖励**规则：更新时不需要知道标签，只需要知道"刚才那个动作好不好"
        if eps > 0 and rng.random() < eps:
            act = bool(rng.random() < 0.5)
            mg_eff = 1.0 if act else -1.0
        else:
            act = mg >= 0
            mg_eff = mg
        acc.append(act == want)
        mg = mg_eff
        if update == "selected":
            # 现状：只动「被选中的」那位，sign 由对错决定
            j = readout[0] if mg >= 0 else readout[1]
            ii = idx[j]
            w[ii] = w[ii] + eta * (1.0 if want else -1.0) * s[ks_of[j]]
        elif update == "boostonly":
            # 只加强「该选的那位」，**不削弱**任何一位
            jw = readout[0] if want else readout[1]
            w[idx[jw]] = w[idx[jw]] + eta * s[ks_of[jw]]
        else:
            # contrast：**该选的那位 +1、另一位 −1**
            jw, jl = (readout[0], readout[1]) if want else (readout[1], readout[0])
            w[idx[jw]] = w[idx[jw]] + eta * s[ks_of[jw]]
            w[idx[jl]] = w[idx[jl]] - eta * s[ks_of[jl]]
        np.clip(w, 0.0, W_CLIP, out=w)
        if homeo:
            for jj in readout:                 # ⭐ per-MBON 稳态：每位自己封顶
                ij = idx[jj]
                tot = float(w[ij].sum())
                if tot > w0j[jj]:
                    w[ij] *= w0j[jj] / tot
    after = {n: resp(p)[1] for n, p in probes.items()}
    q = max(1, len(acc) // 4)
    return {"acc": float(np.mean(acc)),
            "segs": [float(np.mean(acc[i * q:(i + 1) * q])) for i in range(4)],
            "base": base, "after": after}


def main():
    global N_NODES
    t0 = time.perf_counter()
    print("=" * 96)
    print("exp3e · homeo（per-MBON 稳态）下细扫 η × 轮数")
    print("=" * 96)

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
    probes = {"好类": P(sg, gA), "坏类": P(sb, bC), "泛化": P(sg, gE), "无关": P(u1, u2)}
    train_set = [(P(sg, gA), True), (P(sg, gB), True), (P(sb, bC), False), (P(sb, bD), False)]

    print(f"\n[球] 好共享 {sg} / 坏共享 {sb} | 训练好 {gA},{gB} 坏 {bC},{bD} | 泛化 {gE} | 无关 {u1},{u2}")

    for trials in TRIALS:
        print("\n" + "-" * 96)
        print(f"轮数 = {trials}")
        print(f"{'η':<6}{'全程':>8}{'①':>8}{'②':>8}{'③':>8}{'④后段':>9}"
              f"{'坏类 margin 基→后':>22}{'泛化Δ':>10}{'无关Δ':>10}")
        print("-" * 96)
        for update, needs_label in (("selected", False), ("boostonly", True), ("contrast", True)):
            tag = "纯奖励（不用标签）" if not needs_label else "⚠️ 用了标签"
            print(f"  —— update={update} · {tag} · homeo=开 ——", flush=True)
            for eta in (1.0, 3.0, 12.0):
                r = run(p2k, k2m, readout, k, eta, trials, train_set, probes,
                        update, True, 0.0, seed=7)
                s = r["segs"]
                print(f"{eta:<6.1f}{r['acc']:>8.1%}{s[0]:>8.1%}{s[1]:>8.1%}{s[2]:>8.1%}{s[3]:>9.1%}"
                      f"{r['base']['坏类']:>+13.0f} → {r['after']['坏类']:>+7.0f}"
                      f"{r['after']['泛化'] - r['base']['泛化']:>+10.0f}"
                      f"{r['after']['无关'] - r['base']['无关']:>+10.0f}", flush=True)

    print("\n[判据] 后段 > 前段 ⇒ 在学；坏类 margin 翻负 ⇒ 方向对；**无关 Δ 仍 ≈ 0** ⇒ 区分性没被淹")
    print(f"\n[耗时] {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
