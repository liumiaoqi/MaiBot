"""ZG-28 profile 缓存（对齐 PPR 缓存先例，TTL 300s）。

LRU+TTL 双策略。gate 内复用——同一候选在一次 gate 内只构建一次 profile。
"""

import time
from typing import Any, Dict, Optional, Tuple


class ProfileCache:
    """profile 构建结果缓存。"""

    def __init__(self, max_entries: int = 256, ttl_seconds: float = 300.0) -> None:
        self._cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
        self._max_entries = max_entries
        self._ttl_seconds = ttl_seconds

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """命中返回缓存 profile，过期/未命中返回 None。"""
        entry = self._cache.get(key)
        if entry is None:
            return None
        expire_time, profile = entry
        if expire_time < time.monotonic():
            del self._cache[key]
            return None
        return profile

    def put(self, key: str, profile: Dict[str, Any]) -> None:
        """写入缓存，满 max_entries 时 LRU 淘汰。"""
        if len(self._cache) >= self._max_entries and key not in self._cache:
            oldest_key = min(self._cache.items(), key=lambda item: item[1][0])[0]
            del self._cache[oldest_key]
        self._cache[key] = (time.monotonic() + self._ttl_seconds, profile)

    @property
    def size(self) -> int:
        """当前缓存条目数。"""
        return len(self._cache)

    @property
    def cache_dict(self) -> Dict[str, Tuple[float, Dict[str, Any]]]:
        """只读缓存 dict 访问（shrinker 用）。"""
        return self._cache