#!/usr/bin/env python3
"""social_rel · s5.6（v2）—— 综合实验：有效组件的同系统消融

v1 记录：① 格式串踩 %（今天第 4 次——本版全 f-string）；② margin 阈值固定 0.02 过大 → c 臂拒答 100%。
修法：两遍结构——先跑完收集所有 margin，按 10% 分位定 θ，再统计 c 臂。

三臂（同世界同查询流，公平对照）：
  a. base      sim 排序 top5
  b. +grace    G=2（s5.5 组件）
  c. +margin   b 之上：margin(=(s1-s2)/s1) < θ(10% 分位) ⇒ 拒答（s5.3 组件在 sim 分上的复检）

预登记判据：
  P1  b vs a：噪声↓ 且 命中↑
  P2  c：拒答率 ≤10% 且 命中率（全查询口径）≥ b 的 90%
  P3  c：噪声率 ≤ b（拒答拦掉的包含错误侧）

Run: ../../.venv/Scripts/python.exe integrated_system.py
"""

import numpy as np
import pathlib

N_STABLE = 300
D_DIM = 256
N_CLUSTER = 10
NEW_PER_ROUND = 30
N_ROUND = 10
Q_PER_ROUND = 50
K = 5
SEED = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x69_integrated_counts.csv')


def main():
    rng = np.random.RandomState(SEED)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_STABLE)
    stable = centers[labels] + rng.normal(0, 0.3, (N_STABLE, D_DIM))
    stable /= (np.linalg.norm(stable, axis=1, keepdims=True) + 1e-9)

    new_vecs, add_rounds, new_kind, new_true_label = [], [], [], []
    per_q = []  # (top_a, top_b, margin_b, qi)  注：top 为 [(kind, idx)]

    def make_top(grace_g, qi, sims_s):
        cand = [("s", i, float(sims_s[i])) for i in range(N_STABLE)]
        for j in range(len(new_vecs)):
            if add_rounds[j] > r - grace_g:
                continue
            cand.append(("n", j, float(new_vecs[j] @ q)))
        cand.sort(key=lambda t: -t[2])
        return cand

    for r in range(N_ROUND):
        for _ in range(NEW_PER_ROUND):
            fake = rng.random() < 0.55
            c = rng.randint(0, N_CLUSTER)
            sigma = 0.25 if fake else 0.35
            v = centers[c] + rng.normal(0, sigma, D_DIM)
            v /= (np.linalg.norm(v) + 1e-9)
            if fake:
                other = c
                while other == c:
                    other = rng.randint(0, N_CLUSTER)
                new_true_label.append(other)
            else:
                new_true_label.append(c)
            new_vecs.append(v)
            add_rounds.append(r)
            new_kind.append("fake" if fake else "true")

        for _ in range(Q_PER_ROUND):
            qi = rng.randint(0, N_STABLE)
            q = stable[qi]
            sims_s = stable @ q
            sims_s[qi] = -2.0
            cand_a = make_top(0, qi, sims_s)
            cand_b = make_top(2, qi, sims_s)
            m_b = (cand_b[0][2] - cand_b[1][2]) / (cand_b[0][2] + 1e-12) if len(cand_b) >= 2 else 0.0
            per_q.append((cand_a[:K], cand_b[:K], m_b, qi))

    margins = np.array([m for (_, _, m, _) in per_q])
    theta = float(np.quantile(margins, 0.10))
    print("=== s5.6 v2: integrated ablation ===")
    print(f"queries={len(per_q)} | theta(margin reject, 10% quantile)={theta:.6f}")
    print()

    stats = {"a": dict(noise=0, hit=0, kept=0, rej=0), "b": dict(noise=0, hit=0, kept=0, rej=0), "c": dict(noise=0, hit=0, kept=0, rej=0)}

    def score_top(top, qi):
        h = nz = 0
        for t in top:
            if t[0] == "s" and labels[t[1]] == labels[qi]:
                h += 1
            elif t[0] == "n":
                j = t[1]
                if new_kind[j] == "fake":
                    nz += 1
                elif new_true_label[j] == labels[qi]:
                    h += 1
        return h, nz

    for (top_a, top_b, m_b, qi) in per_q:
        for arm, top in (("a", top_a), ("b", top_b)):
            h, nz = score_top(top, qi)
            stats[arm]["hit"] += h; stats[arm]["noise"] += nz; stats[arm]["kept"] += 1
        if m_b < theta:
            stats["c"]["rej"] += 1
        else:
            h, nz = score_top(top_b, qi)
            stats["c"]["hit"] += h; stats["c"]["noise"] += nz; stats["c"]["kept"] += 1

    n_q = len(per_q)
    rows = {}
    print(f"{'arm':<5} {'noise_rate':>12} {'hit_rate':>10} {'reject%':>9} {'kept':>6}")
    print("-" * 48)
    for arm in ("a", "b", "c"):
        s = stats[arm]
        slots = s["kept"] * K
        noise_rate = s["noise"] / slots if slots else 0.0
        hit_rate = s["hit"] / (n_q * K)
        rej = 100.0 * s["rej"] / n_q
        rows[arm] = (noise_rate, hit_rate, rej)
        print(f"{arm:<5} {noise_rate:>12.4f} {hit_rate:>10.4f} {rej:>8.1f}% {s['kept']:>6}")
    print()
    P1 = rows["b"][0] < rows["a"][0] and rows["b"][1] > rows["a"][1]
    P2 = rows["c"][2] <= 10.0 and rows["c"][1] >= 0.9 * rows["b"][1]
    P3 = rows["c"][0] <= rows["b"][0]
    print("=== verdict (pre-registered) ===")
    print(f"P1 grace helps (noise down & hit up): {'PASS' if P1 else 'FAIL'}")
    print(f"P2 margin ok (reject<=10pct & hit>=0.9*b): {'PASS' if P2 else 'FAIL'}")
    print(f"P3 noise not worse with margin: {'PASS' if P3 else 'FAIL'}")
    print("(2026-10-14, s5.6 v2)")

    with open(OUT_CSV, 'w', encoding='utf-8') as f:
        f.write("arm,noise,hit,kept,rejected,n_q\n")
        for arm in ("a", "b", "c"):
            s = stats[arm]
            f.write(f"{arm},{s['noise']},{s['hit']},{s['kept']},{s['rej']},{n_q}\n")
    print(f"x69 counts exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
