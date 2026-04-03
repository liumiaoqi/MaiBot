"""send_emoji 内置工具。"""

from datetime import datetime
from io import BytesIO
from random import sample
from typing import Any, Dict, Optional

import asyncio

from PIL import Image as PILImage
from PIL import ImageDraw, ImageFont
from pydantic import BaseModel, Field as PydanticField

from src.chat.emoji_system.emoji_manager import emoji_manager
from src.chat.emoji_system.maisaka_tool import send_emoji_for_maisaka
from src.common.data_models.image_data_model import MaiEmoji
from src.common.data_models.message_component_data_model import ImageComponent, MessageSequence, TextComponent
from src.common.logger import get_logger
from src.core.tooling import ToolExecutionContext, ToolExecutionResult, ToolInvocation, ToolSpec
from src.llm_models.payload_content.resp_format import RespFormat, RespFormatType
from src.maisaka.context_messages import (
    LLMContextMessage,
    ReferenceMessage,
    ReferenceMessageType,
    SessionBackedMessage,
)

from .context import BuiltinToolRuntimeContext

logger = get_logger("maisaka_builtin_send_emoji")

_EMOJI_SUB_AGENT_CONTEXT_LIMIT = 12
_EMOJI_SUB_AGENT_MAX_TOKENS = 240
_EMOJI_CANDIDATE_COUNT = 25
_EMOJI_CANDIDATE_TILE_SIZE = 256
_EMOJI_SUCCESS_MESSAGE = "表情包发送成功"


class EmojiSelectionResult(BaseModel):
    """表情包子代理的结构化选择结果。"""

    emoji_index: int = PydanticField(default=1, description="选中的表情包序号，从 1 开始计数。")
    reason: str = PydanticField(default="", description="选择这张表情包的简短理由。")


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


async def _load_emoji_bytes(emoji: MaiEmoji) -> bytes:
    """读取单个表情包图片字节。"""

    return await asyncio.to_thread(emoji.full_path.read_bytes)


def _build_placeholder_tile(label: str, tile_size: int) -> PILImage.Image:
    """构建图片读取失败时使用的占位图。"""

    tile = PILImage.new("RGB", (tile_size, tile_size), color=(245, 245, 245))
    draw = ImageDraw.Draw(tile)
    font = ImageFont.load_default()
    text_bbox = draw.textbbox((0, 0), label, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    draw.text(
        ((tile_size - text_width) / 2, (tile_size - text_height) / 2),
        label,
        fill=(80, 80, 80),
        font=font,
    )
    return tile


def _build_labeled_tile(image_bytes: bytes, index: int, tile_size: int) -> PILImage.Image:
    """构建带序号角标的候选图片块。"""

    try:
        with PILImage.open(BytesIO(image_bytes)) as raw_image:
            image = raw_image.convert("RGBA")
    except Exception:
        return _build_placeholder_tile(str(index), tile_size)

    image.thumbnail((tile_size, tile_size))
    tile = PILImage.new("RGBA", (tile_size, tile_size), color=(255, 255, 255, 255))
    offset_x = (tile_size - image.width) // 2
    offset_y = (tile_size - image.height) // 2
    tile.paste(image, (offset_x, offset_y), image)

    draw = ImageDraw.Draw(tile)
    font = ImageFont.load_default()
    badge_size = 56
    badge_margin = 14
    draw.rounded_rectangle(
        (
            badge_margin,
            badge_margin,
            badge_margin + badge_size,
            badge_margin + badge_size,
        ),
        radius=8,
        fill=(0, 0, 0, 180),
    )
    label = str(index)
    text_bbox = draw.textbbox((0, 0), label, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_height = text_bbox[3] - text_bbox[1]
    draw.text(
        (
            badge_margin + (badge_size - text_width) / 2,
            badge_margin + (badge_size - text_height) / 2 - 1,
        ),
        label,
        fill=(255, 255, 255, 255),
        font=font,
    )
    return tile


def _merge_emoji_tiles(image_bytes_list: list[bytes]) -> bytes:
    """将候选表情图拼接成一张 5x5 网格图片。"""

    tile_size = _EMOJI_CANDIDATE_TILE_SIZE
    gap = 12
    grid_columns = 5
    grid_rows = 5
    tiles = [
        _build_labeled_tile(image_bytes=image_bytes, index=index, tile_size=tile_size)
        for index, image_bytes in enumerate(image_bytes_list, start=1)
    ]
    canvas_width = tile_size * grid_columns + gap * (grid_columns - 1)
    canvas_height = tile_size * grid_rows + gap * (grid_rows - 1)
    canvas = PILImage.new("RGBA", (canvas_width, canvas_height), color=(255, 255, 255, 255))

    for index, tile in enumerate(tiles):
        row = index // grid_columns
        column = index % grid_columns
        offset_x = column * (tile_size + gap)
        offset_y = row * (tile_size + gap)
        canvas.paste(tile, (offset_x, offset_y), tile)

    output = BytesIO()
    canvas.convert("RGB").save(output, format="PNG")
    return output.getvalue()


async def _build_emoji_candidate_message(emojis: list[MaiEmoji]) -> SessionBackedMessage:
    """构建供子代理挑选的 5x5 拼图候选消息。"""

    image_bytes_list = await asyncio.gather(*[_load_emoji_bytes(emoji) for emoji in emojis])
    merged_image_bytes = await asyncio.to_thread(_merge_emoji_tiles, list(image_bytes_list))
    raw_message = MessageSequence(
        [
            TextComponent("请从这张 5x5 拼图中选择一个序号。"),
            ImageComponent(binary_hash="", binary_data=merged_image_bytes),
        ]
    )
    return SessionBackedMessage(
        raw_message=raw_message,
        visible_text="[表情包拼图候选]",
        timestamp=datetime.now(),
        source_kind="emoji_candidate",
    )


async def _select_emoji_with_sub_agent(
    tool_ctx: BuiltinToolRuntimeContext,
    requested_emotion: str,
    reasoning: str,
    context_texts: list[str],
    sample_size: int,
    selection_metadata: Optional[Dict[str, str]] = None,
) -> tuple[MaiEmoji | None, str]:
    """通过临时子代理从候选表情包中选出一个结果。"""

    del reasoning, context_texts, sample_size

    available_emojis = list(emoji_manager.emojis)
    if not available_emojis:
        return None, ""

    total_candidate_count = min(len(available_emojis), _EMOJI_CANDIDATE_COUNT)
    sampled_emojis = sample(available_emojis, total_candidate_count)
    candidate_message = await _build_emoji_candidate_message(sampled_emojis)

    system_prompt = (
        "你是 Maisaka 的临时表情包选择子代理。\n"
        "你会收到群聊上下文，以及 1 条额外候选消息，其中包含一张 5x5 的表情包拼图，一共 25 个位置。\n"
        "每张小图左上角都有一个较大的序号，范围是 1 到 25。\n"
        "你的任务是根据上下文和当前语气，从这 25 张图里选出最合适的一张表情包。\n"
        "如果提供了 requested_emotion，请优先考虑与其接近的候选；如果没有完全匹配，则选择最符合上下文语气的候选。\n"
        "你必须返回一个 JSON 对象（json object），不要输出任何 JSON 之外的内容。\n"
        '返回格式固定为：{"emoji_index":1,"reason":"简短理由"}'
    )
    prompt_message = ReferenceMessage(
        content=(
            f"[选择任务]\n"
            f"requested_emotion: {requested_emotion or '未指定'}\n"
            "请只输出 JSON。"
        ),
        timestamp=datetime.now(),
        reference_type=ReferenceMessageType.TOOL_HINT,
        remaining_uses_value=1,
        display_prefix="[表情包选择任务]",
    )

    response = await tool_ctx.runtime.run_sub_agent(
        context_message_limit=_EMOJI_SUB_AGENT_CONTEXT_LIMIT,
        system_prompt=system_prompt,
        extra_messages=[prompt_message, candidate_message],
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
        return fallback_emoji, ""

    if selection_metadata is not None:
        selection_metadata["reason"] = selection.reason.strip()

    emoji_index = int(selection.emoji_index)
    if emoji_index < 1 or emoji_index > len(sampled_emojis):
        logger.warning(
            f"{tool_ctx.runtime.log_prefix} 表情包子代理返回了无效序号: {emoji_index!r}，将回退到第 1 张"
        )
        emoji_index = 1

    return sampled_emojis[emoji_index - 1], ""


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
        "reason": "",
    }
    selection_metadata: Dict[str, str] = {"reason": ""}

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
                selection_metadata,
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
        structured_result["reason"] = selection_metadata["reason"]
        logger.info(
            f"{tool_ctx.runtime.log_prefix} 表情包发送成功 "
            f"描述={send_result.description!r} 情绪标签={send_result.emotions} "
            f"请求情绪={emotion!r} 命中情绪={send_result.matched_emotion!r}"
        )
        tool_ctx.append_sent_emoji_to_chat_history(
            emoji_base64=send_result.emoji_base64,
            success_message=_EMOJI_SUCCESS_MESSAGE,
        )
        structured_result["success"] = True
        return tool_ctx.build_success_result(
            invocation.tool_name,
            selection_metadata["reason"] or _EMOJI_SUCCESS_MESSAGE,
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
