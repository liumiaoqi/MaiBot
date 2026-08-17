"""ZG-28 节点缓存（单例，容量 1，TTL 300s + 失效订阅）。

单例无 max_entries/LRU 淘汰——节点列表整体缓存，变更时 invalidate() 清空。
TTL 300s 兜底（失效信号丢失时最长 300s 后过期重新拉）。
"""

import time
from typing import List, Optional, Tuple


class NodeCache:
    """graph_store 节点列表单例缓存。"""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._entry: Optional[Tuple[float, List[str]]] = None
        self._ttl_seconds = ttl_seconds

    def get(self) -> Optional[List[str]]:
        """命中返回缓存节点列表，过期/未命中返回 None。"""
        if self._entry is None:
            return None
        expire_time, nodes = self._entry
        if expire_time < time.monotonic():
            self._entry = None
            return None
        return nodes

    def put(self, nodes: List[str]) -> None:
        """写入缓存（覆盖旧缓存，容量 1）。"""
        self._entry = (time.monotonic() + self._ttl_seconds, nodes)

    def invalidate(self) -> None:
        """graph_store 节点变更时调，清空缓存。"""
        self._entry = None