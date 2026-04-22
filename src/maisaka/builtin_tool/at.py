"""Maisaka 内置 at 工具。"""

from typing import Any, Optional, TYPE_CHECKING

from src.cli.maisaka_cli_sender import CLI_PLATFORM_NAME, render_cli_message
from src.common.data_models.message_component_data_model import AtComponent, MessageSequence, TextComponent
from src.common.logger import get_logger
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.services import send_service

if TYPE_CHECKING:
    from .context import BuiltinToolRuntimeContext

logger = get_logger("maisaka_builtin_at")


def get_tool_spec() -> ToolSpec:
    """获取 at 工具声明。"""

    return ToolSpec(
        name="at",
        brief_description="当明确提及某位用户时，发送一条 @ 该用户的消息。",
        detailed_description=(
            "参数说明：\n"
            "- msg_id：string，必填。要 @ 的目标用户发过的消息编号。\n"
            "- text：string，可选。@ 后追加发送的短文本；只想单独 @ 人时留空。\n"
            "请优先从上下文里选择一条明确属于目标用户的 msg_id，不要凭昵称或印象猜测用户。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "msg_id": {
                    "type": "string",
                    "description": "要 @ 的目标用户发过的消息编号。",
                },
                "text": {
                    "type": "string",
                    "description": "@ 后追加发送的短文本；只想单独 @ 人时留空。",
                    "default": "",
                },
            },
            "required": ["msg_id"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


def _get_target_user_info(target_message: Any) -> tuple[str, str, str]:
    """从目标消息中提取可用于构造 at 组件的用户信息。"""

    message_info = getattr(target_message, "message_info", None)
    user_info = getattr(message_info, "user_info", None)
    target_user_id = str(getattr(user_info, "user_id", "") or "").strip()
    target_user_nickname = str(getattr(user_info, "user_nickname", "") or "").strip()
    target_user_cardname = str(getattr(user_info, "user_cardname", "") or "").strip()
    return target_user_id, target_user_nickname, target_user_cardname


def _build_at_message_sequence(
    *,
    target_user_id: str,
    target_user_nickname: str = "",
    target_user_cardname: str = "",
    text: str = "",
) -> MessageSequence:
    """构造 @ 用户的消息组件序列。"""

    components = [
        AtComponent(
            target_user_id=target_user_id,
            target_user_nickname=target_user_nickname or None,
            target_user_cardname=target_user_cardname or None,
        )
    ]
    normalized_text = text.strip()
    if normalized_text:
        components.append(TextComponent(f" {normalized_text}"))
    return MessageSequence(components=components)


async def handle_tool(
    tool_ctx: "BuiltinToolRuntimeContext",
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 at 内置工具。"""

    del context
    target_message_id = str(invocation.arguments.get("msg_id") or "").strip()
    text = str(invocation.arguments.get("text") or "").strip()

    if not target_message_id:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "at 工具需要提供有效的 `msg_id` 参数。",
        )

    if not str(getattr(tool_ctx.runtime.chat_stream, "group_id", "") or "").strip():
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "at 工具只能在群聊中使用。",
            structured_content={"msg_id": target_message_id},
        )

    target_message = tool_ctx.runtime._source_messages_by_id.get(target_message_id)
    if target_message is None:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"未找到要 @ 的目标消息，msg_id={target_message_id}",
            structured_content={"msg_id": target_message_id},
        )

    target_user_id, target_user_nickname, target_user_cardname = _get_target_user_info(target_message)
    if not target_user_id:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"目标消息缺少有效用户 ID，msg_id={target_message_id}",
            structured_content={"msg_id": target_message_id},
        )

    target_user_name = target_user_cardname or target_user_nickname or target_user_id
    message_sequence = _build_at_message_sequence(
        target_user_id=target_user_id,
        target_user_nickname=target_user_nickname,
        target_user_cardname=target_user_cardname,
        text=text,
    )
    display_message = f"@{target_user_name}" + (f" {text}" if text else "")

    try:
        if tool_ctx.runtime.chat_stream.platform == CLI_PLATFORM_NAME:
            render_cli_message(display_message)
            tool_ctx.append_guided_reply_to_chat_history(display_message)
            sent_message = None
            sent = True
        else:
            sent_message = await send_service._send_to_target_with_message(
                message_sequence=message_sequence,
                stream_id=tool_ctx.runtime.session_id,
                display_message=display_message,
                typing=False,
                storage_message=True,
                show_log=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind="guided_reply",
            )
            sent = sent_message is not None
    except Exception as exc:
        logger.exception(
            f"{tool_ctx.runtime.log_prefix} 发送 at 消息时发生异常: msg_id={target_message_id} user_id={target_user_id}"
        )
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"发送 at 消息时发生异常：{exc}",
            structured_content={
                "msg_id": target_message_id,
                "target_user_id": target_user_id,
                "target_user_name": target_user_name,
            },
        )

    if not sent:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "at 消息发送失败。",
            structured_content={
                "msg_id": target_message_id,
                "target_user_id": target_user_id,
                "target_user_name": target_user_name,
            },
        )

    sent_message_id = str(getattr(sent_message, "message_id", "") or "").strip() if sent_message is not None else ""
    tool_ctx.runtime._record_reply_sent()
    return tool_ctx.build_success_result(
        invocation.tool_name,
        f"已 @ {target_user_name}。",
        structured_content={
            "msg_id": target_message_id,
            "target_user_id": target_user_id,
            "target_user_name": target_user_name,
            "text": text,
            "sent_message_id": sent_message_id,
        },
    )
