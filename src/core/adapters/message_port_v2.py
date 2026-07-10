"""MessagePortV2 工具函数。

阶段3 后 BridgedMessagePortV2 已迁移到 send_service.py（SendServiceMessagePortV2），
本模块仅保留 segments_to_message_sequence 工具函数，供 plugin_runtime 等调用方使用。
"""

from __future__ import annotations

from typing import Any

from src.common.data_models.message_component_data_model import MessageSequence


def segments_to_message_sequence(segments: list[dict[str, Any]]) -> MessageSequence:
    """将 segments 列表转换为 MessageSequence。

    遍历 segments，按 type 字段构建对应 Component。
    供 plugin_runtime 等需要从 dict 格式转换的调用方使用。
    """
    import base64

    from src.common.data_models.message_component_data_model import (
        EmojiComponent,
        ImageComponent,
        TextComponent,
    )

    components = []
    for seg in segments:
        seg_type = seg.get("type", "text")
        if seg_type == "text":
            components.append(TextComponent(text=seg.get("data", "")))
        elif seg_type == "image":
            b64 = seg.get("binary_data_base64", "")
            binary_data = base64.b64decode(b64) if b64 else b""
            hash_str = seg.get("hash", "")
            components.append(ImageComponent(binary_hash=hash_str, binary_data=binary_data))
        elif seg_type == "emoji":
            b64 = seg.get("binary_data_base64", "")
            binary_data = base64.b64decode(b64) if b64 else b""
            hash_str = seg.get("hash", "")
            components.append(EmojiComponent(binary_hash=hash_str, binary_data=binary_data))
        else:
            from src.services.send_service import _build_message_sequence_from_custom_message

            ms = _build_message_sequence_from_custom_message(seg_type, seg.get("data", seg.get("content", "")))
            components.extend(ms.components)
    return MessageSequence(components=components)
