#!/usr/bin/env python3
"""probe35 — 重写时刻定位：v807/v872 的日历坐标（probe32 遗留 · 只读）

问题：877 版画像的 top 阶跃（v807 0.485 / v872 0.377 / v808 0.348 / v305…）落在什么日历时间？
假说：**与大治理（probe34 的 W27–W28 大标记/清理轮）同期** ⇒「大重写」可能是**系统级事件的产物**，
而非"人的演化"——对"人设漂移研究"的方法学警告（轨迹里混着系统事件成分）。
"""
import sqlite3
import collections
import datetime

MD = 'file:E:/Users/lmq/MaiBot/data/MaiMBot/a-memorix/metadata/metadata.db?mode=ro'
con = sqlite3.connect(MD, uri=True)
cur = con.cursor()

target = cur.execute(
    'SELECT person_id FROM person_profile_snapshots GROUP BY person_id ORDER BY COUNT(*) DESC LIMIT 1'
).fetchone()[0]
rows = cur.execute(
    'SELECT profile_version, updated_at, length(profile_text) FROM person_profile_snapshots '
    'WHERE person_id=? ORDER BY profile_version', (target,)
).fetchall()
ts = [(v, float(t), ln) for v, t, ln in rows if t]


def fmt(t):
    return f"{datetime.datetime.fromtimestamp(t):%Y-%m-%d %H:%M}"


print(f"n versions = {len(ts)}")
if ts:
    print(f"v{ts[0][0]} @ {fmt(ts[0][1])}   →   v{ts[-1][0]} @ {fmt(ts[-1][1])}")

steps = [807, 872, 808, 305, 355, 306, 404]
print("\n== 阶跃版本的日历坐标 ==")
for v in steps:
    hit = [x for x in ts if x[0] == v]
    if hit:
        _, t, ln = hit[0]
        print(f"  v{v}: {fmt(t)}  (len {ln})")

print("\n== 按周版本密度（更新节律的时间轴） ==")
byweek = collections.Counter(f"{datetime.datetime.fromtimestamp(t):%Y-W%V}" for _, t, _ in ts)
for k in sorted(byweek):
    bar = '#' * min(60, byweek[k] // 5)
    print(f"  {k}: {byweek[k]:>4}  {bar}")

print("\n== 阶跃所在周 ==")
step_weeks = []
for v in steps:
    hit = [x for x in ts if x[0] == v]
    if hit:
        step_weeks.append(f"{datetime.datetime.fromtimestamp(hit[0][1]):%Y-W%V}")
print("  ", collections.Counter(step_weeks))

con.close()
print("\ndone (probe35).")
