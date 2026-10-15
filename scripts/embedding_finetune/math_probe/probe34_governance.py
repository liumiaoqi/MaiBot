#!/usr/bin/env python3
"""probe34 — 治理机制细看：标记-删除时序 + 免死名单（承 probe33 · 只读）

预登记问题：
  Q7 `inactive_since` 与 `deleted_at` 的时序——「标记即删」（一轮扫）还是「先标记后批量清」（两阶段）？
  Q8 47 条 pinned 的"免死名单"是什么（谁被钉、钉的哪类关系、何时建的）？
  Q9 三层结构对比：pinned / active-unpinned / deleted 的谓词与时间画像。
边界：只读；隐私——输出为聚合 + 有限短样例。
"""
import sqlite3
import collections
import statistics
import datetime

MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'
con = sqlite3.connect(MD, uri=True)
cur = con.cursor()


def wk(ts):
    return f"{datetime.datetime.fromtimestamp(ts):%Y-W%V}"


def day(ts):
    return f"{datetime.datetime.fromtimestamp(ts):%m-%d}"


# Q7 时序
rows = cur.execute('SELECT inactive_since, deleted_at FROM deleted_relations').fetchall()
iss = [r[0] for r in rows if r[0]]
dd = [r[1] for r in rows if r[1]]
print(f"deleted: n={len(rows)} | has inactive_since: {len(iss)} | has deleted_at: {len(dd)}")
if iss:
    print(f"  inactive_since span: {datetime.datetime.fromtimestamp(min(iss)):%Y-%m-%d} → "
          f"{datetime.datetime.fromtimestamp(max(iss)):%Y-%m-%d}")
if dd:
    print(f"  deleted_at   span: {datetime.datetime.fromtimestamp(min(dd)):%Y-%m-%d} → "
          f"{datetime.datetime.fromtimestamp(max(dd)):%Y-%m-%d}")
both = [(r[0], r[1]) for r in rows if r[0] and r[1]]
if both:
    diffs = sorted((b[1] - b[0]) / 3600 for b in both)
    print(f"  deleted_at - inactive_since (hours): n={len(diffs)} median={statistics.median(diffs):.2f} "
          f"p10={diffs[int(0.1 * len(diffs))]:.2f} p90={diffs[int(0.9 * len(diffs))]:.2f} max={diffs[-1]:.1f}")

c_iss = collections.Counter(wk(t) for t in iss)
c_del = collections.Counter(wk(t) for t in dd)
print("  weekly side-by-side (inactive_since | deleted_at):")
for k in sorted(set(c_iss) | set(c_del)):
    print(f"    {k}: {c_iss.get(k, 0):>6} | {c_del.get(k, 0):>6}")

# Q8 pinned 名单
pinned = cur.execute(
    'SELECT subject, predicate, object, confidence, created_at FROM relations WHERE is_pinned=1 '
    'ORDER BY created_at'
).fetchall()
print(f"\npinned n = {len(pinned)}")
for r in pinned[:18]:
    print(f"  {r[0][:14]}  --{r[1]}-->  {r[2][:16]}  (conf {r[3]})")
pred_p = collections.Counter(r[1] for r in pinned)
print("  predicate dist:", pred_p.most_common(8))
cr = [r[4] for r in pinned if r[4]]
if cr:
    print(f"  created span: {datetime.datetime.fromtimestamp(min(cr)):%m-%d} → "
          f"{datetime.datetime.fromtimestamp(max(cr)):%m-%d}")

# Q9 三层对比
def prof(sql, tag):
    rows = cur.execute(sql).fetchall()
    preds = collections.Counter(r[1] for r in rows)
    cr = [r[2] for r in rows if r[2]]
    print(f"\n[{tag}] n={len(rows)}")
    print("  pred top:", preds.most_common(6))
    if cr:
        print(f"  created span: {datetime.datetime.fromtimestamp(min(cr)):%m-%d} → "
              f"{datetime.datetime.fromtimestamp(max(cr)):%m-%d}")


prof('SELECT subject, predicate, object, created_at FROM relations WHERE is_pinned=1', 'pinned')
prof('SELECT subject, predicate, object, created_at FROM relations WHERE is_pinned=0', 'active-unpinned')
prof('SELECT subject, predicate, object, created_at FROM deleted_relations', 'deleted')

con.close()
print("\ndone (probe34).")
