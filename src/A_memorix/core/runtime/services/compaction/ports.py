"""ZG-N5 压缩升级——Protocol 接口契约。

定义 MemoryStorePort / TokenMeterPort / LlmPort，
对标 dsh compaction-basic 的存储/计量/LLM 调用接口。
"""

from typing import Any, Optional, Protocol, Sequence, runtime_checkable

from .types import (
    CompactionEndEvent,
    CompactionId,
    CompactionRange,
    CompactionStartEvent,
    CompactionSummaryEvent,
    EventSeq,
    ModelRoute,
)


@runtime_checkable
class MemoryStorePort(Protocol):
    """记忆存储端口——事件日志读写 + surface 读写。"""

    async def read_surface_events(self, session_id: str) -> Sequence[Any]:
        """读取 surface 事件序列（模型可见视图）。"""
        ...

    async def read_surface_generation(self, session_id: str) -> int:
        """读取当前 surface replace_generation。"""
        ...

    async def write_compaction_start(
        self,
        session_id: str,
        event: CompactionStartEvent,
    ) -> EventSeq:
        """持久化 compaction/start 事件（durable lock 标记）。"""
        ...

    async def write_compaction_summary(
        self,
        session_id: str,
        event: CompactionSummaryEvent,
    ) -> EventSeq:
        """持久化 compaction/summary 事件。"""
        ...

    async def write_compaction_end(
        self,
        session_id: str,
        event: CompactionEndEvent,
    ) -> EventSeq:
        """持久化 compaction/end 事件。"""
        ...

    async def query_unmatched_starts(self, session_id: str) -> Sequence[CompactionStartEvent]:
        """查询未匹配 compaction/start 标记（durable lock 判定）。"""
        ...

    async def query_latest_end_seed_seq(self, session_id: str) -> Optional[int]:
        """查询最新的 session/end-seed 序号（陈旧判定）。"""
        ...

    async def replace_surface_range(
        self,
        session_id: str,
        range: CompactionRange,
        summary_node_id: str,
        summary_text: str,
        tx_id: CompactionId,
    ) -> int:
        """surface 替换——用摘要节点替换原始范围，返回新 replace_generation。"""
        ...

    async def read_all_events(self, session_id: str) -> Sequence[Any]:
        """读取全部底层日志事件（重放校验用）。"""
        ...


@runtime_checkable
class TokenMeterPort(Protocol):
    """Token 计量端口——压力/保留预算计量。"""

    def count_tokens(self, text: str) -> int:
        """计算文本 token 数。"""
        ...

    def count_events_tokens(self, events: Sequence[Any]) -> int:
        """计算事件序列总 token 数。"""
        ...

    def get_context_window(self, model_route: ModelRoute) -> int:
        """获取模型上下文窗口大小。"""
        ...


@runtime_checkable
class LlmPort(Protocol):
    """LLM 调用端口——摘要生成。"""

    async def summarize(
        self,
        prompt_messages: Sequence[Any],
        model_route: ModelRoute,
    ) -> str:
        """调用 LLM 生成摘要文本。"""
        ...