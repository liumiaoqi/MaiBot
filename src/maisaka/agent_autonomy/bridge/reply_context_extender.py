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

    @staticmethod
    def guard_outbound_text(
        text: str,
        *,
        agent_id: str,
        source: str,
    ) -> bool:
        """出站前判空：**空正文 / 只剩前缀 / 只有空括号**一律**拒发**（返回 False）。

        调用方拿到 False **必须不要发**（这是"要么不出、要么具名"里的"不出"，
        "具名"由 `report_rejected_outbound_text` 落成 logger + 上报口**双通道**）。

        为什么把闸放在这里：这条链（agent_autonomy）原本**只加前缀、无任何过滤**，
        而四个出站点都从这里加前缀 ⇒ 这里是有"最终文本"的**唯一共同点**。
        实测现场：`【Veliona】()`（空壳）与 `agent=bronya` 署名 `【银狼】` 都是从这条链原样出站的。
        """
        from src.maisaka.agent_autonomy.expression_organ import (
            is_sendable_outbound_text,
            report_rejected_outbound_text,
        )
        from src.core.app_config_port_registry import get_app_config_port

        try:
            tag_format = get_app_config_port().get_agent_autonomy_config().speaker_tag_format
        except Exception as exc:
            # 拿不到配置就**别判**（判据依赖格式）；照旧放行，但把这次降级说出来。
            logger.warning("[outbound] 取 speaker_tag_format 失败，跳过空内容闸: %s", exc)
            return True

        sendable, reason = is_sendable_outbound_text(text, tag_format)
        if sendable:
            return True
        report_rejected_outbound_text(reason, agent_id=agent_id, text=text, source=source)
        return False

    @staticmethod
    def guard_outbound_sequence(
        sequence,
        *,
        agent_id: str,
        source: str,
    ) -> bool:
        """按**消息序列**判空；返回 False ⇒ 这条序列**不要发**。

        与 `guard_outbound_text` 的分工：那条只看文本，这条看**整条序列**——
        **只对"纯文本序列"生效**。理由：富回复里图片/表情等分量本来就没有可见文本，
        若拿"可见文本为空"去拒它们，等于把**图片回复**一起拒掉（那是另一个 bug）。
        非文本分量的存在本身就是"非空内容"的证据。

        Args:
            sequence: `MessageSequence`（或任何有 `.components` 的对象）。
            agent_id: 发言智能体（进日志）。
            source: 出站来源标记（进日志）。

        Returns:
            bool: True=可发；False=已拒（调用方必须跳过）。
        """
        from src.common.data_models.message_component_data_model import TextComponent

        components = list(getattr(sequence, "components", []) or [])
        if any(not isinstance(component, TextComponent) for component in components):
            return True  # 有非文本分量（图片/表情/转发…）⇒ 不是"空内容"
        visible = "".join(
            component.text for component in components if isinstance(component, TextComponent)
        )
        return ReplyToolContextExtender.guard_outbound_text(
            visible, agent_id=agent_id, source=source
        )
