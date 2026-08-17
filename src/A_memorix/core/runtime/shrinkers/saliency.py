"""ZG-27 Saliency cache shrinker（graph_store._saliency_cache）。

spec 5.4.1 规则 4：count=1（有缓存），scan=置 None，seeks=1，priority_score=500。
置 None 后 dirty 重建逻辑不变（design 2.6.2 不改 #3）。
"""

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class SaliencyCacheShrinker:
    """graph_store._saliency_cache shrinker。"""

    name = "saliency_cache"
    batch = 0
    seeks = 1
    flags = 0

    def __init__(self, graph_store) -> None:
        self._graph_store = graph_store

    async def count_objects(self, sc: ShrinkControl) -> int:
        """相一：1（_saliency_cache is not None）。"""
        return 1 if getattr(self._graph_store, "_saliency_cache", None) is not None else 0

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """相二：置 None（dirty 重建）。"""
        if getattr(self._graph_store, "_saliency_cache", None) is not None:
            self._graph_store._saliency_cache = None
            sc.nr_scanned = 1
            return 1
        sc.nr_scanned = 0
        return 0