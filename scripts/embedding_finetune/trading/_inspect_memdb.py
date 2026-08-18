
import sqlite3, sys
db = r'E:UserslmqMaiBotdatametadatametadata.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print('tables:', tables)
for t in ['relations', 'paragraphs', 'entities']:
    try:
        n = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(t, ':', n, '行')
    except Exception as e:
        print(t, 'err', e)
# 看 relations 的分数分布
try:
    rows = cur.execute("SELECT confidence, status FROM relations LIMIT 5").fetchall()
    print('relations sample:', rows)
    confs = cur.execute("SELECT confidence FROM relations").fetchall()
    import statistics
    vals = [c[0] for c in confs]
    print('confidence: min %.2f max %.2f mean %.2f n=%d' % (min(vals), max(vals), statistics.mean(vals), len(vals)))
except Exception as e:
    print('relations query err:', e)
conn.close()
