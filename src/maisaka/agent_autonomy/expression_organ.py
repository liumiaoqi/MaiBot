from src.common.logger import get_logger
from src.maisaka.agent_autonomy.autonomy_logger import AutonomyEventType, AutonomyLogger

logger = get_logger("agent_autonomy.expression_organ")


class ExpressionOrgan:
    """表达器官——以角色风格运行 Replyer，绑定发言标记。"""

    def __init__(self, agent_id: str, speaker_tag_format: str = "【{agent_name}】") -> None:
        self._agent_id = agent_id
        self._speaker_tag_format = speaker_tag_format
        self._agent_display_name: str | None = None
        self._autonomy_logger = AutonomyLogger.get()

    @property
    def agent_id(self) -> str:
        return self._agent_id

    def build_speaker_tag(self) -> str:
        """构建发言标记。

        Returns:
            如 "【银狼】" 格式的发言标记。
        """
        agent_name = self._get_agent_display_name()
        return self._speaker_tag_format.format(agent_name=agent_name, agent_id=self._agent_id)

    def should_show_speaker_tag(self, is_multi_agent_active: bool) -> bool:
        """判断是否应显示发言标记。

        Args:
            is_multi_agent_active: 当前会话是否有多个活跃智能体

        Returns:
            仅在多智能体活跃时显示发言标记
        """
        return is_multi_agent_active

    def prepend_speaker_tag(self, content: str, is_multi_agent_active: bool) -> str:
        """在消息内容前添加发言标记（仅在多智能体活跃时）。

        Args:
            content: 原始消息内容
            is_multi_agent_active: 当前会话是否有多个活跃智能体

        Returns:
            带发言标记的消息内容
        """
        if not self.should_show_speaker_tag(is_multi_agent_active):
            return content
        tag = self.build_speaker_tag()
        self._autonomy_logger.log(
            self._agent_id,
            AutonomyEventType.EXPRESSION,
            f"添加发言标记: {tag}",
        )
        return f"{tag}{content}"

    def _get_agent_display_name(self) -> str:
        """获取智能体的显示名称。"""
        if self._agent_display_name is not None:
            return self._agent_display_name
        try:
            from src.maisaka.agent.registry import AgentConfigRegistry

            registry = AgentConfigRegistry.get_instance()
            if registry.has_agent(self._agent_id):
                agent_config = registry.get_agent(self._agent_id)
                self._agent_display_name = agent_config.display_name or self._agent_id
                return self._agent_display_name
        except Exception:
            pass
        self._agent_display_name = self._agent_id
        return self._agent_display_name