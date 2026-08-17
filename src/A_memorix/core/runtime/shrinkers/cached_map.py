"""ZG-27 CachedMap shrinker（vector_store._cached_map）。

spec 5.4.1 规则 6：count=1，scan=del _cached_map，seeks=1，priority_score=500。
del 后下次访问自动重建（懒加载）。
"""

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class CachedMapShrinker:
    """vector_store._cached_map shrinker。"""

    name = "cached_map"
    batch = 0
    seeks = 1
    flags = 0

    def __init__(self, vector_store) -> None:
        self._vector_store = vector_store

    async def count_objects(self, sc: ShrinkControl) -> int:
        """相一：1（hasattr(_cached_map) 且非空）。"""
        cm = getattr(self._vector_store, "_cached_map", None)
        return 1 if cm else 0

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """相二：清空 _cached_map（懒加载可重建）。"""
        cm = getattr(self._vector_store, "_cached_map", None)
        if cm:
            if isinstance(cm, dict):
                cm.clear()
            else:
                self._vector_store._cached_map = None
            sc.nr_scanned = 1
            return 1
        sc.nr_scanned = 0
        return 0