from src.common.logger import get_logger
from src.common.prompt import load_prompt
from src.config.config import global_config

logger = get_logger("agent_autonomy.prompt_builder")


class EmbodiedPlannerPromptBuilder:
    """角色化 Planner 提示词构建器——从旁观者视角变为角色内部视角。"""

    def __init__(self, agent_id: str) -> None:
        self._agent_id = agent_id
        self._degraded = False

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def is_degraded(self) -> bool:
        return self._degraded

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
        """
        from src.maisaka.agent.registry import AgentConfigRegistry

        registry = AgentConfigRegistry()
        agent_config = registry.get_agent(self._agent_id)

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
            "identity": agent_config.identity_prompt,
            "planner_idle_focus_rule": "",
            "query_memory_rule": "",
            "agent_anti_mechanization": agent_anti_mechanization,
            "agent_internal_relationships": agent_internal_relationships,
            "agent_interaction_memory": agent_interaction_memory,
            "agent_favor_injection": agent_favor_injection,
            "agent_emotion_state": "",
            "agent_relationship": "",
        }

    def _build_fallback_prompt(self, tools_section: str) -> str:
        """降级为旁观者模式的提示词。"""
        try:
            context = self._build_embodied_context(tools_section)
            context["bot_name"] = global_config.bot.nickname
            return load_prompt("maisaka_chat", **context)
        except Exception:
            return f"You are a helpful AI assistant.\n\n{tools_section}"

    @staticmethod
    def _build_agent_interaction_memory(agent_id: str, agent_config: object) -> str:
        """构建智能体交互动态记忆提示词。"""
        try:
            from src.maisaka.agent_interaction.memory.profile import AgentProfileService
            from src.maisaka.agent_interaction.memory.adapter import AgentMemoryAdapter
            from src.maisaka.agent_interaction.event_store import InteractionEventStore
            import asyncio

            if not getattr(agent_config, "internal_relationships", None):
                return ""

            adapter = AgentMemoryAdapter()
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
        except Exception:
            return ""

    def _get_agent_display_name(self) -> str:
        """获取智能体的显示名称。"""
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry()
            if registry.has_agent(self._agent_id):
                agent_config = registry.get_agent(self._agent_id)
                return agent_config.display_name or self._agent_id
        except Exception:
            pass
        return self._agent_id