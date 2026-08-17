"""ZG-28 embedding 缓存（对齐 PPR 缓存 dual_path.py:346-348 先例）。

LRU+TTL 双策略：Dict[key, Tuple[expire_time, value]] + max_entries + TTL。
满 max_entries 时淘汰 expires_at 最小者（等效 LRU by TTL）。
"""

import time
from typing import Any, Dict, Optional, Tuple


class EmbeddingCache:
    """embedding 向量缓存。"""

    def __init__(self, max_entries: int = 256, ttl_seconds: float = 300.0) -> None:
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds

    def get(self, query_hash: str) -> Optional[Any]:
        """命中返回缓存向量，过期/未命中返回 None。"""
        entry = self._cache.get(query_hash)
        if entry is None:
            return None
        expire_time, vector = entry
        if expire_time < time.monotonic():
            del self._cache[query_hash]
            return None
        return vector

    def put(self, query_hash: str, vector: Any) -> None:
        """写入缓存，满 max_entries 时 LRU 淘汰。"""
        if len(self._cache) >= self._max_entries and query_hash not in self._cache:
            oldest_key = min(self._cache.items(), key=lambda item: item[1][0])[0]
            del self._cache[oldest_key]
        self._cache[query_hash] = (time.monotonic() + self._ttl_seconds, vector)

    @property
    def size(self) -> int:
        """当前缓存条目数。"""
        return len(self._cache)

    @property
    def cache_dict(self) -> Dict[str, Tuple[float, Any]]:
        """只读缓存 dict 访问（shrinker 用）。"""
        return self._cache