from src.common.logger import get_logger
from src.maisaka.agent_autonomy.prompt_builder import EmbodiedPlannerPromptBuilder
from src.maisaka.agent_autonomy.thinking_organ import ThinkingOrgan

logger = get_logger("agent_autonomy.agent")


class AutonomousAgent:
    """自主智能体——拥有思维器官、表达器官、内在需求和行为意图的自主主体。"""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._prompt_builder = EmbodiedPlannerPromptBuilder(agent_id)
        self._thinking_organ = ThinkingOrgan(agent_id, self._prompt_builder)
        self._expression_organ = None
        self._inner_need_engine = None
        self._behavior_intent_engine = None
        self._emotion_manager = None
        self._relationship_manager = None
        self._memory_adapter = None
        self._agent_config = None

        self._init_components()

    def _init_components(self) -> None:
        """初始化智能体的各个组件。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
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
        except Exception:
            pass

        try:
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

            rel_manager = AgentRelationshipManager()
            self._relationship_manager = rel_manager
        except Exception:
            pass

        try:
            from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter

            self._memory_adapter = AgentMemoryAdapter()
        except Exception:
            pass

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def agent_config(self) -> object | None:
        return self._agent_config

    @property
    def thinking_organ(self) -> ThinkingOrgan:
        return self._thinking_organ

    @property
    def expression_organ(self) -> object | None:
        return self._expression_organ

    @property
    def inner_need_engine(self) -> object | None:
        return self._inner_need_engine

    @property
    def behavior_intent_engine(self) -> object | None:
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

    def build_embodied_prompt_context(self, tools_section: str = "") -> dict[str, str]:
        """构建角色化 Planner 的提示词上下文。

        Returns:
            与 build_prompt_template_context() 兼容的字典，
            但 identity/emotion/relationship/memory 均为该智能体的独立数据。
        """
        return self._prompt_builder._build_embodied_context(tools_section)

    def build_embodied_personality_prompt(self) -> str:
        """构建角色化人格提示词。

        Returns:
            "你是{角色名}，你在思考如何回应" 格式的人格提示词。
        """
        return self._prompt_builder.build_personality_prompt()