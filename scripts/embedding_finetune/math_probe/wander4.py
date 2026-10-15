#!/usr/bin/env python3
"""wander-04 — 广域碰运气 v4（祛魅 v2：强/弱词分级）

相对 v3：
  ① 祛魅层修复：红旗词分**强/弱**，解决 v3 的假阳性（"everything" 误伤 "every tool call"）——
     强词（"免费不限量"/"无需登录"/"逆一切"…）→ ⚠️红旗；弱词（"everything"/"一键"/"终极"…）→ ⚠️?（低置信线索，交人复核）
  ② 其余同 v3：热2/中2/冷2 平衡、HF（UA）、GitHub 池 100。

随机源：hard_random.py（rdrand）；输出：stdout（另存 wander-04_picks.txt）。
"""
import sys
import re
import json
import html
import pathlib
import urllib.request
import subprocess
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

FIXED_HOT = ["cs.AI", "cs.LG"]
# 强词：出现即高置信水货信号
RED_STRONG = ["免费不限量", "不限量", "无需登录", "无需注册", "零成本白嫖", "逆一切", "逆向一切",
              "free unlimited", "unlimited free", "no login", "no sign", "no regist"]
# 弱词：低置信线索（可能误伤）——交人复核
RED_WEAK = ["终极", "一键", "revolution", "everything", "all-in-one", "coming soon",
            "blazing", "ultimate", "anything", "无限"]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) wander/4.0"}


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
        titles = []
        for it in re.findall(r'<item>(.*?)</item>', xml, re.S):
            m = re.search(r'<title>(.*?)</title>', it, re.S)
            if m:
                titles.append(html.unescape(re.sub(r'\s+', ' ', m.group(1)).strip()))
        return c, titles
    except Exception:
        return c, None


def fingerprint(full_name, desc):
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{full_name}", "--jq", "{size,language}"],
            capture_output=True, text=True, timeout=20)
        meta = json.loads(out.stdout) if out.stdout.strip() else {}
    except Exception:
        meta = {}
    d = (desc or "").lower()
    strong = [w for w in RED_STRONG if w.lower() in d]
    weak = [w for w in RED_WEAK if w.lower() in d]
    return meta.get("size", "?"), meta.get("language") or "?", strong, weak


_ = hr.hw_u64()
print(f"== wander-04 (hardware source: {hr.source_name}) ==")

cand = FIXED_HOT + pick_k([c for c in CATS if c not in FIXED_HOT], 22)
with ThreadPoolExecutor(max_workers=8) as ex:
    fetched = dict(ex.map(fetch_cat, cand))
ok = {c: t for c, t in fetched.items() if t}
hot = sorted([c for c, t in ok.items() if len(t) >= 500], key=lambda c: -len(ok[c]))
mid = sorted([c for c, t in ok.items() if 50 <= len(t) < 500], key=lambda c: -len(ok[c]))
cold = sorted([c for c, t in ok.items() if len(t) < 50], key=lambda c: -len(ok[c]))
print(f"分层: 热 {len(hot)} / 中 {len(mid)} / 冷 {len(cold)}")

sel = []
for pool in (hot, mid, cold):
    if pool:
        sel += pick_k(pool, min(2, len(pool)))
if len(sel) < 6:
    rest = [c for c in hot + mid + cold if c not in sel]
    while len(sel) < 6 and rest:
        sel.append(pick_k(rest, 1)[0])
        rest = [c for c in rest if c != sel[-1]]

print("\n抽中 6 类（2/2/2）:")
for c in sel:
    t = ok[c]
    picks = pick_k(t, min(2, len(t)))
    print(f"\n### {c}（本批 {len(t)} 条）")
    for x in picks:
        print(f"  - {x}")

print("\n### HF 趋势模型榜（池 100 硬抽 8）")
try:
    req = urllib.request.Request(
        "https://hf-mirror.com/api/models?sort=trendingScore&direction=-1&limit=100",
        headers=UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        models = json.loads(r.read().decode('utf-8'))
    sel_m = pick_k(models, min(8, len(models)))
    for m in sel_m:
        tags = ",".join(m.get('tags', [])[:4])
        print(f"  - {m['id']}（♥{m.get('likes')} · trend {m.get('trendingScore')} · {tags}）")
except Exception as e:
    print(f"  (HF 抓取失败: {e})")

p = pathlib.Path(r'C:/hub/.scratch/gh-new-0930.json')
if p.exists():
    repos = json.loads(p.read_text(encoding='utf-8'))
    sel_g = pick_k(repos, min(12, len(repos)))
    print(f"\n### GitHub 近一月高星新仓（池 {len(repos)} 硬抽 12）——祛魅 v2")
    for r in sel_g:
        size, lang, strong, weak = fingerprint(r['fullName'], r.get('description'))
        tags = ""
        if strong:
            tags += " ⚠️红旗(强):" + str(strong)
        if weak:
            tags += " ⚠️?(弱):" + str(weak)
        print(f"  - {r['stargazersCount']}★ {r['fullName']}: {(r.get('description') or '(no desc)')[:110]}")
        print(f"      ↳ size={size}KB | lang={lang}{tags}")
else:
    print("\n(gh json 缺失，跳过)")

print("\ndone.")
