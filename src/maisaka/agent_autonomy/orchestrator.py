import asyncio
from datetime import datetime, timedelta
from typing import Any

from src.common.logger import get_logger
from src.config.config import global_config
from src.maisaka.agent_autonomy.agent import AutonomousAgent
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent
from src.maisaka.agent_autonomy.interjection_cooldown import InterjectionCooldownManager
from src.maisaka.agent_autonomy.interjection_scheduler import InterjectionScheduler
from src.maisaka.agent_autonomy.bridge.chat_loop_adapter import ChatLoopServiceAdapter

logger = get_logger("agent_autonomy.orchestrator")


class AgentOrchestrator:
    """智能体编排器——多智能体协作的唯一编排者。

    核心约束：只协调执行顺序和资源分配，不替智能体做决策。
    """

    def __init__(
        self,
        session_id: str,
        session_name: str,
        chat_loop_adapter: ChatLoopServiceAdapter,
    ) -> None:
        self._session_id = session_id
        self._session_name = session_name
        self._chat_loop_adapter = chat_loop_adapter
        self._config = global_config.agent_autonomy
        self._activity_store = AgentActivityStore()

        self._active_agents: dict[str, AutonomousAgent] = {}
        self._primary_agent_id: str | None = None
        self._degraded = False
        self._reply_semaphore = asyncio.Semaphore(2)

        # 插话调度
        self._cooldown_manager = InterjectionCooldownManager()
        self._interjection_scheduler = InterjectionScheduler(self._cooldown_manager)

        # 待处理的行为意图：agent_id -> list[BehaviorIntent]
        self._pending_intents: dict[str, list[BehaviorIntent]] = {}

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    def get_active_agents(self) -> list[AutonomousAgent]:
        """获取当前会话的活跃智能体列表。"""
        return list(self._active_agents.values())

    def get_primary_agent(self) -> AutonomousAgent | None:
        """获取当前主发言智能体。"""
        if self._primary_agent_id is None:
            return None
        return self._active_agents.get(self._primary_agent_id)

    def is_multi_agent_active(self) -> bool:
        """当前会话是否有多个活跃智能体。"""
        return len(self._active_agents) > 1

    async def activate_agent(self, agent_id: str, reason: str) -> bool:
        """激活一个智能体。"""
        if agent_id in self._active_agents:
            return True

        if len(self._active_agents) >= self._config.max_active_agents:
            logger.warning(
                f"[agent_autonomy] 活跃智能体数已满，拒绝激活: "
                f"agent={agent_id} max={self._config.max_active_agents} "
                f"session={self._session_name}"
            )
            return False

        try:
            agent = AutonomousAgent(agent_id)
            self._active_agents[agent_id] = agent

            is_primary = self._primary_agent_id is None
            if is_primary:
                self._primary_agent_id = agent_id

            self._activity_store.save_activity(
                session_id=self._session_id,
                agent_id=agent_id,
                is_primary=is_primary,
                activation_reason=reason,
            )

            logger.info(
                f"[agent_autonomy] agent={agent_id} action=activate "
                f"session={self._session_name} reason={reason} "
                f"is_primary={is_primary}"
            )
            return True
        except Exception as exc:
            logger.error(
                f"[agent_autonomy] 智能体激活失败: agent={agent_id} error={exc}"
            )
            return False

    async def deactivate_agent(self, agent_id: str, reason: str) -> None:
        """退场一个活跃智能体。"""
        if agent_id not in self._active_agents:
            return

        del self._active_agents[agent_id]
        self._pending_intents.pop(agent_id, None)
        self._activity_store.deactivate(self._session_id, agent_id, reason)

        if self._primary_agent_id == agent_id:
            if self._active_agents:
                new_primary = next(iter(self._active_agents))
                await self.switch_primary_speaker(
                    new_primary, reason=f"原主发言退场({reason})", change_type="agent_exit"
                )
            else:
                self._primary_agent_id = None

        logger.info(
            f"[agent_autonomy] agent={agent_id} action=deactivate "
            f"session={self._session_name} reason={reason}"
        )

    async def switch_primary_speaker(
        self,
        target_agent_id: str,
        reason: str,
        change_type: str = "manual_switch",
    ) -> bool:
        """切换主发言智能体。"""
        if target_agent_id == self._primary_agent_id:
            return True

        if target_agent_id not in self._active_agents:
            success = await self.activate_agent(target_agent_id, f"switch_primary:{reason}")
            if not success:
                return False

        from_agent_id = self._primary_agent_id or ""
        self._primary_agent_id = target_agent_id

        self._activity_store.set_primary(self._session_id, target_agent_id)
        self._activity_store.save_speaker_change(
            session_id=self._session_id,
            from_agent_id=from_agent_id,
            to_agent_id=target_agent_id,
            change_type=change_type,
            change_reason=reason,
        )

        self._chat_loop_adapter.switch_agent_context(target_agent_id)

        logger.info(
            f"[agent_autonomy] speaker_change from={from_agent_id} "
            f"to={target_agent_id} reason={reason} "
            f"session={self._session_name}"
        )
        return True

    async def handle_message(self, message: Any) -> None:
        """处理用户消息，编排主发言智能体回复。"""
        if self._degraded:
            return

        try:
            if self._primary_agent_id is None:
                agent_id = self._chat_loop_adapter.current_agent_id
                if agent_id:
                    await self.activate_agent(agent_id, "session_create")

            if self._primary_agent_id:
                self._activity_store.update_last_spoke(self._session_id, self._primary_agent_id)

            # 收集活跃智能体的行为意图
            if self._config.interjection_enabled:
                await self._collect_behavior_intents()

            # 调度插话
            if self._config.interjection_enabled:
                await self._schedule_interjections()

            self._check_timeout_exit()

        except Exception as exc:
            logger.error(
                f"[agent_autonomy] 编排异常，降级为仅主发言模式: "
                f"session={self._session_name} error={exc}"
            )
            self._degraded = True

    async def handle_interaction_signal(self, event: Any) -> None:
        """处理 agent-interaction-alive 的交互信号。"""
        if self._degraded:
            return

        try:
            target_agent_id = getattr(event, "target_agent_id", None)
            if not target_agent_id:
                return

            # 如果目标智能体不活跃，尝试激活
            if target_agent_id not in self._active_agents:
                await self.activate_agent(target_agent_id, "interaction_signal")

            # 通知目标智能体交互信号到达，由其自主决定是否产生行为意图
            agent = self._active_agents.get(target_agent_id)
            if agent is not None:
                intents = await agent.produce_behavior_intents(
                    interaction_signals=[event],
                    intent_threshold=self._config.interjection_intent_threshold,
                )
                for intent in intents:
                    self.report_intent(target_agent_id, intent)

        except Exception as exc:
            logger.warning(
                f"[agent_autonomy] 交互信号处理异常: session={self._session_name} error={exc}"
            )

    def report_intent(self, agent_id: str, intent: BehaviorIntent) -> None:
        """接收智能体自主报告的行为意图。

        Note: Orchestrator 不计算意图，只消费意图强度做调度排序
        """
        if agent_id not in self._pending_intents:
            self._pending_intents[agent_id] = []
        self._pending_intents[agent_id].append(intent)

        logger.debug(
            f"[agent_autonomy] agent={agent_id} intent={intent.intent_type} "
            f"strength={intent.intent_strength:.1f} source={intent.intent_source} "
            f"session={self._session_name}"
        )

    async def _collect_behavior_intents(self) -> None:
        """收集活跃智能体（排除主发言）的行为意图。"""
        for agent_id, agent in list(self._active_agents.items()):
            if agent_id == self._primary_agent_id:
                continue

            try:
                intents = await agent.produce_behavior_intents(
                    intent_threshold=self._config.interjection_intent_threshold,
                )
                for intent in intents:
                    self.report_intent(agent_id, intent)
            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 行为意图收集异常: "
                    f"agent={agent_id} error={exc}"
                )

    async def _schedule_interjections(self) -> None:
        """基于行为意图调度插话。"""
        # 收集所有待处理意图
        all_intents: list[tuple[str, BehaviorIntent]] = []
        for agent_id, intents in self._pending_intents.items():
            for intent in intents:
                all_intents.append((agent_id, intent))

        if not all_intents:
            return

        # 调度
        active_ids = list(self._active_agents.keys())
        primary_id = self._primary_agent_id or ""

        scheduled = self._interjection_scheduler.schedule_with_session(
            pending_intents=all_intents,
            active_agent_ids=active_ids,
            primary_agent_id=primary_id,
            session_id=self._session_id,
        )

        # 执行调度
        for item in scheduled:
            if not item.scheduled:
                logger.debug(
                    f"[agent_autonomy] 插话跳过: agent={item.agent_id} "
                    f"reason={item.skip_reason}"
                )
                continue

            logger.info(
                f"[agent_autonomy] agent={item.agent_id} type=interjection "
                f"reason={item.intent.source_description} "
                f"strength={item.intent.intent_strength:.1f} "
                f"session={self._session_name}"
            )

            # 记录插话冷却
            self._cooldown_manager.record_interjection(self._session_id, item.agent_id)

            # 持久化插话事件
            import time
            event_id = f"ij:{item.agent_id}:{format(int(time.time()), 'x')}:{format(hash(item.intent), 'x')[:6]}"
            self._activity_store.save_interjection_event(
                event_id=event_id,
                agent_id=item.agent_id,
                session_id=self._session_id,
                primary_agent_id=primary_id,
                interjection_type=item.intent.intent_source,
                trigger_reason=item.intent.source_description,
                intent_strength=item.intent.intent_strength,
            )

        # 清空已处理的意图
        self._pending_intents.clear()

    def _check_timeout_exit(self) -> None:
        """检查活跃智能体是否超时需要退场。"""
        timeout_minutes = self._config.auto_exit_timeout_minutes
        now = datetime.now()

        agents_to_exit: list[str] = []
        for agent_id in list(self._active_agents.keys()):
            if agent_id == self._primary_agent_id:
                continue
            activities = self._activity_store.get_active_agents(self._session_id)
            for activity in activities:
                if activity.agent_id == agent_id and activity.last_spoke_at:
                    elapsed = (now - activity.last_spoke_at).total_seconds() / 60
                    if elapsed >= timeout_minutes:
                        agents_to_exit.append(agent_id)

        for agent_id in agents_to_exit:
            asyncio.get_event_loop().create_task(
                self.deactivate_agent(agent_id, "timeout")
            )
