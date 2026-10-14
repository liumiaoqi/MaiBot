#!/usr/bin/env python3
"""social_rel · bench-3 —— 扩散探索位在真实数据上（LongMemEval-S）

设计：每题用 TF-IDF 相似度在 ~50 个会话上建 kNN 图（k=4），跑热核扩散（t=2）；
检索 = sim 排序，其中 m 个席位留给扩散激活的会话（排除已在 sim top 的）。
对照臂：m=0（baseline）/ m=1 / m=2；全量 500 题 + preference 子集单列。

判据（预登记）：
  P1  m=1 全量 R@5 ≥ baseline −0.5%
  P2  m=1 在 preference 子集上 R@5 或 MRR 优于 baseline（扩散补语义弱关联的假说）
  P3  m=2 不显著差于 m=1（探索位预算敏感性）

Run: ../../.venv/Scripts/python.exe bench3_diffusion_channel.py
"""

import json
import re
import pathlib
from collections import Counter

import numpy as np

DATA = pathlib.Path(r'E:/Users/lmq/MaiBot/data/external/bench_datasets/longmemeval_s_cleaned.json')
OUT = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/py_bench3_output.txt')
KNN_K = 4
DIFF_T = 2.0

WORD_RE = re.compile(r"[a-z0-9']+")


def tokens(text):
    return WORD_RE.findall(text.lower())


def session_text(sess):
    if isinstance(sess, str):
        return sess
    parts = []
    for turn in sess:
        if isinstance(turn, dict):
            parts.append(str(turn.get("content", "")))
        else:
            parts.append(str(turn))
    return " ".join(parts)


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    print(f"=== bench-3: diffusion channel on LongMemEval-S ({len(data)} questions) ===")

    arms = {"m0": [], "m1": [], "m2": []}   # (r5, r10, mrr, type)

    for item in data:
        q_tok = tokens(item["question"])
        sesss = item["haystack_sessions"]
        sids = item["haystack_session_ids"]
        ans = set(item["answer_session_ids"])
        qtype = item.get("question_type", "?")

        docs = [Counter(tokens(session_text(s))) for s in sesss]
        df = Counter()
        for d in docs:
            for w in d:
                df[w] += 1
        n_doc = len(docs)
        idf = {w: np.log((1 + n_doc) / (1 + c)) + 1.0 for w, c in df.items()}

        # 文档向量（全词表版：q 词 + 扩散用不了全词——用 q 词算相似度作为图边）
        dn = []
        for d in docs:
            v = np.array([d[w] * idf.get(w, 0.0) for w in q_tok], dtype=float)
            nrm = np.linalg.norm(v)
            dn.append(v / nrm if nrm > 0 else v)
        qv = np.array([1.0 * idf.get(w, 0.0) for w in q_tok], dtype=float)
        qn = np.linalg.norm(qv)
        qv = qv / qn if qn > 0 else qv
        sims = np.array([float(qv @ dv) for dv in dn])

        # 会话间图（用 sim 向量距离近似：余弦）
        Sg = np.array(dn) @ np.array(dn).T if len(dn) > 1 else np.zeros((1, 1))
        np.fill_diagonal(Sg, -2.0)
        # 全负（q 词稀疏）时退化为无图——置零处理
        if (Sg.max() <= -1.9) or np.isnan(Sg).any():
            Sg = np.zeros_like(Sg)
        kk = min(KNN_K, max(1, len(dn) - 1))
        knn = np.argpartition(-Sg, kk, axis=1)[:, :kk]
        Wm = np.zeros((len(dn), len(dn)))
        for i in range(len(dn)):
            for j in knn[i]:
                Wm[i, int(j)] = Wm[int(j), i] = 1.0

        # 扩散（seed = sim top1）
        seed = int(np.argmax(sims))
        deg = Wm.sum(1)
        if deg.sum() > 0:
            vl, ul = np.linalg.eigh(np.diag(deg) - Wm)
            p0 = np.zeros(len(dn))
            p0[seed] = 1.0
            coef = ul.T @ p0
            p = ul @ (np.exp(-vl * DIFF_T) * coef)
            p[seed] = -1
            diff_order = np.argsort(-p)
        else:
            diff_order = []

        def evaluate(m):
            sim_order = np.argsort(-sims)
            picks = [int(i) for i in sim_order[: 5 - m]] if m > 0 else [int(i) for i in sim_order[:5]]
            if m > 0 and len(diff_order) > 0:
                picked_set = set(picks)
                for idx in diff_order:
                    idx = int(idx)
                    if idx not in picked_set:
                        picks.append(idx)
                        picked_set.add(idx)
                    if len(picks) >= 5:
                        break
            # 排名（首次命中）用合成序（sim 序里插入扩散位）——简化：用完整排序近似
            r5 = 1 if any(sids[i] in ans for i in picks) else 0
            r10 = 1 if any(sids[i] in ans for i in sim_order[:10]) else 0
            rank_of_first_hit = None
            for rank, idx in enumerate(sim_order, start=1):
                if sids[int(idx)] in ans:
                    rank_of_first_hit = rank
                    break
            mrr = (1.0 / rank_of_first_hit) if rank_of_first_hit else 0.0
            return r5, r10, mrr

        for m, key in ((0, "m0"), (1, "m1"), (2, "m2")):
            r5, r10, mrr = evaluate(m)
            arms[key].append((r5, r10, mrr, qtype))

    print()
    print("%-6s %10s %10s %8s" % ("arm", "R@5", "R@10", "MRR"))
    print("-" * 38)
    res = {}
    for key in ("m0", "m1", "m2"):
        a = np.array([r[:3] for r in arms[key]], dtype=float)
        res[key] = a
        print("%-6s %10.4f %10.4f %8.4f" % (key, a[:,0].mean(), a[:,1].mean(), a[:,2].mean()))
    print()
    print("--- preference subset (n=%d) ---" % sum(1 for r in arms['m0'] if r[3] == 'single-session-preference'))
    for key in ("m0", "m1", "m2"):
        pref = np.array([r[:3] for r in arms[key] if r[3] == 'single-session-preference'], dtype=float)
        if len(pref):
            print("%-6s n=%d R@5 %.4f R@10 %.4f MRR %.4f" % (key, len(pref), pref[:,0].mean(), pref[:,1].mean(), pref[:,2].mean()))
    print()
    base = res["m0"][:,0].mean()
    P1 = res["m1"][:,0].mean() >= base - 0.005
    pref0 = np.array([r[:3] for r in arms["m0"] if r[3] == 'single-session-preference'])
    pref1 = np.array([r[:3] for r in arms["m1"] if r[3] == 'single-session-preference'])
    P2 = (pref1[:,0].mean() > pref0[:,0].mean()) or (pref1[:,2].mean() > pref0[:,2].mean())
    P3 = abs(res["m2"][:,0].mean() - res["m1"][:,0].mean()) <= 0.01
    print("=== verdict (pre-registered) ===")
    print(f"P1 m1 full-set not worse than baseline: {'PASS' if P1 else 'FAIL'}")
    print(f"P2 m1 improves preference subset: {'PASS' if P2 else 'FAIL'}")
    print(f"P3 m2 near m1 (budget sensitivity ok): {'PASS' if P3 else 'FAIL'}")
    print("(2026-10-14, bench-3)")

    OUT.write_text(
        "\n".join(f"{k} R@5={v[:,0].mean():.4f} R@10={v[:,1].mean():.4f} MRR={v[:,2].mean():.4f}"
                  for k, v in res.items()) + "\n",
        encoding="utf-8")
    print(f"saved: {OUT.name}")


if __name__ == "__main__":
    main()
