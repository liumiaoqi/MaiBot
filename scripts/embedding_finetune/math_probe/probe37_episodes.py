#!/usr/bin/env python3
"""probe37 — 情节（episodes）结构画像——数据宝库最后一块大表（只读）

对象：metadata.db 的 episodes（694）/ episode_paragraphs（540）/ episode_pending_paragraphs（688）
预登记：
  E1 时间线：episodes.created_at 的周分布（与消息/画像/治理的时间轴对照）
  E2 规模结构：每 episode 关联段落数的分布（情节的"颗粒度"）
  E3 抽样短读：3 个 episode 的字段形状（不发正文）
"""
import sqlite3
import collections
import datetime

MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'
con = sqlite3.connect(MD, uri=True)
cur = con.cursor()

cols = [r[1] for r in cur.execute('PRAGMA table_info(episodes)')]
print('episodes cols:', cols)
for r in cur.execute('SELECT * FROM episodes LIMIT 2'):
    print(' sample:', str(r)[:260])

rows = cur.execute('SELECT created_at FROM episodes').fetchall()
ts = [float(r[0]) for r in rows if r[0]]
print(f"\nE1 时间线: n={len(ts)}")
if ts:
    print(f"  span: {datetime.datetime.fromtimestamp(min(ts)):%Y-%m-%d} → {datetime.datetime.fromtimestamp(max(ts)):%Y-%m-%d}")
    c = collections.Counter(f"{datetime.datetime.fromtimestamp(t):%Y-W%V}" for t in ts)
    for k in sorted(c):
        print(f"  {k}: {c[k]:>4}  {'#' * min(50, c[k] // 3)}")

# E2 每 episode 的段落数
cnt = cur.execute('SELECT episode_id, COUNT(*) c FROM episode_paragraphs GROUP BY episode_id').fetchall()
if cnt:
    sizes = sorted(c for _, c in cnt)
    import statistics
    print(f"\nE2 段落数分布: episodes with paragraphs = {len(sizes)} | "
          f"median {statistics.median(sizes)} | min {sizes[0]} max {sizes[-1]}")
    hist = collections.Counter(min(s // 5 * 5, 40) for s in sizes)
    for k in sorted(hist):
        print(f"  {k:>2}-{k+4}: {hist[k]:>4}")

# pending 状态分布
st = collections.Counter(r[0] for r in cur.execute('SELECT status FROM episode_pending_paragraphs'))
print("\npending_paragraphs status:", dict(st))

con.close()
print('\ndone (probe37).')
