import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

from src.common.logger import get_logger
from src.config.config import global_config
from src.maisaka.agent_autonomy.agent import AutonomousAgent
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger, AutonomyEventSubscriber
from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent
from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus, InteractionSignalEvent, InterjectionMentionEvent
from src.maisaka.agent_autonomy.interjection_cooldown import InterjectionCooldownManager
from src.maisaka.agent_autonomy.interjection_scheduler import InterjectionScheduler
from src.maisaka.agent_autonomy.orchestrator_strategy import BaseOrchestratorStrategy, DefaultOrchestratorStrategy, create_strategy
from src.maisaka.agent_autonomy.bridge.chat_loop_adapter import ChatLoopServiceAdapter

logger = get_logger("agent_autonomy.orchestrator")


class AgentOrchestrator:
    """智能体编排器——多智能体协作的唯一编排者。

    核心约束：只协调执行顺序和资源分配，不替智能体做决策。
    """

    # 类级别注册表：session_id -> AgentOrchestrator
    _registry: dict[str, "AgentOrchestrator"] = {}

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
        self._autonomy_logger = AutonomyLogger.get()

        # 插话调度
        self._cooldown_manager = InterjectionCooldownManager()
        self._interjection_scheduler = InterjectionScheduler(self._cooldown_manager)

        # 待处理的行为意图：agent_id -> list[BehaviorIntent]
        self._pending_intents: dict[str, list[BehaviorIntent]] = {}

        # 编排策略
        strategy_name = getattr(self._config, "orchestrator_strategy", "default")
        try:
            self._strategy: BaseOrchestratorStrategy = create_strategy(strategy_name)
        except ValueError:
            logger.warning(
                f"[agent_autonomy] 未知编排策略: {strategy_name}，使用默认策略"
            )
            self._strategy = DefaultOrchestratorStrategy()

        # 上下文切换缓存：agent_id -> prompt_context
        self._context_cache: dict[str, dict[str, str]] = {}

        # 并发控制
        max_concurrent = self._strategy.get_max_concurrent_interjections()
        self._interjection_semaphore = asyncio.Semaphore(max_concurrent)

        # 订阅交互信号事件
        self._subscribe_events()

        # 启动自主性事件日志订阅
        self._event_subscriber = AutonomyEventSubscriber()
        self._event_subscriber.subscribe_all()

        # 注册到全局注册表
        AgentOrchestrator._registry[session_id] = self

    def _subscribe_events(self) -> None:
        """订阅自主性事件总线的交互信号。"""
        bus = AutonomyEventBus.get_instance()
        bus.subscribe("interaction_signal", self._on_interaction_signal)
        bus.subscribe("interjection_mention", self._on_interjection_mention)

    async def _on_interaction_signal(self, event: Any) -> None:
        """交互信号事件处理器。"""
        if self._degraded:
            return

        target_agent_id = getattr(event, "target_agent_id", None)
        if not target_agent_id:
            return

        logger.debug(
            f"[agent_autonomy] 收到交互信号: "
            f"initiator={getattr(event, 'initiator_agent_id', '')} "
            f"target={target_agent_id} "
            f"type={getattr(event, 'interaction_type', '')} "
            f"session={self._session_name}"
        )

        await self.handle_interaction_signal(event)

    async def _on_interjection_mention(self, event: Any) -> None:
        """插话提及事件处理器——插话反哺交互系统。"""
        mentioned_agent_id = getattr(event, "mentioned_agent_id", None)
        speaker_agent_id = getattr(event, "speaker_agent_id", None)
        if not mentioned_agent_id or not speaker_agent_id:
            return

        logger.debug(
            f"[agent_autonomy] 插话提及信号: "
            f"speaker={speaker_agent_id} mentioned={mentioned_agent_id} "
            f"session={self._session_name}"
        )

        # 如果被提及的智能体活跃，更新其情绪
        agent = self._active_agents.get(mentioned_agent_id)
        if agent is not None and agent.emotion_manager is not None:
            try:
                agent.emotion_manager.apply_trigger("happy", 5.0)
                logger.debug(
                    f"[agent_autonomy] 插话提及情绪更新: "
                    f"agent={mentioned_agent_id} emotion=happy delta=5.0"
                )
            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 插话提及情绪更新失败: "
                    f"agent={mentioned_agent_id} error={exc}"
                )

        # 产生提及传递信号写入交互系统
        try:
            from src.maisaka.agent_interaction.engine import InteractionEngine
            from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
            from src.maisaka.agent_interaction.event_store import InteractionEventStore
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager
            from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation

            emotion_registry = AgentEmotionManagerRegistry()
            relationship_manager = AgentRelationshipManager()
            event_store = InteractionEventStore()
            engine = InteractionEngine(
                emotion_registry=emotion_registry,
                relationship_manager=relationship_manager,
                event_store=event_store,
            )

            evaluation = TriggerEvaluation(
                should_trigger=True,
                trigger_probability=1.0,
                initiator_agent_id=speaker_agent_id,
                target_agent_id=mentioned_agent_id,
                interaction_type="mention_propagation",
                trigger_reason=f"插话提及传递: {getattr(event, 'content_summary', '')}",
                metadata={"source": "interjection_mention"},
            )
            result = await engine.execute(evaluation)
            if result.success:
                logger.info(
                    f"[agent_autonomy] 插话反哺交互成功: "
                    f"speaker={speaker_agent_id}→mentioned={mentioned_agent_id} "
                    f"event_id={result.event_id}"
                )
        except Exception as exc:
            logger.warning(
                f"[agent_autonomy] 插话反哺交互失败: error={exc}"
            )

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    @classmethod
    def get_by_session(cls, session_id: str) -> "AgentOrchestrator | None":
        """根据 session_id 获取编排器实例。"""
        return cls._registry.get(session_id)

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

    def get_pending_intents(self) -> dict[str, list[BehaviorIntent]]:
        """获取当前待处理的行为意图。"""
        return dict(self._pending_intents)

    async def activate_agent(self, agent_id: str, reason: str) -> bool:
        """激活一个智能体。"""
        if agent_id in self._active_agents:
            return True

        if len(self._active_agents) >= self._config.max_active_agents:
            logger.warning(
                f"[agent_autonomy] agent={agent_id} action=activate_rejected "
                f"reason=max_agents_reached max={self._config.max_active_agents} "
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
            self._autonomy_logger.log(
                agent_id,
                AutonomyEventType.ORCHESTRATION,
                f"加入会话(原因={reason}, 主发言={is_primary})",
                session_id=self._session_id,
            )
            )
            return True
        except Exception as exc:
            logger.error(
                f"[agent_autonomy] agent={agent_id} action=activate_failed "
                f"error={exc}"
            )
            return False

    def restore_agent(self, agent_id: str, is_primary: bool = False) -> None:
        """从数据库恢复智能体到编排器（不触发事件、不记录 activity）。

        用于重启时恢复会话关联，区别于 activate_agent()。
        """
        if agent_id in self._active_agents:
            return

        agent = AutonomousAgent(agent_id)
        self._active_agents[agent_id] = agent

        if is_primary:
            self._primary_agent_id = agent_id

        self._autonomy_logger.log(
            agent_id,
            AutonomyEventType.ORCHESTRATION,
            f"恢复会话关联(主发言={is_primary})",
            session_id=self._session_id,
            level="debug",
        )

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
        self._autonomy_logger.log(
            target_agent_id,
            AutonomyEventType.ORCHESTRATION,
            f"发言权变更(来自={from_agent_id}, 原因={reason})",
            session_id=self._session_id,
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
                logger.info(
                    f"[agent_autonomy] agent={self._primary_agent_id} type=primary "
                    f"session={self._session_name}"
                )

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

                # 持久化行为意图
                for intent in intents:
                    self._persist_behavior_intent(target_agent_id, intent)

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

    def _persist_behavior_intent(self, agent_id: str, intent: BehaviorIntent) -> None:
        """持久化行为意图记录。"""
        try:
            intent_id = f"bi:{agent_id}:{format(int(time.time()), 'x')}:{format(hash(intent), 'x')[:6]}"
            expired_at = datetime.now() + timedelta(seconds=self._config.intent_expiry_seconds)
            self._activity_store.save_behavior_intent(
                intent_id=intent_id,
                agent_id=agent_id,
                session_id=self._session_id,
                intent_type=intent.intent_type,
                intent_strength=intent.intent_strength,
                intent_source=intent.intent_source,
                source_description=intent.source_description,
                expired_at=expired_at,
            )
        except Exception as exc:
            logger.warning(
                f"[agent_autonomy] 行为意图持久化失败: agent={agent_id} error={exc}"
            )

    async def _collect_behavior_intents(self) -> None:
        """并行收集活跃智能体（排除主发言）的行为意图。"""
        tasks: list[tuple[str, asyncio.Task]] = []
        for agent_id, agent in list(self._active_agents.items()):
            if agent_id == self._primary_agent_id:
                continue
            tasks.append((agent_id, asyncio.create_task(
                agent.produce_behavior_intents(
                    intent_threshold=self._config.interjection_intent_threshold,
                )
            )))

        for agent_id, task in tasks:
            try:
                intents = await task
                for intent in intents:
                    self.report_intent(agent_id, intent)
                    self._persist_behavior_intent(agent_id, intent)
            except Exception as exc:
                logger.warning(
                    f"[agent_autonomy] 行为意图收集异常: "
                    f"agent={agent_id} error={exc}"
                )

    async def _schedule_interjections(self) -> None:
        """基于行为意图调度插话（使用可配置策略）。"""
        # 收集所有待处理意图
        all_intents: list[tuple[str, BehaviorIntent]] = []
        for agent_id, intents in self._pending_intents.items():
            for intent in intents:
                all_intents.append((agent_id, intent))

        if not all_intents:
            return

        # 使用策略调度
        active_ids = list(self._active_agents.keys())
        primary_id = self._primary_agent_id or ""

        decisions = self._strategy.schedule_interjections(
            pending_intents=all_intents,
            active_agent_ids=active_ids,
            primary_agent_id=primary_id,
            session_id=self._session_id,
            cooldown_manager=self._cooldown_manager,
        )

        # 执行调度决策
        for decision in decisions:
            if not decision.scheduled:
                logger.debug(
                    f"[agent_autonomy] 插话跳过: agent={decision.agent_id} "
                    f"reason={decision.skip_reason}"
                )
                continue

            logger.info(
                f"[agent_autonomy] agent={decision.agent_id} type=interjection "
                f"reason={decision.intent.source_description} "
                f"strength={decision.intent.intent_strength:.1f} "
                f"session={self._session_name}"
            )

            # 记录插话冷却
            self._cooldown_manager.record_interjection(self._session_id, decision.agent_id)

            # 持久化插话事件
            event_id = f"ij:{decision.agent_id}:{format(int(time.time()), 'x')}:{format(hash(decision.intent), 'x')[:6]}"
            self._activity_store.save_interjection_event(
                event_id=event_id,
                agent_id=decision.agent_id,
                session_id=self._session_id,
                primary_agent_id=primary_id,
                interjection_type=decision.intent.intent_source,
                trigger_reason=decision.intent.source_description,
                intent_strength=decision.intent.intent_strength,
            )

            # 插话反哺：检查插话内容是否提及其他智能体
            self._check_interjection_mention(decision.agent_id, decision.intent.source_description)

        # 清空已处理的意图
        self._pending_intents.clear()

    def _check_interjection_mention(self, speaker_agent_id: str, content_summary: str) -> None:
        """检查插话内容是否提及其他智能体，产生提及传递信号。"""
        if not content_summary:
            return

        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            for agent in registry.list_agents():
                if agent.agent_id == speaker_agent_id:
                    continue
                # 简单匹配：检查智能体显示名或ID是否出现在内容中
                display_name = agent.display_name.lower()
                agent_id_lower = agent.agent_id.lower()
                content_lower = content_summary.lower()

                if display_name and display_name in content_lower or agent_id_lower in content_lower:
                    mention_event = InterjectionMentionEvent(
                        speaker_agent_id=speaker_agent_id,
                        mentioned_agent_id=agent.agent_id,
                        session_id=self._session_id,
                        content_summary=content_summary,
                    )
                    AutonomyEventBus.get_instance().emit_sync("interjection_mention", mention_event)
                    logger.debug(
                        f"[agent_autonomy] 插话提及检测: "
                        f"speaker={speaker_agent_id} mentioned={agent.agent_id}"
                    )
        except Exception as exc:
            logger.debug(
                f"[agent_autonomy] 插话提及检测异常: error={exc}"
            )

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
            logger.info(
                f"[agent_autonomy] agent={agent_id} action=timeout_exit "
                f"session={self._session_name}"
            )
            asyncio.get_event_loop().create_task(
                self.deactivate_agent(agent_id, "timeout")
            )

    def get_cached_context(self, agent_id: str) -> dict[str, str] | None:
        """获取智能体的缓存提示词上下文。"""
        return self._context_cache.get(agent_id)

    def update_cached_context(self, agent_id: str, context: dict[str, str]) -> None:
        """更新智能体的缓存提示词上下文。"""
        self._context_cache[agent_id] = context

    def invalidate_cached_context(self, agent_id: str) -> None:
        """使智能体的缓存提示词上下文失效。"""
        self._context_cache.pop(agent_id, None)

    def cleanup_expired_intents(self) -> int:
        """清理过期的行为意图记录。"""
        now = datetime.now()
        cleaned = 0
        try:
            from src.common.database.database import get_db_session
            from src.common.database.database_model import AgentAutonomyBehaviorIntent

            with get_db_session() as session:
                expired = (
                    session.query(AgentAutonomyBehaviorIntent)
                    .filter(
                        AgentAutonomyBehaviorIntent.expired_at.isnot(None),
                        AgentAutonomyBehaviorIntent.expired_at < now,
                        AgentAutonomyBehaviorIntent.status == "pending",
                    )
                    .all()
                )
                for intent in expired:
                    intent.status = "expired"
                    cleaned += 1
                if cleaned > 0:
                    session.commit()
        except Exception as exc:
            logger.warning(f"[agent_autonomy] 清理过期意图异常: error={exc}")

        if cleaned > 0:
            logger.debug(
                f"[agent_autonomy] 清理过期行为意图: count={cleaned} "
                f"session={self._session_name}"
            )
        return cleaned
