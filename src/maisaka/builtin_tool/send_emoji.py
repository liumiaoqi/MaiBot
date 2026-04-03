"""send_emoji 内置工具。"""

from datetime import datetime
from random import sample
from secrets import token_hex
from typing import Any, Dict, Optional

import asyncio

from pydantic import BaseModel, Field as PydanticField

from src.chat.emoji_system.emoji_manager import emoji_manager
from src.chat.emoji_system.maisaka_tool import send_emoji_for_maisaka
from src.common.data_models.message_component_data_model import ImageComponent, MessageSequence, TextComponent
from src.common.data_models.image_data_model import MaiEmoji
from src.common.logger import get_logger
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.llm_models.payload_content.resp_format import RespFormat, RespFormatType
from src.maisaka.context_messages import LLMContextMessage, ReferenceMessage, ReferenceMessageType, SessionBackedMessage

from .context import BuiltinToolRuntimeContext

logger = get_logger("maisaka_builtin_send_emoji")

_EMOJI_SUB_AGENT_CONTEXT_LIMIT = 12
_EMOJI_SUB_AGENT_MAX_TOKENS = 240
_EMOJI_SUB_AGENT_SAMPLE_SIZE = 20
_EMOJI_SUCCESS_MESSAGE = "???????"


class EmojiSelectionResult(BaseModel):
    """表情包子代理的结构化选择结果。"""

    emoji_id: str = PydanticField(default="", description="选中的候选表情包 ID。")
    matched_emotion: str = PydanticField(default="", description="本次命中的情绪标签，可为空。")
    reason: str = PydanticField(default="", description="简短选择理由。")


def get_tool_spec() -> ToolSpec:
    """获取 send_emoji 工具声明。"""

    return ToolSpec(
        name="send_emoji",
        brief_description="发送一个合适的表情包来辅助表达情绪。",
        detailed_description="参数说明：\n- emotion：string，可选。希望表达的情绪，例如 happy、sad、angry 等。",
        parameters_schema={
            "type": "object",
            "properties": {
                "emotion": {
                    "type": "string",
                    "description": "希望表达的情绪，例如 happy、sad、angry 等。",
                },
            },
        },
        provider_name="maisaka_builtin",
        provider_type="builtin",
    )


async def _build_emoji_candidate_message(emoji: MaiEmoji, candidate_id: str) -> SessionBackedMessage:
    """构建供子代理挑选的图片候选消息。"""

    image_bytes = await asyncio.to_thread(emoji.full_path.read_bytes)
    raw_message = MessageSequence(
        [
            TextComponent(f"ID: {candidate_id}"),
            ImageComponent(binary_hash=str(emoji.file_hash or ""), binary_data=image_bytes),
        ]
    )
    return SessionBackedMessage(
        raw_message=raw_message,
        visible_text=f"ID: {candidate_id}",
        timestamp=datetime.now(),
        source_kind="emoji_candidate",
    )


async def _select_emoji_with_sub_agent(
    tool_ctx: BuiltinToolRuntimeContext,
    requested_emotion: str,
    reasoning: str,
    context_texts: list[str],
    sample_size: int,
) -> tuple[MaiEmoji | None, str]:
    """通过临时子代理从候选表情包中选出一个结果。"""

    available_emojis = list(emoji_manager.emojis)
    if not available_emojis:
        return None, ""

    effective_sample_size = min(max(sample_size, 1), _EMOJI_SUB_AGENT_SAMPLE_SIZE, len(available_emojis))
    sampled_emojis = sample(available_emojis, effective_sample_size)

    candidate_map: dict[str, MaiEmoji] = {}
    candidate_messages: list[LLMContextMessage] = []
    for emoji in sampled_emojis:
        candidate_id = token_hex(4)
        while candidate_id in candidate_map:
            candidate_id = token_hex(4)
        candidate_map[candidate_id] = emoji
        candidate_messages.append(await _build_emoji_candidate_message(emoji, candidate_id))

    context_text = "\n".join(context_texts[-5:]) if context_texts else "（暂无额外上下文）"
    system_prompt = (
        "你是 Maisaka 的临时表情包选择子代理。\n"
        "你会收到一段群聊上下文，以及若干条候选表情包消息。每条候选消息里都有一个临时 ID。\n"
        "你的任务是根据上下文、当前语气和发送意图，从候选里选出最合适的一个表情包。\n"
        "必须只从候选消息中选择，不能编造新的 ID。\n"
        "如果提供了 requested_emotion，请优先考虑与其接近的候选；如果没有完全匹配，则选择最符合上下文语气的候选。\n"
        "你必须返回一个 JSON 对象（json object），不要输出任何 JSON 之外的内容。\n"
        '返回格式固定为：{"emoji_id":"候选ID","matched_emotion":"情绪标签","reason":"简短理由"}'
    )
    prompt_message = ReferenceMessage(
        content=(
            f"[选择任务]\n"
            f"requested_emotion: {requested_emotion or '未指定'}\n"
            f"reasoning: {reasoning or '辅助表达当前语气和情绪'}\n"
            f"recent_context:\n{context_text}\n"
            '请只输出 JSON。'
        ),
        timestamp=datetime.now(),
        reference_type=ReferenceMessageType.TOOL_HINT,
        remaining_uses_value=1,
        display_prefix="[表情包选择任务]",
    )

    response = await tool_ctx.runtime.run_sub_agent(
        context_message_limit=_EMOJI_SUB_AGENT_CONTEXT_LIMIT,
        system_prompt=system_prompt,
        extra_messages=[prompt_message, *candidate_messages],
        max_tokens=_EMOJI_SUB_AGENT_MAX_TOKENS,
        response_format=RespFormat(
            format_type=RespFormatType.JSON_SCHEMA,
            schema=EmojiSelectionResult,
        ),
    )

    try:
        selection = EmojiSelectionResult.model_validate_json(response.content or "")
    except Exception as exc:
        logger.warning(f"{tool_ctx.runtime.log_prefix} 表情包子代理结果解析失败，将回退到候选首项: {exc}")
        fallback_emoji = sampled_emojis[0] if sampled_emojis else None
        return fallback_emoji, requested_emotion

    selected_emoji = candidate_map.get(selection.emoji_id.strip())
    if selected_emoji is None:
        logger.warning(
            f"{tool_ctx.runtime.log_prefix} 表情包子代理返回了无效 ID: {selection.emoji_id!r}，将回退到候选首项"
        )
        fallback_emoji = sampled_emojis[0] if sampled_emojis else None
        return fallback_emoji, requested_emotion

    matched_emotion = selection.matched_emotion.strip()
    if not matched_emotion:
        matched_emotion = requested_emotion.strip()
    return selected_emoji, matched_emotion


async def handle_tool(
    tool_ctx: BuiltinToolRuntimeContext,
    invocation: ToolInvocation,
    context: Optional[ToolExecutionContext] = None,
) -> ToolExecutionResult:
    """执行 send_emoji 内置工具。"""

    del context
    emotion = str(invocation.arguments.get("emotion") or "").strip()
    context_texts = [
        message.processed_plain_text.strip()
        for message in tool_ctx.runtime._chat_history[-5:]
        if isinstance(message, LLMContextMessage) and message.processed_plain_text.strip()
    ]
    structured_result: Dict[str, Any] = {
        "success": False,
        "message": "",
        "description": "",
        "emotion": [],
        "requested_emotion": emotion,
        "matched_emotion": "",
    }

    logger.info(f"{tool_ctx.runtime.log_prefix} 触发表情包发送工具，请求情绪={emotion!r}")

    try:
        send_result = await send_emoji_for_maisaka(
            stream_id=tool_ctx.runtime.session_id,
            requested_emotion=emotion,
            reasoning=tool_ctx.engine.last_reasoning_content,
            context_texts=context_texts,
            emoji_selector=lambda requested_emotion, reasoning, context_texts, sample_size: _select_emoji_with_sub_agent(
                tool_ctx,
                requested_emotion,
                reasoning,
                list(context_texts or []),
                sample_size,
            ),
        )
    except Exception as exc:
        logger.exception(f"{tool_ctx.runtime.log_prefix} 发送表情包时发生异常: {exc}")
        structured_result["message"] = f"发送表情包时发生异常：{exc}"
        return tool_ctx.build_failure_result(
            invocation.tool_name,
            structured_result["message"],
            structured_content=structured_result,
        )

    if send_result.success:
        structured_result["message"] = _EMOJI_SUCCESS_MESSAGE
        logger.info(
            f"{tool_ctx.runtime.log_prefix} ??????? "
            f"??={send_result.description!r} ????={send_result.emotions} "
            f"????={emotion!r} ????={send_result.matched_emotion!r}"
        )
        tool_ctx.append_sent_emoji_to_chat_history(
            emoji_base64=send_result.emoji_base64,
            success_message=_EMOJI_SUCCESS_MESSAGE,
        )
        structured_result["success"] = True
        return tool_ctx.build_success_result(
            invocation.tool_name,
            _EMOJI_SUCCESS_MESSAGE,
            structured_content=structured_result,
        )

    structured_result["description"] = send_result.description
    structured_result["emotion"] = list(send_result.emotions)
    structured_result["matched_emotion"] = send_result.matched_emotion
    structured_result["message"] = send_result.message

    logger.warning(
        f"{tool_ctx.runtime.log_prefix} 表情包发送失败 "
        f"请求情绪={emotion!r} 错误信息={send_result.message}"
    )
    return tool_ctx.build_failure_result(
        invocation.tool_name,
        structured_result["message"],
        structured_content=structured_result,
    )
