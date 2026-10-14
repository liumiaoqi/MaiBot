#!/usr/bin/env python3
"""social_rel · s7.1 —— 生长反馈 × 综合系统 v2（s6.1 机制接缝 s5.6/5.7）

背景链：
  s5.6/s5.7 综合系统 v2 = sim + grace + 扩散探索位（三组件同系统消融）；
  s6.1 v8 生长反馈 = 展示-选择反馈（all 口径拒）使 conf 学习（平台=f(信号纯度)）。
本实验把「反馈生长层」装进综合系统，回答：流式世界（fake 持续入场）里
反馈生长还成立吗？与既有组件（grace/扩散位）叠加是否可加？

三臂（同世界、同查询流；用户 rng 独立；各臂交互历史自洽）：
  a  v2 基线        sim + grace                    （不学习）
  b  +反馈          sim×conf + grace + 反馈更新     （学习臂）
  c  +反馈+扩散位    b + 扩散探索位 m=1（seed=加权 top1） （全系统）

反馈：展示后 pu=0.8 选展示中正确者（随机），否则选最前非正确者；
      all 口径——展示未选全拒（+tot），选中者 +pos+tot。
conf = (pos+2)/(tot+2)，未评=1.0（x72 处方）。

预登记判据：
  P1 反馈生长：b hit > a hit
  P2 反馈压噪：b noise ≤ a noise
  P3 全系统：c hit ≥ b hit − 2%（扩散位在反馈之上不亏）

口径注：hit/noise 按各臂实际展示席位数归一（s5.7 用固定 K 为分母，本版修正）。
x76：每轮 CSV → wolframscript 复核（§9）。

Run: ../../.venv/Scripts/python.exe growth_integrated.py
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
GRACE = 2
DIFF_T = 2.0
KNN_K = 6
PU = 0.8
SEED_WORLD = 20261014
SEED_USER = 20261014
OUT_CSV = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/x76_growth_integrated_rounds.csv')


def gen_world():
    """世界生成 + 查询流（与 s5.7 同序同 rng：先加该轮新节点，再生成该轮 queries）。"""
    rng = np.random.RandomState(SEED_WORLD)
    centers = rng.normal(0, 1, (N_CLUSTER, D_DIM))
    labels = rng.randint(0, N_CLUSTER, N_STABLE)
    stable = centers[labels] + rng.normal(0, 0.3, (N_STABLE, D_DIM))
    stable /= (np.linalg.norm(stable, axis=1, keepdims=True) + 1e-9)
    new_vecs, add_rounds, is_fake, new_true_label = [], [], [], []
    queries = []  # (qi, r) 全局顺序
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
            is_fake.append(fake)
        for _ in range(Q_PER_ROUND):
            queries.append((rng.randint(0, N_STABLE), r))
    return (stable, labels, np.array(new_vecs), np.array(add_rounds),
            np.array(is_fake), np.array(new_true_label), queries)


def build_graph(stable, new_vecs):
    nodes = np.vstack([stable, new_vecs])
    n_nodes = nodes.shape[0]
    Sg = nodes @ nodes.T
    np.fill_diagonal(Sg, -2.0)
    knn = np.argpartition(-Sg, KNN_K, axis=1)[:, :KNN_K]
    Wm = np.zeros((n_nodes, n_nodes))
    for i in range(n_nodes):
        for j in knn[i]:
            Wm[i, int(j)] = Wm[int(j), i] = 1.0
    deg = Wm.sum(1)
    vl, ul = np.linalg.eigh(np.diag(deg) - Wm)
    return Wm, vl, ul, n_nodes


def run_arm(arm, stable, labels, new_vecs, add_rounds, is_fake, new_true_label,
            queries, graph=None):
    n_all = N_STABLE + len(new_vecs)
    pos = np.zeros(n_all)
    tot = np.zeros(n_all)
    rng_u = np.random.RandomState(SEED_USER + {"a": 0, "b": 1, "c": 2}[arm])
    m = 1 if arm == "c" else 0
    per_round = []

    def is_true(gi, target):
        if gi < N_STABLE:
            return labels[gi] == target
        j = gi - N_STABLE
        return (not is_fake[j]) and new_true_label[j] == target

    for r in range(N_ROUND):
        hit_r = noise_r = slots_r = 0
        for (qi, rr) in [x for x in queries if x[1] == r]:
            q = stable[qi]
            target = labels[qi]
            sims_s = stable @ q
            sims_s[qi] = -2.0
            s_all = np.concatenate([sims_s, new_vecs @ q])
            # grace 过滤（新节点）
            vis = add_rounds <= (r - GRACE)
            mask = np.concatenate([np.ones(N_STABLE, dtype=bool), vis])
            conf = (pos + 2.0) / (tot + 2.0)
            score = s_all * conf if arm in ("b", "c") else s_all.copy()
            score = np.where(mask, score, -np.inf)
            # sim 部分取前 K-m 席
            order = np.argsort(-score)
            show = []
            for gi in order:
                if not np.isfinite(score[gi]):
                    break
                show.append(int(gi))
                if len(show) == K - m:
                    break
            # 扩散探索位（c 臂）
            if arm == "c":
                Wm, vl, ul, n_nodes = graph
                p0 = np.zeros(n_nodes)
                p0[show[0]] = 1.0
                p = ul @ (np.exp(-vl * DIFF_T) * (ul.T @ p0))
                dord = np.argsort(-p)
                got = 0
                for gi in dord:
                    if got >= m:
                        break
                    gi = int(gi)
                    if gi in show or gi == qi:
                        continue
                    if gi >= N_STABLE:
                        j = gi - N_STABLE
                        if add_rounds[j] > r - GRACE:
                            continue
                    show.append(gi)
                    got += 1
            # 统计
            for gi in show:
                if is_true(gi, target):
                    hit_r += 1
                elif gi >= N_STABLE and is_fake[gi - N_STABLE]:
                    noise_r += 1
            slots_r += len(show)
            # 反馈（b/c）
            if arm in ("b", "c"):
                true_shown = [gi for gi in show if is_true(gi, target)]
                if true_shown and rng_u.random() < PU:
                    pick = int(rng_u.choice(true_shown))
                else:
                    non = [gi for gi in show if not is_true(gi, target)]
                    pick = non[0] if non else show[0]
                for gi in show:
                    if gi != pick:
                        tot[gi] += 1
                tot[pick] += 1
                pos[pick] += 1
        per_round.append((hit_r, noise_r, slots_r))
    return per_round


def main():
    print("=== s7.1: growth feedback x integrated system v2 ===")
    (stable, labels, new_vecs, add_rounds, is_fake, new_true_label, queries) = gen_world()
    print(f"world: {N_STABLE} stable + {len(new_vecs)} streamed nodes"
          f" (fake {(is_fake.sum()/len(is_fake)):.0%}) | queries={len(queries)}"
          f" | grace={GRACE} | pu={PU}")
    graph = build_graph(stable, new_vecs)
    print(f"graph for diffusion arm: {graph[3]} nodes")
    print()
    res = {}
    for arm in ("a", "b", "c"):
        res[arm] = run_arm(arm, stable, labels, new_vecs, add_rounds, is_fake,
                           new_true_label, queries, graph)
    print("%-4s %10s %10s %10s" % ("rnd", "hit_a", "hit_b", "hit_c"))
    print("-" * 38)
    for r in range(N_ROUND):
        row = []
        for arm in ("a", "b", "c"):
            h, nz, sl = res[arm][r]
            row.append(h / sl if sl else 0.0)
        print("%-4d %10.4f %10.4f %10.4f" % (r, row[0], row[1], row[2]))
    print()
    print("%-4s %10s %10s %10s" % ("rnd", "noise_a", "noise_b", "noise_c"))
    print("-" * 38)
    for r in range(N_ROUND):
        row = []
        for arm in ("a", "b", "c"):
            h, nz, sl = res[arm][r]
            row.append(nz / sl if sl else 0.0)
        print("%-4d %10.4f %10.4f %10.4f" % (r, row[0], row[1], row[2]))
    print()
    total = {}
    for arm in ("a", "b", "c"):
        h = sum(x[0] for x in res[arm])
        nz = sum(x[1] for x in res[arm])
        sl = sum(x[2] for x in res[arm])
        total[arm] = (h / sl, nz / sl, sl)
        print(f"{arm}: total hit {h/sl:.4f} | noise {nz/sl:.4f} | slots {sl}")
    print()
    P1 = total["b"][0] > total["a"][0]
    P2 = total["b"][1] <= total["a"][1]
    P3 = total["c"][0] >= total["b"][0] - 0.02
    print("=== verdict (pre-registered) ===")
    print(f"P1 feedback growth (b hit > a): {'PASS' if P1 else 'FAIL'}"
          f" ({total['a'][0]:.4f} -> {total['b'][0]:.4f})")
    print(f"P2 feedback suppresses noise (b <= a): {'PASS' if P2 else 'FAIL'}"
          f" ({total['a'][1]:.4f} -> {total['b'][1]:.4f})")
    print(f"P3 full system (c >= b - 2pct): {'PASS' if P3 else 'FAIL'}"
          f" ({total['b'][0]:.4f} -> {total['c'][0]:.4f})")
    print("(2026-10-14, s7.1)")

    with open(OUT_CSV, 'w', encoding='utf-8', newline='') as f:
        f.write("round,hit_a,noise_a,hit_b,noise_b,hit_c,noise_c\n")
        for r in range(N_ROUND):
            vals = []
            for arm in ("a", "b", "c"):
                h, nz, sl = res[arm][r]
                vals += [h / sl, nz / sl]
            f.write("%d," % r + ",".join("%.6f" % v for v in vals) + "\n")
    print(f"x76 exported: {OUT_CSV.name}")


if __name__ == "__main__":
    main()
