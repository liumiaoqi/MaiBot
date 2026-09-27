#!/usr/bin/env python3
"""exp3: 果蝇蘑菇体·真接线 —— 嗅-奖励联想学习

背景
----
`snn_behavior/NOTES.md` 的 exp0-2b 走完了 LIF → Braitenberg → STDP → R-STDP，但**骨架都是人造的**
（exp38 也是 8 维人造气味特征）。这一版把骨架换成**真接线**：
`flywire_data/mb_connections.csv` 里落在 **PN→KC→MBON** 主干上的那部分。

核心假设（可证伪）
------------------
**用真接线的蘑菇体 + 奖励调制，能学会「好气味趋近 / 坏气味逃避」。**
证伪条件：训练后正确率不高于 no_learn 基线。

⚠️ 设计上的一次修正（2026-09-27 第一版跑完后改的，原因见 NOTES）
-----------------------------------------------------------------
第一版用 **LIF + 脉冲计数**当读出，结果三组都恰好 50%。诊断查出两层原因：
  1. MBON 层**饱和**（稳态 1359 ≫ 阈值 1），两位读出每步都放电 ⇒ 决策恒为同一侧；
  2. ⭐ **更根本**：这个任务的输入是**静态的**（气味恒定驱动），
     LIF 的时间维**不提供额外判别信息** —— 一旦过阈值就每步都发，脉冲计数退化成常数。
⇒ 所以这一版把读出改成**静态前馈 + argmax**，**并写明"为什么去掉时间维"**，而不是调参把它凑对。

四组对照（每组回答一个具体问题）
--------------------------------
  no_learn    —— 真接线，权重冻结（不会学的果蝇）      ⇒ **基线**
  real        —— 真接线 + KC→MBON 可塑 + 外部奖励       ⇒ **能不能学会**
  random_proj —— **随机投影**置换真接线 + 同学习         ⇒ ⭐ **真接线比随机投影好吗**
                 （经典蘑菇体模型用的就是随机 PN→KC，这一组直接判它的价值）
  shuffle     —— 把 PN→KC 的**目标 KC 打乱**（保权重/保数量） + 同学习
                 ⇒ ⭐ 预期**仍能学**：因为"气味→KC 模式"的**确定性还在**，
                    打乱只是换了一套编码 ⇒ **说明"打乱 targets"不是有效的破坏**
                    （与线虫那条"打乱掉到 1/5"的差异要在这里说清，别混为一谈）

必须写明的两个假设（数据本身没有）
----------------------------------
  1. ⚠️ **没有递质/极性** ⇒ 全部当**兴奋性**（化学突触权重非负，与数据一致）
  2. ⚠️ **切片里 DAN = 0** ⇒ 奖励从**外部**给（±1），顶替三因子调制里的多巴胺（同 exp2b）

依赖：numpy。运行：python exp3_mb_real_wiring.py
"""

import csv
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DATA = HERE / "flywire_data"

TRIALS = 480          # 训练试验数
K_SPARSE = 0.05       # KC 稀疏度：每个气味只让输入最强的 5% KC 激活（k-WTA）
ETAS = (0.05, 0.2, 1.0)   # 扫学习率（避免"没学会只是 η 选错"）
W_CLIP = 2000.0
N_SIDE = 4            # 好/坏气味各取几个嗅小球通道


def load_graph():
    src, dst, w = [], [], []
    with open(DATA / "mb_connections.csv", newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r)
        for a, b, c in r:
            src.append(int(a)); dst.append(int(b)); w.append(float(c))
    src, dst, w = np.array(src), np.array(dst), np.array(w)
    ids = np.unique(np.concatenate([src, dst]))
    pos = {int(v): i for i, v in enumerate(ids)}
    kinds = {int(b): t for b, t, _s in json.load(open(DATA / "mb_neurons.json", encoding="utf-8"))}
    return src, dst, w, ids, pos, kinds


def classify(t):
    if t.startswith("KC"):
        return "KC"
    if t.startswith("MBON"):
        return "MBON"
    if t.endswith("PN"):
        return "PN"
    return None


def backbone(ids, pos, kinds, src, dst, w):
    """抽出 PN→KC 与 KC→MBON 两段（蘑菇体的经典主干）。"""
    kind = np.array([classify(kinds.get(int(i), "")) or "" for i in ids])
    p2k, k2m = [], []
    for e in range(len(src)):
        ks, kd = kind[pos[int(src[e])]], kind[pos[int(dst[e])]]
        if ks == "PN" and kd == "KC":
            p2k.append((pos[int(src[e])], pos[int(dst[e])], w[e]))
        elif ks == "KC" and kd == "MBON":
            k2m.append((pos[int(src[e])], pos[int(dst[e])], w[e]))
    return kind, np.array(p2k), np.array(k2m)


def scramble(p2k, mode, rng):
    """两种"破坏"对照：随机投影 / 打乱目标 KC。两者都**保权重集合与入度分布**。"""
    out = p2k.copy()
    if mode == "random_proj":
        out[:, 0] = rng.permutation(out[:, 0])   # 谁喂它 → 随机
    elif mode == "shuffle":
        out[:, 1] = rng.permutation(out[:, 1])   # 它喂谁 → 随机
    return out


def pick_readout(k2m):
    indeg = Counter(int(d) for _s, d, _w in k2m)
    return [b for b, _ in indeg.most_common(2)]


def odor_channels(kinds, ids, kind):
    """气味 = glomerulus（嗅小球）—— 用 PN 类型名的前缀。⭐ 这一层是真的：DA1_lPN 里 DA1 就是嗅小球。"""
    chan = defaultdict(list)
    for i, body_id in enumerate(ids):
        if kind[i] == "PN":
            chan[kinds[int(body_id)].split("_")[0]].append(i)
    sizes = sorted(chan.items(), key=lambda kv: -len(kv[1]))
    good = [g for g, _ in sizes[:N_SIDE]]
    bad = [g for g, _ in sizes[N_SIDE : 2 * N_SIDE]]
    return chan, good, bad


def kc_pattern(p2k, drive, k):
    """PN 驱动 → KC 稀疏模式（k-WTA）。返回 0/1 向量（长度 = 节点数）。"""
    inp = np.zeros(len(drive))
    np.add.at(inp, p2k[:, 1].astype(int), p2k[:, 2] * drive[p2k[:, 0].astype(int)])
    idx = np.argpartition(inp, -k)[-k:]
    idx = idx[inp[idx] > 0]
    s = np.zeros(len(drive), dtype=bool)
    s[idx] = True
    return s


def train_arm(name, p2k, k2m, chan, good, bad, readout, learn, eta, rng):
    """静态前馈 + 可塑读出。决策 = 两个读出 MBON 谁的输入大。"""
    w = k2m[:, 2].astype(float).copy()
    w0 = w.copy()
    ks, kd = k2m[:, 0].astype(int), k2m[:, 1].astype(int)
    odors = [(g, "good") for g in good] + [(g, "bad") for g in bad]
    k = max(1, int(K_SPARSE * len(set(ks))))

    acc, patterns = [], {}
    for t in range(TRIALS):
        glom, label = odors[t % len(odors)]
        drive = np.zeros(int(max(p2k[:, 0].max(), p2k[:, 1].max(), k2m[:, 0].max(), k2m[:, 1].max())) + 1)
        for i in chan[glom]:
            drive[i] = 1.0
        s = kc_pattern(p2k, drive, k)
        if glom not in patterns:
            patterns[glom] = s.copy()

        x = np.zeros(len(drive))
        np.add.at(x, kd, w * s[ks])
        approach = x[readout[0]] >= x[readout[1]]
        correct = approach == (label == "good")
        acc.append(correct)

        if learn:
            j = readout[0] if approach else readout[1]
            # MB 的标准学习形式：按**当前气味激活的 KC 模式**加强/削弱 → 只改被选中那一位
            mask = kd == j
            w[mask] += eta * (1.0 if correct else -1.0) * s[ks[mask]]
            np.clip(w, 0.0, W_CLIP, out=w)
            w *= w0.sum() / max(w.sum(), 1e-9)   # 稳态可塑性：保住总强度

    L = len(odors) * 2
    return {
        "name": name, "eta": eta,
        "first": float(np.mean(acc[:L])), "last": float(np.mean(acc[-L:])),
        "overall": float(np.mean(acc)),
        "patterns": patterns, "w": w, "w0": w0,
    }


def pattern_stats(patterns, good, bad):
    """⭐ 关键可解释指标：好气味之间的 KC 模式相似度 vs 好-坏之间。任务有没有可学的结构看这里。"""
    def jac(a, b):
        u = (a | b).sum()
        return float((a & b).sum() / u) if u else 0.0
    within = [jac(patterns[good[i]], patterns[good[j]]) for i in range(len(good)) for j in range(i + 1, len(good))]
    across = [jac(patterns[g], patterns[b]) for g in good for b in bad]
    overlap = [jac(patterns[good[i]], patterns[good[j]]) for i in range(len(good)) for j in range(len(good)) if i != j]
    return float(np.mean(within)), float(np.mean(across)), float(np.mean(overlap))


def main():
    t0 = time.perf_counter()
    rng = np.random.default_rng(20260927)
    print("=" * 70)
    print("exp3 · 果蝇蘑菇体（真接线）—— 嗅-奖励联想学习")
    print("=" * 70)

    src, dst, w, ids, pos, kinds = load_graph()
    kind, p2k, k2m = backbone(ids, pos, kinds, src, dst, w)
    print(f"\n[数据] 边 {len(src):,} · 端点 {len(ids):,} · 注释 {len(kinds):,}")
    print(f"[主干] PN {(kind=='PN').sum()} · KC {(kind=='KC').sum()} · MBON {(kind=='MBON').sum()}"
          f" | PN→KC {len(p2k):,} 边 · KC→MBON {len(k2m):,} 边")
    readout = pick_readout(k2m)
    print(f"[读出] KC 输入最多的两个 MBON: {readout}")
    chan, good, bad = odor_channels(kinds, ids, kind)
    print(f"[气味] 嗅小球通道 {len(chan)} 个 → 好 {good} / 坏 {bad}")
    k = max(1, int(K_SPARSE * len(set(k2m[:, 0].astype(int)))))
    print(f"[稀疏] KC 取 top-{k}（{K_SPARSE:.0%}）")
    print(f"[学习率] 扫 η ∈ {ETAS}")

    # 四组
    variants = [
        ("no_learn", None, False),
        ("real", None, True),
        ("random_proj", "random_proj", True),
        ("shuffle", "shuffle", True),
    ]
    results = []
    for name, mode, learn in variants:
        p = p2k if mode is None else scramble(p2k, mode, rng)
        for eta in (ETAS if learn else (0.0,)):
            r = train_arm(name, p, k2m, chan, good, bad, readout, learn, eta, rng)
            results.append(r)
            if name == "real" and eta == ETAS[0]:
                w_ = pattern_stats(r["patterns"], good, bad)
                print(f"\n[模式] KC 模式 Jaccard —— 好-好 {w_[0]:.3f} · 好-坏 {w_[1]:.3f}"
                      f"  ⇒ {'可学（类内>类间）' if w_[0] > w_[1] else '⚠️ 类内不高于类间，任务结构性可疑'}")

    print("\n" + "-" * 70)
    print(f"{'组':<14}{'η':>6}{'开头':>9}{'结尾':>9}{'全程':>9}{'Δ|w|均值':>11}")
    print("-" * 70)
    for r in results:
        d = np.abs(r["w"] - r["w0"]).mean() if r["eta"] else 0.0
        print(f"{r['name']:<14}{r['eta']:>6.2f}{r['first']:>9.1%}{r['last']:>9.1%}{r['overall']:>9.1%}{d:>11.2f}")

    print(f"\n[耗时] {time.perf_counter() - t0:.1f} s")


if __name__ == "__main__":
    main()
