#!/usr/bin/env python3
"""t7_sample.py — 任务书 T7 随机漫游抽样（硬随机器）

从 openai/math 的族目录（CONTENTS.md 解析）里**硬随机**抽取 N 个族，
打印族号 + 标题 + 摘要首句（漫游素材）。

随机源：hard_random.py（RDSEED/RDRAND 机器码注入直读）；rejection sampling（无 modulo bias）。
产出：stdout（另存 `t7_picks.txt`）；观察记录见 social_rel/notes/T7-random-walk.md。
"""
import sys
import re
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import hard_random as hr  # noqa: E402

CONTENTS = pathlib.Path(r'C:/hub/.scratch/openai-math-CONTENTS.md')
N_PICK = 40

text = CONTENTS.read_text(encoding='utf-8')
pat = re.compile(r'\*\*(\d{3})\.\s(.*?)\.\*\*\s(.*?)</', re.S)
fams = {}
for m in pat.finditer(text):
    fid = int(m.group(1))
    if fid not in fams:
        fams[fid] = (m.group(2).strip(), m.group(3).strip())

ids = sorted(fams)
print(f"族总数: {len(ids)}")
assert len(ids) >= 300, "CONTENTS 解析异常"

# —— 硬随机抽样（rejection sampling）——
picks, k = set(), len(ids)
limit = (2**64 // k) * k
while len(picks) < N_PICK:
    v = hr.hw_u64()
    if v < limit:
        picks.add(ids[v % k])

print(f"硬随机源: {hr.source_name} | 抽样 N={len(picks)}")
print("=" * 72)
for i in sorted(picks):
    title, desc = fams[i]
    desc = re.sub(r'<[^>]+>', '', desc)          # 去 HTML 标签
    desc = re.sub(r'\s+', ' ', desc).strip()
    print(f"\n[{i:03d}] {title}")
    print(f"    {desc[:230]}")
print("\n=== done ===")
