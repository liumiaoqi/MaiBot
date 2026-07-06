"""自主性架构内部事件总线。

轻量级事件机制，连接交互引擎与自主性编排器。
不依赖核心 EventBus，避免与 MaiMessages 耦合。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from src.common.logger import get_logger

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
    """自主性架构内部事件总线。"""

    _instance: AutonomyEventBus | None = None

    def __init__(self) -> None:
        self._handlers: dict[str, list[AutonomyEventHandler]] = {}

    @classmethod
    def get_instance(cls) -> AutonomyEventBus:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

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
        """同步发射事件，创建异步任务执行。"""
        handlers = self._handlers.get(event_type, [])
        if not handlers:
            return

        for handler in handlers:
            try:
                asyncio.create_task(handler(event))
            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 同步事件发射异常: type={event_type} error={exc}"
                )