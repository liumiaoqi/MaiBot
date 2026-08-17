"""ZG-27 AdjacencyT shrinker（graph_store._adjacency_T）。

spec 5.4.1 规则 5：count=1，scan=置 None + dirty=True，seeks=1，priority_score=500。
置 None + dirty=True 触发下次访问时重建。
"""

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class AdjacencyTShrinker:
    """graph_store._adjacency_T shrinker。"""

    name = "adjacency_t"
    batch = 0
    seeks = 1
    flags = 0

    def __init__(self, graph_store) -> None:
        self._graph_store = graph_store

    async def count_objects(self, sc: ShrinkControl) -> int:
        """相一：1（_adjacency_T is not None）。"""
        return 1 if getattr(self._graph_store, "_adjacency_T", None) is not None else 0

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """相二：置 None + dirty=True（从邻接表重建）。"""
        if getattr(self._graph_store, "_adjacency_T", None) is not None:
            self._graph_store._adjacency_T = None
            if hasattr(self._graph_store, "_adjacency_dirty"):
                self._graph_store._adjacency_dirty = True
            sc.nr_scanned = 1
            return 1
        sc.nr_scanned = 0
        return 0