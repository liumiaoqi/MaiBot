"""接线审计 v2（正确口径）：按 **Pydantic 字段名**在代码里的出现次数判定

口径（上一版错在哪，写清）：
  ✗ v1 拿配置键字符串去 grep `_cfg("...")` ⇒ 报 234 个"从未被读"，但里面含 `memory_fusion.stage`
    等**我已亲手核实被读**的键 ⇒ **口径错**：代码是用 `official_configs.py` 的**字段对象**读配置的 ✓
  ✓ v2 用**字段名**（定义在 official_configs.py）在**别处**的出现次数判定

对照（判据要求）：
  · 正对照（应被判定为"被读"）：`memory_fusion.stage` 别名 `stage` — 实测 `fusion_config.py:47` 读它
  · 负对照（应被判定为"没接线"）：`feedback_correction_episode_query_block_enabled` — 声明+面板展示，判定函数不读
"""
from __future__ import annotations

import re
from pathlib import Path

MAI = Path(r'E:\Users\lmq\MaiBot')
SRC = MAI / 'src'
DEF_FILES = {'official_configs.py', 'config_schema.py'}   # 只算"声明"，不算实现


def main() -> None:
    txt = (SRC / 'config' / 'official_configs.py').read_text(encoding='utf-8', errors='ignore')
    # 形如 `    name: bool = Field(` / `    name: Optional[str] = None`
    fields = sorted(set(re.findall(r'^\s{4}([a-z][a-z0-9_]{3,})\s*:\s*[^=\n]+=', txt, re.M)))
    print(f'   official_configs.py 里的字段 {len(fields)} 个')

    uses: dict[str, list[str]] = {f: [] for f in fields}
    for p in SRC.rglob('*.py'):
        if '__pycache__' in str(p) or p.name in DEF_FILES:
            continue
        t = p.read_text(encoding='utf-8', errors='ignore')
        for f in fields:
            n = len(re.findall(rf'\b{re.escape(f)}\b', t))
            if n:
                uses[f].append(f'{p.relative_to(SRC)}×{n}')

    zero = [f for f in fields if not uses[f]]
    print(f'   **声明后代码里 0 次引用** 的字段 = {len(zero)} 个')
    for f in zero:
        print(f'      {f}')
    print('\n   === 对照 ===')
    for probe in ('stage', 'feedback_correction_episode_query_block_enabled'):
        if probe in uses:
            print(f'      {probe:<52} 引用 {len(uses[probe])} 处 {uses[probe][:3]}')
        else:
            print(f'      {probe:<52} ⚠️ 不在字段表里（可能名字不对）')


if __name__ == '__main__':
    main()
