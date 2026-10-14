#!/usr/bin/env python3
"""social_rel · bench-1 —— LongMemEval 检索任务首秀

任务：对 500 题中的每题，在 haystack_sessions（~53 会话）里检索出 answer_session_ids。
指标：recall@5 / recall@10 / MRR（答案会话的首次命中排名倒数）。
检索器：TF-IDF（纯 numpy 实现，词级）——本轮目的是"跑通真实数据评估管线"，
      组件级对照（grace/扩散）留 bench-2。

数据：E:/Users/lmq/MaiBot/data/external/bench_datasets/longmemeval_oracle.json（不入库）
Run: ../../.venv/Scripts/python.exe bench_longmemeval.py
"""

import json
import re
import pathlib
from collections import Counter

import numpy as np

DATA = pathlib.Path(r'E:/Users/lmq/MaiBot/data/external/bench_datasets/longmemeval_s_cleaned.json')
OUT = pathlib.Path(r'E:/Users/lmq/MaiBot/scripts/embedding_finetune/math_probe/py_bench1_output.txt')
TOPK = (5, 10)

WORD_RE = re.compile(r"[a-z0-9']+")


def tokens(text):
    return WORD_RE.findall(text.lower())


def session_text(sess):
    """haystack_sessions 里一个会话：list of turns（dict 带 role/content 或直接 str）"""
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
    n = len(data)
    print(f"=== bench-1: LongMemEval retrieval ({n} questions) ===")

    rows = []
    for qi, item in enumerate(data):
        q_tok = tokens(item["question"])
        sesss = item["haystack_sessions"]
        sids = item["haystack_session_ids"]
        ans = set(item["answer_session_ids"])

        # 语料（每会话一篇文档）
        docs = [Counter(tokens(session_text(s))) for s in sesss]
        df = Counter()
        for d in docs:
            for w in d:
                df[w] += 1
        n_doc = len(docs)
        # idf（平滑）
        idf = {w: np.log((1 + n_doc) / (1 + c)) + 1.0 for w, c in df.items()}
        # 文档向量（l2 归一前的 tf-idf）
        dn = []
        for d in docs:
            v = np.array([d[w] * idf.get(w, 0.0) for w in q_tok], dtype=float)
            nrm = np.linalg.norm(v)
            dn.append(v / nrm if nrm > 0 else v)
        qv = np.array([1.0 * idf.get(w, 0.0) for w in q_tok], dtype=float)
        qn = np.linalg.norm(qv)
        qv = qv / qn if qn > 0 else qv
        sims = np.array([float(qv @ dv) for dv in dn])

        order = np.argsort(-sims)
        rank_of_first_hit = None
        for rank, idx in enumerate(order, start=1):
            if sids[idx] in ans:
                rank_of_first_hit = rank
                break
        r5 = 1 if any(sids[i] in ans for i in order[:5]) else 0
        r10 = 1 if any(sids[i] in ans for i in order[:10]) else 0
        rows.append((r5, r10, (1.0 / rank_of_first_hit) if rank_of_first_hit else 0.0))

    arr = np.array(rows, dtype=float)
    print(f"recall@5  = {arr[:,0].mean():.4f}")
    print(f"recall@10 = {arr[:,1].mean():.4f}")
    print(f"MRR       = {arr[:,2].mean():.4f}")
    print()
    print("reference (published): Zep/Graphiti ~0.64-0.84 R@5 range on this bench;")
    print("note: TF-IDF baseline is expected to be far below neural retrievers —")
    print("this run's purpose = pipeline works on real data (bench-2 adds our components).")
    print("(2026-10-14, bench-1)")

    OUT.write_text(
        f"recall@5={arr[:,0].mean():.4f}\nrecall@10={arr[:,1].mean():.4f}\nMRR={arr[:,2].mean():.4f}\n",
        encoding="utf-8")
    print(f"saved: {OUT.name}")


if __name__ == "__main__":
    main()
