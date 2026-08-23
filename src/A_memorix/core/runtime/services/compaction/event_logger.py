"""ZG-N5 压缩升级——事件日志记录器。

对标 dsh region.ts:189 session.append('compaction/start') + :215 session.append('compaction/end')。
三事件对（start/summary/end）带事务身份 UUID4，持久化到 A_memorix 事件日志。
"""

from datetime import datetime

from .ports import MemoryStorePort
from .types import (
    CompactionEndEvent,
    CompactionId,
    CompactionRange,
    CompactionReason,
    CompactionStartEvent,
    CompactionSummaryEvent,
    EventSeq,
    ModelRoute,
)


class CompactionEventLogger:
    """压缩事件日志记录器——持久化 start/summary/end 事件对。"""

    def __init__(self, memory_store: MemoryStorePort) -> None:
        self._memory_store = memory_store

    async def log_start(
        self,
        tx_id: CompactionId,
        session_id: str,
        range: CompactionRange,
        reason: CompactionReason,
        turn: int | None = None,
    ) -> EventSeq:
        """持久化 compaction/start 事件——durable lock 标记。

        Args:
            tx_id: 事务身份（UUID4）
            session_id: 会话标识
            range: 被压缩范围
            reason: 触发原因
            turn: 当前轮次（可选）

        Returns:
            事件序列标识
        """
        event = CompactionStartEvent(
            tx_id=tx_id,
            session_id=session_id,
            range=range,
            triggered_at=datetime.now(),
            reason=reason,
            turn=turn,
        )
        return await self._memory_store.write_compaction_start(session_id, event)

    async def log_summary(
        self,
        tx_id: CompactionId,
        session_id: str,
        summary: str,
        range_ref: CompactionRange,
        model_route: ModelRoute,
    ) -> EventSeq:
        """持久化 compaction/summary 事件——摘要文本 + 原始范围引用 + 模型路由。

        Args:
            tx_id: 事务身份（与 start 一致）
            session_id: 会话标识
            summary: 摘要文本
            range_ref: 原始范围引用
            model_route: 模型路由

        Returns:
            事件序列标识
        """
        event = CompactionSummaryEvent(
            tx_id=tx_id,
            summary=summary,
            range_ref=range_ref,
            model_route=model_route,
            generated_at=datetime.now(),
            closed=True,
        )
        return await self._memory_store.write_compaction_summary(session_id, event)

    async def log_end(
        self,
        tx_id: CompactionId,
        session_id: str,
        error: str | None = None,
    ) -> EventSeq:
        """持久化 compaction/end 事件——闭合标记。

        Args:
            tx_id: 事务身份（与 start 一致）
            session_id: 会话标识
            error: 错误信息（None 为成功闭合，非 None 为错误闭合）

        Returns:
            事件序列标识
        """
        event = CompactionEndEvent(
            tx_id=tx_id,
            error=error,
        )
        return await self._memory_store.write_compaction_end(session_id, event)