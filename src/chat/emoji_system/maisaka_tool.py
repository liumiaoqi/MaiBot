"""Maisaka 表情工具内置能力。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Optional, Sequence, TYPE_CHECKING

import random

from src.chat.message_receive.chat_manager import chat_manager
from src.cli.maisaka_cli_sender import CLI_PLATFORM_NAME, render_cli_message
from src.common.data_models.image_data_model import MaiEmoji
from src.common.data_models.llm_service_data_models import LLMGenerationOptions
from src.common.logger import get_logger
from src.common.utils.utils_image import ImageUtils
from src.services import send_service

from .emoji_manager import _serialize_emoji_for_hook, emoji_manager, emoji_manager_emotion_judge_llm

logger = get_logger("emoji_maisaka_tool")

if TYPE_CHECKING:
    from src.chat.message_receive.message import SessionMessage

EmojiSelector = Callable[
    [str, str, Sequence[str] | None, int],
    Awaitable[tuple[MaiEmoji | None, str]],
]


@dataclass(slots=True)
class MaisakaEmojiSendResult:
    """Maisaka 表情发送结果。"""

    success: bool
    message: str
    emoji_base64: str = ""
    description: str = ""
    emotions: list[str] = field(default_factory=list)
    requested_emotion: str = ""
    matched_emotion: str = ""
    sent_message: Optional["SessionMessage"] = None


def _get_runtime_manager() -> Any:
    """获取插件运行时管理器。

    Returns:
        Any: 插件运行时管理器单例。
    """

    from src.plugin_runtime.integration import get_plugin_runtime_manager

    return get_plugin_runtime_manager()


def _coerce_positive_int(value: Any, default: int) -> int:
    """将任意值安全转换为正整数。

    Args:
        value: 待转换的值。
        default: 转换失败时使用的默认值。

    Returns:
        int: 规范化后的正整数。
    """

    try:
        normalized_value = int(value)
    except (TypeError, ValueError):
        return default
    return normalized_value if normalized_value > 0 else default


def _normalize_context_texts(context_texts: Sequence[str] | None) -> list[str]:
    """清洗 Hook 和调用链传入的上下文文本列表。

    Args:
        context_texts: 原始上下文文本序列。

    Returns:
        list[str]: 过滤空白后的上下文文本列表。
    """

    if not context_texts:
        return []
    return [str(item).strip() for item in context_texts if str(item).strip()]


def _resolve_selected_emoji(raw_value: Any) -> Optional[MaiEmoji]:
    """根据 Hook 返回值解析目标表情包对象。

    Args:
        raw_value: Hook 返回的 ``selected_emoji`` 或 ``selected_emoji_hash``。

    Returns:
        Optional[MaiEmoji]: 命中的表情包对象；未命中时返回 ``None``。
    """

    raw_hash: str = ""
    if isinstance(raw_value, dict):
        raw_hash = str(raw_value.get("file_hash") or raw_value.get("hash") or "").strip()
    elif isinstance(raw_value, str):
        raw_hash = raw_value.strip()

    if not raw_hash:
        return None

    for emoji in emoji_manager.emojis:
        if emoji.file_hash == raw_hash:
            return emoji
    return None


def _normalize_emotions(emoji: MaiEmoji) -> list[str]:
    """提取并清洗单个表情的情绪标签。"""

    return [str(item).strip() for item in emoji.emotion if str(item).strip()]


def _build_recent_context_text(context_texts: Sequence[str], max_items: int = 5) -> str:
    """构建供情绪判断使用的最近上下文文本。"""

    normalized_items = [str(item).strip() for item in context_texts if str(item).strip()]
    if not normalized_items:
        return ""
    return "\n".join(normalized_items[-max_items:])


async def _select_emoji_with_llm(
    *,
    sampled_emojis: Sequence[MaiEmoji],
    reasoning: str,
    context_text: str,
) -> tuple[MaiEmoji, str]:
    """让模型在采样表情中选择更合适的情绪标签。"""

    emotion_map: dict[str, list[MaiEmoji]] = {}
    for emoji in sampled_emojis:
        for emotion in _normalize_emotions(emoji):
            emotion_map.setdefault(emotion, []).append(emoji)

    available_emotions = list(emotion_map.keys())
    if not available_emotions:
        return random.choice(list(sampled_emojis)), ""

    prompt = (
        "你正在为聊天场景选择一个最合适的表情包情绪标签。\n"
        f"发送原因：{reasoning or '辅助表达当前语气和情绪'}\n"
        f"最近聊天记录：\n{context_text or '（暂无额外上下文）'}\n\n"
        "可选情绪标签如下：\n"
        f"{chr(10).join(available_emotions)}\n\n"
        "请只返回一个最匹配的情绪标签，不要解释。"
    )

    try:
        llm_result = await emoji_manager_emotion_judge_llm.generate_response(
            prompt,
            options=LLMGenerationOptions(temperature=0.3, max_tokens=60),
        )
        chosen_emotion = (llm_result.response or "").strip().strip("\"'")
    except Exception as exc:
        logger.warning(f"使用 LLM 选择表情情绪失败，将回退为随机选择: {exc}")
        chosen_emotion = ""

    if chosen_emotion and chosen_emotion in emotion_map:
        return random.choice(emotion_map[chosen_emotion]), chosen_emotion
    return random.choice(list(sampled_emojis)), ""


async def select_emoji_for_maisaka(
    *,
    requested_emotion: str = "",
    reasoning: str = "",
    context_texts: Sequence[str] | None = None,
    sample_size: int = 30,
) -> tuple[MaiEmoji | None, str]:
    """为 Maisaka 选择一个合适的表情。"""

    available_emojis = list(emoji_manager.emojis)
    if not available_emojis:
        return None, ""

    normalized_requested_emotion = requested_emotion.strip()
    if normalized_requested_emotion:
        matched_emojis = [
            emoji
            for emoji in available_emojis
            if normalized_requested_emotion.lower() in (emotion.lower() for emotion in _normalize_emotions(emoji))
        ]
        if matched_emojis:
            return random.choice(matched_emojis), normalized_requested_emotion

    sampled_emojis = random.sample(
        available_emojis,
        min(max(sample_size, 1), len(available_emojis)),
    )
    context_text = _build_recent_context_text(context_texts or [])
    return await _select_emoji_with_llm(
        sampled_emojis=sampled_emojis,
        reasoning=reasoning,
        context_text=context_text,
    )


async def send_emoji_for_maisaka(
    *,
    stream_id: str,
    requested_emotion: str = "",
    reasoning: str = "",
    context_texts: Sequence[str] | None = None,
    emoji_selector: EmojiSelector | None = None,
) -> MaisakaEmojiSendResult:
    """为 Maisaka 选择并发送一个表情。"""

    normalized_requested_emotion = requested_emotion.strip()
    normalized_reasoning = reasoning.strip()
    normalized_context_texts = _normalize_context_texts(context_texts)
    sample_size = 20

    before_select_result = await _get_runtime_manager().invoke_hook(
        "emoji.maisaka.before_select",
        stream_id=stream_id,
        requested_emotion=normalized_requested_emotion,
        reasoning=normalized_reasoning,
        context_texts=list(normalized_context_texts),
        sample_size=sample_size,
        abort_message="表情选择已被 Hook 中止。",
    )
    if before_select_result.aborted:
        abort_message = str(before_select_result.kwargs.get("abort_message") or "表情选择已被 Hook 中止。").strip()
        return MaisakaEmojiSendResult(
            success=False,
            message=abort_message or "表情选择已被 Hook 中止。",
            requested_emotion=normalized_requested_emotion,
        )

    before_select_kwargs = before_select_result.kwargs
    normalized_requested_emotion = str(
        before_select_kwargs.get("requested_emotion", normalized_requested_emotion) or ""
    ).strip()
    normalized_reasoning = str(before_select_kwargs.get("reasoning", normalized_reasoning) or "").strip()
    if isinstance(before_select_kwargs.get("context_texts"), list):
        normalized_context_texts = _normalize_context_texts(before_select_kwargs.get("context_texts"))
    sample_size = _coerce_positive_int(before_select_kwargs.get("sample_size"), sample_size)

    if emoji_selector is None:
        selected_emoji, matched_emotion = await select_emoji_for_maisaka(
            requested_emotion=normalized_requested_emotion,
            reasoning=normalized_reasoning,
            context_texts=normalized_context_texts,
            sample_size=sample_size,
        )
    else:
        selected_emoji, matched_emotion = await emoji_selector(
            normalized_requested_emotion,
            normalized_reasoning,
            normalized_context_texts,
            sample_size,
        )
    after_select_result = await _get_runtime_manager().invoke_hook(
        "emoji.maisaka.after_select",
        stream_id=stream_id,
        requested_emotion=normalized_requested_emotion,
        reasoning=normalized_reasoning,
        context_texts=list(normalized_context_texts),
        sample_size=sample_size,
        selected_emoji=_serialize_emoji_for_hook(selected_emoji),
        selected_emoji_hash=str(selected_emoji.file_hash or "").strip() if selected_emoji is not None else "",
        matched_emotion=matched_emotion,
        abort_message="表情发送已被 Hook 中止。",
    )
    if after_select_result.aborted:
        abort_message = str(after_select_result.kwargs.get("abort_message") or "表情发送已被 Hook 中止。").strip()
        return MaisakaEmojiSendResult(
            success=False,
            message=abort_message or "表情发送已被 Hook 中止。",
            requested_emotion=normalized_requested_emotion,
            matched_emotion=matched_emotion,
        )

    after_select_kwargs = after_select_result.kwargs
    normalized_requested_emotion = str(
        after_select_kwargs.get("requested_emotion", normalized_requested_emotion) or ""
    ).strip()
    matched_emotion = str(after_select_kwargs.get("matched_emotion", matched_emotion) or "").strip()
    override_emoji = _resolve_selected_emoji(after_select_kwargs.get("selected_emoji_hash"))
    if override_emoji is None:
        override_emoji = _resolve_selected_emoji(after_select_kwargs.get("selected_emoji"))
    if override_emoji is not None:
        selected_emoji = override_emoji

    if selected_emoji is None:
        return MaisakaEmojiSendResult(
            success=False,
            message="当前表情包库中没有可用表情。",
            requested_emotion=normalized_requested_emotion,
            matched_emotion=matched_emotion,
        )

    try:
        emoji_base64 = ImageUtils.image_path_to_base64(str(selected_emoji.full_path))
        if not emoji_base64:
            raise ValueError("表情图片转换为 base64 失败")
    except Exception as exc:
        return MaisakaEmojiSendResult(
            success=False,
            message=f"发送表情包失败：{exc}",
            description=selected_emoji.description.strip(),
            emotions=_normalize_emotions(selected_emoji),
            requested_emotion=normalized_requested_emotion,
            matched_emotion=matched_emotion,
        )

    try:
        target_session = chat_manager.get_session_by_session_id(stream_id)
        sent_message = None
        if target_session is not None and target_session.platform == CLI_PLATFORM_NAME:
            preview_message = (
                f"已发送表情包：{selected_emoji.description.strip()}"
                if selected_emoji.description.strip()
                else "[表情包]"
            )
            render_cli_message(preview_message)
            sent = True
        else:
            sent_message = await send_service.emoji_to_stream_with_message(
                emoji_base64=emoji_base64,
                stream_id=stream_id,
                storage_message=True,
                set_reply=False,
                reply_message=None,
            )
            sent = sent_message is not None
    except Exception as exc:
        return MaisakaEmojiSendResult(
            success=False,
            message=f"发送表情包时发生异常：{exc}",
            description=selected_emoji.description.strip(),
            emotions=_normalize_emotions(selected_emoji),
            requested_emotion=normalized_requested_emotion,
            matched_emotion=matched_emotion,
        )

    description = selected_emoji.description.strip()
    emotions = _normalize_emotions(selected_emoji)
    if not sent:
        return MaisakaEmojiSendResult(
            success=False,
            message="发送表情包失败。",
            description=description,
            emotions=emotions,
            requested_emotion=normalized_requested_emotion,
            matched_emotion=matched_emotion,
        )

    emoji_manager.update_emoji_usage(selected_emoji)
    success_message = (
        f"已发送表情包：{description}（情绪：{', '.join(emotions)}）"
        if emotions
        else f"已发送表情包：{description}"
    )
    return MaisakaEmojiSendResult(
        success=True,
        message=success_message,
        emoji_base64=emoji_base64,
        description=description,
        emotions=emotions,
        requested_emotion=normalized_requested_emotion,
        matched_emotion=matched_emotion,
        sent_message=sent_message,
    )
