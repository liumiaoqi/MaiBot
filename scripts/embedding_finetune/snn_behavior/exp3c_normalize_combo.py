#!/usr/bin/env python3
"""exp3c: 修掉 exp3b 的三个毛病 —— 通道名归一 / 制造类别结构 / 归一化开关

修的是 exp3b 的三处问题（NOTES 里都记过）
------------------------------------------
1. ⚠️ **通道名没归一**：`VA1v`/`VL2a` 看着像通道，其实是**分区**（同一个球的两半）。
   ⇒ 本支先归一：拆 `+` 多通道 ＋ 合并尾部分区字母 d/v/l/m ⇒ 得到"完整球"。
2. ⚠️ **任务没有类别结构**：单球气味之间近乎正交 ⇒ 没有"类内相似"可学。
   ⇒ 本支加 `combo` 变体：**气味 = 共享球 ＋ 特异球** ⇒ 同类共享一个球 ⇒ **结构是我们造出来的**。
      （题目问的"我们不需要完整的" —— combo 就是这个意思：**自己组回路**，不搬整个脑。）
3. ⚠️ **稳态归一化可能在抵消学习**（学习只能重新分配、不能改总量）。
   ⇒ 本支把它做成**开关**，开/关各跑一遍对照。

两个变体（同一批球、同一批超参、**同一个测试探针**）
------------------------------------------------------
  single —— 气味 = 单个球（≈ exp3b 的情形）⇒ 预期：无类别结构 ⇒ 泛化无从谈起
  combo  —— 气味 = 共享球 + 特异球           ⇒ 预期：类内有结构 ⇒ 泛化测得出

泛化测试（用**同一个探针 E**，这就构成干净对照）
------------------------------------------------
  训练：好 = 共享球A+特异球1 / 共享球A+特异球2 ；坏 = 共享球B+特异球3 / 共享球B+特异球4
  测试：`共享球A + 特异球5`（没见过的组合）⇒ **combo 该趋近**（共享球A 学到了"好"）；
        single 变体里 5 号球没被训练过、也没有共享球帮忙 ⇒ **该跟基线差不多**。
  另设**无关组合**（两个都没参与任何阶段）当对照。

依赖：numpy ＋ 复用 exp3 的加载/主干/k-WTA。运行：python exp3c_normalize_combo.py
"""

import re
import time
from collections import defaultdict

import numpy as np

from exp3_mb_real_wiring import backbone, kc_pattern, load_graph, pick_readout

K_SPARSE = 0.05
TRIALS = 1200
ETAS = (0.2, 1.0)
W_CLIP = 2000.0
N_NODES = None            # main() 里设定


def norm_glom(g):
    """归一到「完整球」：拆 `+` 多通道；去掉尾部的分区字母（d/v/l/m/a/p）。"""
    out = []
    for part in re.split(r"\s*\+\s*", g):
        m = re.match(r"^([A-Z]+\d+)([a-z])?$", part)
        out.append(m.group(1) if m else part)
    return out


def channels_of(kinds, ids, kind):
    """按**归一后**的球名聚合 PN 节点索引。"""
    chan = defaultdict(list)
    for i, body_id in enumerate(ids):
        if kind[i] == "PN":
            for g in norm_glom(kinds[int(body_id)].split("_")[0]):
                chan[g].append(i)
    # ⚠️ 只留**标准球名**（形如 DL2 / VP1 / DA1）——
    #    否则会混进空串与 `D`/`V`/`LPN`/`MZ` 这类非 glomerulus 命名（实测踩过）
    return {g: v for g, v in chan.items() if v and re.match(r"^[A-Z]{1,3}\d+$", g)}


def drive(pool):
    d = np.zeros(N_NODES)
    for i in pool:
        d[i] = 1.0
    return d


def make_learner(p2k, k2m, readout, k, normalize, eta):
    """可塑读出。⚠️ 权重只在 `w[...]` 上原地改 —— 绝不用裸 `w *= ...`（会重绑定名字）。"""
    w = k2m[:, 2].astype(float).copy()
    w0 = float(w.sum())
    ks, kd = k2m[:, 0].astype(int), k2m[:, 1].astype(int)

    def margin_of(pool):
        s = kc_pattern(p2k, drive(pool), k)
        x = np.zeros(N_NODES)
        np.add.at(x, kd, w * s[ks])
        return s, float(x[readout[0]] - x[readout[1]])

    def learn(s, margin, want_approach):
        j = readout[0] if margin >= 0 else readout[1]
        m = kd == j
        w[m] = w[m] + eta * (1.0 if want_approach else -1.0) * s[ks[m]]
        np.clip(w, 0.0, W_CLIP, out=w)
        if normalize:
            w[:] *= w0 / max(w.sum(), 1e-9)   # 原地

    return margin_of, learn


def run_arm(p2k, k2m, readout, k, normalize, eta, train_set, probes):
    margin_of, learn = make_learner(p2k, k2m, readout, k, normalize, eta)
    base = {name: margin_of(pool)[1] for name, pool in probes.items()}
    trail = []
    for t in range(TRIALS):
        pool, want = train_set[t % len(train_set)]
        s, mg = margin_of(pool)
        trail.append((mg >= 0) == want)
        learn(s, mg, want)
    after = {name: margin_of(pool)[1] for name, pool in probes.items()}
    n = len(train_set) * 3
    return {"acc": float(np.mean(trail)),
            "first": float(np.mean(trail[:n])), "last": float(np.mean(trail[-n:])),
            "base": base, "after": after}


def main():
    global N_NODES
    t0 = time.perf_counter()
    np.random.seed(20260927)
    print("=" * 74)
    print("exp3c · 通道名归一 + 类别结构(combo) + 归一化开关")
    print("=" * 74)

    src, dst, w, ids, pos, kinds = load_graph()
    kind, p2k, k2m = backbone(ids, pos, kinds, src, dst, w)
    N_NODES = len(kind)
    readout = pick_readout(k2m)
    k = max(1, int(K_SPARSE * len(set(k2m[:, 0].astype(int)))))

    chan = channels_of(kinds, ids, kind)
    order = sorted(chan, key=lambda g: -len(chan[g]))
    print(f"\n[归一] 球数 {len(chan)}（此前 raw 前缀 64 ⇒ 合并分区后减少）")
    print(f"[取用] PN 数最多的 10 个球：" + " ".join(f"{g}={len(chan[g])}" for g in order[:10]))
    sg, sb = order[0], order[1]                     # 共享球（好 / 坏）
    gA, gB, gE = order[2], order[3], order[4]       # 好：训练两个 + 泛化一个
    bC, bD, bF = order[5], order[6], order[7]       # 坏：训练两个 + 泛化一个
    u1, u2 = order[8], order[9]                     # 无关对照

    def P(*gs):
        out = []
        for g in gs:
            out += chan[g]
        return out

    probes = {"泛化(好共享+新特异)": P(sg, gE), "泛化(坏共享+新特异)": P(sb, bF),
              "无关组合": P(u1, u2)}
    single_probes = {"泛化探针(仅新特异球)": P(gE), "无关组合": P(u1, u2)}

    combo_train = [(P(sg, gA), True), (P(sg, gB), True), (P(sb, bC), False), (P(sb, bD), False)]
    single_train = [(P(sg), True), (P(gA), True), (P(sb), False), (P(bC), False)]

    def jac(a, b_):
        u = (a | b_).sum()
        return float((a & b_).sum() / u) if u else 0.0

    pa = {g: kc_pattern(p2k, drive(chan[g]), k) for g in (sg, sb, gA, gB, bC, gE)}
    print(f"\n[结构] KC 模式 Jaccard（归一命名后）:")
    print(f"   共享球 vs 同训练特异的组合内部：{jac(pa[sg] | pa[gA], pa[sg] | pa[gB]):.4f}  ← combo 的『类内』")
    print(f"   好共享球 vs 坏共享球：          {jac(pa[sg], pa[sb]):.4f}  ← 类间")
    print(f"   （single 情形下『类内』就是 {jac(pa[sg], pa[gA]):.4f} —— 两个无关球）")

    print("\n" + "-" * 74)
    print(f"{'变体':<10}{'归一化':<8}{'η':<6}{'训练 前段→后段':<22}{'泛化探针 Δmargin':<20}{'无关 Δmargin'}")
    print("-" * 74)
    rows = []
    for variant, train_set, pr in (("combo", combo_train, probes), ("single", single_train, single_probes)):
        for normalize in (False, True):
            for eta in ETAS:
                r = run_arm(p2k, k2m, readout, k, normalize, eta, train_set, pr)
                gen_name, ctrl_name = list(pr)[0], list(pr)[1]
                dg = r["after"][gen_name] - r["base"][gen_name]
                dc = r["after"][ctrl_name] - r["base"][ctrl_name]
                rows.append((variant, normalize, eta, r, gen_name, dg, ctrl_name, dc))
                flag = "✅" if dg > dc + 20 else ""
                print(f"{variant:<10}{('开' if normalize else '关'):<8}{eta:<6}"
                      f"{r['first']:>7.1%} → {r['last']:<9.1%}"
                      f"{dg:>+12.0f}（基线 {r['base'][gen_name]:>7.0f}）"
                      f"{dc:>+12.0f} {flag}")

    print("\n[读法] '泛化探针 Δmargin' **明显大于** '无关 Δmargin' ⇒ 才算真泛化（不是整体推高）")
    print(f"\n[耗时] {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
