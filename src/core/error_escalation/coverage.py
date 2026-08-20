"""ZG-14 渐进改造覆盖率接口（Phase 4）。"""

import re
from pathlib import Path


def get_coverage() -> dict:
    """返回 ZG-14 改造覆盖率（真实采集，非硬编码）。

    Returns:
        已改造文件数、已改造 except 处数、全量待改造 except 处数
    """
    src_root = Path(__file__).resolve().parents[3]
    total_sites = 0
    reformed_sites = 0
    reformed_files = 0

    for py_file in src_root.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            except_count = len(re.findall(r'except\s+\w+', content))
            if except_count == 0:
                continue
            pass_count = len(re.findall(r'except\s+\w+.*:\s*\n\s*pass', content))
            total_sites += except_count
            reformed_sites += except_count - pass_count
            if pass_count < except_count:
                reformed_files += 1
        except (OSError, UnicodeDecodeError):
            continue

    return {
        "reformed_files": reformed_files,
        "reformed_sites": reformed_sites,
        "total_sites": total_sites,
    }
