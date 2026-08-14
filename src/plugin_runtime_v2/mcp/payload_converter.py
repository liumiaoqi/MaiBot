"""napcat Event payload → SessionMessage 转换器。

CQ-6 T2: 将 napcat-adapter 推送的 Event payload dict 转为核心统一的 SessionMessage。
"""


from datetime import datetime
from typing import Any

from src.common.data_models.mai_message_data_model import GroupInfo, MessageInfo, UserInfo
from src.common.data_models.message_component_data_model import MessageSequence
from src.common.data_models.session_message_data_model import SessionMessage
from src.common.logger import get_logger
from src.plugin_runtime.host.message_utils import PluginMessageUtils

logger = get_logger("plugin_runtime_v2.mcp.payload_converter")

_NAPCAT_MESSAGE_EVENTS = frozenset({"napcat.message", "napcat.group_message"})


class NapCatPayloadConverter:
    """napcat Event payload → SessionMessage 转换器。"""

    def convert(self, payload: dict[str, Any], event_name: str) -> SessionMessage:
        """将 napcat Event payload 转为 SessionMessage。"""
        if event_name == "napcat.notice":
            return self._convert_notice(payload)
        return self._convert_message(payload)

    def _convert_message(self, payload: dict[str, Any]) -> SessionMessage:
        """转换消息类 Event（napcat.message / napcat.group_message）。"""
        message_id = str(payload.get("message_id", ""))
        timestamp = datetime.fromtimestamp(payload.get("timestamp", 0))
        platform = "qq"

        user_info = UserInfo(
            user_id=str(payload.get("qq_user_id", "") or "unknown"),
            user_nickname=str(payload.get("sender_name", "") or "unknown"),
            user_cardname=payload.get("sender_card"),
        )

        group_info = self._build_group_info(payload)

        message_info = MessageInfo(
            user_info=user_info,
            group_info=group_info,
            additional_config={
                "at_user_ids": payload.get("at_user_ids", []),
                "reply_message_id": payload.get("reply_message_id"),
                "platform_card_payloads": payload.get("platform_card_payloads", []),
            },
        )

        raw_message = self._build_raw_message(payload)
        is_mentioned = self._detect_mention(raw_message)
        session_id = str(payload.get("session_id", ""))

        msg = SessionMessage(
            message_id=message_id,
            timestamp=timestamp,
            platform=platform,
        )
        msg.message_info = message_info
        msg.raw_message = raw_message
        msg.is_mentioned = is_mentioned
        msg.session_id = session_id
        msg.is_notify = False
        return msg

    def _convert_notice(self, payload: dict[str, Any]) -> SessionMessage:
        """转换通知类 Event（napcat.notice）。"""
        notice_type = payload.get("napcat_notice_type", "unknown")
        qq_user_id = payload.get("qq_user_id", "")
        message_id = f"notice_{notice_type}_{qq_user_id}"

        timestamp = datetime.fromtimestamp(payload.get("timestamp", 0))
        platform = "qq"

        user_info = UserInfo(
            user_id=str(qq_user_id or "unknown"),
            user_nickname=str(payload.get("sender_name", "") or "unknown"),
            user_cardname=None,
        )

        group_info = self._build_group_info(payload)

        message_info = MessageInfo(
            user_info=user_info,
            group_info=group_info,
            additional_config={},
        )

        session_id = str(payload.get("session_id", ""))

        msg = SessionMessage(
            message_id=message_id,
            timestamp=timestamp,
            platform=platform,
        )
        msg.message_info = message_info
        msg.raw_message = MessageSequence(components=[])
        msg.session_id = session_id
        msg.is_notify = True
        return msg

    @staticmethod
    def _build_group_info(payload: dict[str, Any]) -> GroupInfo | None:
        """从 payload 构造 GroupInfo（群聊时）。

        notice 事件不含 group_name 字段（NapCat OneBot 11 限制），
        用 group_id 作为降级值避免 Hook 拒绝。
        """
        group_id = payload.get("qq_group_id")
        if group_id:
            group_name = str(payload.get("group_name") or "")
            if not group_name:
                group_name = str(group_id)
            return GroupInfo(
                group_id=str(group_id),
                group_name=group_name,
            )
        return None

    @staticmethod
    def _build_raw_message(payload: dict[str, Any]) -> MessageSequence:
        """从 payload segments 构造 MessageSequence。"""
        segments = payload.get("segments")
        if isinstance(segments, list) and segments:
            return PluginMessageUtils._message_sequence_from_dict(segments)
        return MessageSequence(components=[])

    @staticmethod
    def _detect_mention(raw_message: MessageSequence) -> bool:
        """检测消息中是否包含 at 段。"""
        from src.common.data_models.message_component_data_model import AtComponent

        return any(isinstance(c, AtComponent) for c in raw_message.components)
