"""ZG-N5 压缩升级——持久锁管理器。

对标 dsh region.ts:286 assertCompactionInactive + :305 assertNoActiveCompaction。
以持久化 compaction/start 标记为锁，非内存锁——进程崩溃后重启仍存在。
陈旧标记（位于较新 session/end-seed 之前）不阻塞新压缩。
"""

from typing import Optional

from .ports import MemoryStorePort
from .types import (
    CompactionId,
    CompactionRange,
    CompactionReason,
    CompactionStartEvent,
    LockResult,
    LockStateUnqueryableError,
)


class DurableLockManager:
    """持久锁管理器——以 compaction/start 标记为锁。"""

    def __init__(self, memory_store: MemoryStorePort) -> None:
        self._memory_store = memory_store

    async def acquire(
        self,
        session_id: str,
        tx_id: CompactionId,
        range: CompactionRange,
        reason: CompactionReason,
    ) -> LockResult:
        """获取持久锁——查询未匹配 start 标记，陈旧不阻塞，非陈旧返回 busy。

        Args:
            session_id: 会话标识
            tx_id: 事务身份
            range: 被压缩范围
            reason: 触发原因

        Returns:
            LockResult(acquired=True) 获取成功
            LockResult(acquired=False) 锁占用（busy）

        Raises:
            LockStateUnqueryableError: 锁标记查询失败（不假设无锁）
        """
        try:
            unmatched_starts = await self._memory_store.query_unmatched_starts(session_id)
            latest_end_seed_seq = await self._memory_store.query_latest_end_seed_seq(session_id)
        except Exception as exc:
            raise LockStateUnqueryableError(f"锁状态查询失败: {exc}") from exc

        for unmatched in unmatched_starts:
            if not self.is_stale(unmatched, latest_end_seed_seq):
                return LockResult(acquired=False, tx_id=tx_id)

        return LockResult(acquired=True, tx_id=tx_id)

    async def release(
        self,
        session_id: str,
        tx_id: CompactionId,
        error: str | None = None,
    ) -> None:
        """释放锁——记录 compaction/end 闭合标记。

        Args:
            session_id: 会话标识
            tx_id: 事务身份
            error: None 为成功闭合，非 None 为错误闭合（保留阻塞标记）
        """
        # compaction/end 事件由 CompactionEventLogger.log_end 写入
        # 失败时（error 非 None）保留未匹配 start 标记阻塞后续
        # 成功时（error None）start 已被 summary 匹配，锁自然释放
        pass

    def is_stale(
        self,
        unmatched_start: CompactionStartEvent,
        latest_end_seed_seq: Optional[int],
    ) -> bool:
        """判定陈旧——unmatched_start.seq < latest_end_seed_seq。

        位于较新 session/end-seed 之前的未匹配 start 属先前生命周期残留。

        Args:
            unmatched_start: 未匹配的 compaction/start 标记
            latest_end_seed_seq: 最新的 session/end-seed 序号

        Returns:
            True 为陈旧（不阻塞），False 为活跃（阻塞）
        """
        if latest_end_seed_seq is None:
            return False
        return unmatched_start.seq < latest_end_seed_seq