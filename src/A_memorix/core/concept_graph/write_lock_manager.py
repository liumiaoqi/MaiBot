"""WriteLockManager — 概念节点级写入锁（MF-P2-004）。

并发写入同一概念节点时串行执行；按需排序加锁避免死锁。
超时抛 WriteLockTimeoutError（调用方返回超时错误码）。
"""

import asyncio
from dataclasses import dataclass


class WriteLockTimeoutError(TimeoutError):
    """获取写入锁超时。"""


@dataclass(slots=True)
class WriteLockToken:
    """已持有的写入锁令牌（release 用）。"""

    concept_ids: tuple[str, ...]


class WriteLockManager:
    """概念节点级 asyncio.Lock 管理器。"""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, concept_id: str) -> asyncio.Lock:
        lock = self._locks.get(concept_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[concept_id] = lock
        return lock

    async def acquire(
        self,
        concept_ids: list[str],
        timeout: float = 5.0,
    ) -> WriteLockToken:
        """按序获取全部节点锁（排序防死锁），超时抛 WriteLockTimeoutError。

        Args:
            concept_ids: 涉及的概念节点 id 列表
            timeout: 获取全部锁的总超时（秒）

        Raises:
            WriteLockTimeoutError: 超时未获取到全部锁
        """
        ordered = sorted({cid for cid in concept_ids if cid})
        acquired: list[tuple[str, asyncio.Lock]] = []
        try:
            async with asyncio.timeout(timeout):
                for cid in ordered:
                    lock = self._get_lock(cid)
                    await lock.acquire()
                    acquired.append((cid, lock))
        except TimeoutError:
            # 释放已持有的锁后抛超时（按 cid 精确配对，逆序释放）
            for cid, lock in reversed(acquired):
                lock.release()
                self._maybe_prune(cid, lock)
            raise WriteLockTimeoutError(
                f"写入锁获取超时: concepts={ordered} timeout={timeout}s"
            ) from None
        return WriteLockToken(concept_ids=tuple(ordered))

    def release(self, token: WriteLockToken) -> None:
        """释放令牌持有的全部锁（逆序释放），无等待者时清理字典条目。"""
        for cid in reversed(token.concept_ids):
            lock = self._locks.get(cid)
            if lock is not None and lock.locked():
                lock.release()
                self._maybe_prune(cid, lock)

    def _maybe_prune(self, cid: str, lock: asyncio.Lock) -> None:
        """无等待者且未持有 → 移除字典条目（防无界增长）。

        仅用 lock.locked() 不够：释放后有等待者的锁若移出字典，等待者会
        永远挂在旧锁上。_waiters 是 CPython 实现细节——加 hasattr 防护，
        缺失时保守保留条目（不 prune）。
        """
        if not lock.locked():
            if hasattr(lock, "_waiters") and lock._waiters:
                return
            self._locks.pop(cid, None)
