"""ZG-28 ProfileCache shrinker（ZG-27 Shrinker Protocol 衔接）。

count=超 TTL 条数，scan=pop 过期，seeks=1，priority_score=600。
"""

import time

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class ProfileCacheShrinker:
    """ProfileCache TTL 过期 shrinker。"""

    name = "profile_cache"
    batch = 0
    seeks = 1
    flags = 0

    def __init__(self, profile_cache) -> None:
        self._cache = profile_cache

    async def count_objects(self, sc: ShrinkControl) -> int:
        """超 TTL 条数。"""
        cache_dict = self._cache.cache_dict
        if not cache_dict:
            return 0
        now = time.monotonic()
        return sum(1 for entry in cache_dict.values() if entry[0] < now)

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """pop 过期条目。"""
        cache_dict = self._cache.cache_dict
        if not cache_dict:
            return 0
        now = time.monotonic()
        expired_keys = [key for key, entry in cache_dict.items() if entry[0] < now]
        for key in expired_keys:
            del cache_dict[key]
        sc.nr_scanned = len(expired_keys)
        return len(expired_keys)