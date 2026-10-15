#!/usr/bin/env python3
"""wander-06 — 定向漫游（最后碰运气 · 主题：记忆 / 检索 / agent / 图）

承 lmq「在这个方向最后碰碰运气，差不多可以考虑改动 maibot 了」。
相对 wander4 的广域：分类池收窄到目标领域（cs.IR/cs.DB/cs.SI/cs.MA/…），
GitHub 段改**关键词池**（memory agent / retrieval graph / llm memory 近两月高星）。
输出：stdout（另存 wander-06_picks.txt）。
"""
import sys
import re
import json
import html
import pathlib
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr

CATS = ["cs.IR", "cs.DB", "cs.SI", "cs.MA", "cs.CL", "cs.AI", "cs.LG", "cs.NE", "cs.DC", "cs.SE",
        "cs.GT", "cs.CR", "cs.HC", "stat.ML", "stat.ME", "math.OC", "math.PR", "q-bio.NC",
        "eess.SY", "nlin.AO", "physics.soc-ph"]
PER = 8
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) wander/6.0"}


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
        ts = []
        for it in re.findall(r'<item>(.*?)</item>', xml, re.S):
            m = re.search(r'<title>(.*?)</title>', it, re.S)
            if m:
                ts.append(html.unescape(re.sub(r'\s+', ' ', m.group(1)).strip()))
        return c, ts
    except Exception:
        return c, None


_ = hr.hw_u64()
print(f"== wander-06 定向漫游 (source: {hr.source_name}) ==")
sel = pick_k(CATS, 6)
print("抽中分类:", " · ".join(sel))
with ThreadPoolExecutor(max_workers=8) as ex:
    fetched = dict(ex.map(fetch_cat, sel))
for c in sel:
    ts = fetched.get(c)
    if not ts:
        print(f"\n### {c}: 空批/失败")
        continue
    picks = pick_k(ts, min(PER, len(ts)))
    print(f"\n### {c}（本批 {len(ts)} 条，硬抽 {len(picks)}）")
    for t in picks:
        print(f"  - {t}")

print("\n### GitHub 关键词池（近两月高星）")
pool = {}
for kw in ["memory agent", "retrieval graph", "llm memory", "knowledge graph agent"]:
    try:
        out = subprocess.run(
            ["gh", "search", "repos", "--created", ">2026-08-01", "--sort", "stars",
             "--limit", "30", kw, "--json", "fullName,description,stargazersCount"],
            capture_output=True, text=True, timeout=60)
        for r in json.loads(out.stdout or "[]"):
            pool[r['fullName']] = r
    except Exception as e:
        print(f"  (kw '{kw}' 搜索失败: {e})")
repos = list(pool.values())
print(f"  池 {len(repos)} 个（去重）")
for r in pick_k(repos, min(12, len(repos))):
    print(f"  - {r['stargazersCount']}★ {r['fullName']}: {(r.get('description') or '')[:130]}")

print("\n### HF 趋势榜（池 100 抽 8）")
try:
    req = urllib.request.Request(
        "https://hf-mirror.com/api/models?sort=trendingScore&direction=-1&limit=100", headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        models = json.loads(r.read().decode('utf-8'))
    for m in pick_k(models, min(8, len(models))):
        print(f"  - {m['id']}（♥{m.get('likes')} · {','.join(m.get('tags', [])[:4])}）")
except Exception as e:
    print(f"  (HF 失败: {e})")
print("\ndone.")
