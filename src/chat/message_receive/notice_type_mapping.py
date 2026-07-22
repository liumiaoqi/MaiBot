"""NapCat 通知类型 → NoticeKind 映射常量。

SSD-4 T3.1：从 src/core/adapters/notice_classifier.py 迁移至 bot.py 所在目录。
入站点在构造 CoreMessage 时使用此映射，核心层不再感知 napcat_* 字段。
"""

from src.core.types import NoticeKind

# napcat_notice_sub_type → NoticeKind
NAPCAT_NOTICE_KIND_MAP: dict[str, NoticeKind] = {
    "input_status": NoticeKind.INPUT_STATUS,
    "group_ban": NoticeKind.AMBIENT,
    "group_increase": NoticeKind.AMBIENT,
    "group_decrease": NoticeKind.AMBIENT,
    "group_name": NoticeKind.AMBIENT,
    "group_upload": NoticeKind.AMBIENT,
    "group_msg_emoji_like": NoticeKind.AMBIENT,
    "poke": NoticeKind.INTERACTION,
    "group_poke": NoticeKind.INTERACTION,
    "friend_add": NoticeKind.INTERACTION,
    "group_admin": NoticeKind.INTERACTION,
}


def map_napcat_notice(sub_type: str) -> NoticeKind:
    return NAPCAT_NOTICE_KIND_MAP.get(sub_type, NoticeKind.UNKNOWN)
