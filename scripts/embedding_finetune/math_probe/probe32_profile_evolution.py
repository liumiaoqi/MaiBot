#!/usr/bin/env python3
"""probe32 — 画像演化首挖（person_profile_snapshots · 只读）

对象：`data/MaiMBot/a-memorix/metadata/metadata.db` · person_profile_snapshots
      （1220 条 / 13 人；来自 3.5 个月真实运行史 05-07 → 07-22）
预登记（先写后跑）：
  R1 **版本节律**：最长序列（877 版那位）的 updated_at 间隔分布——更新频率画像；
  R2 **漂移曲线**：相邻版 profile_text 的字符集 Jaccard 差异——形状判定（渐进 / 阶跃 / 周期），
     阶跃 = diff > 2×中位数的转移点（"重写时刻"）；
  R3 **关系边演化**：relation_edges_json 每版边数序列（增长曲线）；
  R4 **首尾对比**：v1 vs v_last 的（长度 / 边数 / 别名数）三元组——"从什么样到什么样"（统计口径）。
边界：**只读**（mode=ro）；**隐私**——产出仅统计与短引，不复制画像原文。
"""
import sqlite3
import json
import statistics
from datetime import datetime

MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'
con = sqlite3.connect(MD, uri=True)
cur = con.cursor()

# 〇、快照分布
rows = cur.execute(
    'SELECT person_id, COUNT(*) c FROM person_profile_snapshots GROUP BY person_id ORDER BY c DESC'
).fetchall()
print(f"== persons with snapshots: {len(rows)}")
for pid, c in rows:
    print(f"  {pid[:14]}…: {c}")

target = rows[0][0]
print(f"\n== target {target[:14]}… ==")

snaps = cur.execute(
    'SELECT profile_version, updated_at, length(profile_text), relation_edges_json, aliases_json '
    'FROM person_profile_snapshots WHERE person_id=? ORDER BY profile_version', (target,)
).fetchall()
texts = [r[0] for r in cur.execute(
    'SELECT profile_text FROM person_profile_snapshots WHERE person_id=? ORDER BY profile_version',
    (target,))]


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00').strip())
    except Exception:
        return None


# R1 节律
dts = [parse_dt(s[1]) for s in snaps]
dts_ok = [d for d in dts if d]
print(f"versions: {len(snaps)} | parsed times: {len(dts_ok)}")
if len(dts_ok) >= 2:
    print(f"time span: {dts_ok[0]}  →  {dts_ok[-1]}")
    gaps = [(dts_ok[i + 1] - dts_ok[i]).total_seconds() / 3600 for i in range(len(dts_ok) - 1)]
    gaps_s = [g for g in gaps if g > 0]
    if gaps_s:
        print(f"gap hours: median {statistics.median(gaps_s):.2f} | mean {statistics.mean(gaps_s):.2f} "
              f"| max {max(gaps_s):.1f} | zero-gaps {sum(1 for g in gaps if g == 0)}")

# R2 漂移曲线
lens = [s[2] for s in snaps]
print(f"\nprofile length: first {lens[0]} → last {lens[-1]} | min {min(lens)} max {max(lens)}")


def jac(a, b):
    sa, sb = set(a), set(b)
    return 1 - len(sa & sb) / max(1, len(sa | sb))


diffs = [jac(texts[i], texts[i + 1]) for i in range(len(texts) - 1)]
print(f"adjacent diff (Jaccard): median {statistics.median(diffs):.3f} | mean {statistics.mean(diffs):.3f} "
      f"| p90 {sorted(diffs)[int(0.9 * len(diffs))]:.3f} | max {max(diffs):.3f}")
thr = max(0.001, 2 * statistics.median(diffs))
steps = [(i + 2, round(diffs[i], 3)) for i in range(len(diffs)) if diffs[i] > thr]
print(f"step-like transitions (diff>{thr:.3f}): {len(steps)} / {len(diffs)}")
print("  top 8:", sorted(steps, key=lambda x: -x[1])[:8])

# R3 关系边演化
def n_edges(js):
    try:
        d = json.loads(js)
        if isinstance(d, list):
            return len(d)
        if isinstance(d, dict):
            return sum(len(v) if isinstance(v, list) else 1 for v in d.values())
        return -1
    except Exception:
        return -1


ecounts = [n_edges(s[3]) for s in snaps]
print(f"\nrelation_edges: first {ecounts[0]} → last {ecounts[-1]} | min {min(ecounts)} max {max(ecounts)}")

# R4 首尾
def n_aliases(js):
    try:
        return len(json.loads(js)) if js else 0
    except Exception:
        return -1


al = [n_aliases(s[4]) for s in snaps]
print(f"aliases: {al[0]} → {al[-1]}")
print(f"\n== v1 → v{len(snaps)}: len {lens[0]}→{lens[-1]} | edges {ecounts[0]}→{ecounts[-1]} | aliases {al[0]}→{al[-1]} ==")

con.close()
print("\ndone (probe32).")
