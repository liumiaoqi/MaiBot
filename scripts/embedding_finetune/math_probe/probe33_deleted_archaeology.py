#!/usr/bin/env python3
"""probe33 — 关系大清洗考古（deleted_relations 14868 vs relations 184 · 只读）

承 probe32：W27–W28 两周删除 13703 条（占全部删除 92%）。本挖回答「什么被删了、为什么」。

预登记问题（先写后跑）：
  Q1 confidence 分布对比（删的是不是低置信？）
  Q2 predicate 词频对比（删的是某类关系？）
  Q3 vector_state / vector_error 对比（**假说：清洗 = 向量索引失败条目的批量清理**）
  Q4 端点重复度（删的是不是重复 / 近重关系？）
  Q5 双时间联合：被删关系的「出生」（created_at）与「死亡」（deleted_at）——老少分析
边界：只读（mode=ro）；隐私——仅聚合统计与短样例。
"""
import sqlite3
import collections
import statistics
import datetime

MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'
con = sqlite3.connect(MD, uri=True)
cur = con.cursor()

cols = [r[1] for r in cur.execute('PRAGMA table_info(relations)')]
print('schema:', cols)
for r in cur.execute('SELECT hash, subject, predicate, object, confidence, vector_state FROM relations LIMIT 2'):
    print(' KEEP:', str(r)[:150])
for r in cur.execute('SELECT hash, subject, predicate, object, confidence, vector_state FROM deleted_relations LIMIT 2'):
    print(' DEL :', str(r)[:150])


def grab(t):
    rows = cur.execute(
        f'SELECT confidence, vector_state, vector_error, vector_retry_count, created_at FROM "{t}"'
    ).fetchall()
    confs = [r[0] for r in rows if r[0] is not None]
    return rows, confs


rows_k, conf_k = grab('relations')
rows_d, conf_d = grab('deleted_relations')


def hist(vals, edges):
    out = collections.Counter()
    for v in vals:
        for lo, hi in zip(edges[:-1], edges[1:]):
            if v < hi:
                out[f'[{lo},{hi})'] += 1
                break
        else:
            out[f'>={edges[-1]}'] += 1
    return out


print('\n== Q1 confidence ==')
print(' keep: n', len(conf_k), '| median', round(statistics.median(conf_k), 3) if conf_k else None)
print(' del : n', len(conf_d), '| median', round(statistics.median(conf_d), 3) if conf_d else None)
edges = [0, 0.3, 0.5, 0.7, 0.9, 1.01]
print(' keep hist:', dict(hist(conf_k, edges)))
print(' del  hist:', dict(hist(conf_d, edges)))

print('\n== Q2 predicate ==')
top_k = cur.execute('SELECT predicate, COUNT(*) c FROM relations GROUP BY predicate ORDER BY c DESC LIMIT 8').fetchall()
top_d = cur.execute(
    'SELECT predicate, COUNT(*) c FROM deleted_relations GROUP BY predicate ORDER BY c DESC LIMIT 12'
).fetchall()
print(' keep top:', top_k)
print(' del  top:', top_d)

print('\n== Q3 vector_state / error ==')
vs_k = collections.Counter(r[1] for r in rows_k)
vs_d = collections.Counter(r[1] for r in rows_d)
print(' keep states:', dict(vs_k))
print(' del  states:', dict(vs_d))
ve_d = collections.Counter((r[2] or '(none)')[:50] for r in rows_d)
ve_k = collections.Counter((r[2] or '(none)')[:50] for r in rows_k)
print(' del  errors top:', ve_d.most_common(4))
print(' keep errors top:', ve_k.most_common(3))

print('\n== Q4 端点重复度 ==')
s_k = cur.execute('SELECT subject, COUNT(*) c FROM relations GROUP BY subject ORDER BY c DESC LIMIT 6').fetchall()
s_d = cur.execute(
    'SELECT subject, COUNT(*) c FROM deleted_relations GROUP BY subject ORDER BY c DESC LIMIT 6'
).fetchall()
print(' keep top subj:', [(x[:16], c) for x, c in s_k])
print(' del  top subj:', [(x[:16], c) for x, c in s_d])

print('\n== Q5 双时间 ==')


def fmt(ts):
    return f"{datetime.datetime.fromtimestamp(ts):%Y-%m-%d}" if ts else None


r = cur.execute('SELECT MIN(created_at), MAX(created_at) FROM deleted_relations').fetchone()
print(' del created span:', fmt(r[0]), '→', fmt(r[1]))
r = cur.execute('SELECT MIN(deleted_at), MAX(deleted_at) FROM deleted_relations').fetchone()
print(' del deleted span:', fmt(r[0]), '→', fmt(r[1]))
r = cur.execute('SELECT MIN(created_at), MAX(created_at) FROM relations').fetchone()
print(' keep created span:', fmt(r[0]), '→', fmt(r[1]))

con.close()
print('\ndone (probe33).')
