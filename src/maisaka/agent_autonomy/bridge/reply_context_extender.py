from typing import TYPE_CHECKING

from src.common.logger import get_logger

logger = get_logger("agent_autonomy.reply_context_extender")

if TYPE_CHECKING:
    from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext


class ReplyToolContextExtender:
    """reply 工具上下文扩展——注入当前发言智能体 ID 和发言标记。"""

    @staticmethod
    def extend_context(
        tool_ctx: "BuiltinToolRuntimeContext",
        current_agent_id: str,
        is_multi_agent_active: bool = False,
    ) -> None:
        """扩展 reply 工具的运行时上下文。

        Args:
            tool_ctx: reply 工具的运行时上下文
            current_agent_id: 当前发言智能体 ID
            is_multi_agent_active: 当前会话是否有多个活跃智能体
        """
        tool_ctx.current_agent_id = current_agent_id
        tool_ctx.is_multi_agent_active = is_multi_agent_active

    @staticmethod
    def prepend_speaker_tag_to_content(
        content: str,
        agent_id: str,
        is_multi_agent_active: bool,
    ) -> str:
        """在消息内容前添加发言标记。

        Args:
            content: 原始消息内容
            agent_id: 发言智能体 ID
            is_multi_agent_active: 当前会话是否有多个活跃智能体

        Returns:
            带发言标记的消息内容
        """
        if not is_multi_agent_active:
            return content
        try:
            from src.maisaka.agent_autonomy.expression_organ import ExpressionOrgan
            from src.core.app_config_port_registry import get_app_config_port

            tag_format = get_app_config_port().get_agent_autonomy_config().speaker_tag_format
            organ = ExpressionOrgan(agent_id, tag_format)
            return organ.prepend_speaker_tag(content, is_multi_agent_active)
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "添加发言标记失败", exception=exc)
            logger.warning(f"添加发言标记失败: agent_id={agent_id}", exc_info=True)
            return content
