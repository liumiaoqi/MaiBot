from src.common.logger import get_logger
from src.config.config import global_config

logger = get_logger("agent_autonomy.chat_loop_adapter")


class ChatLoopServiceAdapter:
    """对话循环服务适配器，支持运行时切换 agent_id 和提示词上下文。"""

    def __init__(self, chat_loop_service: "MaisakaChatLoopService") -> None:
        self._chat_loop_service = chat_loop_service
        self._use_embodied_prompt = False

    @property
    def chat_loop_service(self) -> "MaisakaChatLoopService":
        return self._chat_loop_service

    @property
    def current_agent_id(self) -> str:
        return self._chat_loop_service._agent_id or ""

    def switch_agent_context(self, agent_id: str) -> None:
        """切换当前活跃的智能体上下文。

        切换后，personality_prompt、build_prompt_template_context()
        等方法将返回目标智能体的上下文。
        """
        old_agent_id = self._chat_loop_service._agent_id
        self._chat_loop_service._agent_id = agent_id

        # 更新情绪状态文本
        try:
            from src.maisaka.agent_interaction.emotion_registry import AgentEmotionManagerRegistry

            emotion_registry = AgentEmotionManagerRegistry()
            emotion_manager = emotion_registry.get_emotion_manager(agent_id)
            if emotion_manager is not None:
                emotion_state = emotion_manager.state
                self._chat_loop_service.update_emotion_state_text(
                    emotion_state.to_prompt_text()
                )
        except Exception:
            self._chat_loop_service.update_emotion_state_text("")

        # 更新关系文本
        try:
            from src.maisaka.agent_interaction.relationship_manager import AgentRelationshipManager

            rel_manager = AgentRelationshipManager()
            # 关系文本在 build_prompt_template_context 中动态获取
            self._chat_loop_service.update_relationship_text("")
        except Exception:
            pass

        logger.debug(
            f"[agent_autonomy] 上下文切换: agent {old_agent_id} -> {agent_id}"
        )

    def switch_to_embodied_prompt(self) -> None:
        """切换到角色化 Planner 提示词模板。"""
        self._use_embodied_prompt = True

    def switch_to_observer_prompt(self) -> None:
        """切换回旁观者模式 Planner 提示词模板（降级时使用）。"""
        self._use_embodied_prompt = False

    @property
    def use_embodied_prompt(self) -> bool:
        return self._use_embodied_prompt

    def get_prompt_template_name(self) -> str:
        """获取当前应使用的提示词模板名。"""
        if self._use_embodied_prompt:
            return "maisaka_chat_embodied"
        return self._chat_loop_service._get_chat_prompt_name()