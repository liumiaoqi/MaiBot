from copy import deepcopy
from typing import Any, Dict, Optional, Tuple

import base64
import hashlib
import re

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
from src.common.data_models.session_message_data_model import SessionMessage
from src.common.logger import get_logger
from src.common.data_models.chat_target_info_data_model import ChatTargetInfo

from src.core.bot_config_port_registry import get_bot_config_port
from src.core.identity import get_bot_account, is_bot_self
from src.core.chat_config_port_registry import get_chat_config_port
from src.core.session_port_registry import get_session_info
from src.core.person_info_port_registry import get_person_info_port

logger = get_logger("core.message_utils")

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


# ── is_mentioned_bot_in_message / get_chat_type_and_target_info（从 src/chat/utils/utils.py 物理迁移）──
# 迁移时间：SSD-4 T2.3
# 原位置：src/chat/utils/utils.py

def _has_at_component_targeting_bot(message: SessionMessage, platform: str) -> bool:
    """检查消息中的结构化 @ 组件是否直接指向当前 bot。"""

    raw_message = message.raw_message
    for component in raw_message.components:
        if isinstance(component, AtComponent) and is_bot_self(platform, component.target_user_id):
            return True
    return False


def is_mentioned_bot_in_message(message: SessionMessage) -> tuple[bool, bool, float]:
    """检查消息是否提到了机器人（统一多平台实现）"""
    text = message.processed_plain_text or ""
    platform = str(message.platform or "").strip().lower()

    # 获取当前平台对应的账号
    current_account = get_bot_account(platform)

    nickname = get_bot_config_port().get_bot_nickname()
    alias_names = get_bot_config_port().get_bot_alias_names()
    keywords = [nickname] + alias_names

    reply_probability = 0.0
    is_at = False
    is_mentioned = False

    # 1) 直接的 additional_config 标记
    add_cfg = message.message_info.additional_config
    if isinstance(add_cfg, dict):
        if add_cfg.get("at_bot") or add_cfg.get("is_mentioned"):
            is_mentioned = True
            if add_cfg.get("at_bot"):
                is_at = True
            # 当提供数值型 is_mentioned 时，当作概率提升；布尔提及标记只负责标记命中。
            raw_mention_boost = add_cfg.get("is_mentioned")
            if raw_mention_boost not in (None, "") and not isinstance(raw_mention_boost, bool):
                reply_probability = float(raw_mention_boost)

    # 2) 已经在上游设置过的 message.is_at / message.is_mentioned
    if message.is_at:
        is_at = True
        is_mentioned = True
    if message.is_mentioned:
        is_mentioned = True

    # 3) 扫描分段：是否包含 mention_bot（适配器插入）
    def _has_mention_bot(seg) -> bool:
        try:
            if seg is None:
                return False
            if seg.type == "mention_bot":
                return True
            if seg.type == "seglist":
                for s in seg.data:
                    if _has_mention_bot(s):
                        return True
            return False
        except Exception as exc:
            from src.core.tainted_mask.mark import mark_exception_swallowed
            mark_exception_swallowed()
            logger.debug("核心消息@检测异常: %s", exc)
            return False

    if _has_mention_bot(getattr(message, "message_segment", None)):
        is_at = True
        is_mentioned = True

    # 4) 结构化 @ 组件检测。处理后的文本可能只剩群名片，不能依赖文本里的显示名判断。
    if not is_at and _has_at_component_targeting_bot(message, platform):
        is_at = True
        is_mentioned = True

    # 5) 统一的 @ 检测逻辑
    if current_account and not is_at and not is_mentioned:
        if platform == "qq":
            # QQ 格式: @<name:qq_id>
            if re.search(rf"@<(.+?):{re.escape(current_account)}>", text):
                is_at = True
                is_mentioned = True
        else:
            # 其他平台格式: @username 或 @account
            if re.search(rf"@{re.escape(current_account)}(\b|$)", text, flags=re.IGNORECASE):
                is_at = True
                is_mentioned = True

    # 6) 统一的回复检测逻辑
    if not is_mentioned:
        # 通用回复格式：包含 "(你)" 或 "（你）"
        if re.search(r"\[回复 .*?\(你\)：", text) or re.search(r"\[回复 .*?（你）：", text):
            is_mentioned = True
        # ID 形式的回复检测
        elif current_account:
            if re.search(rf"\[回复 (.+?)\({re.escape(current_account)}\)：(.+?)\]，说：", text):
                is_mentioned = True
            elif re.search(
                rf"\[回复<(.+?)(?=:{re.escape(current_account)}>)\:{re.escape(current_account)}>：(.+?)\]，说：", text
            ):
                is_mentioned = True

    # 7) 名称/别名 提及（去除 @/回复标记后再匹配）
    if not is_mentioned and keywords:
        msg_content = text
        # 去除各种 @ 与 回复标记，避免误判
        msg_content = re.sub(r"@(.+?)（(\d+)）", "", msg_content)
        msg_content = re.sub(r"@<(.+?)(?=:(\d+))\:(\d+)>", "", msg_content)
        msg_content = re.sub(r"\[回复 (.+?)\(((\d+)|未知id|你)\)：(.+?)\]，说：", "", msg_content)
        msg_content = re.sub(r"\[回复<(.+?)(?=:(\d+))\:(\d+)>：(.+?)\]，说：", "", msg_content)
        for kw in keywords:
            if kw and kw in msg_content:
                is_mentioned = True
                break

    # 8) 概率设置
    reply_timing_config = get_chat_config_port().get_reply_timing_config()
    if is_at and reply_timing_config.inevitable_at_reply:
        reply_probability = 1.0
        logger.debug("被@，回复概率设置为100%")
    elif is_mentioned and reply_timing_config.mentioned_bot_reply:
        reply_probability = max(reply_probability, 1.0)
        logger.debug("被提及，回复概率设置为100%")

    return is_mentioned, is_at, reply_probability


def get_chat_type_and_target_info(chat_id: str) -> Tuple[bool, Optional["ChatTargetInfo"]]:
    """
    获取聊天类型（是否群聊）和私聊对象信息。

    Args:
        chat_id: 聊天流ID

    Returns:
        Tuple[bool, Optional[Dict]]:
            - bool: 是否为群聊 (True 是群聊, False 是私聊或未知)
            - Optional[Dict]: 如果是私聊，包含对方信息的字典；否则为 None。
            字典包含: platform, user_id, user_nickname, person_id, person_name
    """
    is_group_chat = False  # Default to private/unknown
    chat_target_info = None

    try:
        if chat_stream := get_session_info(chat_id):
            if chat_stream.is_group_session:
                is_group_chat = True
                chat_target_info = None  # Explicitly None for group chat
            elif chat_stream.user_id:  # It's a private chat
                is_group_chat = False
                platform: str = chat_stream.platform
                user_id: str = chat_stream.user_id

                # Try to get nickname from SessionInfo
                user_nickname = chat_stream.user_nickname or None

                from src.common.data_models.chat_target_info_data_model import ChatTargetInfo  # 解决循环导入问题

                # Initialize target_info with basic info
                target_info = ChatTargetInfo(
                    platform=platform,
                    user_id=user_id,
                    session_nickname=user_nickname or "",
                    person_id=None,
                    person_name=None,
                )

                # Try to fetch person info
                try:
                    port = get_person_info_port()
                    person_info = port.get_person_info(platform, user_id) if port is not None else None
                    if person_info is not None:
                        if not person_info.is_known:
                            logger.warning(f"用户 {user_nickname} 尚未认识")
                            return False, None
                        target_info.is_known = True
                        if person_info.person_id:
                            target_info.person_id = person_info.person_id
                            target_info.person_name = person_info.person_name or ""
                except Exception as person_e:
                    from src.core.tainted_mask.mark import mark_exception_swallowed
                    mark_exception_swallowed()
                    logger.warning(
                        f"获取 person_id 或 person_name 时出错 for {platform}:{user_id} in utils: {person_e}"
                    )

                chat_target_info = target_info
        else:
            logger.warning(f"无法获取 chat_stream for {chat_id} in utils")
    except Exception as e:
        from src.core.tainted_mask.mark import mark_exception_swallowed
        mark_exception_swallowed()
        logger.error(f"获取聊天类型和目标信息时出错 for {chat_id}: {e}", exc_info=True)

    return is_group_chat, chat_target_info


