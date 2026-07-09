import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

from src.common.logger import get_logger
from src.config.config import global_config
from src.core.protocols import AgentRoutingService, NoticeClassifier, ThinkingOrganFactory
from src.core.types import CoreMessage, NoticeKind, ThinkAction, ThinkContext, ThinkResult
from src.maisaka.agent_autonomy.agent import AutonomousAgent
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger, AutonomyEventSubscriber
from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent
from src.maisaka.agent_autonomy.event_bus import AutonomyEventBus, InterjectionMentionEvent, SessionMessageEvent
from src.maisaka.agent_autonomy.interjection_cooldown import InterjectionCooldownManager
from src.maisaka.agent_autonomy.interjection_scheduler import InterjectionScheduler
from src.maisaka.agent_autonomy.lifecycle import AgentLifecycleManager, AgentLifecycleState
from src.maisaka.agent_autonomy.orchestrator_strategy import BaseOrchestratorStrategy, DefaultOrchestratorStrategy, create_strategy
from src.maisaka.agent_autonomy.bridge.chat_loop_adapter import ChatLoopServiceAdapter
from src.maisaka.agent_autonomy.vitality_manager import VitalityManager
from src.maisaka.agent_autonomy.ambient_awareness import AmbientAwarenessProcessor
from src.maisaka.agent_autonomy.vitality_tick import VitalityTickScheduler
from src.maisaka.agent_autonomy.state_awareness.rule_engine import StateAwareRuleEngine
from src.maisaka.agent_autonomy.state_awareness.summary_generator import CohabitantStateSummaryGenerator
from src.maisaka.agent_autonomy.state_awareness.visibility_rule import StateVisibilityRule
from src.maisaka.agent_autonomy.butler import Butler

logger = get_logger("agent_autonomy.orchestrator")


class AgentOrchestrator:
    """智能体编排器——多智能体协作的唯一编排者。

    核心约束：只协调执行顺序和资源分配，不替智能体做决策。
    """

    # 类级别注册表：session_id -> AgentOrchestrator
    _registry: dict[str, "AgentOrchestrator"] = {}

    @staticmethod
    def _get_default_routing_service() -> AgentRoutingService:
        from src.core.adapters.routing_adapter import ChatManagerRoutingAdapter
        return ChatManagerRoutingAdapter()

    @staticmethod
    def _get_default_notice_classifier() -> NoticeClassifier:
        from src.core.adapters.notice_classifier import NapCatNoticeClassifier
        return NapCatNoticeClassifier()

    @staticmethod
    def _get_default_thinking_organ_factory() -> ThinkingOrganFactory:
        from src.maisaka.agent_autonomy.thinking_organ_factory import ThinkingOrganFactory
        return ThinkingOrganFactory()

    def __init__(
        self,
        session_id: str,
        session_name: str,
        chat_loop_adapter: ChatLoopServiceAdapter,
        routing_service: AgentRoutingService | None = None,
        notice_classifier: NoticeClassifier | None = None,
        thinking_organ_factory: ThinkingOrganFactory | None = None,
    ) -> None:
        self._session_id = session_id
        self._session_name = session_name
        self._chat_loop_adapter = chat_loop_adapter
        self._routing_service = routing_service or self._get_default_routing_service()
        self._notice_classifier = notice_classifier or self._get_default_notice_classifier()
        self._thinking_organ_factory = thinking_organ_factory or self._get_default_thinking_organ_factory()
        self._config = global_config.agent_autonomy
        self._activity_store = AgentActivityStore()
        self._lifecycle_manager = AgentLifecycleManager(self._activity_store)

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
        strategy_name = self._config.orchestrator_strategy
        try:
            self._strategy: BaseOrchestratorStrategy = create_strategy(strategy_name)
        except ValueError:
            logger.warning(
                f"[agent_autonomy] 未知编排策略: {strategy_name}，使用默认策略"
            )
            self._strategy = DefaultOrchestratorStrategy()

        # 生命力管理
        self._vitality_manager = VitalityManager(self)
        self._vitality_tick_scheduler = VitalityTickScheduler(self._vitality_manager)
        self._vitality_tick_scheduler.start()

        # 状态互知
        self._visibility_rule = StateVisibilityRule()
        self._rule_engine = StateAwareRuleEngine(
            self._vitality_manager, self._visibility_rule
        )
        self._summary_generator = CohabitantStateSummaryGenerator(
            self._vitality_manager, self, self._visibility_rule
        )

        # 环境感知（注入规则引擎）
        self._ambient_awareness = AmbientAwarenessProcessor(
            self._vitality_manager, self._rule_engine
        )

        # 管家系统（过滤+协调+提醒）
        self._butler: Butler | None = None

        # 并行思考调度器
        from src.maisaka.agent_autonomy.parallel_think import ParallelThinkScheduler
        self._think_scheduler = ParallelThinkScheduler(max_concurrent=2)


        # 提醒心跳检查
        self._reminder_tick_task: asyncio.Task | None = None

        # 交互引擎（插话反哺用）
        self._interaction_engine: InteractionEngine | None = None

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
        bus.subscribe("session_message", self._ambient_awareness.on_session_message)
        bus.subscribe("agent_speak", self._ambient_awareness.on_agent_speak)


    async def _on_interaction_signal(self, event: Any) -> None:
        """交互信号事件处理器。"""
        if self._degraded:
            return

        target_agent_id = event.target_agent_id
        if not target_agent_id:
            return

        logger.debug(
            f"[agent_autonomy] 收到交互信号: "
            f"initiator={event.initiator_agent_id} "
            f"target={target_agent_id} "
            f"type={event.interaction_type} "
            f"session={self._session_name}"
        )

        await self.handle_interaction_signal(event)

    async def _on_interjection_mention(self, event: Any) -> None:
        """插话提及事件处理器——插话反哺交互系统。"""
        mentioned_agent_id = event.mentioned_agent_id
        speaker_agent_id = event.speaker_agent_id
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
            if self._interaction_engine is None:
                from src.maisaka.agent_interaction.engine import InteractionEngine
                from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry
                from src.maisaka.agent_interaction.event_store import InteractionEventStore
                from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

                emotion_registry = AgentEmotionManagerRegistry()
                relationship_manager = AgentRelationshipManager()
                event_store = InteractionEventStore()
                self._interaction_engine = InteractionEngine(
                    emotion_registry=emotion_registry,
                    relationship_manager=relationship_manager,
                    event_store=event_store,
                )

            from src.maisaka.agent_interaction.trigger_base import TriggerEvaluation

            evaluation = TriggerEvaluation(
                should_trigger=True,
                trigger_probability=1.0,
                initiator_agent_id=speaker_agent_id,
                target_agent_id=mentioned_agent_id,
                interaction_type="mention_propagation",
                trigger_reason=f"插话提及传递: {event.content_summary}",
                metadata={"source": "interjection_mention"},
            )
            result = await self._interaction_engine.execute(evaluation)
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


    async def _trigger_interjection_for(self, agent_id: str, context: str) -> None:
        """管家协调的插话——直接触发目标智能体的 ThinkingOrgan。

        管家已经做了三层过滤，不需要策略再过滤。
        """
        if agent_id not in self._active_agents:
            activated = await self.activate_agent(agent_id, "butler_interjection")
            if not activated:
                return

        agent = self._active_agents.get(agent_id)
        if agent is None:
            return

        logger.info(
            f"[agent_autonomy] 管家插话执行: agent={agent_id} "
            f"session={self._session_name}"
        )

        think_context = self._build_think_context(
            agent=agent,
            messages=(CoreMessage(session_id=self._session_id, plain_text=context, is_notify=False),),
            trigger_reason="butler_interjection",
        )
        task = self._think_scheduler.schedule(agent_id, agent.thinking_organ, think_context)
        result = await task

        if result.action == ThinkAction.REPLY and result.text:
            from src.core.message_port_registry import get_message_port
            port = get_message_port()
            if port is not None:
                await port.send(
                    session_id=self._session_id,
                    text=result.text,
                    agent_id=agent_id,
                    source="butler_interjection",
                )
                logger.info(
                    f"[agent_autonomy] 管家插话发送: agent={agent_id} "
                    f"text_len={len(result.text)} session={self._session_name}"
                )

        self._cooldown_manager.record_interjection(self._session_id, agent_id)

    def _start_reminder_tick(self) -> None:
        """启动提醒心跳检查。"""
        if self._reminder_tick_task is not None:
            return
        self._reminder_tick_task = asyncio.create_task(self._reminder_tick_loop())
        logger.info(f"[agent_autonomy] 提醒心跳启动: session={self._session_name}")

    async def _reminder_tick_loop(self) -> None:
        """周期性检查到期提醒，直接触发主智能体的 ThinkingOrgan。"""
        while True:
            try:
                await asyncio.sleep(30)
                if self._butler is None:
                    continue
                due_reminders = self._butler.check_reminders()
                for reminder in due_reminders:
                    logger.info(
                        f"[agent_autonomy] 提醒触发: agent={reminder.agent_id} "
                        f"context={reminder.context} session={self._session_name}"
                    )

                    agent = self._active_agents.get(reminder.agent_id)
                    if agent is None:
                        if self._primary_agent_id:
                            agent = self._active_agents.get(self._primary_agent_id)
                    if agent is None:
                        continue

                    think_context = self._build_think_context(
                        agent=agent,
                        messages=(CoreMessage(session_id=self._session_id, plain_text=reminder.context, is_notify=False),),
                        trigger_reason="reminder",
                        metadata={"reminder_id": reminder.reminder_id, "is_direct": reminder.is_direct},
                    )
                    task = self._think_scheduler.schedule_proactive(
                        reminder.agent_id, agent.thinking_organ, "reminder", think_context,
                    )
                    result = await task

                    if result.action == ThinkAction.REPLY and result.text:
                        from src.core.message_port_registry import get_message_port
                        port = get_message_port()
                        if port is not None:
                            await port.send(
                                session_id=self._session_id,
                                text=result.text,
                                agent_id=reminder.agent_id,
                                source="reminder",
                            )
                            logger.info(
                                f"[agent_autonomy] 提醒发送: agent={reminder.agent_id} "
                                f"text_len={len(result.text)} session={self._session_name}"
                            )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning(f"[agent_autonomy] 提醒心跳异常: error={exc}")

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

            # 注入共居状态摘要生成器到 PromptBuilder
            if self._config.state_awareness_enabled:
                agent._prompt_builder.set_summary_generator(self._summary_generator)

            is_primary = self._primary_agent_id is None
            if is_primary:
                self._primary_agent_id = agent_id
                self._butler = Butler(
                    primary_agent_id=agent_id,
                    session_id=self._session_id,
                )
                self._butler.reminder_manager.load_session(self._session_id)
                self._start_reminder_tick()

            self._activity_store.save_activity(
                session_id=self._session_id,
                agent_id=agent_id,
                is_primary=is_primary,
                activation_reason=reason,
            )

            self._lifecycle_manager.transition(
                agent_id, self._session_id, AgentLifecycleState.ACTIVE, reason
            )

            # 同步到 AgentRouter
            self._routing_service.bind_session(self._session_id, agent_id)

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

        # 注入共居状态摘要生成器
        if self._config.state_awareness_enabled:
            agent._prompt_builder.set_summary_generator(self._summary_generator)

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

        self._lifecycle_manager.transition(
            agent_id, self._session_id, AgentLifecycleState.EXITING, reason
        )

        del self._active_agents[agent_id]
        self._pending_intents.pop(agent_id, None)
        self._activity_store.deactivate(self._session_id, agent_id, reason)

        self._lifecycle_manager.transition(
            agent_id, self._session_id, AgentLifecycleState.DESTROYED, reason
        )

        # 同步解绑 AgentRouter
        self._routing_service.unbind_session(self._session_id, agent_id)

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

        # 同步 ChatSession.agent_id
        from src.common.database.database import get_db_session
        from src.common.database.database_model import ChatSession
        with get_db_session() as db:
            chat_session = db.query(ChatSession).filter(
                ChatSession.session_id == self._session_id
            ).first()
            if chat_session is not None:
                chat_session.agent_id = target_agent_id

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

    def _classify_notice(self, message: Any) -> NoticeKind:
        """分类通知消息，返回 NoticeKind 枚举值。"""
        return self._notice_classifier.classify(message)

    async def handle_message(self, message: Any) -> None:
        """处理用户消息，编排主发言智能体回复。"""
        if self._degraded:
            return

        notice_kind = self._classify_notice(message)
        if notice_kind in (NoticeKind.AMBIENT, NoticeKind.INPUT_STATUS):
            self._handle_ambient_notice(message, notice_kind)
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

            # 同步待命智能体列表
            self._vitality_manager.sync_standby_agents(self._session_id)

            # 发布环境感知事件
            content = message.processed_plain_text or ""
            sender_id = message.message_info.user_info.user_id if message.message_info else ""


            # 管家：尝试从用户消息中创建提醒
            if self._butler is not None and content:
                try:
                    reminder = await self._butler.try_create_reminder(
                        text=content,
                        agent_id=self._primary_agent_id or "",
                    )
                    if reminder is not None:
                        logger.info(
                            f"[agent_autonomy] 管家创建提醒: "
                            f"agent={reminder.agent_id} time={reminder.trigger_time} "
                            f"context={reminder.context}"
                        )
                except Exception as exc:
                    logger.warning(f"[agent_autonomy] 管家提醒创建异常: error={exc}")

            session_message_event = SessionMessageEvent(
                session_id=self._session_id,
                sender_type="user",
                sender_id=sender_id,
                content=str(content),
                timestamp=datetime.now().isoformat(),
            )
            AutonomyEventBus.get_instance().emit_sync("session_message", session_message_event)

            # 收集活跃智能体的行为意图
            if self._config.interjection_enabled:
                await self._collect_behavior_intents()

            # 调度插话
            if self._config.interjection_enabled:
                await self._schedule_interjections()

            # 管家插话决策（基于用户消息，补充现有插话机制）
            if self._butler is not None and content:
                try:
                    candidates = await self._butler.decide_interjection(content, "")
                    for c in candidates:
                        logger.info(
                            f"[agent_autonomy] 管家插话候选: agent={c.agent_id} "
                            f"name={c.display_name} mentioned={c.is_mentioned} "
                            f"session={self._session_name}"
                        )
                        self._butler.mark_interjected(c.agent_id)
                        await self._trigger_interjection_for(c.agent_id, content)
                except Exception as exc:
                    logger.warning(f"[agent_autonomy] 管家插话决策异常: error={exc}")


            self._check_timeout_exit()

        except Exception as exc:
            logger.error(
                f"[agent_autonomy] 编排异常，降级为仅主发言模式: "
                f"session={self._session_name} error={exc}"
            )
            self._degraded = True

    def _handle_ambient_notice(self, message: Any, notice_kind: NoticeKind) -> None:
        """处理纯环境感知通知：更新待命智能体生命力，不触发Planner。"""
        try:
            self._vitality_manager.sync_standby_agents(self._session_id)

            sender_id = message.message_info.user_info.user_id if message.message_info else ""
            ambient_stimulus = 1.0

            for info in self._vitality_manager.get_standby_agents(self._session_id):
                self._vitality_manager.update_vitality(
                    info.agent_id, self._session_id, ambient_stimulus,
                    reason=f"ambient_notice:{notice_kind.value}",
                )

            logger.debug(
                f"[agent_autonomy] ambient_notice: kind={notice_kind.value} "
                f"session={self._session_name} sender={sender_id}"
            )
        except Exception as exc:
            logger.debug(f"[agent_autonomy] ambient_notice处理异常: {exc}")

    async def handle_interaction_signal(self, event: Any) -> None:
        """处理 agent-interaction-alive 的交互信号。"""
        if self._degraded:
            return

        try:
            target_agent_id = event.target_agent_id
            if not target_agent_id:
                return

            # 如果目标智能体不活跃也不在待命列表，先唤醒为待命
            if (
                target_agent_id not in self._active_agents
                and not self._vitality_manager.registry.contains(target_agent_id, self._session_id)
            ):
                self._vitality_manager.add_to_standby(
                    target_agent_id, self._session_id, "interaction_signal"
                )

            # 如果目标智能体不活跃，尝试激活
            if target_agent_id not in self._active_agents:
                await self.activate_agent(target_agent_id, "interaction_signal")

            # 通知目标智能体交互信号到达，由其自主决定是否产生行为意图
            agent = self._active_agents.get(target_agent_id)
            if agent is not None:
                cohabitation_params = self._vitality_manager.get_cohabitation_params(self._session_id)
                intents = await agent.produce_behavior_intents(
                    interaction_signals=[event],
                    intent_threshold=cohabitation_params.intent_threshold,
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
        # 获取动态插话参数
        cohabitation_params = self._vitality_manager.get_cohabitation_params(self._session_id)
        dynamic_threshold = cohabitation_params.intent_threshold

        # 感知规则引擎调整阈值
        if self._config.state_awareness_enabled:
            try:
                rule_result = self._rule_engine.evaluate_for_interjection(self._session_id)
                dynamic_threshold += rule_result.intent_threshold_adjustment
                dynamic_threshold = max(
                    dynamic_threshold,
                    self._config.interjection_threshold_minimum,
                )
                if rule_result.triggered_rules:
                    logger.debug(
                        f"[agent_autonomy] 感知规则触发: "
                        f"rules={rule_result.triggered_rules} "
                        f"adjustment={rule_result.intent_threshold_adjustment:.1f} "
                        f"session={self._session_name}"
                    )
            except Exception as exc:
                logger.warning(f"[agent_autonomy] 感知规则评估异常: error={exc}")

        tasks: list[tuple[str, asyncio.Task]] = []
        for agent_id, agent in list(self._active_agents.items()):
            if agent_id == self._primary_agent_id:
                continue
            tasks.append((agent_id, asyncio.create_task(
                agent.produce_behavior_intents(
                    intent_threshold=dynamic_threshold,
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
        """基于行为意图调度插话（使用可配置策略 + 动态共居参数）。"""
        # 收集所有待处理意图
        all_intents: list[tuple[str, BehaviorIntent]] = []
        for agent_id, intents in self._pending_intents.items():
            for intent in intents:
                all_intents.append((agent_id, intent))

        if not all_intents:
            return

        # 获取动态冷却参数
        cohabitation_params = self._vitality_manager.get_cohabitation_params(self._session_id)

        # 使用策略调度
        active_ids = list(self._active_agents.keys())
        primary_id = self._primary_agent_id or ""

        decisions = self._strategy.schedule_interjections(
            pending_intents=all_intents,
            active_agent_ids=active_ids,
            primary_agent_id=primary_id,
            session_id=self._session_id,
            cooldown_manager=self._cooldown_manager,
            override_cooldown=cohabitation_params.cooldown_minutes,
            override_max_per_hour=cohabitation_params.max_interjections_per_hour,
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

            registry = AgentConfigRegistry.get_instance()
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
        """检查活跃智能体是否超时需要退场。非主发言超时后回落为待命。"""
        timeout_minutes = self._config.auto_exit_timeout_minutes
        now = datetime.now()

        agents_to_fallback: list[str] = []
        for agent_id in list(self._active_agents.keys()):
            if agent_id == self._primary_agent_id:
                continue
            activities = self._activity_store.get_active_agents(self._session_id)
            for activity in activities:
                if activity.agent_id == agent_id and activity.last_spoke_at:
                    elapsed = (now - activity.last_spoke_at).total_seconds() / 60
                    if elapsed >= timeout_minutes:
                        agents_to_fallback.append(agent_id)

        for agent_id in agents_to_fallback:
            logger.info(
                f"[agent_autonomy] agent={agent_id} action=timeout_fallback "
                f"session={self._session_name}"
            )
            # 先加入待命列表
            self._vitality_manager.add_to_standby(
                agent_id, self._session_id, "timeout_fallback"
            )
            # 从活跃列表移除（使用 fallback_to_standby reason 触发回落逻辑）
            asyncio.get_event_loop().create_task(
                self.deactivate_agent(agent_id, "fallback_to_standby")
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

    def _build_think_context(
        self,
        agent: AutonomousAgent,
        messages: tuple[CoreMessage, ...],
        trigger_reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> ThinkContext:
        """构建 ThinkContext，自动填充内心世界数据。"""
        inner_voice_text = ""
        emotion_state_text = ""
        memory_personality_params: dict[str, Any] | None = None

        snapshot = agent.get_inner_world_snapshot()
        if snapshot is not None:
            inner_voice_text = snapshot.inner_voice_text
            emotion_state_text = snapshot.emotion_state_text
            memory_personality_params = snapshot.memory_personality_params.model_dump()

        return ThinkContext(
            messages=messages,
            emotion_state_text=emotion_state_text,
            inner_voice_text=inner_voice_text,
            memory_personality_params=memory_personality_params,
            trigger_reason=trigger_reason,
            metadata=metadata or {},
        )
