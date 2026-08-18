"""ZG-27 Cognitive state 过期 shrinker（测试专用，未在生产环境注册）。

spec 5.4.1 规则 2：count=过期条数，scan=resolve 过期，seeks=1，priority_score=700。

本 shrinker 未在 kernel_initializer.init_watermark_reclaim 中注册——认知状态存于
CognitiveStore(SQLite)，无内存 _states dict 可回收。保留此文件仅用于测试 shrinker
接口契约（count_objects/scan_objects）。参见 kernel_initializer.py:662-666。
"""

import time

from src.A_memorix.core.runtime.shrinker import ShrinkControl


class CognitiveStateShrinker:
    """Cognitive state 过期 shrinker。"""

    name = "cognitive_state"
    batch = 0
    seeks = 1
    flags = 0

    def __init__(self, cognitive_stratifier) -> None:
        self._stratifier = cognitive_stratifier

    def _get_states(self) -> dict:
        """获取 cognitive states dict（容错）。"""
        states = getattr(self._stratifier, "_states", None)
        return states if isinstance(states, dict) else {}

    async def count_objects(self, sc: ShrinkControl) -> int:
        """相一：过期条数（expires_at < now）。"""
        states = self._get_states()
        if not states:
            return 0
        now = time.monotonic()
        count = 0
        for entry in states.values():
            expires_at = getattr(entry, "expires_at", None)
            if expires_at is not None and expires_at < now:
                count += 1
        return count

    async def scan_objects(self, sc: ShrinkControl) -> int:
        """相二：resolve 过期条目。"""
        states = self._get_states()
        if not states:
            return 0
        now = time.monotonic()
        resolved = 0
        for key, entry in states.items():
            is_pinned = getattr(entry, "is_pinned", False)
            if is_pinned:
                continue
            expires_at = getattr(entry, "expires_at", None)
            if expires_at is not None and expires_at < now:
                update_fn = getattr(self._stratifier, "update_entry", None)
                if update_fn is not None:
                    try:
                        update_fn(key, status="resolved")
                        resolved += 1
                    except Exception:
                        pass
        sc.nr_scanned = resolved
        return resolved