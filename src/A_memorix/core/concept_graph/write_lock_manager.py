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
        acquired: list[asyncio.Lock] = []
        try:
            async with asyncio.timeout(timeout):
                for cid in ordered:
                    lock = self._get_lock(cid)
                    await lock.acquire()
                    acquired.append(lock)
        except TimeoutError:
            # 释放已持有的锁后抛超时
            for lock in reversed(acquired):
                lock.release()
            raise WriteLockTimeoutError(
                f"写入锁获取超时: concepts={ordered} timeout={timeout}s"
            ) from None
        return WriteLockToken(concept_ids=tuple(ordered))

    def release(self, token: WriteLockToken) -> None:
        """释放令牌持有的全部锁（逆序释放）。"""
        for cid in reversed(token.concept_ids):
            lock = self._locks.get(cid)
            if lock is not None and lock.locked():
                lock.release()
