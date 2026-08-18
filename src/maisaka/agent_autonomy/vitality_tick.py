"""生命力心跳调度器——周期性触发待命智能体的生命力评估。"""


import asyncio
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.core.app_config_port_registry import get_app_config_port

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.vitality_manager import VitalityManager

logger = get_logger("agent_autonomy.vitality_tick")


class VitalityTickScheduler:
    """生命力心跳调度器。"""

    def __init__(
        self,
        vitality_manager: VitalityManager,
        interval_seconds: int | None = None,
    ) -> None:
        self._vitality_manager = vitality_manager
        self._interval = interval_seconds or get_app_config_port().get_agent_autonomy_config().vitality_tick_interval_seconds
        self._task: asyncio.Task | None = None
        self._running = False

    def start(self) -> None:
        """启动心跳周期任务。"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._tick_loop())
        logger.info(f"[vitality_tick] 心跳调度器启动: interval={self._interval}s")

    def stop(self) -> None:
        """停止心跳周期任务。"""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("[vitality_tick] 心跳调度器停止")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _tick_loop(self) -> None:
        """心跳循环。"""
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._vitality_manager.evaluate_vitality_tick()
                # LS-0: 心跳驱动情绪衰减
                self._tick_emotion_decay()
                # LS-4: 心跳驱动共激活衰减
                await self._tick_coactivation_decay()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.WARNING, '[vitality_tick] 心跳评估异常: error=', exception=exc)
                logger.warning(f"[vitality_tick] 心跳评估异常: error={exc}")

    def _tick_emotion_decay(self) -> None:
        """LS-0: 遍历活跃智能体，触发情绪衰减。"""
        try:
            for agent in self._vitality_manager._registry.all_agents():
                emotion_manager = getattr(agent, "emotion_manager", None)
                if emotion_manager is not None:
                    emotion_manager.tick_decay()
                    try:
                        asyncio.get_event_loop().create_task(
                            emotion_manager.check_and_write_emotional_imprint(
                                agent_id=agent.agent_id,
                                trigger_reason="vitality_tick",
                            )
                        )
                    except RuntimeError as exc:
                        # P0-7: get_event_loop 失败出声（debug 防刷屏，无事件循环）（ZG-31）
                        logger.debug("create_task 失败（无事件循环？）: %s", exc)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '[vitality_tick] 情绪衰减跳过: error=', exception=exc)
            logger.debug(f"[vitality_tick] 情绪衰减跳过: error={exc}")

    async def _tick_coactivation_decay(self) -> None:
        """LS-4: 遍历活跃智能体，衰减共激活强度。"""
        try:
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

            rel_manager = AgentRelationshipManager()
            for agent in self._vitality_manager._registry.all_agents():
                decayed = await rel_manager.decay_coactivations(agent.agent_id)
                if decayed > 0:
                    logger.debug(f"[vitality_tick] 共激活衰减: agent={agent.agent_id} rows={decayed}")
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '[vitality_tick] 共激活衰减跳过: error=', exception=exc)
            logger.debug(f"[vitality_tick] 共激活衰减跳过: error={exc}")
