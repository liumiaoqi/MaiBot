#!/usr/bin/env python3
"""wander-01 — 广域碰运气（arXiv 随机分类 × GitHub 近周新仓）

机制：硬随机（hard_random.py）——
  ① 从 28 个分类池里抽 6 个分类 → 抓各分类最新 RSS → 每类硬随机抽 2 篇（标题）；
  ② GitHub 近 7 天高星新仓 JSON（gh search 产出）→ 硬随机抽 12 个。
输出：stdout（漫游素材，另存 wander-01_picks.txt）。
"""
import sys
import re
import json
import html
import pathlib
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

CATS = ["cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.NE", "cs.SI", "cs.MA", "cs.HC", "cs.RO",
        "cs.CR", "math.OC", "math.ST", "math.DS", "math.PR", "stat.ML", "stat.ME",
        "cond-mat.stat-mech", "quant-ph", "nlin.AO", "physics.soc-ph",
        "q-bio.NC", "q-bio.QM", "econ.GN", "q-fin.ST", "eess.SP", "eess.SY", "cs.DC", "cs.SE"]


def pick_k(lst, k):
    n = len(lst)
    limit = (2 ** 64 // n) * n
    seen = set()
    while len(seen) < k:
        v = hr.hw_u64()
        if v < limit:
            seen.add(v % n)
    return [lst[i] for i in sorted(seen)]


_ = hr.hw_u64()
print(f"== wander-01 (hardware source: {hr.source_name}) ==")

cats = pick_k(CATS, 6)
print("抽中分类:", " · ".join(cats))

for c in cats:
    try:
        with urllib.request.urlopen(f"https://rss.arxiv.org/rss/{c}", timeout=15) as r:
            xml = r.read().decode('utf-8', 'ignore')
    except Exception as e:
        print(f"\n### {c} — 抓取失败: {e}")
        continue
    items = re.findall(r'<item>(.*?)</item>', xml, re.S)
    titles = []
    for it in items:
        m = re.search(r'<title>(.*?)</title>', it, re.S)
        if m:
            t = html.unescape(re.sub(r'\s+', ' ', m.group(1)).strip())
            titles.append(t)
    if not titles:
        print(f"\n### {c} — 本批无条目（空批？）")
        continue
    sel = pick_k(titles, min(2, len(titles)))
    print(f"\n### {c}（本批 {len(titles)} 条，硬随机抽 {len(sel)}）")
    for t in sel:
        print(f"  - {t}")

p = pathlib.Path(r'C:/hub/.scratch/gh-new-1015.json')
if p.exists():
    repos = json.loads(p.read_text(encoding='utf-8'))
    sel = pick_k(repos, min(12, len(repos)))
    print(f"\n### GitHub 近 7 天新仓（池 {len(repos)}，硬随机抽 {len(sel)}）")
    for r in sel:
        print(f"  - {r['stargazersCount']}★ {r['fullName']}: {(r.get('description') or '(no desc)')[:160]}")
else:
    print("\n(gh-new-1015.json 不存在，跳过 GitHub 段)")

print("\ndone.")
