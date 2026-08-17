"""ZG-27 shrinker 两相回收接口（对标 Linux mm/shrinker.c）。

Linux 源码参考：
- include/linux/shrinker.h:82 — struct shrinker count_objects/scan_objects
- include/linux/shrinker.h:58-59 — SHRINK_STOP / SHRINK_EMPTY
- include/linux/shrinker.h:119 — DEFAULT_SEEKS=2
- mm/shrinker.c:374 — SHRINK_BATCH=128
- mm/shrinker.c:376 — do_shrink_slab 两相回收
"""

from dataclasses import dataclass
from typing import Protocol


SHRINK_STOP = -1
"""scan_objects 返回终止信号（对标 shrinker.h:58）"""

SHRINK_EMPTY = -2
"""count_objects 返回空信号（对标 shrinker.h:59）"""

DEFAULT_SEEKS = 2
"""默认重建成本（对标 shrinker.h:119）"""

SHRINK_BATCH = 128
"""默认批次大小（对标 shrinker.c:374）"""


@dataclass
class ShrinkControl:
    """shrinker 回收控制参数（对标 Linux shrinker.h:34 struct shrink_control）。

    nr_to_scan 由调度器设置，nr_scanned 由 callee 填充。
    """

    nr_to_scan: int = 0
    """本次计划扫描数（调度器设置）"""
    nr_scanned: int = 0
    """实际扫描数（callee 填充）"""
    priority: int = 12
    """当前 priority（DEF_PRIORITY 起始）"""


class Shrinker(Protocol):
    """shrinker 两相回收接口（对标 Linux include/linux/shrinker.h:82 struct shrinker）。

    count_objects（相一：轻量预估可释放数）→ scan_objects（相二：实际释放）。
    count_objects 返回 0/SHRINK_EMPTY 时跳过 scan_objects。
    """

    name: str
    batch: int
    """0 = 默认 SHRINK_BATCH=128"""
    seeks: int
    """重建成本（DEFAULT_SEEKS=2，纯缓存=1，向量=8）"""
    flags: int
    """保留位"""

    async def count_objects(self, sc: ShrinkControl) -> int:
        """相一：轻量预估可释放数（不做死锁检查）。

        返回 0 或 SHRINK_EMPTY 表示无可释放对象。
        """
        ...

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """相二：实际释放（仅当 count_objects 返回非零才调用）。

        返回 SHRINK_STOP 表示终止扫描。正数表示实际释放数。
        """
        ...