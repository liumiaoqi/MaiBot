"""reply 内置工具。"""

import traceback
from typing import Optional

from src.chat.replyer.replyer_manager import replyer_manager
from src.cli.maisaka_cli_sender import CLI_PLATFORM_NAME, render_cli_message
from src.common.data_models.reply_generation_data_models import ReplyGenerationResult
from src.common.logger import get_logger
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.services import send_service

from .context import BuiltinToolRuntimeContext

logger = get_logger("maisaka_builtin_reply")


async def _run_expression_selector(tool_ctx: BuiltinToolRuntimeContext, system_prompt: str) -> str:
    """运行 replyer 侧表达方式选择子代理，并返回文本结果。"""
    response = await tool_ctx.runtime.run_sub_agent(
        context_message_limit=10,
        system_prompt=system_prompt,
        request_kind="expression_selector",
        max_tokens=256,
        temperature=0.1,
    )
    return (response.content or "").strip()


def get_tool_spec() -> ToolSpec:
    """获取 reply 工具声明。"""

    return ToolSpec(
        name="reply",
        brief_description="根据当前思考生成并发送一条可见回复。",
        detailed_description=(
            "参数说明：\n"
            "- msg_id：string，必填。要回复的目标用户消息编号。\n"
            "- set_quote：boolean，可选。以引用回复的方式发送，默认 true。\n"
            "- reference_info：string，可选。上文中有助于回复的所有参考信息，使用平文本格式。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "msg_id": {
                    "type": "string",
                    "description": "要回复的目标用户消息编号。",
                },
                "set_quote": {
                    "type": "boolean",
                    "description": "以引用回复的方式发送这条回复，不用每句都引用。",
                    "default": True,
                },
                "reference_info": {
                    "type": "string",
                    "description": "有助于回复的信息，之前搜集得到的事实性信息，记忆等，使用平文本格式。",
                    "default": True,
                },
            },
            "required": ["msg_id"],
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


def _build_monitor_metadata(reply_result: ReplyGenerationResult) -> dict[str, object]:
    """从 reply 结果中提取统一监控详情。"""

    monitor_detail = reply_result.monitor_detail
    if isinstance(monitor_detail, dict):
        return {"monitor_detail": monitor_detail}
    return {}


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 reply 内置工具。"""

    latest_thought = context.reasoning if context is not None else invocation.reasoning
    reference_info = str(invocation.arguments.get("reference_info") or "").strip()
    target_message_id = str(invocation.arguments.get("msg_id") or "").strip()
    set_quote = bool(invocation.arguments.get("set_quote", True))

    if not target_message_id:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "reply 工具需要提供有效的 `msg_id` 参数。",
        )

    target_message = tool_ctx.runtime._source_messages_by_id.get(target_message_id)
    if target_message is None:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            f"未找到要回复的目标消息，msg_id={target_message_id}",
        )

    try:
        replyer = replyer_manager.get_replyer(
            chat_stream=tool_ctx.runtime.chat_stream,
            request_type="maisaka_replyer",
            replyer_type="maisaka",
        )
    except Exception:
        logger.exception(
            f"{tool_ctx.runtime.log_prefix} 获取回复生成器时发生异常: 目标消息编号={target_message_id}"
        )
        logger.info(traceback.format_exc())
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "获取 Maisaka 回复生成器时发生异常。",
        )

    if replyer is None:
        logger.error(f"{tool_ctx.runtime.log_prefix} 获取 Maisaka 回复生成器失败")
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "Maisaka 回复生成器当前不可用。",
        )

    replyer_chat_history = list(tool_ctx.runtime._chat_history)

    try:
        success, reply_result = await replyer.generate_reply_with_context(
            reply_reason=latest_thought,
            reference_info=reference_info,
            stream_id=tool_ctx.runtime.session_id,
            reply_message=target_message,
            chat_history=replyer_chat_history,
            sub_agent_runner=lambda system_prompt: _run_expression_selector(
                tool_ctx,
                system_prompt,
            ),
            log_reply=False,
        )
    except Exception as exc:
        logger.exception(
            f"{tool_ctx.runtime.log_prefix} 回复生成器执行异常: 目标消息编号={target_message_id} 异常={exc}"
        )
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "生成可见回复时发生异常。",
        )

    reply_metadata = _build_monitor_metadata(reply_result)
    reply_text = reply_result.completion.response_text.strip() if success else ""
    if not reply_text:
        logger.warning(
            f"{tool_ctx.runtime.log_prefix} 回复生成器返回空文本: "
            f"目标消息编号={target_message_id} 错误信息={reply_result.error_message!r}"
        )
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "生成可见回复失败。",
            metadata=reply_metadata,
        )

    reply_segments = tool_ctx.post_process_reply_text(reply_text)
    combined_reply_text = "".join(reply_segments)
    sent_message_ids: list[str] = []
    try:
        sent = False
        if tool_ctx.runtime.chat_stream.platform == CLI_PLATFORM_NAME:
            for segment in reply_segments:
                render_cli_message(segment)
            sent = True
        else:
            for index, segment in enumerate(reply_segments):
                sent_message = await send_service.text_to_stream_with_message(
                    text=segment,
                    stream_id=tool_ctx.runtime.session_id,
                    set_reply=set_quote if index == 0 else False,
                    reply_message=target_message if set_quote and index == 0 else None,
                    selected_expressions=reply_result.selected_expression_ids or None,
                    typing=index > 0,
                    sync_to_maisaka_history=True,
                    maisaka_source_kind="guided_reply",
                )
                sent = sent_message is not None
                if not sent:
                    break
                sent_message_id = str(getattr(sent_message, "message_id", "") or "").strip()
                if sent_message_id:
                    sent_message_ids.append(sent_message_id)
    except Exception:
        logger.exception(
            f"{tool_ctx.runtime.log_prefix} 发送文字消息时发生异常，目标消息编号={target_message_id}"
        )
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "发送可见回复时发生异常。",
            metadata=reply_metadata,
        )

    if not sent:
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            "可见回复生成成功，但发送失败。",
            structured_content={
                "msg_id": target_message_id,
                "set_quote": set_quote,
                "reply_segments": reply_segments,
            },
            metadata=reply_metadata,
        )

    target_user_info = target_message.message_info.user_info
    target_user_name = target_user_info.user_cardname or target_user_info.user_nickname or target_user_info.user_id

    if tool_ctx.runtime.chat_stream.platform == CLI_PLATFORM_NAME:
        tool_ctx.append_guided_reply_to_chat_history(combined_reply_text)
    tool_ctx.runtime._record_reply_sent()
    reply_metadata["sent_message_ids"] = sent_message_ids
    await tool_ctx.runtime.track_reply_effect(
        tool_call_id=invocation.call_id,
        target_message=target_message,
        set_quote=set_quote,
        reply_text=combined_reply_text,
        reply_segments=reply_segments,
        planner_reasoning=latest_thought,
        reference_info=reference_info,
        reply_metadata=reply_metadata,
        replyer_context_messages=replyer_chat_history,
    )
    return tool_ctx.build_success_result(
        invocation.tool_name,
        "回复已生成并发送。",
        structured_content={
            "msg_id": target_message_id,
            "set_quote": set_quote,
            "reply_text": combined_reply_text,
            "reply_segments": reply_segments,
            "target_user_name": target_user_name,
        },
        metadata=reply_metadata,
    )
