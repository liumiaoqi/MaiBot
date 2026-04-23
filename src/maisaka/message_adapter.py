"""Maisaka 文本与消息片段适配工具。"""

from copy import deepcopy
from datetime import datetime
from typing import Optional

import re

from src.common.data_models.message_component_data_model import (
    AtComponent,
    EmojiComponent,
    ImageComponent,
    MessageSequence,
    ReplyComponent,
    TextComponent,
)

SPEAKER_PREFIX_PATTERN = re.compile(
    r"^(?:(?P<timestamp>\d{2}:\d{2}:\d{2}))?(?:\[msg_id:(?P<message_id>[^\]]+)\])?\[(?P<speaker>[^\]]+)\](?P<content>.*)$",
    re.DOTALL,
)


def format_speaker_content(
    speaker_name: str,
    content: str,
    timestamp: Optional[datetime] = None,
    message_id: Optional[str] = None,
) -> str:
    """将可见文本格式化为带说话人前缀的样式。"""

    time_prefix = timestamp.strftime("%H:%M:%S") if timestamp is not None else ""
    message_id_prefix = f"[msg_id:{message_id}]" if message_id else ""
    return f"{time_prefix}{message_id_prefix}[{speaker_name}]{content}"


def parse_speaker_content(content: str) -> tuple[Optional[str], str]:
    """解析形如 `[speaker]message` 的可见文本。"""

    match = SPEAKER_PREFIX_PATTERN.match(content or "")
    if not match:
        return None, content or ""
    return match.group("speaker"), match.group("content")


def clone_message_sequence(message_sequence: MessageSequence) -> MessageSequence:
    """复制消息片段序列。"""

    return MessageSequence([deepcopy(component) for component in message_sequence.components])


def _render_at_component_text(component: AtComponent) -> str:
    """将 AtComponent 渲染为文本。"""

    target_name = component.target_user_cardname or component.target_user_nickname or component.target_user_id
    return f"@{target_name}".strip()


def build_visible_text_from_sequence(message_sequence: MessageSequence) -> str:
    """从消息片段序列提取可见文本。"""

    parts: list[str] = []
    for component in message_sequence.components:
        if isinstance(component, TextComponent):
            match = SPEAKER_PREFIX_PATTERN.match(component.text or "")
            if not match:
                parts.append(component.text)
                continue

            normalized_parts: list[str] = []
            if match.group("timestamp"):
                normalized_parts.append(match.group("timestamp"))
            message_id = match.group("message_id")
            if message_id:
                normalized_parts.append(f"[msg_id:{message_id}]")
            normalized_parts.append(f"[{match.group('speaker')}]")
            normalized_parts.append(match.group("content"))
            parts.append("".join(normalized_parts))
            continue

        if isinstance(component, EmojiComponent):
            parts.append(component.content.strip() or "[表情包]")
            continue

        if isinstance(component, ImageComponent):
            parts.append(component.content.strip() or "[图片]")
            continue

        if isinstance(component, AtComponent):
            parts.append(_render_at_component_text(component))
            continue

        if isinstance(component, ReplyComponent):
            target_message_id = component.target_message_id.strip()
            if target_message_id:
                parts.append(f"[引用]quote_id={target_message_id}")

    return "".join(parts)
