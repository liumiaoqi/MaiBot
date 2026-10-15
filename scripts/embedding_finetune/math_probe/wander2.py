#!/usr/bin/env python3
"""wander-02 — 广域碰运气 v2（冷门优先分层 + HF 趋势榜）

相对 v1 的改进：
  ① 分类池扩到 59 个；先硬抽 24 个候选分类去抓 RSS；
  ② **按当日批量分层**（热 ≥500 / 中 50–499 / 冷 <50），硬抽 热1+中2+冷3（不足跨层补）——落实"冷门优先"；
  ③ 新增 HF 趋势模型榜（hf-mirror.com API；官方直连不通）；
  ④ GitHub 窗口拉宽到近一月（池 100）。

随机源：hard_random.py（rdrand）；输出：stdout（另存 wander-02_picks.txt）。
"""
import sys
import re
import json
import html
import pathlib
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

CATS = ["cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.RO", "cs.NE", "cs.SI", "cs.MA", "cs.HC",
        "cs.CR", "cs.PL", "cs.LO", "cs.DM", "cs.GT", "cs.DC", "cs.SE", "cs.CY", "cs.IR", "cs.SD",
        "math.NT", "math.CO", "math.LO", "math.DS", "math.PR", "math.OC", "math.ST", "math.GR",
        "math.AP", "math.RT", "math.QA", "math.MG",
        "stat.ML", "stat.ME", "stat.TH",
        "cond-mat.stat-mech", "cond-mat.soft", "cond-mat.dis-nn",
        "quant-ph", "nlin.AO", "nlin.CD",
        "physics.soc-ph", "physics.bio-ph", "physics.data-an",
        "q-bio.NC", "q-bio.QM", "q-bio.PE", "q-bio.BM",
        "q-fin.ST", "q-fin.PM", "q-fin.TR",
        "econ.GN", "econ.TH",
        "eess.SP", "eess.SY", "eess.AS",
        "astro-ph.EP", "astro-ph.CO", "hep-th"]


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
        with urllib.request.urlopen(f"https://rss.arxiv.org/rss/{c}", timeout=15) as r:
            xml = r.read().decode('utf-8', 'ignore')
        titles = []
        for it in re.findall(r'<item>(.*?)</item>', xml, re.S):
            m = re.search(r'<title>(.*?)</title>', it, re.S)
            if m:
                titles.append(html.unescape(re.sub(r'\s+', ' ', m.group(1)).strip()))
        return c, titles
    except Exception as e:
        return c, None


_ = hr.hw_u64()
print(f"== wander-02 (hardware source: {hr.source_name}) ==")

cand = pick_k(CATS, 24)
print(f"候选分类（59 池硬抽 24）: {' · '.join(cand)}")
with ThreadPoolExecutor(max_workers=8) as ex:
    fetched = dict(ex.map(fetch_cat, cand))

ok = {c: t for c, t in fetched.items() if t}
hot = sorted([c for c, t in ok.items() if len(t) >= 500], key=lambda c: -len(ok[c]))
mid = sorted([c for c, t in ok.items() if 50 <= len(t) < 500], key=lambda c: -len(ok[c]))
cold = sorted([c for c, t in ok.items() if len(t) < 50], key=lambda c: -len(ok[c]))
print(f"分层结果: 热 {len(hot)} / 中 {len(mid)} / 冷 {len(cold)}（抓取失败 {len(fetched)-len(ok)}）")

sel = []
for pool, k in ((hot, 1), (mid, 2), (cold, 3)):
    if pool:
        sel += pick_k(pool, min(k, len(pool)))
# 不足时跨层补
while len(sel) < 6 and (hot + mid + cold):
    rest = [c for c in hot + mid + cold if c not in sel]
    if not rest:
        break
    sel.append(pick_k(rest, 1)[0])

print("\n抽中 6 类（冷门优先）:")
for c in sel:
    t = ok[c]
    picks = pick_k(t, min(2, len(t)))
    print(f"\n### {c}（本批 {len(t)} 条）")
    for x in picks:
        print(f"  - {x}")

# HF 趋势榜
print("\n### HF 趋势模型榜（hf-mirror；池 100 硬抽 8）")
try:
    with urllib.request.urlopen(
            "https://hf-mirror.com/api/models?sort=trendingScore&direction=-1&limit=100",
            timeout=15) as r:
        models = json.loads(r.read().decode('utf-8'))
    sel_m = pick_k(models, min(8, len(models)))
    for m in sel_m:
        tags = ",".join(m.get('tags', [])[:4])
        print(f"  - {m['id']}（♥{m.get('likes')} · trend {m.get('trendingScore')} · {tags}）")
except Exception as e:
    print(f"  (HF 抓取失败: {e})")

# GitHub
p = pathlib.Path(r'C:/hub/.scratch/gh-new-0930.json')
if p.exists():
    repos = json.loads(p.read_text(encoding='utf-8'))
    sel_g = pick_k(repos, min(12, len(repos)))
    print(f"\n### GitHub 近一月高星新仓（池 {len(repos)} 硬抽 12）")
    for r in sel_g:
        print(f"  - {r['stargazersCount']}★ {r['fullName']}: {(r.get('description') or '(no desc)')[:150]}")
else:
    print("\n(gh json 缺失，跳过)")

print("\ndone.")
