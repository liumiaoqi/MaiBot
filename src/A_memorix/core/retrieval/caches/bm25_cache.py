"""ZG-28 BM25 缓存（对齐 PPR 缓存先例，TTL 60s 短——对新增文档敏感）。

LRU+TTL 双策略 + clear() 索引变更时清空。
"""

import time
from typing import Any, Dict, List, Optional, Tuple


class Bm25Cache:
    """BM25 检索结果缓存。"""

    def __init__(self, max_entries: int = 256, ttl_seconds: float = 60.0) -> None:
        self._cache: Dict[Tuple[str, int, int, str], Tuple[float, List[Dict[str, Any]]]] = {}
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds

    def get(self, key: Tuple[str, int, int, str]) -> Optional[List[Dict[str, Any]]]:
        """命中返回缓存结果，过期/未命中返回 None。"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        expire_time, results = entry
        if expire_time < time.monotonic():
            del self._cache[key]
            return None
        return results

    def put(self, key: Tuple[str, int, int, str], results: List[Dict[str, Any]]) -> None:
        """写入缓存，满 max_entries 时 LRU 淘汰。"""
        if len(self._cache) >= self._max_entries and key not in self._cache:
            oldest_key = min(self._cache.items(), key=lambda item: item[1][0])[0]
            del self._cache[oldest_key]
        self._cache[key] = (time.monotonic() + self._ttl_seconds, results)

    def clear(self) -> None:
        """索引变更时清空缓存（add/delete paragraph）。"""
        self._cache.clear()

    @property
    def size(self) -> int:
        """当前缓存条目数。"""
        return len(self._cache)

    @property
    def cache_dict(self) -> Dict[Tuple[str, int, int, str], Tuple[float, List[Dict[str, Any]]]]:
        """只读缓存 dict 访问（shrinker 用）。"""
        return self._cache