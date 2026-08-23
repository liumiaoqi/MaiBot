"""ZG-N5 压缩升级——核心压缩服务（ReplayAwareCompactor）。

对标 dsh compaction-basic/src/index.ts:103 BasicCompactionEngine + region.ts:152 compactSurfaceRegion。
编排 start → summarize → surface 稳定性校验 → summary + surface 替换同步提交 → end 事务。
失败闭合：任一阶段失败记录错误 compaction/end，surface 保持替换前状态，保留未匹配 start 阻塞后续。
"""

from typing import Any, Sequence

from src.common.logger import get_logger

from .config import ResolvedConfig
from .durable_lock import DurableLockManager
from .event_logger import CompactionEventLogger
from .idle_task import IdleTaskCoordinator
from .ports import MemoryStorePort, TokenMeterPort
from .summarizer import Summarizer, SummarizationInput
from .surface import SurfaceReplacer
from .tool_pairing import ToolPairingBalancer
from .types import (
    AbortSignal,
    CompactionAbortedError,
    CompactionId,
    CompactionRange,
    CompactionReason,
    CompactionResult,
    ManualCompactionError,
    ModelRoute,
    SummaryNotSmallerError,
)

logger = get_logger("A_Memorix.compaction.engine")


class ReplayAwareCompactor:
    """核心压缩服务——编排 surface 替换式 Replay-aware 压缩事务。"""

    def __init__(
        self,
        *,
        config: ResolvedConfig,
        lock_manager: DurableLockManager,
        balancer: ToolPairingBalancer,
        event_logger: CompactionEventLogger,
        surface_replacer: SurfaceReplacer,
        summarizer: Summarizer,
        token_meter: TokenMeterPort,
        memory_store: MemoryStorePort,
        idle_coordinator: IdleTaskCoordinator | None = None,
    ) -> None:
        self._config = config
        self._lock_manager = lock_manager
        self._balancer = balancer
        self._event_logger = event_logger
        self._surface_replacer = surface_replacer
        self._summarizer = summarizer
        self._token_meter = token_meter
        self._memory_store = memory_store
        self._idle_coordinator = idle_coordinator

    async def compact_if_needed(
        self,
        session_id: str,
        agent_id: str,
        trigger: str = "pressure",
        signal: AbortSignal | None = None,
        model_route: ModelRoute | None = None,
    ) -> CompactionResult | None:
        """自动压力触发压缩。压力未超阈值返回 None。

        对标 dsh index.ts:258 compactIfNeeded。
        自动压缩跳过 idle-task 协调器，直接执行。
        """
        if signal is None:
            signal = AbortSignal()
        if not self._config.auto:
            return None

        reason = CompactionReason.PRESSURE if trigger == "pressure" else CompactionReason.OVERFLOW_RECOVERY
        context_window = self._token_meter.get_context_window(
            model_route or ModelRoute(provider="", model="", max_tokens=self._config.max_tokens)
        )
        threshold_tokens = int(self._config.threshold_ratio * context_window)

        events = await self._memory_store.read_surface_events(session_id)
        current_tokens = self._token_meter.count_events_tokens(events)
        if current_tokens <= threshold_tokens:
            return None

        result = await self._compact_with_retries(
            session_id=session_id,
            agent_id=agent_id,
            reason=reason,
            signal=signal,
            model_route=model_route,
            threshold_tokens=threshold_tokens,
        )
        return result

    async def compact_now(
        self,
        session_id: str,
        agent_id: str,
        signal: AbortSignal | None = None,
        source_command_id: str | None = None,
        model_route: ModelRoute | None = None,
    ) -> CompactionResult | None:
        """手动空闲压缩。经 IdleTaskCoordinator 协调。

        对标 dsh index.ts:368 compactNow。
        """
        if signal is None:
            signal = AbortSignal()
        if self._idle_coordinator is None:
            return await self.compact_region(
                session_id=session_id,
                agent_id=agent_id,
                start=0,
                end=-1,
                signal=signal,
                reason=CompactionReason.MANUAL,
                model_route=model_route,
            )

        async def _compact_fn(sig: AbortSignal) -> CompactionResult:
            result = await self.compact_region(
                session_id=session_id,
                agent_id=agent_id,
                start=0,
                end=-1,
                signal=sig,
                reason=CompactionReason.MANUAL,
                model_route=model_route,
            )
            return result

        return await self._idle_coordinator.request_manual_compact(agent_id, _compact_fn, signal)

    async def compact_region(
        self,
        session_id: str,
        agent_id: str,
        start: int,
        end: int,
        signal: AbortSignal,
        reason: CompactionReason = CompactionReason.PRESSURE,
        model_route: ModelRoute | None = None,
    ) -> CompactionResult:
        """压缩指定范围——核心事务编排。

        对标 dsh region.ts:152 compactSurfaceRegion。
        事务：start 持久化 → 摘要生成 → surface 稳定性校验 → summary + surface 替换同步提交 → end 闭合。
        """
        tx_id = CompactionId.generate()
        signal.throw_if_aborted()

        # 读取 surface 事件
        events = await self._memory_store.read_surface_events(session_id)
        surface_nodes = [getattr(e, "seq", i) for i, e in enumerate(events)]
        generation = await self._memory_store.read_surface_generation(session_id)

        # 选择压缩范围
        range_to_compact = self._select_compactable_range(
            session_id=session_id,
            surface_nodes=surface_nodes,
            generation=generation,
            events=events,
            start=start,
            end=end,
        )
        if range_to_compact is None:
            raise ManualCompactionError("changed", "无可行压缩范围")

        # 1. 获取持久锁
        lock_result = await self._lock_manager.acquire(
            session_id=session_id,
            tx_id=tx_id,
            range=range_to_compact,
            reason=reason,
        )
        if not lock_result.acquired:
            raise ManualCompactionError("busy", "压缩进行中")

        # 2. 记录 compaction/start
        await self._event_logger.log_start(
            tx_id=tx_id,
            session_id=session_id,
            range=range_to_compact,
            reason=reason,
        )

        try:
            signal.throw_if_aborted()

            # 3. 摘要生成
            shadowed_events = events[range_to_compact.start_idx : range_to_compact.end_idx + 1]
            shadowed_token_count = self._token_meter.count_events_tokens(shadowed_events)
            resolved_route = model_route or ModelRoute(
                provider="", model="", max_tokens=self._config.max_tokens
            )

            summarization_input = SummarizationInput(
                session_id=session_id,
                source_events=shadowed_events,
                shadowed_token_count=shadowed_token_count,
                shadowed_seqs=range_to_compact.shadowed_seqs,
            )
            prompt_messages = self._build_summary_prompt(shadowed_events)
            summary_result = await self._summarizer.summarize(
                input=summarization_input,
                tx_id=tx_id,
                model_route=resolved_route,
                prompt_messages=prompt_messages,
            )

            signal.throw_if_aborted()

            # 4. surface 稳定性校验
            surface_unchanged = await self._surface_replacer.assert_surface_unchanged(
                session_id=session_id,
                expected_generation=generation,
            )
            if not surface_unchanged:
                raise ManualCompactionError("changed", "surface 在异步摘要期间已变")

            # 5. 记录 compaction/summary + surface 替换（同步提交）
            await self._event_logger.log_summary(
                tx_id=tx_id,
                session_id=session_id,
                summary=summary_result.summary,
                range_ref=range_to_compact,
                model_route=resolved_route,
            )
            replace_result = await self._surface_replacer.replace(
                session_id=session_id,
                range=range_to_compact,
                summary_node=summary_result.summary_node,
            )
            _ = replace_result

            # 缓存失效
            self._balancer.invalidate_cache(session_id)

            # 6. 记录 compaction/end（成功）
            await self._event_logger.log_end(
                tx_id=tx_id,
                session_id=session_id,
                error=None,
            )

            return CompactionResult(
                compaction_id=tx_id,
                shadowed_range=range_to_compact,
                shadowed_seqs=range_to_compact.shadowed_seqs,
                shadowed_token_count=shadowed_token_count,
                summary=summary_result.summary,
                model_route=resolved_route,
            )

        except (
            CompactionAbortedError,
            SummaryNotSmallerError,
            ManualCompactionError,
        ) as exc:
            await self._event_logger.log_end(
                tx_id=tx_id,
                session_id=session_id,
                error=str(exc),
            )
            raise
        except Exception as exc:
            logger.error(f"压缩事务失败 tx_id={tx_id.value}: {exc}", exc_info=True)
            await self._event_logger.log_end(
                tx_id=tx_id,
                session_id=session_id,
                error=str(exc),
            )
            raise ManualCompactionError("commit", str(exc)) from exc

    async def _compact_with_retries(
        self,
        *,
        session_id: str,
        agent_id: str,
        reason: CompactionReason,
        signal: AbortSignal,
        model_route: ModelRoute | None,
        threshold_tokens: int,
    ) -> CompactionResult:
        """重试循环——摘要后压力仍超阈值时按 compaction_retries 重试。"""
        last_result: CompactionResult | None = None
        max_attempts = 1 + self._config.compaction_retries
        for _attempt in range(max_attempts):
            result = await self.compact_region(
                session_id=session_id,
                agent_id=agent_id,
                start=0,
                end=-1,
                signal=signal,
                reason=reason,
                model_route=model_route,
            )
            last_result = result
            events = await self._memory_store.read_surface_events(session_id)
            current_tokens = self._token_meter.count_events_tokens(events)
            if current_tokens <= threshold_tokens:
                return result
        return last_result

    def _select_compactable_range(
        self,
        *,
        session_id: str,
        surface_nodes: Sequence[int],
        generation: int,
        events: Sequence[Any],
        start: int,
        end: int,
    ) -> CompactionRange | None:
        """选择压缩范围——保留尾部 + tool-pairing 平衡调整。

        对标 dsh region.ts:98 selectCompactableRange。
        """
        if not surface_nodes:
            return None

        if end < 0:
            end = surface_nodes[-1]
        if start < 0:
            start = surface_nodes[0]

        start_idx = surface_nodes.index(start) if start in surface_nodes else 0


        # 保留尾部（retain_ratio 或 retain_tokens）
        if self._config.retain_tokens is not None:
            retain_count = self._config.retain_tokens
        else:
            retain_count = int((self._config.retain_ratio or 0.16) * len(surface_nodes))
        retain_count = max(0, min(retain_count, len(surface_nodes)))

        ideal_end_idx = len(surface_nodes) - retain_count - 1
        if ideal_end_idx <= start_idx:
            return None

        # tool-pairing 平衡调整
        balanced_seq = self._balancer.adjust_to_nearest_balanced(
            session_id=session_id,
            surface_nodes=surface_nodes,
            generation=generation,
            events=events,
            ideal_idx=ideal_end_idx,
        )
        if balanced_seq is None:
            return None

        balanced_end_idx = surface_nodes.index(balanced_seq)
        if balanced_end_idx <= start_idx:
            return None

        shadowed_seqs = tuple(surface_nodes[start_idx : balanced_end_idx + 1])
        return CompactionRange(
            start=start,
            end=balanced_seq,
            start_idx=start_idx,
            end_idx=balanced_end_idx,
            shadowed_seqs=shadowed_seqs,
        )

    def _build_summary_prompt(self, events: Sequence[Any]) -> Sequence[Any]:
        """构建摘要 prompt 消息——从事件中提取文本内容。"""
        prompt_messages: list[Any] = []
        for event in events:
            event_type = getattr(event, "type", None)
            if event_type in ("user/message", "assistant/message"):
                data = getattr(event, "data", None)
                if data is not None:
                    message = getattr(data, "message", None)
                    if message is not None:
                        prompt_messages.append(message)
        return prompt_messages

    async def close(self) -> None:
        """关闭——释放 idle 接纳预留、清理 balance 缓存。"""
        if self._idle_coordinator is not None:
            for agent_id in list(self._idle_coordinator._admission_reserved):
                await self._idle_coordinator.release_admission(agent_id)