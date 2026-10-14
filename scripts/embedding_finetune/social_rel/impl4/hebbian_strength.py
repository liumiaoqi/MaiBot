#!/usr/bin/env python3
"""social_rel · s5.4 —— Hebbian 共激活关系强度（方向 A）

假说（学 HeLa-Mem）：把「同一次交互中被一起使用」作为共激活事件，
用共激活（带邻居相关度加权的 Σ_j coact_ij·rel_j）生成的关系强度，
比单边频次计数更接近真值——ρ(派生, rel*) 提升 ≥ 0.05。

装置：自实现合成世界（184 关系 · 300 次交互）。
  每次交互：按 softmax(rel*) 抽 5 个「真命中」；真命中以 p=0.9「被使用」、噪声（另 5 个随机）以 p=0.1 被使用。
  痕迹：freq = 每次被使用 +1；coact_ij = 每次同批被使用 +1（对）
  派生 conf：映射 [0.3, 1]（无痕迹=地板）
真值：rel*（潜变量）。指标：Spearman ρ(conf, rel*)。

x 装置（§9）：导出逐关系聚合 CSV（freq/coact/rel*，184 行）→ wolframscript 独立算 Spearman 对拍。

预登记判据：ρ_coact − ρ_freq ≥ 0.05。

Run: ../../.venv/Scripts/python.exe hebbian_strength.py
"""

import numpy as np
import pathlib

N_REL = 184
N_INTER = 300
K_USE = 5
P_USE_TRUE = 0.9
P_USE_NOISE = 0.1
FLOOR = 0.3
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x67_hebbian_sample.csv')

rng = np.random.RandomState(SEED)


def spearman(a, b):
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    return float((ra @ rb) / (np.sqrt((ra @ ra) * (rb @ rb)) + 1e-12))


def main():
    print("=== s5.4：Hebbian 共激活关系强度（方向 A）===")
    rel = rng.normal(0, 1, N_REL)

    def run(p_use_true):
        rr = np.random.RandomState(SEED + int(p_use_true * 100))
        freq = np.zeros(N_REL)
        coact = np.zeros((N_REL, N_REL))
        for _ in range(N_INTER):
            w = np.exp(rel - rel.max()); w /= w.sum()
            true_hits = rr.choice(N_REL, K_USE, replace=False, p=w)
            noise = rr.choice(N_REL, K_USE, replace=False)
            used = [int(i) for i in true_hits if rr.random() < p_use_true]
            used += [int(i) for i in noise if rr.random() < P_USE_NOISE]
            for i in used:
                freq[i] += 1
            for a in range(len(used)):
                for b in range(a + 1, len(used)):
                    coact[used[a], used[b]] += 1
                    coact[used[b], used[a]] += 1
        cs = coact @ rel
        def to_conf(x):
            z = (x - x.mean()) / (x.std() + 1e-9)
            c = np.full(N_REL, FLOOR)
            c[z > -6] = FLOOR + (1 - FLOOR) / (1 + np.exp(-z[z > -6]))
            return c
        return spearman(to_conf(freq), rel), spearman(to_conf(cs), rel), freq, cs

    print("%-10s %10s %10s %10s" % ("p_use(真)", "rho_freq", "rho_coact", "delta"))
    print("-" * 46)
    store = None
    for p in (0.9, 0.7, 0.6):
        rf, rc, freq, cs = run(p)
        print("%-10.1f %10.4f %10.4f %+10.4f" % (p, rf, rc, rc - rf))
        if p == 0.9:
            store = (freq, cs, rf, rc)
    freq, cs, rho_f, rho_c = store
    print()
    print("=== 判据（预登记）===")
    print("rho_coact - rho_freq >= +0.05（p_use=0.9 主档）: %s" % ("成立" if (rho_c - rho_f) >= 0.05 else "不成立"))
    print("（2026-10-14 · s5.4 · 含 p_use 敏感性扫描）")

    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("freq,coact_strength,rel\n")
        for i in range(N_REL):
            f.write("%.8f,%.8f,%.8f\n" % (freq[i], cs[i], rel[i]))
    print("已导出 x67 对拍样本：%s（%d 行）" % (OUT_CSV.name, N_REL))


if __name__ == "__main__":
    main()
