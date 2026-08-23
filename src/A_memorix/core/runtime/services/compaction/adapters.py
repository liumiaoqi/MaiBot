"""ZG-N5 压缩升级——端口适配器。

将 kernel 现有能力适配为 compaction Protocol 接口。
初始实现使用内存存储 + 简单 token 计量——后续可替换为持久化实现。
"""

from typing import Any, Optional, Sequence

from .types import (
    CompactionEndEvent,
    CompactionId,
    CompactionRange,
    CompactionStartEvent,
    CompactionSummaryEvent,
    EventSeq,
    ModelRoute,
)


class InMemoryCompactionStore:
    """内存 compaction 事件存储——初始实现，后续替换为持久化。"""

    def __init__(self) -> None:
        self._events_by_session: dict[str, list[Any]] = {}
        self._compaction_events: dict[str, list[Any]] = {}
        self._surface_generation: dict[str, int] = {}
        self._surface_events: dict[str, list[Any]] = {}
        self._next_seq: int = 0

    async def read_surface_events(self, session_id: str) -> Sequence[Any]:
        return self._surface_events.get(session_id, [])

    async def read_surface_generation(self, session_id: str) -> int:
        return self._surface_generation.get(session_id, 0)

    async def write_compaction_start(
        self,
        session_id: str,
        event: CompactionStartEvent,
    ) -> EventSeq:
        self._next_seq += 1
        event_with_seq = CompactionStartEvent(
            tx_id=event.tx_id,
            session_id=event.session_id,
            range=event.range,
            triggered_at=event.triggered_at,
            reason=event.reason,
            turn=event.turn,
            seq=self._next_seq,
        )
        self._compaction_events.setdefault(session_id, []).append(event_with_seq)
        return EventSeq(seq=self._next_seq, event_type="compaction/start")

    async def write_compaction_summary(
        self,
        session_id: str,
        event: CompactionSummaryEvent,
    ) -> EventSeq:
        self._next_seq += 1
        event_with_seq = CompactionSummaryEvent(
            tx_id=event.tx_id,
            summary=event.summary,
            range_ref=event.range_ref,
            model_route=event.model_route,
            generated_at=event.generated_at,
            closed=event.closed,
            error=event.error,
            seq=self._next_seq,
        )
        self._compaction_events.setdefault(session_id, []).append(event_with_seq)
        return EventSeq(seq=self._next_seq, event_type="compaction/summary")

    async def write_compaction_end(
        self,
        session_id: str,
        event: CompactionEndEvent,
    ) -> EventSeq:
        self._next_seq += 1
        event_with_seq = CompactionEndEvent(
            tx_id=event.tx_id,
            error=event.error,
            seq=self._next_seq,
        )
        self._compaction_events.setdefault(session_id, []).append(event_with_seq)
        return EventSeq(seq=self._next_seq, event_type="compaction/end")

    async def query_unmatched_starts(self, session_id: str) -> Sequence[CompactionStartEvent]:
        events = self._compaction_events.get(session_id, [])
        matched_tx_ids: set[str] = set()
        for e in events:
            if isinstance(e, CompactionEndEvent):
                matched_tx_ids.add(e.tx_id.value)
        return [
            e for e in events
            if isinstance(e, CompactionStartEvent) and e.tx_id.value not in matched_tx_ids
        ]

    async def query_latest_end_seed_seq(self, session_id: str) -> Optional[int]:
        return None

    async def replace_surface_range(
        self,
        session_id: str,
        range: CompactionRange,
        summary_node_id: str,
        summary_text: str,
        tx_id: CompactionId,
    ) -> int:
        gen = self._surface_generation.get(session_id, 0) + 1
        self._surface_generation[session_id] = gen
        events = self._surface_events.get(session_id, [])
        if range.start_idx < len(events) and range.end_idx < len(events):
            del events[range.start_idx : range.end_idx + 1]
            events.insert(range.start_idx, {"type": "summary", "text": summary_text, "seq": summary_node_id})
        return gen

    async def read_all_events(self, session_id: str) -> Sequence[Any]:
        return self._compaction_events.get(session_id, [])

    def set_surface_events(self, session_id: str, events: list[Any]) -> None:
        """测试辅助：设置 surface 事件。"""
        self._surface_events[session_id] = events


class SimpleTokenMeter:
    """简单 token 计量器——按字符数估算。"""

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def count_events_tokens(self, events: Sequence[Any]) -> int:
        total = 0
        for event in events:
            if hasattr(event, "data") and hasattr(event.data, "message"):
                message = event.data.message
                if hasattr(message, "get_text_content"):
                    total += self.count_tokens(message.get_text_content() or "")
                elif hasattr(message, "content"):
                    total += self.count_tokens(str(message.content))
            elif isinstance(event, dict):
                total += self.count_tokens(str(event.get("text", "")))
        return total

    def get_context_window(self, model_route: ModelRoute) -> int:
        return 32768


class LlmServiceAdapter:
    """LLM 服务适配器——委托既有 LLM 服务。"""

    def __init__(self, llm_service: Any = None) -> None:
        self._llm_service = llm_service

    async def summarize(
        self,
        prompt_messages: Sequence[Any],
        model_route: ModelRoute,
    ) -> str:
        if self._llm_service is None:
            return "摘要内容（LLM 服务未接线，返回占位文本）"
        try:
            return await self._llm_service.generate_summary(
                prompt_messages=prompt_messages,
                provider=model_route.provider,
                model=model_route.model,
                max_tokens=model_route.max_tokens,
            )
        except Exception:
            return "摘要生成失败，返回占位文本"