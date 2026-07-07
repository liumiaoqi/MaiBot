"""NapCatNoticeClassifier — NoticeClassifier 的 NapCat 适配器。"""

from __future__ import annotations

from typing import Any

from src.common.logger import get_logger
from src.core.protocols import NoticeClassifier
from src.core.types import NoticeKind

logger = get_logger("core.adapters.notice_classifier")

_NAPCAT_AMBIENT_SUBTYPES: frozenset[str] = frozenset({
    "input_status",
    "group_ban",
    "group_increase",
    "group_decrease",
    "group_name",
    "group_upload",
    "group_msg_emoji_like",
})

_NAPCAT_INTERACTION_SUBTYPES: frozenset[str] = frozenset({
    "poke",
    "group_poke",
    "friend_add",
    "group_admin",
})

_NAPCAT_INPUT_STATUS_SUBTYPES: frozenset[str] = frozenset({
    "input_status",
})


class NapCatNoticeClassifier:
    """通过 napcat_notice_sub_type 字段实现 NoticeClassifier Protocol。

    将 NapCat 平台特定的通知子类型映射为平台无关的 NoticeKind 枚举。
    这是全项目中唯一定义 napcat_notice_sub_type 映射的地方。
    """

    def classify(self, message: Any) -> NoticeKind:
        sub_type = self._extract_napcat_sub_type(message)
        if not sub_type:
            return NoticeKind.UNKNOWN

        if sub_type in _NAPCAT_INPUT_STATUS_SUBTYPES:
            return NoticeKind.INPUT_STATUS

        if sub_type in _NAPCAT_AMBIENT_SUBTYPES:
            return NoticeKind.AMBIENT

        if sub_type in _NAPCAT_INTERACTION_SUBTYPES:
            return NoticeKind.INTERACTION

        return NoticeKind.UNKNOWN

    @staticmethod
    def _extract_napcat_sub_type(message: Any) -> str:
        if hasattr(message, "message_info") and hasattr(message.message_info, "additional_config"):
            return message.message_info.additional_config.get("napcat_notice_sub_type", "")
        if hasattr(message, "additional_config"):
            return message.additional_config.get("napcat_notice_sub_type", "")
        if isinstance(message, dict):
            additional_config = message.get("additional_config", {})
            if isinstance(additional_config, dict):
                return additional_config.get("napcat_notice_sub_type", "")
        return ""