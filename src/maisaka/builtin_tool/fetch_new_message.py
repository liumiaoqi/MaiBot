"""fetch_new_message focus-mode builtin tool."""

from typing import Any, Optional

from .context import BuiltinToolRuntimeContext
from src.config.config import global_config
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec


def get_tool_spec() -> ToolSpec:
    """Build the fetch_new_message tool spec."""

    return ToolSpec(
        name="fetch_new_message",
        description=(
            "按 chat_id，或 platform + id + type(group/private) 获取某个运行中已创建聊天的最新消息。"
            "返回内容来自目标聊天，不是当前聊天。page 不填默认为最新一页，num 是每页数量。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "string",
                    "description": "目标聊天的真实 chat_id；与 platform/id/type 组合二选一。",
                },
                "platform": {
                    "type": "string",
                    "description": "目标聊天平台；与 id、type 一起使用。",
                },
                "id": {
                    "type": "string",
                    "description": "目标 ID。type=group 时为群 ID，type=private 时为用户 ID。",
                },
                "type": {
                    "type": "string",
                    "enum": ["group", "private"],
                    "description": "目标聊天类型。",
                },
                "page": {
                    "type": "integer",
                    "description": "页码。1 表示最新一页；不填默认为 1。",
                    "minimum": 1,
                },
                "num": {
                    "type": "integer",
                    "description": "每页消息数；不填默认为 10。",
                    "minimum": 1,
                    "maximum": 50,
                },
            },
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


def _coerce_positive_int(value: Any, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """Execute fetch_new_message."""

    del context
    if not bool(global_config.experimental.focus_mode):
        return tool_ctx.build_failure_result(invocation.tool_name, "focus_mode 未启用，fetch_new_message 不可用。")

    resolution = tool_ctx.runtime.resolve_running_focus_session_from_args(invocation.arguments)
    if resolution.session is None:
        return tool_ctx.build_failure_result(invocation.tool_name, resolution.error)

    page = _coerce_positive_int(invocation.arguments.get("page"), 1)
    num = min(50, _coerce_positive_int(invocation.arguments.get("num"), 10))
    content, structured_content, post_history_messages = await tool_ctx.runtime.build_focus_fetch_messages_result(
        resolution.session,
        page=page,
        num=num,
    )
    return tool_ctx.build_success_result(
        invocation.tool_name,
        content,
        structured_content=structured_content,
        metadata={"record_display_prompt": content},
        post_history_messages=post_history_messages,
    )
