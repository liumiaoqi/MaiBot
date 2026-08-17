"""ZG-27 PPR 缓存 shrinker（对标 dual_path._ppr_cache TTL 过期回收）。

spec 5.4.1 规则 1：count=超 TTL 条数，scan=pop 过期+超限，seeks=1，priority_score=800。
与既有 256 硬驱逐互补不冲突（design 2.6.4）——仅处理 TTL 过期。

真实 _ppr_cache 结构（dual_path.py:346）：
    Dict[Tuple[Any, ...], Tuple[float, Dict[str, float]]]
    entry[0] = time.monotonic() + ttl_seconds  （过期时间戳，monotonic 时钟）
    entry[1] = dict(scores)                     （PPR 分数）
无 is_pinned 概念——PPR 缓存全是可驱逐的 TTL 条目。
"""

import time

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class PprCacheShrinker:
    """PPR 缓存 shrinker。"""

    name = "ppr_cache"
    batch = 0
    seeks = 1
    flags = 0

    def __init__(self, dual_path_retriever) -> None:
        self._retriever = dual_path_retriever

    def _get_cache(self) -> dict:
        """获取 _ppr_cache dict（容错）。"""
        cache = getattr(self._retriever, "_ppr_cache", None)
        return cache if isinstance(cache, dict) else {}

    @staticmethod
    def _extract_expiry(entry) -> float | None:
        """从缓存条目提取过期时间戳。

        真实结构为 Tuple[float, Dict]（dual_path.py:2437-2440），
        entry[0] 即 monotonic 过期时间戳。
        """
        if isinstance(entry, tuple) and len(entry) >= 1:
            return entry[0]
        return getattr(entry, "expires_at", None)

    async def count_objects(self, sc: ShrinkControl) -> int:
        """相一：超 TTL 条数（遍历 _ppr_cache 检查 expiry < now）。"""
        cache = self._get_cache()
        if not cache:
            return 0
        now = time.monotonic()
        count = 0
        for entry in cache.values():
            expires_at = self._extract_expiry(entry)
            if expires_at is not None and expires_at < now:
                count += 1
        return count

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """相二：pop 过期条目。PPR 缓存无 is_pinned，全部可驱逐。"""
        cache = self._get_cache()
        if not cache:
            return 0
        now = time.monotonic()
        expired_keys = []
        for key, entry in cache.items():
            expires_at = self._extract_expiry(entry)
            if expires_at is not None and expires_at < now:
                expired_keys.append(key)
        for key in expired_keys:
            cache.pop(key, None)
        sc.nr_scanned = len(expired_keys)
        return len(expired_keys)