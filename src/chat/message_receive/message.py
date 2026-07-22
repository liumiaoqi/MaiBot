import asyncio
from asyncio import Task
from typing import Dict, List, Sequence, Tuple

from rich.traceback import install
from sqlmodel import select

from src.common.logger import get_logger
from src.common.database.database import get_db_session
from src.common.database.database_model import Messages
from src.common.data_models.mai_message_data_model import MaiMessage, UserInfo
from src.common.data_models.message_component_data_model import (
    AtComponent,
    DictComponent,
    EmojiComponent,
    FileComponent,
    ForwardNodeComponent,
    ImageComponent,
    ReplyComponent,
    StandardMessageComponents,
    TextComponent,
    VoiceComponent,
)


install(extra_lines=3)

logger = get_logger("chat_message")


class MsgIDMapping:
    """回复消息内容缓存。"""

    def __init__(self) -> None:
        """初始化消息 ID 到内容的映射缓存。"""
        self.mapping: Dict[str, Tuple[str | Task[str], UserInfo]] = {}



# ── SSD-4 re-export（实际定义已迁移到 src/common/data_models/session_message_data_model.py）──
from src.common.data_models.session_message_data_model import SessionMessage as SessionMessage  # noqa: F401
