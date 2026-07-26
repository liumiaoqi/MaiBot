from typing import TYPE_CHECKING, Any, Callable

from src.common.logger import get_logger
from src.common.prompt_i18n import load_prompt
from src.core.app_config_port_registry import get_app_config_port
from src.core.bot_config_port_registry import get_bot_config_port

if TYPE_CHECKING:
    from src.maisaka.agent_autonomy.state_awareness.summary_generator import CohabitantStateSummaryGenerator

logger = get_logger("agent_autonomy.prompt_builder")

# 动态数据源类型：接收 agent_id，返回人设字符串
DynamicIdentityProvider = Callable[[str], str | None]


class EmbodiedPlannerPromptBuilder:
    """角色化 Planner 提示词构建器——从旁观者视角变为角色内部视角。

    支持动态数据源：可通过 register_identity_provider 注入动态人设提供者，
    使 {identity} 占位符可被运行时数据替换，为未来的动态性格引擎预留接口。
    """

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._degraded = False
        self._identity_providers: list[DynamicIdentityProvider] = []
        self._summary_generator: CohabitantStateSummaryGenerator | None = None

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_degraded(self) -> bool:
        return self._degraded

    def set_summary_generator(self, generator: CohabitantStateSummaryGenerator) -> None:
        """注入共居状态摘要生成器。"""
        self._summary_generator = generator

    def register_identity_provider(self, provider: DynamicIdentityProvider) -> None:
        """注册动态人设数据源。

        动态数据源按注册顺序依次调用，第一个返回非 None 的结果将替换
        默认的 identity_prompt。这为未来的动态性格引擎预留了接口。
        """
        self._identity_providers.append(provider)

    def build_system_prompt(self, tools_section: str = "") -> str:
        """构建角色化系统提示词。

        优先使用 maisaka_chat_embodied 模板，
        构建失败时降级为 maisaka_chat 旁观者模板。
        """
        try:
            context = self._build_embodied_context(tools_section)
            return load_prompt("maisaka_chat_embodied", **context)
        except Exception as exc:
            logger.warning(
                f"[agent_autonomy] 角色化提示词构建失败，降级为旁观者模板: "
                f"agent={self._agent_id} error={exc}"
            )
            self._degraded = True
            return self._build_fallback_prompt(tools_section)

    def build_personality_prompt(self) -> str:
        """构建角色化人格提示词。

        Returns:
            "你是{角色名}，你在思考如何回应" 格式的人格提示词。
        """
        agent_name = self._get_agent_display_name()
        return f"你是{agent_name}，你在思考如何回应"

    def get_prompt_template_name(self) -> str:
        """获取当前使用的提示词模板名。"""
        if self._degraded:
            return "maisaka_chat"
        return "maisaka_chat_embodied"

    def _build_embodied_context(self, tools_section: str) -> dict[str, str]:
        """构建角色化提示词渲染上下文。

        复用 MaisakaChatLoopService.build_prompt_template_context() 的 slot 结构，
        但 identity/emotion/relationship/memory 均为该智能体的独立数据。

        动态数据源优先：如果注册了 identity_provider 且返回非 None，
        则使用动态数据源替换默认的 identity_prompt。
        """
        from src.core.adapters.agent_config_port import get_agent_config_provider

        registry = get_agent_config_provider()
        agent_config = registry.get_agent(self._agent_id)

        # 动态数据源优先
        identity_prompt = agent_config.identity_prompt
        for provider in self._identity_providers:
            dynamic_identity = provider(self._agent_id)
            if dynamic_identity is not None:
                identity_prompt = dynamic_identity
                break

        agent_anti_mechanization = agent_config.anti_mechanization_prompt
        agent_internal_relationships = agent_config.internal_relationships_prompt
        agent_favor_injection = agent_config.get_favor_injection(
            user_name="",
            is_owner=False,
        )
        agent_interaction_memory = self._build_agent_interaction_memory(
            self._agent_id, agent_config
        )

        return {
            "bot_name": self._get_agent_display_name(),
            "file_tools_section": tools_section,
            "group_chat_attention_block": "",
            "identity": identity_prompt,
            "planner_idle_focus_rule": "",
            "query_memory_rule": self._build_query_memory_rule(),
            "agent_anti_mechanization": agent_anti_mechanization,
            "agent_internal_relationships": agent_internal_relationships,
            "agent_interaction_memory": agent_interaction_memory,
            "agent_favor_injection": agent_favor_injection,
            "agent_emotion_state": "",
            "agent_relationship": "",
            "butler_context": self._build_butler_context(),
            "cohabitant_states": self._build_cohabitant_states(),
        }

    def _build_butler_context(self) -> str:
        """构建管家存在提示文本。"""
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

        for orch in AgentOrchestrator._registry.values():
            butler = getattr(orch, "_butler", None)
            if butler is not None and getattr(butler, "_butler_display_name", ""):
                return (
                    f"# 管家\n"
                    f"{butler._butler_display_name}（{butler._butler_id}）是这个客厅的管家。"
                    f"她负责协调谁该说话、提醒大家该做什么、必要时自己也会发言。"
                    f"你可以通过管家来协调和其他角色的互动——她了解每个人的状态。"
                )
        return ""

    def _build_cohabitant_states(self) -> str:
        """构建共居状态摘要文本。"""
        if not get_app_config_port().get_agent_autonomy_config().state_awareness_enabled:
            return ""

        if self._summary_generator is None:
            return ""

        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

        for orch in AgentOrchestrator._registry.values():
            if self._agent_id in orch._active_agents:
                return self._summary_generator.generate(orch.session_id, self._agent_id)

        return ""

    def _build_query_memory_rule(self) -> str:
        """按当前聊天类型构造记忆检索提示。

        复用 MaisakaChatLoopService 的逻辑，通过 orchestrator 获取 is_group_chat。
        """
        from src.maisaka.agent_autonomy.orchestrator import AgentOrchestrator

        is_group_chat = False
        for orch in AgentOrchestrator._registry.values():
            if self._agent_id in orch._active_agents:
                is_group_chat = getattr(orch, "_is_group_chat", False)
                break

        if is_group_chat:
            return "- query_memory()：只有回复明显依赖群内过去对话、共同经历、公开约定、任务进展或近期线索时使用；不要为了寒暄、即时情绪回应、轻松接话、只看最近消息就能回答的内容而检索。不要把私聊或个人隐私记忆带到群聊里。"

        return "- query_memory()：当对方提到\"之前\"\"上次\"\"最近\"\"还记得吗\"\"我喜欢\"\"我说过\"等信号，或回复依赖长期偏好、先前承诺、共同经历、人物长期信息时，可以更积极检索。"

    def _build_fallback_prompt(self, tools_section: str) -> str:
        """降级为旁观者模式的提示词。"""
        try:
            context = self._build_embodied_context(tools_section)
            context["bot_name"] = get_bot_config_port().get_bot_nickname()
            return load_prompt("maisaka_chat", **context)
        except Exception as exc:
            logger.warning("操作异常 in prompt_builder.py", exc_info=True)
            return f"你是一个有用的AI助手。\n\n{tools_section}"

    @staticmethod
    def _build_agent_interaction_memory(agent_id: str, agent_config: object) -> str:
        """构建智能体交互动态记忆提示词。"""
        try:
            from src.maisaka.agent_interaction.memory.profile import AgentProfileService
            from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
            from src.maisaka.agent_interaction.event_store import InteractionEventStore
            from src.core.adapters import get_memory_service_port
            import asyncio

            if not agent_config.internal_relationships:
                return ""

            adapter = AgentMemoryAdapter(get_memory_service_port())
            store = InteractionEventStore()
            service = AgentProfileService(adapter, store)

            loop = None
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None and loop.is_running():
                return ""

            results: list[str] = []
            for rel in agent_config.internal_relationships:
                profile = asyncio.run(service.get_profile(agent_id, rel.target_agent_id))
                text = profile.to_prompt_text()
                if text:
                    display_name = rel.target_agent_id
                    results.append(f"- 与{display_name}：{text}")

            if not results:
                return ""
            return "## 最近的交互动态\n" + "\n".join(results)
        except Exception as exc:
            logger.warning("操作异常 in prompt_builder.py", exc_info=True)
            return ""

    def _get_agent_display_name(self) -> str:
        """获取智能体的显示名称。"""
        try:
            from src.core.adapters.agent_config_port import get_agent_config_provider

            registry = get_agent_config_provider()
            if registry.has_agent(self._agent_id):
                agent_config = registry.get_agent(self._agent_id)
                return agent_config.display_name or self._agent_id
        except Exception as exc:
            logger.warning("操作异常 in prompt_builder.py", exc_info=True)
        return self._agent_id
