"""自主性架构统一日志器——所有智能体活动日志的入口。"""

from __future__ import annotations

from typing import Any

from src.common.logger import get_logger
from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus

logger = get_logger("agent_autonomy.autonomy_logger")


class AutonomyEventType:
    """自主性事件类型枚举。"""

    THINKING = "thinking"
    EXPRESSION = "expression"
    INNER_NEED = "inner_need"
    BEHAVIOR_INTENT = "behavior_intent"
    INTERJECTION = "interjection"
    ORCHESTRATION = "orchestration"


class AutonomyLogger:
    """自主性架构统一日志器。

    所有自主性日志通过此类输出，确保格式统一、Docker 可见。
    日志格式: [Autonomy:{agent_id}] {event_type}: {detail}
    """

    _instance: AutonomyLogger | None = None

    def __init__(self) -> None:
        self._logger = get_logger("agent_autonomy")

    def log(
        self,
        agent_id: str,
        event_type: str,
        detail: str,
        *,
        level: str = "info",
        session_id: str = "",
    ) -> None:
        """记录自主性事件日志。

        Args:
            agent_id: 智能体 ID
            event_type: 事件类型（AutonomyEventType 枚举值）
            detail: 人类可读的决策描述
            level: 日志级别 debug/info/warning/error
            session_id: 可选，关联的会话 ID
        """
        prefix = f"[Autonomy:{agent_id}]"
        message = f"{prefix} {event_type}: {detail}"

        log_method = getattr(self._logger, level, self._logger.info)
        log_method(message)

    @classmethod
    def get(cls) -> AutonomyLogger:
        """获取全局 AutonomyLogger 实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance


class AutonomyEventSubscriber:
    """订阅自主性事件总线，转发跨模块事件到日志器。"""

    def __init__(self, autonomy_logger: AutonomyLogger | None = None) -> None:
        self._logger = autonomy_logger or AutonomyLogger.get()

    def subscribe_all(self) -> None:
        """订阅所有自主性事件类型。"""
        bus = AutonomyEventBus.get_instance()
        bus.subscribe("interaction_signal", self._on_interaction_signal)
        bus.subscribe("interjection_mention", self._on_interjection_mention)

    async def _on_interaction_signal(self, event: Any) -> None:
        """处理交互信号事件。"""
        if hasattr(event, "initiator_agent_id"):
            self._logger.log(
                event.initiator_agent_id,
                AutonomyEventType.ORCHESTRATION,
                f"交互信号: {getattr(event, 'interaction_type', '')} "
                f"→ {getattr(event, 'target_agent_id', '')}",
            )

    async def _on_interjection_mention(self, event: Any) -> None:
        """处理插话提及事件。"""
        if hasattr(event, "speaker_agent_id"):
            self._logger.log(
                event.speaker_agent_id,
                AutonomyEventType.INTERJECTION,
                f"提及 {getattr(event, 'mentioned_agent_id', '')}: "
                f"{getattr(event, 'content_summary', '')}",
            )