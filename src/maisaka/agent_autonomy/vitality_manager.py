"""生命力管理器——待命智能体的生命力计算、跃迁判定与共居参数动态调整。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from src.common.logger import get_logger
from src.config.config import global_config
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
from src.maisaka.agent_autonomy.event_bus import AgentStateChangeEvent, AutonomyEventBus
from src.maisaka.agent_autonomy.standby_registry import StandbyAgentInfo, StandbyAgentRegistry

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

logger = get_logger("agent_autonomy.vitality_manager")


@dataclass
class CohabitationParams:
    """共居插话动态参数。"""

    intent_threshold: float
    cooldown_minutes: float
    max_interjections_per_hour: int


class VitalityManager:
    """生命力管理器——负责待命智能体的生命力计算、跃迁判定与共居参数。"""

    def __init__(self, orchestrator: AgentOrchestrator) -> None:
        self._orchestrator = orchestrator
        self._registry = StandbyAgentRegistry()
        self._activity_store = AgentActivityStore()
        self._config = global_config.agent_autonomy
        self._tick_lock = asyncio.Lock()

        from src.maisaka.agent_autonomy.inner_need import (
            EmotionNeedCalculator,
            InnerNeedEngine,
            MemoryNeedCalculator,
            TimeNeedCalculator,
        )
        self._inner_need_engine = InnerNeedEngine()
        self._inner_need_engine.register_calculator("emotion", EmotionNeedCalculator())
        self._inner_need_engine.register_calculator("memory", MemoryNeedCalculator())
        self._inner_need_engine.register_calculator("time", TimeNeedCalculator())

    @property
    def registry(self) -> StandbyAgentRegistry:
        return self._registry

    def _emit_state_change(
        self,
        agent_id: str,
        session_id: str,
        from_state: str,
        to_state: str,
        trigger_reason: str,
        vitality: float = 0.0,
    ) -> None:
        """发布状态变更事件。"""
        try:
            event = AgentStateChangeEvent(
                agent_id=agent_id,
                session_id=session_id,
                from_state=from_state,
                to_state=to_state,
                trigger_reason=trigger_reason,
                vitality_at_change=vitality,
                timestamp=datetime.now().isoformat(),
            )
            AutonomyEventBus.get_instance().emit_sync("agent_state_change", event)
        except Exception as exc:
            logger.warning(
                f"[vitality] 状态变更事件发布失败: agent={agent_id} error={exc}"
            )

    def sync_standby_agents(self, session_id: str) -> None:
        """同步待命列表：将绑定但非活跃且非待命的智能体加入待命。"""
        try:
            from src.chat.message_receive.chat_manager import chat_manager

            if chat_manager is None or chat_manager._agent_router is None:
                return

            agent_router = chat_manager.agent_router
            bound_agents = agent_router.get_session_all_agents(session_id)
            if not bound_agents:
                return

            active_ids = set(self._orchestrator._active_agents.keys())
            standby_ids = {
                info.agent_id for info in self._registry.get_by_session(session_id)
            }

            for agent_id in bound_agents:
                if agent_id in active_ids or agent_id in standby_ids:
                    continue
                self.add_to_standby(
                    agent_id, session_id, reason="sync_from_binding"
                )
        except Exception as exc:
            logger.warning(f"[vitality] 同步待命列表异常: session={session_id} error={exc}")

    def add_to_standby(
        self,
        agent_id: str,
        session_id: str,
        reason: str = "standby_enter",
        initial_vitality: float | None = None,
    ) -> None:
        """将智能体加入待命列表并持久化。"""
        vitality = (
            initial_vitality
            if initial_vitality is not None
            else self._config.vitality_base_value
        )
        now = datetime.now()
        info = StandbyAgentInfo(
            agent_id=agent_id,
            session_id=session_id,
            vitality_value=vitality,
            last_stimulus_at=now,
            fallback_to_standby_at=now,
        )
        self._registry.add(info)
        self._activity_store.save_standby_activity(
            session_id=session_id,
            agent_id=agent_id,
            vitality_value=vitality,
            activation_reason=reason,
        )
        logger.info(
            f"[vitality] agent={agent_id} action=enter_standby "
            f"session={session_id} reason={reason} vitality={vitality:.1f}"
        )
        self._emit_state_change(agent_id, session_id, "dormant", "standby", reason, vitality)

    def remove_from_standby(
        self, agent_id: str, session_id: str, reason: str = "exit_standby"
    ) -> None:
        """从待命列表移除并持久化退场记录。"""
        self._registry.remove(agent_id, session_id)
        self._activity_store.exit_standby(session_id, agent_id, reason)
        logger.info(
            f"[vitality] agent={agent_id} action=exit_standby "
            f"session={session_id} reason={reason}"
        )
        self._emit_state_change(agent_id, session_id, "standby", "dormant", reason)

    def update_vitality(
        self, agent_id: str, session_id: str, delta: float, reason: str = ""
    ) -> float:
        """更新生命力值，范围限制 [0.0, 100.0]，返回更新后值。"""
        info = self._registry.get(agent_id, session_id)
        if info is None:
            return 0.0

        new_value = max(0.0, min(100.0, info.vitality_value + delta))
        info.vitality_value = new_value
        info.last_stimulus_at = datetime.now()
        self._registry.update_vitality(agent_id, session_id, new_value)
        self._activity_store.update_vitality(
            session_id, agent_id, new_value, info.inner_need_summary, update_stimulus=True
        )

        if delta != 0:
            logger.debug(
                f"[vitality] agent={agent_id} delta={delta:+.1f} "
                f"new={new_value:.1f} reason={reason}"
            )
        return new_value

    async def check_instant_activation(
        self, agent_id: str, session_id: str
    ) -> bool:
        """检查即时跃迁条件（被直接提及），满足时调用 activate_agent。"""
        info = self._registry.get(agent_id, session_id)
        if info is None:
            return False

        active_count = len(self._orchestrator._active_agents)
        max_active = self._config.max_active_agents
        if active_count >= max_active:
            logger.debug(
                f"[vitality] 即时跃迁被拒绝: agent={agent_id} "
                f"active={active_count}/{max_active}"
            )
            return False

        self._registry.remove(agent_id, session_id)
        self._activity_store.activate_from_standby(session_id, agent_id)

        activated = await self._orchestrator.activate_agent(
            agent_id, "vitality_instant_activation"
        )
        if activated:
            logger.info(
                f"[vitality] agent={agent_id} action=instant_activation "
                f"session={session_id}"
            )
            self._emit_state_change(agent_id, session_id, "standby", "active", "vitality_instant_activation", info.vitality_value)
        return activated

    async def evaluate_vitality_tick(self) -> None:
        """执行一次心跳评估：遍历所有待命智能体，计算生命力，判定跃迁。"""
        if self._tick_lock.locked():
            return

        async with self._tick_lock:
            all_standby = self._registry.all_agents()
            if not all_standby:
                return

            now = datetime.now()
            config = self._config
            activation_threshold = config.vitality_activation_threshold
            fallback_timeout = config.fallback_exit_timeout_minutes
            decay_per_minute = config.vitality_decay_per_minute

            for info in all_standby:
                try:
                    await self._evaluate_single_agent(
                        info, now, activation_threshold, fallback_timeout, decay_per_minute
                    )
                except Exception as exc:
                    logger.warning(
                        f"[vitality] 心跳评估异常: agent={info.agent_id} error={exc}"
                    )

    async def _evaluate_single_agent(
        self,
        info: StandbyAgentInfo,
        now: datetime,
        activation_threshold: float,
        fallback_timeout: int,
        decay_per_minute: float,
    ) -> None:
        """评估单个待命智能体。"""
        agent_id = info.agent_id
        session_id = info.session_id

        # 内在需求加成
        inner_need_bonus = 0.0
        try:
            from src.maisaka.agent_autonomy.agent import AutonomousAgent

            agent = self._orchestrator._active_agents.get(agent_id) or AutonomousAgent(agent_id)

            time_context = {"hour": now.hour, "night_active": False}
            needs = await self._inner_need_engine.evaluate(
                agent_id=agent_id,
                emotion_state=agent.emotion_manager.state if agent.emotion_manager else None,
                time_context=time_context,
            )
            if needs:
                total_strength = sum(n.strength for n in needs)
                inner_need_bonus = min(total_strength / 5.0, 20.0)
                info.inner_need_summary = ", ".join(
                    f"{n.need_type}({n.strength:.0f})" for n in needs[:3]
                )
        except Exception as exc:
            logger.debug(f"[vitality] 内在需求评估跳过: agent={agent_id} error={exc}")

        # 情绪加成
        emotion_bonus = 0.0
        try:
            from src.maisaka.agent_autonomy.agent import AutonomousAgent

            agent = self._orchestrator._active_agents.get(agent_id) or AutonomousAgent(agent_id)
            if agent.emotion_manager is not None:
                intensity = agent.emotion_manager.state.get_dominant_intensity()
                emotion_bonus = min(intensity / 10.0, 10.0)
        except (AttributeError, TypeError):
            pass

        # 时间衰减
        elapsed_minutes = 0.0
        if info.last_stimulus_at is not None:
            elapsed_minutes = (now - info.last_stimulus_at).total_seconds() / 60
        decay = decay_per_minute * elapsed_minutes

        # 计算新生命力
        new_vitality = max(0.0, min(100.0, info.vitality_value + inner_need_bonus + emotion_bonus - decay))
        info.vitality_value = new_vitality
        self._registry.update_vitality(agent_id, session_id, new_vitality)
        self._activity_store.update_vitality(
            session_id, agent_id, new_vitality, info.inner_need_summary
        )

        # 跃迁判定
        if new_vitality >= activation_threshold:
            active_count = len(self._orchestrator._active_agents)
            if active_count < self._config.max_active_agents:
                self._registry.remove(agent_id, session_id)
                self._activity_store.activate_from_standby(session_id, agent_id)
                await self._orchestrator.activate_agent(
                    agent_id, "vitality_activation"
                )
                logger.info(
                    f"[vitality] agent={agent_id} action=vitality_activation "
                    f"vitality={new_vitality:.1f} session={session_id}"
                )
                self._emit_state_change(agent_id, session_id, "standby", "active", "vitality_activation", new_vitality)
                return

        # 退场判定：待命超时且生命力为0
        if info.fallback_to_standby_at is not None:
            standby_minutes = (now - info.fallback_to_standby_at).total_seconds() / 60
            if standby_minutes >= fallback_timeout and new_vitality <= 0.0:
                self.remove_from_standby(agent_id, session_id, "vitality_depleted")
                logger.info(
                    f"[vitality] agent={agent_id} action=vitality_depleted_exit "
                    f"standby_minutes={standby_minutes:.0f} session={session_id}"
                )

    def get_standby_agents(self, session_id: str) -> list[StandbyAgentInfo]:
        """获取待命智能体列表。"""
        return self._registry.get_by_session(session_id)

    def get_agent_vitality(self, agent_id: str, session_id: str) -> float:
        """获取生命力值。"""
        info = self._registry.get(agent_id, session_id)
        return info.vitality_value if info is not None else 0.0

    def get_cohabitation_params(self, session_id: str) -> CohabitationParams:
        """计算共居插话动态参数。"""
        config = self._config
        try:
            from src.chat.message_receive.chat_manager import ChatManager

            chat_manager = ChatManager.get_instance()
            if chat_manager is None or chat_manager.agent_router is None:
                return CohabitationParams(
                    intent_threshold=config.interjection_intent_threshold,
                    cooldown_minutes=float(config.interjection_cooldown_minutes),
                    max_interjections_per_hour=config.max_interjections_per_hour,
                )

            bound_count = len(
                chat_manager.agent_router.get_session_all_agents(session_id)
            )
        except Exception:
            bound_count = 1

        if bound_count < 3:
            return CohabitationParams(
                intent_threshold=config.interjection_intent_threshold,
                cooldown_minutes=float(config.interjection_cooldown_minutes),
                max_interjections_per_hour=config.max_interjections_per_hour,
            )

        adjustment_factor = min(bound_count / 3.0, 2.0)

        dynamic_threshold = max(
            config.interjection_intent_threshold
            - config.cohabitation_threshold_reduction * adjustment_factor,
            config.interjection_threshold_minimum,
        )
        dynamic_cooldown = max(
            float(config.interjection_cooldown_minutes)
            - config.cohabitation_cooldown_reduction_minutes * adjustment_factor,
            config.interjection_cooldown_minimum_minutes,
        )
        dynamic_max = config.max_interjections_per_hour + 2

        return CohabitationParams(
            intent_threshold=dynamic_threshold,
            cooldown_minutes=dynamic_cooldown,
            max_interjections_per_hour=dynamic_max,
        )