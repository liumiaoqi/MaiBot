#!/usr/bin/env python3
"""wander-05 — 论文侧专项加强（承 lmq「论文侧刚刚好像没怎么碰运气」）

诊断：wander 系列论文侧每轮仅抽 12 篇（覆盖率 ~0.06%）——出不了大货是数学必然；
      且 wander-01 教训：论文侧真命中全在「擦边分类」（q-fin / eess）。
本轮口径（预登记）：
  ① 加量 8 倍：8 类 × 12 篇 = 96 篇（标题 + 摘要前 180 字符）；
  ② **专挑跨界富矿池**（28 个应用/交叉类，硬随机抽 8）——热门 cs.AI/cs.LG 本轮不参与；
  ③ 目标：验证「擦边专项 + 加量」能否把论文侧命中率拉起来；命中 = 与我们的线
     （记忆/关系/扩散/agent/韧性/决策/情绪/交易）有可引用连接。

随机源：hard_random.py（rdrand）；输出：stdout（另存 wander-05_picks.txt）。
"""
import sys
import re
import html
import pathlib
from concurrent.futures import ThreadPoolExecutor

import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

CATS_EDGE = [
    "q-fin.ST", "q-fin.PM", "q-fin.TR",
    "eess.SY", "eess.SP", "eess.AS",
    "nlin.AO", "nlin.CD",
    "physics.soc-ph", "physics.bio-ph", "physics.data-an",
    "q-bio.NC", "q-bio.QM", "q-bio.PE",
    "cond-mat.dis-nn", "cond-mat.stat-mech", "cond-mat.soft",
    "cs.MA", "cs.SI", "cs.GT", "cs.NE",
    "stat.ME", "stat.TH", "stat.ML",
    "econ.GN", "econ.TH",
    "math.DS", "math.PR",
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) wander/5.0"}
PER_CAT = 12


def pick_k(lst, k):
    n = len(lst)
    limit = (2 ** 64 // n) * n
    seen = set()
    while len(seen) < k:
        v = hr.hw_u64()
        if v < limit:
            seen.add(v % n)
    return [lst[i] for i in sorted(seen)]


def fetch_cat(c):
    try:
        req = urllib.request.Request(f"https://rss.arxiv.org/rss/{c}", headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            xml = r.read().decode('utf-8', 'ignore')
        items = []
        for it in re.findall(r'<item>(.*?)</item>', xml, re.S):
            mt = re.search(r'<title>(.*?)</title>', it, re.S)
            md = re.search(r'<description>(.*?)</description>', it, re.S)
            if mt:
                title = html.unescape(re.sub(r'\s+', ' ', mt.group(1)).strip())
                desc = html.unescape(re.sub(r'\s+', ' ', md.group(1)).strip()) if md else ""
                desc = re.sub(r'^arXiv:\S+\s*Announce Type:\s*\S+\s*', '', desc)
                desc = re.sub(r'^Abstract:\s*', '', desc)
                items.append((title, desc[:180]))
        return c, items
    except Exception as e:
        return c, None


_ = hr.hw_u64()
print(f"== wander-05 · 论文侧专项（source: {hr.source_name}）==")

sel = pick_k(CATS_EDGE, 8)
print(f"擦边富矿池 {len(CATS_EDGE)} 个，硬抽 8 类：{' · '.join(sel)}")

with ThreadPoolExecutor(max_workers=8) as ex:
    fetched = dict(ex.map(fetch_cat, sel))

total = 0
for c in sel:
    items = fetched.get(c)
    if items is None:
        print(f"\n### {c} — 抓取失败")
        continue
    if not items:
        print(f"\n### {c} — 空批")
        continue
    picks = pick_k(items, min(PER_CAT, len(items)))
    total += len(picks)
    print(f"\n### {c}（本批 {len(items)} 条，硬抽 {len(picks)}）")
    for t, d in picks:
        print(f"- {t}")
        print(f"    → {d}")

print(f"\n合计 {total} 篇。done.")
