"""自主性架构内部事件总线。

轻量级事件机制，连接交互引擎与自主性编排器。
不依赖核心 EventBus，避免与 MaiMessages 耦合。
"""



from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from src.common.logger import get_logger
from src.core.softirq_batcher import SchedulingStrategy, SoftirqBatcher

logger = get_logger("agent_autonomy.event_bus")

AutonomyEventHandler = Callable[[Any], Coroutine[Any, Any, None]]


@dataclass
class InteractionSignalEvent:
    """交互信号事件——交互引擎执行成功后发布。"""

    initiator_agent_id: str = ""
    target_agent_id: str = ""
    interaction_type: str = ""
    trigger_reason: str = ""
    emotion_effects: dict[str, dict[str, float]] = field(default_factory=dict)
    relationship_effect: float = 0.0
    event_id: str = ""


@dataclass
class InterjectionMentionEvent:
    """插话提及事件——智能体插话中提及其他智能体时发布。"""

    speaker_agent_id: str = ""
    mentioned_agent_id: str = ""
    session_id: str = ""
    content_summary: str = ""
    # ZG-23a: 连锁深度节流（默认值保证向后兼容）
    chain_id: str = ""
    depth: int = 1


@dataclass
class SessionMessageEvent:
    """会话消息事件——用户或智能体发送消息时发布。"""

    session_id: str = ""
    sender_type: str = ""
    sender_id: str = ""
    content: str = ""
    timestamp: str = ""


@dataclass
class AgentSpeakEvent:
    """智能体发言事件——智能体完成发言后发布。"""

    session_id: str = ""
    agent_id: str = ""
    content_summary: str = ""
    emotion_type: str = ""
    emotion_intensity: float = 0.0


@dataclass
class AgentStateChangeEvent:
    """智能体状态变更事件——状态跃迁时发布。"""

    agent_id: str = ""
    session_id: str = ""
    from_state: str = ""
    to_state: str = ""
    trigger_reason: str = ""
    vitality_at_change: float = 0.0
    timestamp: str = ""


class AutonomyEventBus:
    """自主性架构内部事件总线。

    不再使用 get_instance() 单例模式，通过 AutonomyEventBusPort 注册点注入。
    """

    def __init__(
        self,
        budget_ms: float = 2.0,
        budget_count: int = 200,
        strategy: SchedulingStrategy = SchedulingStrategy.HRRN,
    ) -> None:
        self._handlers: dict[str, list[AutonomyEventHandler]] = {}
        # SoftirqBatcher 负责批量执行 emit_sync 入队的事件回调（对标 ksoftirqd）
        self._softirq: SoftirqBatcher[tuple[AutonomyEventHandler, Any]] = SoftirqBatcher(
            handler=self._batch_fire_handlers,
            budget_ms=budget_ms,
            budget_count=budget_count,
            strategy=strategy,
        )

    def subscribe(self, event_type: str, handler: AutonomyEventHandler) -> None:
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unsubscribe(self, event_type: str, handler: AutonomyEventHandler) -> bool:
        handlers = self._handlers.get(event_type, [])
        if handler in handlers:
            handlers.remove(handler)
            return True
        return False

    async def emit(self, event_type: str, event: Any) -> None:
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 事件处理异常: type={event_type} error={exc}"
                )

    def emit_sync(self, event_type: str, event: Any) -> None:
        """同步发射事件，只入 SoftirqBatcher 队列，由 drainer 批量执行。

        不创建逐条 Task（对标 raise_softirq 只置 pending 位）。
        """
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        for handler in handlers:
            self._softirq.raise_softirq((handler, event))

    async def _batch_fire_handlers(
        self, batch: list[tuple[AutonomyEventHandler, Any]]
    ) -> None:
        """批量执行事件 handler（异常隔离，单条异常不中断同批）"""
        for handler, event in batch:
            try:
                await handler(event)
            except Exception as exc:
                handler_name = getattr(handler, "__name__", repr(handler))
                logger.warning(
                    f"[agent_autonomy] 事件处理异常: handler={handler_name} error={exc}"
                )

    def start(self) -> None:
        """启动 SoftirqBatcher drainer（供装配点调用，必须在事件循环运行后调用）"""
        self._softirq.start()

    async def stop(self) -> None:
        """停止 SoftirqBatcher drainer（供关闭链调用，积压不再处理）"""
        await self._softirq.stop()
