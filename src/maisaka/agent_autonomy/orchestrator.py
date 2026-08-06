import asyncio
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.maisaka.agent_interaction.engine import InteractionEngine

from src.common.logger import get_logger
from src.core.app_config_port_registry import get_app_config_port
from src.core.event_bus_port_registry import get_event_bus_port
from src.core.protocols import AgentRoutingService, NoticeClassifier, ThinkingOrganFactory
from src.core.types import CoreMessage, NoticeKind, ThinkAction, ThinkContext
from src.maisaka.agent_autonomy.agent import AutonomousAgent
from src.maisaka.agent_autonomy.activity_store import AgentActivityStore
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger, AutonomyEventSubscriber
from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent
from src.maisaka.agent_autonomy.event_bus import InterjectionMentionEvent, SessionMessageEvent
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
from src.maisaka.agent_autonomy.log_utils import fmt_butler, fmt_transfer
from src.maisaka.agent_autonomy.speaker_transfer import (
    SpeakerTransferType,
    TransferDecisionSource,
)

logger = get_logger("agent_autonomy.orchestrator")


class AgentOrchestrator:
    """智能体编排器——多智能体协作的唯一编排者。

    核心约束：只协调执行顺序和资源分配，不替智能体做决策。
    """

    # 类级别注册表：session_id -> AgentOrchestrator
    _registry: dict[str, "AgentOrchestrator"] = {}

    @staticmethod
    def _get_default_routing_service() -> AgentRoutingService:
        from src.core.routing_port_registry import get_routing_service
        service = get_routing_service()
        if service is None:
            raise RuntimeError("AgentRoutingService 未注册")
        return service

    @staticmethod
    def _get_default_notice_classifier() -> NoticeClassifier:
        from src.core.adapters.notice_classifier import NapCatNoticeClassifier
        return NapCatNoticeClassifier()

    @staticmethod
    def _get_default_thinking_organ_factory() -> ThinkingOrganFactory:
        raise ValueError(
            "AgentOrchestrator 必须显式传入 thinking_organ_factory，"
            "简化模式已废除，默认工厂不再可用"
        )

    def __init__(
        self,
        session_id: str,
        session_name: str,
        chat_loop_adapter: ChatLoopServiceAdapter,
        routing_service: AgentRoutingService | None = None,
        notice_classifier: NoticeClassifier | None = None,
        thinking_organ_factory: ThinkingOrganFactory | None = None,
        is_group_chat: bool = False,
    ) -> None:
        self._session_id = session_id
        self._session_name = session_name
        self._chat_loop_adapter = chat_loop_adapter
        self._is_group_chat = is_group_chat
        self._routing_service = routing_service or self._get_default_routing_service()
        self._notice_classifier = notice_classifier or self._get_default_notice_classifier()
        self._thinking_organ_factory = thinking_organ_factory or self._get_default_thinking_organ_factory()
        if self._thinking_organ_factory._chat_loop_adapter is None:
            self._thinking_organ_factory._chat_loop_adapter = chat_loop_adapter
        self._config = get_app_config_port().get_agent_autonomy_config()
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

        # LS-1: 欲求驱动主动发言心跳
        self._desire_tick_task: asyncio.Task | None = None

        # 交互引擎（插话反哺用）
        self._interaction_engine: InteractionEngine | None = None

        # 体验写入器
        from src.core.adapters import get_memory_service_port
        from src.maisaka.agent_autonomy.experience_writer import ExperienceWriter
        self._experience_writer = ExperienceWriter(memory_port=get_memory_service_port())

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
        bus = get_event_bus_port()
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
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "更新插话提及情绪失败", exception=exc)
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
                from src.core.adapters import get_memory_service_port
                from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter

                memory_adapter = AgentMemoryAdapter(memory_port=get_memory_service_port())
                self._interaction_engine = InteractionEngine(
                    emotion_registry=emotion_registry,
                    relationship_manager=relationship_manager,
                    event_store=event_store,
                    memory_adapter=memory_adapter,
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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "插话反哺交互失败", exception=exc)
            logger.warning(
                f"[agent_autonomy] 插话反哺交互失败: error={exc}"
            )


    async def _trigger_interjection_for(
        self,
        agent_id: str,
        context: str,
        trigger_reason: str = "butler_interjection",
    ) -> None:
        """管家协调的插话——直接触发目标智能体的 ThinkingOrgan。

        管家已经做了三层过滤，不需要策略再过滤。
        trigger_reason: "butler_interjection"（普通插话）或 "interjection_borrow"（临时借用）
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
            f"trigger={trigger_reason} session={self._session_name}"
        )

        think_context = await self._build_think_context(
            agent=agent,
            messages=(CoreMessage(session_id=self._session_id, plain_text=context, is_notify=False),),
            trigger_reason=trigger_reason,
        )

        prev_agent_id = self._chat_loop_adapter.current_agent_id
        if prev_agent_id != agent_id:
            self._chat_loop_adapter.switch_agent_context(agent_id)

        task = self._think_scheduler.schedule(agent_id, agent.thinking_organ, think_context)
        result = await task

        self._try_write_experience(agent_id, result)

        if prev_agent_id != agent_id:
            self._chat_loop_adapter.switch_agent_context(prev_agent_id)

        source = "interjection_borrow" if trigger_reason == "interjection_borrow" else "butler_interjection"

        if result.action == ThinkAction.REPLY and result.text and not result.reply_sent:
            from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
            from src.core.message_port_registry import get_message_port_v2
            from src.maisaka.agent_autonomy.bridge.reply_context_extender import ReplyToolContextExtender
            port = get_message_port_v2()
            if port is not None:
                # 多智能体活跃时添加名字前缀
                is_multi = len(self._active_agents) > 1
                text = ReplyToolContextExtender.prepend_speaker_tag_to_content(
                    result.text, agent_id, is_multi,
                )
                await port.send_message(
                    session_id=self._session_id,
                    message=MessageSequence(components=[TextComponent(text=text)]),
                    agent_id=agent_id,
                    source=source,
                )
                logger.info(
                    f"[agent_autonomy] 管家插话发送: agent={agent_id} "
                    f"text_len={len(result.text)} source={source} session={self._session_name}"
                )
        elif result.action == ThinkAction.REPLY and result.reply_sent:
            logger.info(
                f"[agent_autonomy] 管家插话跳过(reply已发送): agent={agent_id} "
                f"session={self._session_name}"
            )

        self._cooldown_manager.record_interjection(self._session_id, agent_id)

    def _try_write_experience(
        self, agent_id: str, result: Any, emotion_state: Any = None
    ) -> None:
        if self._experience_writer.should_write(result):
            try:
                self._experience_writer.write_experience(
                    result, self._session_id, agent_id, emotion_state,
                )
            except Exception as e:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "写入体验失败", exception=e)
                logger.warning(
                    "体验写入发起失败: agent=%s", agent_id, exc_info=True,
                )

    async def _persist_thought_summary(self, agent_id: str, thought_summary: str) -> None:
        """LS-0: 将 thought_summary 写入 AgentAutonomyActivity 表。"""
        if not thought_summary:
            return
        try:
            from src.common.database.database import get_db_session
            from src.common.database.database_model import AgentAutonomyActivity
            from datetime import datetime

            with get_db_session() as db:
                activity = db.query(AgentAutonomyActivity).filter(
                    AgentAutonomyActivity.session_id == self._session_id,
                    AgentAutonomyActivity.agent_id == agent_id,
                    AgentAutonomyActivity.state == "active",
                ).first()
                if activity is not None:
                    activity.thought_summary = thought_summary[:500]
                    activity.last_think_at = datetime.now()
                    db.commit()
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "持久化思考摘要失败", exception=e)
            logger.debug("thought_summary 持久化跳过: agent=%s", agent_id, exc_info=True)

    async def _load_thought_summary(self, agent_id: str) -> tuple[str, float]:
        """LS-0: 从 AgentAutonomyActivity 读取 thought_summary 和距上次思考的秒数。"""
        try:
            from src.common.database.database import get_db_session
            from src.common.database.database_model import AgentAutonomyActivity
            from datetime import datetime

            with get_db_session() as db:
                activity = db.query(AgentAutonomyActivity).filter(
                    AgentAutonomyActivity.session_id == self._session_id,
                    AgentAutonomyActivity.agent_id == agent_id,
                    AgentAutonomyActivity.state == "active",
                ).first()
                if activity is not None and activity.thought_summary:
                    elapsed = 0.0
                    if activity.last_think_at:
                        elapsed = (datetime.now() - activity.last_think_at).total_seconds()
                    return activity.thought_summary, elapsed
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "读取思考摘要失败", exception=e)
            logger.debug("thought_summary 读取跳过: agent=%s", agent_id, exc_info=True)
        return "", 0.0

    def _start_reminder_tick(self) -> None:
        """启动提醒心跳检查。"""
        if self._reminder_tick_task is not None:
            return
        self._reminder_tick_task = asyncio.create_task(self._reminder_tick_loop())
        logger.info(f"[agent_autonomy] 提醒心跳启动: session={self._session_name}")

    def _start_desire_tick(self) -> None:
        """LS-1: 启动欲求驱动主动发言心跳。"""
        if self._desire_tick_task is not None:
            return
        self._desire_tick_task = asyncio.create_task(self._desire_tick_loop())
        logger.info(f"[agent_autonomy] 欲求心跳启动: session={self._session_name}")

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

                    think_context = await self._build_think_context(
                        agent=agent,
                        messages=(CoreMessage(session_id=self._session_id, plain_text=reminder.context, is_notify=False),),
                        trigger_reason="reminder",
                        metadata={"reminder_id": reminder.reminder_id, "is_direct": reminder.is_direct},
                    )
                    task = self._think_scheduler.schedule_proactive(
                        reminder.agent_id, agent.thinking_organ, "reminder", think_context,
                    )
                    result = await task

                    self._try_write_experience(reminder.agent_id, result)

                    if result.action == ThinkAction.REPLY and result.text and not result.reply_sent:
                        from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
                        from src.core.message_port_registry import get_message_port_v2
                        port = get_message_port_v2()
                        if port is not None:
                            await port.send_message(
                                session_id=self._session_id,
                                message=MessageSequence(components=[TextComponent(text=result.text)]),
                                agent_id=reminder.agent_id,
                                source="reminder",
                            )
                            logger.info(
                                f"[agent_autonomy] 提醒发送: agent={reminder.agent_id} "
                                f"text_len={len(result.text)} session={self._session_name}"
                            )
                    elif result.action == ThinkAction.REPLY and result.reply_sent:
                        logger.info(
                            f"[agent_autonomy] 提醒跳过(reply已发送): agent={reminder.agent_id} "
                            f"session={self._session_name}"
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "提醒心跳执行失败", exception=exc)
                logger.warning(f"[agent_autonomy] 提醒心跳异常: error={exc}")

    async def _desire_tick_loop(self) -> None:
        """LS-1: 欲求驱动主动发言心跳。

        周期性检查活跃主智能体的 inner_need_summary，
        若欲求强度超过阈值且冷却允许，触发主动思考。
        """
        while True:
            try:
                await asyncio.sleep(60)
                if not self._primary_agent_id:
                    continue

                agent = self._active_agents.get(self._primary_agent_id)
                if agent is None or agent.thinking_organ is None:
                    continue

                inner_need_summary = ""
                try:
                    from src.common.database.database import get_db_session
                    from src.common.database.database_model import AgentAutonomyActivity

                    with get_db_session() as db:
                        activity = db.query(AgentAutonomyActivity).filter(
                            AgentAutonomyActivity.session_id == self._session_id,
                            AgentAutonomyActivity.agent_id == self._primary_agent_id,
                            AgentAutonomyActivity.state == "active",
                        ).first()
                        if activity is not None and activity.inner_need_summary:
                            inner_need_summary = activity.inner_need_summary
                except Exception as e:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, "读取欲求摘要失败", exception=e)
                    pass

                if not inner_need_summary:
                    continue

                if not self._cooldown_manager.can_speak_proactively(self._session_id, self._primary_agent_id):
                    continue

                max_strength = 0.0
                for part in inner_need_summary.split(","):
                    part = part.strip()
                    if "(" in part and part.endswith(")"):
                        try:
                            strength = float(part[part.index("(") + 1 : -1])
                            max_strength = max(max_strength, strength)
                        except ValueError:
                            pass

                if max_strength < 30.0:
                    continue

                think_context = await self._build_think_context(
                    agent=agent,
                    messages=(),
                    trigger_reason=f"inner_need:{inner_need_summary}",
                    metadata={"proactive_reason": "desire_tick"},
                )
                task = self._think_scheduler.schedule_proactive(
                    self._primary_agent_id, agent.thinking_organ, "inner_need", think_context,
                )
                result = await task

                self._try_write_experience(self._primary_agent_id, result)
                await self._persist_thought_summary(self._primary_agent_id, result.thought_summary)

                if result.action == ThinkAction.REPLY and result.text and not result.reply_sent:
                    from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
                    from src.core.message_port_registry import get_message_port_v2
                    port = get_message_port_v2()
                    if port is not None:
                        await port.send_message(
                            session_id=self._session_id,
                            message=MessageSequence(components=[TextComponent(text=result.text)]),
                            agent_id=self._primary_agent_id,
                            source="proactive_desire",
                        )
                        self._cooldown_manager.record_proactive_speech(self._session_id, self._primary_agent_id)
                        logger.info(
                            f"[agent_autonomy] 欲求主动发言: agent={self._primary_agent_id} "
                            f"desire={inner_need_summary[:30]} session={self._session_name}"
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "欲求心跳执行失败", exception=exc)
                logger.warning(f"[agent_autonomy] 欲求心跳异常: error={exc}")

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
            agent = AutonomousAgent(agent_id, thinking_organ_factory=self._thinking_organ_factory)
            self._active_agents[agent_id] = agent

            # T20 ZG-8：agent 运行时声明 UNKILLABLE（普通控制消息不杀活跃 agent，force 通道可绕过）
            try:
                from src.core.control_message_port_registry import get_control_message_port

                control_port = get_control_message_port()
                if control_port is not None:
                    await control_port.declare_unkillable(agent_id, "agent")
            except Exception as e:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "声明智能体不可杀失败", exception=e)
                pass

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
                self._start_desire_tick()

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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "激活智能体失败", exception=exc)
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

        agent = AutonomousAgent(agent_id, thinking_organ_factory=self._thinking_organ_factory)
        self._active_agents[agent_id] = agent
        if self._config.state_awareness_enabled:
            agent._prompt_builder.set_summary_generator(self._summary_generator)

        if is_primary:
            self._primary_agent_id = agent_id
            # 确保管家在 session_recovery 时也被初始化
            if self._butler is None:
                self._butler = Butler(
                    primary_agent_id=agent_id,
                    session_id=self._session_id,
                )
                self._butler.reminder_manager.load_session(self._session_id)
                self._start_reminder_tick()
                self._start_desire_tick()
                logger.info(
                    f"[agent_autonomy] 管家初始化(恢复): "
                    f"primary={agent_id} session={self._session_name}"
                )

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

        # T20 ZG-8：agent 退场清除 UNKILLABLE 声明
        try:
            from src.core.control_message_port_registry import get_control_message_port

            control_port = get_control_message_port()
            if control_port is not None:
                await control_port.clear_unkillable(agent_id)
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "清除智能体不可杀声明失败", exception=e)
            pass

        self._lifecycle_manager.transition(
            agent_id, self._session_id, AgentLifecycleState.DESTROYED, reason
        )

        # 同步解绑 AgentRouter
        self._routing_service.unbind_session(self._session_id, agent_id)

        if self._primary_agent_id == agent_id:
            if self._active_agents:
                new_primary = next(iter(self._active_agents))
                await self.switch_primary_speaker(
                    new_primary,
                    reason=f"原主发言退场({reason})",
                    change_type="agent_exit",
                    transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                    decision_source=TransferDecisionSource.AGENT_EXIT,
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
        transfer_type: SpeakerTransferType = SpeakerTransferType.PERMANENT_TRANSFER,
        decision_source: TransferDecisionSource = TransferDecisionSource.MANUAL,
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
            transfer_type=transfer_type.value,
            decision_source=decision_source.value,
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

        # 同步管家的主发言追踪
        if self._butler is not None:
            self._butler.update_primary(target_agent_id)

        logger.info(fmt_transfer(
            from_agent_id, target_agent_id,
            reason=reason,
            transfer_type=transfer_type.value,
            session_name=self._session_name,
        ) + f" decision_source={decision_source.value}")
        self._autonomy_logger.log(
            target_agent_id,
            AutonomyEventType.SPEAKER_TRANSFER,
            f"{transfer_type.value} from={from_agent_id} to={target_agent_id} reason={reason} source={decision_source.value}",
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

            # 主回复调度：非环境通知消息触发主智能体思考
            primary_reply_text = ""
            should_reply = not message.is_notify or notice_kind == NoticeKind.INTERACTION
            if should_reply and self._primary_agent_id is not None:
                primary_reply_text = await self._schedule_primary_reply(message)

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
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, "创建管家提醒失败", exception=exc)
                    logger.warning(f"[agent_autonomy] 管家提醒创建异常: error={exc}")

            session_message_event = SessionMessageEvent(
                session_id=self._session_id,
                sender_type="user",
                sender_id=sender_id,
                content=str(content),
                timestamp=datetime.now().isoformat(),
            )
            get_event_bus_port().emit_sync("session_message", session_message_event)

            # 收集活跃智能体的行为意图
            if self._config.interjection_enabled:
                await self._collect_behavior_intents(content=content, sender_id=sender_id)

            # 调度插话
            if self._config.interjection_enabled:
                await self._schedule_interjections()

            # LS-4: 共在场/提及事件触发 coactivation 更新
            if self._primary_agent_id:
                await self._update_coactivation_on_message(
                    primary_reply_text, content,
                )

            # 管家发言权转移决策（统一临时借用和永久转移）
            if self._butler is not None and content:
                try:
                    decisions = await self._butler.decide_speaker_transfer(
                        content, primary_reply_text, "reply",
                    )
                    for decision in decisions:
                        if decision.transfer_type == SpeakerTransferType.TEMPORARY_BORROW:
                            logger.info(
                                f"[agent_autonomy] 临时借用: agent={decision.target_agent_id} "
                                f"name={decision.display_name} reason={decision.reason} "
                                f"session={self._session_name}"
                            )
                            self._butler.mark_interjected(decision.target_agent_id)
                            await self._trigger_interjection_for(
                                decision.target_agent_id, content,
                                trigger_reason="interjection_borrow",
                            )
                            self._butler.record_borrow(decision.target_agent_id)
                        elif decision.transfer_type == SpeakerTransferType.PERMANENT_TRANSFER:
                            transferred = await self.switch_primary_speaker(
                                decision.target_agent_id,
                                reason=decision.reason,
                                change_type="butler_auto",
                                transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                                decision_source=decision.decision_source,
                            )
                            if transferred:
                                logger.info(
                                    f"[agent_autonomy] 发言权永久转移(插话分支): "
                                    f"to={decision.target_agent_id} reason={decision.reason} "
                                    f"session={self._session_name}"
                                )
                                new_primary = self._active_agents.get(decision.target_agent_id)
                                if new_primary:
                                    await self._trigger_new_primary_think(new_primary, content)
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, "管家发言权转移决策失败", exception=exc)
                    logger.warning(f"[agent_autonomy] 管家发言权转移决策异常: error={exc}")


            self._check_timeout_exit()

        except Exception as exc:
            logger.error(
                f"[agent_autonomy] 编排异常，降级为仅主发言模式: "
                f"session={self._session_name} error={exc}"
            )
            self._degraded = True

    async def _schedule_primary_reply(self, message: Any) -> str:
        """调度主智能体回复——消息入队、去重、触发思考。

        返回主智能体的回复文本（SILENT/WAIT 时返回空字符串）。
        """
        primary = self._active_agents.get(self._primary_agent_id or "")
        if primary is None:
            return ""

        # 延迟创建 butler（session_recovery 可能绕过 activate_agent）
        if self._butler is None and self._primary_agent_id:
            self._butler = Butler(
                primary_agent_id=self._primary_agent_id,
                session_id=self._session_id,
            )
            self._butler.reminder_manager.load_session(self._session_id)
            self._start_reminder_tick()
            self._start_desire_tick()
            logger.info(
                f"[agent_autonomy] 管家延迟初始化: "
                f"primary={self._primary_agent_id} session={self._session_name}"
            )

        content = message.processed_plain_text or ""
        sender_name = ""
        if message.message_info and message.message_info.user_info:
            sender_name = message.message_info.user_info.user_cardname or message.message_info.user_info.user_id

        core_msg = CoreMessage(
            session_id=self._session_id,
            plain_text=content,
            sender_name=sender_name,
            is_notify=message.is_notify,
        )

        think_context = await self._build_think_context(
            agent=primary,
            messages=(core_msg,),
            trigger_reason="user_message",
        )

        task = self._think_scheduler.schedule(
            self._primary_agent_id, primary.thinking_organ, think_context,
        )
        result = await task

        self._try_write_experience(self._primary_agent_id, result)

        # LS-0: 思维连续性 — 持久化 thought_summary
        await self._persist_thought_summary(self._primary_agent_id, result.thought_summary)

        if result.action == ThinkAction.REPLY and result.text and not result.reply_sent:
            from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
            from src.core.message_port_registry import get_message_port_v2
            port = get_message_port_v2()
            if port is not None:
                await port.send_message(
                    session_id=self._session_id,
                    message=MessageSequence(components=[TextComponent(text=result.text)]),
                    agent_id=self._primary_agent_id,
                    source="primary_reply",
                )
                logger.info(
                    f"[agent_autonomy] 主回复发送: agent={self._primary_agent_id} "
                    f"text_len={len(result.text)} session={self._session_name}"
                )
            # 主智能体回复 → 重置沉默/接管计数器，更新连续回应追踪
            if self._butler is not None:
                self._butler.update_primary_status("reply", responder_id=self._primary_agent_id)
            return result.text
        elif result.action == ThinkAction.REPLY and result.reply_sent:
            logger.info(
                f"[agent_autonomy] 主回复跳过(reply已发送): agent={self._primary_agent_id} "
                f"session={self._session_name}"
            )
            if self._butler is not None:
                self._butler.update_primary_status("reply", responder_id=self._primary_agent_id)
            return result.text or ""
        elif result.action == ThinkAction.WAIT:
            logger.info(
                f"[agent_autonomy] 主回复等待: agent={self._primary_agent_id} "
                f"wait={result.wait_seconds}s session={self._session_name}"
            )
            return ""
        elif result.action == ThinkAction.SILENT:
            reason_str = result.silence_reason.value if result.silence_reason else "unknown"
            logger.info(
                f"[agent_autonomy] 主回复静默: agent={self._primary_agent_id} "
                f"reason={reason_str} "
                f"thought=\"{result.thought_summary[:50]}\" "
                f"rounds={result.rounds} tools={result.tool_calls_count} "
                f"session={self._session_name}"
            )
            # 主智能体 SILENT → 递增沉默计数
            if self._butler is not None:
                self._butler.update_primary_status("silent")

            # 评估发言权转移：先评估永久转移 → 再管家接管 → 放弃
            if self._butler is not None and content:
                try:
                    decisions = await self._butler.decide_speaker_transfer(
                        user_text=content, agent_text="", primary_status="silent",
                    )
                    # 永久转移优先
                    for decision in decisions:
                        if decision.transfer_type == SpeakerTransferType.PERMANENT_TRANSFER:
                            transferred = await self.switch_primary_speaker(
                                decision.target_agent_id,
                                reason=decision.reason,
                                change_type="butler_auto",
                                transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                                decision_source=decision.decision_source,
                            )
                            if transferred:
                                logger.info(
                                    f"[agent_autonomy] 发言权永久转移: "
                                    f"to={decision.target_agent_id} reason={decision.reason} "
                                    f"session={self._session_name}"
                                )
                                # 触发新主发言思考
                                new_primary = self._active_agents.get(decision.target_agent_id)
                                if new_primary:
                                    await self._trigger_new_primary_think(new_primary, content)
                                return ""
                            # 转移失败，继续评估

                    # 无永久转移 → 管家接管
                    butler_sent = await self._butler.speak_and_send(
                        user_text=content,
                        agent_text="",
                        context_hint="主智能体沉默了，需要你接管回复",
                    )
                    if butler_sent:
                        self._butler.update_primary_status("butler_takeover")
                        logger.info(fmt_butler(
                            "接管回复", butler_id=self._butler._butler_id,
                            butler_name=self._butler._butler_display_name,
                            session_name=self._session_name,
                            extra=f"SILENT_count={self._butler._consecutive_silent_count} takeover_count={self._butler._butler_takeover_count}",
                        ))
                        # 接管次数达阈值 → 触发永久转移评估
                        if (self._butler._butler_takeover_count
                                >= self._butler._butler_transfer_config.butler_takeover_threshold):
                            upgrade = self._butler._evaluate_permanent_transfer(content)
                            if upgrade and upgrade.transfer_type == SpeakerTransferType.PERMANENT_TRANSFER:
                                transferred = await self.switch_primary_speaker(
                                    upgrade.target_agent_id,
                                    reason=upgrade.reason,
                                    change_type="butler_auto",
                                    transfer_type=SpeakerTransferType.PERMANENT_TRANSFER,
                                    decision_source=upgrade.decision_source,
                                )
                                if transferred:
                                    logger.info(
                                        f"[agent_autonomy] 管家接管触发永久转移: "
                                        f"to={upgrade.target_agent_id} session={self._session_name}"
                                    )
                        return ""
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, "发言权转移评估失败", exception=exc)
                    logger.warning(f"[agent_autonomy] 发言权转移评估异常: error={exc}")
                    # 降级：管家接管
                    if self._butler is not None and content:
                        try:
                            butler_sent = await self._butler.speak_and_send(
                                user_text=content, agent_text="",
                                context_hint="主智能体沉默了，需要你接管回复",
                            )
                            if butler_sent:
                                self._butler.update_primary_status("butler_takeover")
                        except Exception as exc2:
                            from src.core.error_escalation.types import ErrorLevel
                            from src.core.error_escalation_port_registry import get_error_escalation_port
                            port = get_error_escalation_port()
                            if port is not None:
                                port.report(ErrorLevel.ERROR, "管家接管发言失败", exception=exc2)
                            logger.warning(f"[agent_autonomy] 管家接管异常: error={exc2}")
            return ""
        return ""

    async def _trigger_new_primary_think(self, agent: AutonomousAgent, content: str) -> None:
        """永久转移后触发新主发言思考。"""
        think_context = await self._build_think_context(
            agent=agent,
            messages=(CoreMessage(session_id=self._session_id, plain_text=content, is_notify=False),),
            trigger_reason="user_message",
        )
        task = self._think_scheduler.schedule(
            self._primary_agent_id, agent.thinking_organ, think_context,
        )
        result = await task
        self._try_write_experience(self._primary_agent_id, result)
        if result.action == ThinkAction.REPLY and result.text and not result.reply_sent:
            from src.common.data_models.message_component_data_model import MessageSequence, TextComponent
            from src.core.message_port_registry import get_message_port_v2
            from src.maisaka.agent_autonomy.bridge.reply_context_extender import ReplyToolContextExtender
            port = get_message_port_v2()
            if port is not None:
                is_multi = len(self._active_agents) > 1
                text = ReplyToolContextExtender.prepend_speaker_tag_to_content(
                    result.text, self._primary_agent_id, is_multi,
                )
                await port.send_message(
                    session_id=self._session_id,
                    message=MessageSequence(components=[TextComponent(text=text)]),
                    agent_id=self._primary_agent_id,
                    source="primary_reply",
                )

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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "处理环境通知失败", exception=exc)
            logger.warning(f"[agent_autonomy] ambient_notice处理异常: {exc}")

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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "处理交互信号失败", exception=exc)
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
            intent_id = f"bi:{agent_id}:{format(int(time.time()), 'x')}:{format(hash((intent.intent_type, intent.intent_source)), 'x')[:6]}"
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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "持久化行为意图失败", exception=exc)
            logger.warning(
                f"[agent_autonomy] 行为意图持久化失败: agent={agent_id} error={exc}"
            )

    async def _collect_behavior_intents(self, *, content: str = "", sender_id: str = "") -> None:
        """并行收集活跃智能体（排除主发言）的行为意图。"""
        # 构造对话上下文 — 供行为意图引擎的 TopicRelevance/Relationship 源使用
        from datetime import datetime
        conversation_context: list[dict[str, Any]] = []
        if content:
            conversation_context.append({
                "sender_id": sender_id,
                "sender_type": "user",
                "content": content,
                "timestamp": datetime.now().isoformat(),
            })

        # 构造时间上下文
        now = datetime.now()
        time_context: dict[str, Any] = {
            "hour": now.hour,
            "weekday": now.weekday(),
            "timestamp": now.isoformat(),
        }

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
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "评估感知规则失败", exception=exc)
                logger.warning(f"[agent_autonomy] 感知规则评估异常: error={exc}")

        tasks: list[tuple[str, asyncio.Task]] = []
        for agent_id, agent in list(self._active_agents.items()):
            if agent_id == self._primary_agent_id:
                continue
            tasks.append((agent_id, asyncio.create_task(
                agent.produce_behavior_intents(
                    conversation_context=conversation_context or None,
                    time_context=time_context,
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
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "收集行为意图失败", exception=exc)
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
            event_id = f"ij:{decision.agent_id}:{format(int(time.time()), 'x')}:{format(hash((decision.intent.intent_type, decision.intent.intent_source)), 'x')[:6]}"
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
            from src.core.adapters.agent_config_port import get_agent_config_provider

            registry = get_agent_config_provider()
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
                    get_event_bus_port().emit_sync("interjection_mention", mention_event)
                    logger.debug(
                        f"[agent_autonomy] 插话提及检测: "
                        f"speaker={speaker_agent_id} mentioned={agent.agent_id}"
                    )
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "检测插话提及失败", exception=exc)
            logger.warning(
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
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "清理过期意图失败", exception=exc)
            logger.warning(f"[agent_autonomy] 清理过期意图异常: error={exc}")

        if cleaned > 0:
            logger.warning(
                f"[agent_autonomy] 清理过期行为意图: count={cleaned} "
                f"session={self._session_name}"
            )
        return cleaned

    async def _build_think_context(
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

        snapshot = await agent.get_inner_world_snapshot()
        if snapshot is not None:
            inner_voice_text = snapshot.inner_voice_text
            emotion_state_text = snapshot.emotion_state_text
            memory_personality_params = snapshot.memory_personality_params.model_dump()

        # LS-0: inner_voice 自然淡出（5分钟后指数淡出，30分钟后清空）
        if inner_voice_text:
            prev_summary, elapsed = await self._load_thought_summary(agent.agent_id)
            if elapsed > 300:
                import math
                decay = math.exp(-0.1 * (elapsed / 60 - 5))
                if decay < 0.1:
                    inner_voice_text = ""
                else:
                    inner_voice_text = f"[淡出中] {inner_voice_text}"

        memory_snippets: tuple[str, ...] = ()
        intuition_context = None
        try:
            from src.core.adapters import get_memory_service_port
            port = get_memory_service_port()
            seeds = [trigger_reason, self._session_name]
            if emotion_state_text:
                seeds.append(emotion_state_text[:60])
            recall_result = await port.recall_with_intuition(
                seeds=seeds,
                context_text=messages[-1].plain_text if messages else "",
                agent_id=agent.agent_id,
                max_tokens=800,
            )
            items = getattr(recall_result, "recall_items", []) or []
            if isinstance(items, list) and items:
                memory_snippets = self._format_layered_memory_snippets(items)
            intuition_context = getattr(recall_result, "intuition", None)
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "记忆检索失败", exception=e)
            logger.warning("记忆检索跳过: agent=%s", agent.agent_id, exc_info=True)

        # LS-0: 读取上次思考摘要
        prev_thought_summary, time_since_last_think = await self._load_thought_summary(agent.agent_id)

        return ThinkContext(
            messages=messages,
            emotion_state_text=emotion_state_text,
            inner_voice_text=inner_voice_text,
            memory_personality_params=memory_personality_params,
            memory_snippets=memory_snippets,
            intuition_context=intuition_context,
            trigger_reason=trigger_reason,
            metadata=metadata or {},
            session_id=self._session_id,
            is_group_chat=self._is_group_chat,
            prev_thought_summary=prev_thought_summary,
            time_since_last_think=time_since_last_think,
        )

    @staticmethod
    def _format_layered_memory_snippets(items: list) -> tuple[str, ...]:
        """LS-2: 按认知类型分层格式化记忆条目。"""
        from src.common.memory_types import COGNITIVE_TYPE_LABELS, COGNITIVE_TYPE_SORT_ORDER

        TYPE_LIMITS: dict[str, int] = {
            "immutable_fact": 99,
            "stable_trait": 3,
            "emotional_imprint": 2,
            "current_state": 3,
            "active_hypothesis": 2,
            "": 5,
        }

        grouped: dict[str, list] = {}
        for item in items:
            ctype = getattr(item, "cognitive_type", "") or ""
            grouped.setdefault(ctype, []).append(item)

        result: list[str] = []
        for ctype in sorted(grouped, key=lambda t: COGNITIVE_TYPE_SORT_ORDER.get(t, 99)):
            entries = grouped[ctype]
            entries.sort(key=lambda x: getattr(x, "activation", 0.0), reverse=True)
            limit = TYPE_LIMITS.get(ctype, 5)
            label = COGNITIVE_TYPE_LABELS.get(ctype, "记忆")
            for entry in entries[:limit]:
                concept = getattr(entry, "concept", "") or str(entry)
                confidence = getattr(entry, "activation", 0.0)
                contra_mark = "[矛盾]" if getattr(entry, "contradicts_id", None) else ""
                result.append(f"[{label}]{contra_mark} {concept}（置信度{confidence:.1f}）")

        return tuple(result)

    @staticmethod
    def _format_intuition_context(intuition: Any) -> str:
        """LS-2: 格式化直觉上下文为 prompt 注入文本。"""
        if intuition is None:
            return ""

        entries: list[dict] = []
        episodes: list[dict] = []
        sagas: list[dict] = []

        if isinstance(intuition, dict):
            entries = intuition.get("triggered_entries", []) or []
            episodes = intuition.get("triggered_episodes", []) or []
            sagas = intuition.get("triggered_sagas", []) or []
        else:
            entries = list(getattr(intuition, "triggered_entries", ()) or ())
            episodes = list(getattr(intuition, "triggered_episodes", ()) or ())
            sagas = list(getattr(intuition, "triggered_sagas", ()) or ())

        if not entries and not episodes and not sagas:
            return ""

        parts: list[str] = []
        type_groups: dict[str, list[str]] = {
            "current_state": [],
            "stable_trait": [],
            "active_hypothesis": [],
        }
        for entry in entries:
            etype = entry.get("type", "") if isinstance(entry, dict) else getattr(entry, "type", "")
            concept = entry.get("concept", "") if isinstance(entry, dict) else getattr(entry, "concept", "")
            if etype in type_groups and concept:
                type_groups[etype].append(concept)

        type_labels = {"current_state": "当前状态", "stable_trait": "稳定特质", "active_hypothesis": "活跃假设"}
        for etype, label in type_labels.items():
            items = type_groups[etype][:2]
            if items:
                parts.append(f"{label}：" + "、".join(items))

        ep_concepts = []
        for ep in episodes[:2]:
            title = ep.get("title", "") if isinstance(ep, dict) else getattr(ep, "title", "")
            if title:
                ep_concepts.append(title)
        if ep_concepts:
            parts.append("相关事件：" + "、".join(ep_concepts))

        saga_concepts = []
        for s in sagas[:2]:
            title = s.get("title", "") if isinstance(s, dict) else getattr(s, "title", "")
            if title:
                saga_concepts.append(title)
        if saga_concepts:
            parts.append("叙事线索：" + "、".join(saga_concepts))

        if not parts:
            return ""
        return "直觉触发：\n" + "\n".join(f"- {p}" for p in parts)

    async def _update_coactivation_on_message(
        self, agent_reply_text: str, user_text: str,
    ) -> None:
        """LS-4: 消息后更新共激活强度。

        1. 共在场：主智能体发言后，检查最近5分钟内其他活跃智能体是否发言
        2. 互相提及：检查回复文本是否提及其他智能体名字
        """
        import time as _time

        try:
            from src.maisaka.agent_interaction.relationship_manager import (
                AgentRelationshipManager,
                _COACTIVATION_DELTA_COPRESENCE,
                _COACTIVATION_DELTA_MENTION,
            )

            rel_manager = AgentRelationshipManager()
            primary_id = self._primary_agent_id or ""
            now = _time.time()
            copresence_window = 300.0  # 5分钟

            # 1. 共在场：检查活跃智能体最近是否发言
            active_agents = self._activity_store.get_active_agents(self._session_id)
            for activity in active_agents:
                aid = activity.agent_id
                if aid == primary_id:
                    continue
                last_spoke_at = activity.last_spoke_at
                if last_spoke_at and (now - last_spoke_at.timestamp()) < copresence_window:
                    await rel_manager.update_coactivation(primary_id, aid, _COACTIVATION_DELTA_COPRESENCE)
                    await rel_manager.update_coactivation(aid, primary_id, _COACTIVATION_DELTA_COPRESENCE)

            # 2. 互相提及：检查回复文本中是否提及其他智能体
            if agent_reply_text:
                all_text = f"{user_text} {agent_reply_text}"
                registry = self._vitality_manager._registry
                for agent_cfg in registry.all_agents():
                    aid = agent_cfg.agent_id
                    if aid == primary_id:
                        continue
                    name = agent_cfg.display_name
                    if name in all_text or aid in all_text:
                        await rel_manager.update_coactivation(primary_id, aid, _COACTIVATION_DELTA_MENTION)
                        await rel_manager.update_coactivation(aid, primary_id, _COACTIVATION_DELTA_MENTION)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "更新共激活状态失败", exception=exc)
            logger.debug(f"[agent_autonomy] 共激活更新跳过: error={exc}")
