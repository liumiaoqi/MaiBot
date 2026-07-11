from copy import deepcopy
from typing import Any, Dict

import base64
import hashlib

from src.common.data_models.message_component_data_model import (
    AtComponent,
    DictComponent,
    EmojiComponent,
    FileComponent,
    ImageComponent,
    MessageSequence,
    ReplyComponent,
    StandardMessageComponents,
    TextComponent,
    VoiceComponent,
)


def build_binary_component_from_base64(component_type: str, raw_data: str) -> StandardMessageComponents:
    """根据 Base64 数据构造二进制消息组件。

    Args:
        component_type: 组件类型名称。
        raw_data: Base64 编码后的二进制数据。

    Returns:
        StandardMessageComponents: 转换后的内部消息组件。

    Raises:
        ValueError: 当组件类型不受支持时抛出。
    """
    binary_data = base64.b64decode(raw_data)
    binary_hash = hashlib.sha256(binary_data).hexdigest()

    if component_type == "image":
        return ImageComponent(binary_hash=binary_hash, binary_data=binary_data)
    if component_type == "emoji":
        return EmojiComponent(binary_hash=binary_hash, binary_data=binary_data)
    if component_type == "voice":
        return VoiceComponent(binary_hash=binary_hash, binary_data=binary_data)
    raise ValueError(f"不支持的二进制组件类型: {component_type}")


def build_message_sequence_from_custom_message(
    message_type: str,
    content: str | Dict[str, Any],
) -> MessageSequence:
    """根据自定义消息类型构造内部消息组件序列。

    Args:
        message_type: 自定义消息类型。
        content: 自定义消息内容。

    Returns:
        MessageSequence: 转换后的消息组件序列。
    """
    normalized_type = message_type.strip().lower()

    if normalized_type == "text":
        return MessageSequence(components=[TextComponent(text=str(content))])

    if normalized_type in {"image", "emoji", "voice"}:
        return MessageSequence(components=[build_binary_component_from_base64(normalized_type, str(content))])

    if normalized_type == "at":
        return MessageSequence(components=[AtComponent(target_user_id=str(content))])

    if normalized_type == "reply":
        return MessageSequence(components=[ReplyComponent(target_message_id=str(content))])

    if normalized_type == "file" and isinstance(content, dict):
        return MessageSequence(components=[FileComponent.from_payload(deepcopy(content))])

    if normalized_type == "dict" and isinstance(content, dict):
        return MessageSequence(components=[DictComponent(data=deepcopy(content))])

    return MessageSequence(
        components=[
            DictComponent(
                data={
                    "type": normalized_type,
                    "data": deepcopy(content),
                }
            )
        ]
    )