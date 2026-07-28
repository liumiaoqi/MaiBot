"""NapCatNoticeClassifier — NoticeClassifier 的 NapCat 适配器。"""


from typing import Any

from src.common.logger import get_logger
from src.core.protocols import NoticeClassifier  # noqa: F401
from src.core.types import NoticeKind

logger = get_logger("core.adapters.notice_classifier")


class NapCatNoticeClassifier:
    """通过 napcat_notice_sub_type 字段实现 NoticeClassifier Protocol。

    将 NapCat 平台特定的通知子类型映射为平台无关的 NoticeKind 枚举。
    这是全项目中唯一定义 napcat_notice_sub_type 映射的地方。
    """

    def classify(self, message: Any) -> NoticeKind:
        # SSD-4 T3.3：优先使用 bot.py 入站点预填充的 notice_kind
        notice_kind = self._extract_notice_kind(message)
        if notice_kind:
            try:
                return NoticeKind(notice_kind)
            except ValueError:
                pass
        return NoticeKind.UNKNOWN

    @staticmethod
    def _extract_notice_kind(message: Any) -> str:
        if hasattr(message, "message_info") and hasattr(message.message_info, "additional_config"):
            kind = message.message_info.additional_config.get("notice_kind")
            if kind:
                return str(kind)
        if hasattr(message, "additional_config"):
            kind = message.additional_config.get("notice_kind")
            if kind:
                return str(kind)
        if isinstance(message, dict):
            additional_config = message.get("additional_config", {})
            if isinstance(additional_config, dict):
                return str(additional_config.get("notice_kind", ""))
        return ""
