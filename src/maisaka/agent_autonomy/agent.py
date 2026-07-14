from typing import Any, Optional

from src.common.logger import get_logger
from src.core.protocols import ThinkingOrgan as ThinkingOrganProtocol
from src.core.protocols import ThinkingOrganFactory
from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder
from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan
from src.maisaka.agent_autonomy.inner_need import InnerNeed, InnerNeedEngine
from src.maisaka.agent_autonomy.inner_need import (
    EmotionNeedCalculator,
    MemoryNeedCalculator,
    TimeNeedCalculator,
)
from src.maisaka.agent_autonomy.behavior_intent import BehaviorIntent, BehaviorIntentEngine
from src.maisaka.agent_autonomy.behavior_intent import (
    InnerNeedIntentSource,
    EmotionIntentSource,
    TopicRelevanceIntentSource,
    RelationshipIntentSource,
    InteractionSignalIntentSource,
)
from src.maisaka.agent_autonomy.inner_world import InnerWorld, InnerWorldSnapshot

logger = get_logger("agent_autonomy.agent")


class AutonomousAgent:
    """自主智能体——拥有思维器官、表达器官、内在需求和行为意图的自主主体。"""

    def __init__(self, agent_id: str, thinking_organ_factory: ThinkingOrganFactory | None = None) -> None:
        self._agent_id = agent_id
        self._prompt_builder = EmbodiedPlannerPromptBuilder(agent_id)

        if thinking_organ_factory is not None:
            self._thinking_organ = thinking_organ_factory.create(agent_id, "")
        else:
            raise ValueError(
                f"AutonomousAgent(agent={agent_id}) 需要 thinking_organ_factory，"
                f"简化模式已废除，所有思考路径必须走工具循环"
            )
        self._expression_organ = None
        self._emotion_manager = None
        self._relationship_manager = None
        self._memory_adapter = None
        self._agent_config = None
        self._inner_world: InnerWorld | None = None
        self._inner_need_engine: InnerNeedEngine | None = None

        self._init_engines()
        self._init_components()

    def _init_components(self) -> None:
        """初始化智能体的各个组件。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry.get_instance()
            if registry.has_agent(self._agent_id):
                self._agent_config = registry.get_agent(self._agent_id)
        except Exception as exc:
            logger.warning(
                f"[agent_autonomy] 加载智能体配置失败: agent={self._agent_id} error={exc}"
            )

        try:
            from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry

            emotion_registry = AgentEmotionManagerRegistry()
            self._emotion_manager = emotion_registry.get_emotion_manager(self._agent_id)
        except Exception as exc:
            logger.warning("情绪管理器初始化失败: agent=%s error=%s", self._agent_id, exc)

        try:
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

            rel_manager = AgentRelationshipManager()
            self._relationship_manager = rel_manager
        except Exception as exc:
            logger.warning("关系管理器初始化失败: agent=%s error=%s", self._agent_id, exc)

        try:
            from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter

            self._memory_adapter = AgentMemoryAdapter()
        except Exception as exc:
            logger.warning("记忆适配器初始化失败: agent=%s error=%s", self._agent_id, exc)

        if self._agent_config is not None:
            try:
                self._inner_world = InnerWorld(
                    self._agent_id, self._agent_config, inner_need_engine=self._inner_need_engine
                )
            except Exception as exc:
                logger.warning("内心世界初始化失败: agent=%s error=%s", self._agent_id, exc)

            try:
                self._set_memory_personality()
            except Exception as exc:
                logger.warning("记忆性格传递失败: agent=%s error=%s", self._agent_id, exc)

    def _init_engines(self) -> None:
        """初始化内在需求引擎和行为意图引擎。"""
        self._inner_need_engine = InnerNeedEngine()
        self._inner_need_engine.register_calculator("emotion", EmotionNeedCalculator())
        self._inner_need_engine.register_calculator("memory", MemoryNeedCalculator())
        self._inner_need_engine.register_calculator("time", TimeNeedCalculator())

        self._behavior_intent_engine = BehaviorIntentEngine(self._inner_need_engine)
        self._behavior_intent_engine.register_source("inner_need", InnerNeedIntentSource())
        self._behavior_intent_engine.register_source("emotion", EmotionIntentSource())
        self._behavior_intent_engine.register_source("topic_relevance", TopicRelevanceIntentSource())
        self._behavior_intent_engine.register_source("relationship", RelationshipIntentSource())
        self._behavior_intent_engine.register_source("interaction_signal", InteractionSignalIntentSource())

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def agent_config(self) -> object | None:
        return self._agent_config

    @property
    def thinking_organ(self) -> ThinkingOrganProtocol:
        return self._thinking_organ

    @property
    def expression_organ(self) -> object | None:
        return self._expression_organ

    @property
    def inner_need_engine(self) -> InnerNeedEngine:
        return self._inner_need_engine

    @property
    def behavior_intent_engine(self) -> BehaviorIntentEngine:
        return self._behavior_intent_engine

    @property
    def emotion_manager(self) -> object | None:
        return self._emotion_manager

    @property
    def relationship_manager(self) -> object | None:
        return self._relationship_manager

    @property
    def memory_adapter(self) -> object | None:
        return self._memory_adapter

    @property
    def inner_world(self) -> InnerWorld | None:
        return self._inner_world

    async def get_inner_world_snapshot(self) -> InnerWorldSnapshot | None:
        """获取内心世界状态快照。"""
        if self._inner_world is not None:
            return await self._inner_world.get_state_snapshot()
        return None

    def refresh_config(self) -> None:
        """从 AgentConfigRegistry 重新加载配置。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry.get_instance()
            if registry.has_agent(self._agent_id):
                self._agent_config = registry.get_agent(self._agent_id)
                if self._inner_world is not None and self._agent_config is not None:
                    self._inner_world = InnerWorld(
                        self._agent_id, self._agent_config, inner_need_engine=self._inner_need_engine
                    )
                self._set_memory_personality()
        except Exception as exc:
            logger.warning("配置刷新失败: agent=%s error=%s", self._agent_id, exc)

    def _set_memory_personality(self) -> None:
        """将记忆性格参数传递给 A_memorix。"""
        if self._agent_config is None:
            return
        try:
            import asyncio
            from src.core.adapters.memory_service import AMemorixMemoryServicePort

            port = AMemorixMemoryServicePort()
            params = self._agent_config.memory_personality.model_dump()
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(port.set_memory_personality(self._agent_id, params))
            except RuntimeError:
                asyncio.run(port.set_memory_personality(self._agent_id, params))
        except Exception as exc:
            logger.debug("记忆性格传递跳过: agent=%s error=%s", self._agent_id, exc)

    def get_emotion_state(self) -> Any | None:
        """获取当前情绪状态快照。"""
        if self._emotion_manager is not None:
            return self._emotion_manager.state
        return None

    async def evaluate_inner_needs(
        self,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
    ) -> list[InnerNeed]:
        """评估当前内在需求。"""
        return await self._inner_need_engine.evaluate(
            agent_id=self._agent_id,
            emotion_state=self.get_emotion_state(),
            memory_context=memory_context,
            time_context=time_context,
        )

    async def produce_behavior_intents(
        self,
        conversation_context: list[Any] | None = None,
        interaction_signals: list[Any] | None = None,
        memory_context: dict[str, Any] | None = None,
        time_context: dict[str, Any] | None = None,
        intent_threshold: float = 0.0,
    ) -> list[BehaviorIntent]:
        """自主产生行为意图。"""
        return await self._behavior_intent_engine.produce_intents(
            agent_id=self._agent_id,
            emotion_state=self.get_emotion_state(),
            conversation_context=conversation_context,
            interaction_signals=interaction_signals,
            memory_context=memory_context,
            time_context=time_context,
            intent_threshold=intent_threshold,
        )

    def build_embodied_prompt_context(self, tools_section: str = "") -> dict[str, str]:
        """构建角色化 Planner 的提示词上下文。"""
        return self._prompt_builder._build_embodied_context(tools_section)

    def build_embodied_personality_prompt(self) -> str:
        """构建角色化人格提示词。"""
        return self._prompt_builder.build_personality_prompt()
