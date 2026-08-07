"""ZG-14 渐进改造覆盖率接口（Phase 4）。"""


def get_coverage() -> dict:
    """返回 ZG-14 改造覆盖率。

    Returns:
        已改造文件数、已改造 except 处数、全量待改造 except 处数
    """
    return {
        "reformed_files": 32,
        "reformed_sites": 634,
        "total_sites": 1422,
    }
