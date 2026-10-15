#!/usr/bin/env python3
"""probe36 — 系统运行史第二挖：消耗曲线 + 记忆重组管线（只读）

目标：
  ① llm_usage（15354）——模型调用时序（周聚合 + 模型分布）——与画像爆发月 / 治理轮对照；
  ② episode_rebuild_sources（348）/ episode_pending_paragraphs（688）——「情节重建」管线结构；
  ③ relation_hash_aliases（14984）之谜——「别名」到底是什么。
边界：只读（mode=ro）。
"""
import sqlite3
import collections
import datetime

MB = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/MaiBot.db?mode=ro'
MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'


def wk(s):
    try:
        t = float(s)
        return f"{datetime.datetime.fromtimestamp(t):%Y-W%V}"
    except Exception:
        try:
            return f"{datetime.datetime.fromisoformat(str(s).replace('Z', '').strip()):%Y-W%V}"
        except Exception:
            return '?'


print("========== ① llm_usage ==========")
con = sqlite3.connect(MB, uri=True)
cur = con.cursor()
cols = [r[1] for r in cur.execute('PRAGMA table_info(llm_usage)')]
print('cols:', cols)
for r in cur.execute('SELECT * FROM llm_usage LIMIT 2'):
    print(' sample:', str(r)[:220])
# 周聚合（timestamp 列）
rows = cur.execute('SELECT timestamp, model_name FROM llm_usage').fetchall() if 'model_name' in cols else \
    cur.execute('SELECT timestamp FROM llm_usage').fetchall()
c = collections.Counter(wk(r[0]) for r in rows)
print('weekly calls:')
for k in sorted(c):
    print(f"  {k}: {c[k]:>5}  {'#' * min(50, c[k] // 30)}")
if 'model_name' in cols:
    m = collections.Counter(r[1] for r in rows)
    print('model dist:', m.most_common(8))
elif len(cols) > 2:
    # 猜模型列
    for cand in cols:
        if 'model' in cand.lower():
            m = collections.Counter(r[cols.index(cand)] for r in rows)
            print(f'{cand} dist:', m.most_common(8))
            break
con.close()

print("\n========== ② episode 重建管线 ==========")
con = sqlite3.connect(MD, uri=True)
cur = con.cursor()
for t in ['episode_rebuild_sources', 'episode_pending_paragraphs']:
    cols = [r[1] for r in cur.execute(f'PRAGMA table_info("{t}")')]
    print(f"== {t} cols: {cols}")
    for r in cur.execute(f'SELECT * FROM "{t}" LIMIT 2'):
        print('  sample:', str(r)[:200])
# rebuild_sources 结构聚合（按第一列类型）
cols = [r[1] for r in cur.execute('PRAGMA table_info("episode_rebuild_sources")')]
if cols:
    rows = cur.execute(f'SELECT * FROM episode_rebuild_sources').fetchall()
    print(f"  total rows: {len(rows)}")
    for i, col in enumerate(cols[:4]):
        vals = [str(r[i])[:20] for r in rows]
        c = collections.Counter(vals)
        print(f"  col[{i}] {col} top:", c.most_common(5))

print("\n========== ③ aliases 之谜 ==========")
cols = [r[1] for r in cur.execute('PRAGMA table_info("relation_hash_aliases")')]
print('cols:', cols)
for r in cur.execute('SELECT * FROM relation_hash_aliases LIMIT 3'):
    print('  sample:', str(r)[:200])
rows = cur.execute('SELECT COUNT(DISTINCT hash) FROM relation_hash_aliases').fetchone() \
    if 'hash' in cols else None
print('distinct hash:', rows)
con.close()
print('\ndone (probe36).')
