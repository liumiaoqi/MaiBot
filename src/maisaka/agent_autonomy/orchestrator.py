import asyncio
from datetime import datetime, timedelta

from src.common.logger import get_logger
from src.config.config import global_config
from src.maisaka.agent_autonomy.agent import AutonomousAgent
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
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

        # 活跃智能体：agent_id -> AutonomousAgent
        self._active_agents: dict[str, AutonomousAgent] = {}
        self._primary_agent_id: str | None = None
        self._degraded = False
        self._reply_semaphore = asyncio.Semaphore(2)

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
            logger.debug(
                f"[agent_autonomy] 智能体已活跃，跳过激活: "
                f"agent={agent_id} session={self._session_name}"
            )
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
                f"[agent_autonomy] 智能体激活失败: "
                f"agent={agent_id} error={exc}"
            )
            return False

    async def deactivate_agent(self, agent_id: str, reason: str) -> None:
        """退场一个活跃智能体。"""
        if agent_id not in self._active_agents:
            return

        del self._active_agents[agent_id]
        self._activity_store.deactivate(self._session_id, agent_id, reason)

        # 如果退场的是主发言智能体，需要切换
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

        # 确保目标智能体已激活
        if target_agent_id not in self._active_agents:
            success = await self.activate_agent(target_agent_id, f"switch_primary:{reason}")
            if not success:
                return False

        from_agent_id = self._primary_agent_id or ""
        old_primary = self._primary_agent_id
        self._primary_agent_id = target_agent_id

        # 更新持久化状态
        self._activity_store.set_primary(self._session_id, target_agent_id)
        self._activity_store.save_speaker_change(
            session_id=self._session_id,
            from_agent_id=from_agent_id,
            to_agent_id=target_agent_id,
            change_type=change_type,
            change_reason=reason,
        )

        # 切换 ChatLoopService 上下文
        self._chat_loop_adapter.switch_agent_context(target_agent_id)

        logger.info(
            f"[agent_autonomy] speaker_change from={from_agent_id} "
            f"to={target_agent_id} reason={reason} "
            f"session={self._session_name}"
        )
        return True

    async def handle_message(self, message: "SessionMessage") -> None:
        """处理用户消息，编排主发言智能体回复。

        Postcondition: 主发言智能体的角色化 Planner 已执行
        """
        if self._degraded:
            return

        try:
            # 确保主发言智能体已激活
            if self._primary_agent_id is None:
                agent_id = self._chat_loop_adapter.current_agent_id
                if agent_id:
                    await self.activate_agent(agent_id, "session_create")

            # 更新主发言智能体的最近发言时间
            if self._primary_agent_id:
                self._activity_store.update_last_spoke(self._session_id, self._primary_agent_id)

            # 检查超时退场
            self._check_timeout_exit()

        except Exception as exc:
            logger.error(
                f"[agent_autonomy] 编排异常，降级为仅主发言模式: "
                f"session={self._session_name} error={exc}"
            )
            self._degraded = True

    async def handle_interaction_signal(self, event: object) -> None:
        """处理 agent-interaction-alive 的交互信号。

        阶段二为占位实现，阶段四完善。
        """
        pass

    def report_intent(self, agent_id: str, intent: object) -> None:
        """接收智能体自主报告的行为意图。

        阶段二为占位实现，阶段三完善。
        Note: Orchestrator 不计算意图，只消费意图强度做调度排序
        """
        pass

    def _check_timeout_exit(self) -> None:
        """检查活跃智能体是否超时需要退场。"""
        timeout_minutes = self._config.auto_exit_timeout_minutes
        now = datetime.now()

        agents_to_exit: list[str] = []
        for agent_id, agent in list(self._active_agents.items()):
            if agent_id == self._primary_agent_id:
                continue
            # 从持久化存储获取 last_spoke_at
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