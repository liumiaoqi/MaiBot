from typing import TYPE_CHECKING, Dict, Optional

from src.common.logger import get_logger
from src.common.utils.utils_session import SessionUtils
from src.platform_io.route_key_factory import RouteKeyFactory

if TYPE_CHECKING:
    from .chat_manager import BotChatSession
    from .message import SessionMessage
    from .session_store import SessionStore

logger = get_logger("message_registry")


class MessageRegistry:
    """消息注册 — 管理入站消息注册、缓存和会话身份更新。"""

    def __init__(self, session_store: "SessionStore") -> None:
        self._store = session_store
        self.last_messages: Dict[str, "SessionMessage"] = {}

    def register(self, message: "SessionMessage") -> None:
        """注册消息 + 更新会话身份 + 持久化变更。"""
        platform = message.platform
        if not platform:
            raise ValueError("消息缺少平台信息")
        user_id = message.message_info.user_info.user_id
        group_id = message.message_info.group_info.group_id if message.message_info.group_info else None
        account_id = None
        scope = None
        additional_config = message.message_info.additional_config
        if isinstance(additional_config, dict):
            account_id, scope = RouteKeyFactory.extract_components(additional_config)
        session_id = SessionUtils.calculate_session_id(
            platform,
            user_id=user_id,
            group_id=group_id,
            account_id=account_id,
            scope=scope,
        )
        message.session_id = session_id
        self.last_messages[session_id] = message
        session = self._store.sessions.get(session_id)
        if session is not None and self.update_session_identity(session, message):
            self._store.save(session)

    def get_last(self, session_id: str) -> Optional["SessionMessage"]:
        """获取指定会话的最后一条消息。"""
        return self.last_messages.get(session_id)

    @staticmethod
    def _normalize_identity_text(value: Optional[str]) -> Optional[str]:
        normalized_value = str(value or "").strip()
        return normalized_value or None

    def update_session_identity(self, session: "BotChatSession", message: "SessionMessage") -> bool:
        """用真实入站消息补齐聊天流展示身份，群聊不保存最近发言人的用户信息。"""
        changed = False
        group_info = message.message_info.group_info
        user_info = message.message_info.user_info
        if group_info is not None:
            group_name = self._normalize_identity_text(group_info.group_name)
            if group_name and session.group_name != group_name:
                session.group_name = group_name
                changed = True
            if session.user_id is not None:
                session.user_id = None
                changed = True
            if session.user_nickname is not None:
                session.user_nickname = None
                changed = True
            if session.user_cardname is not None:
                session.user_cardname = None
                changed = True
            return changed

        user_nickname = self._normalize_identity_text(user_info.user_nickname)
        user_cardname = self._normalize_identity_text(user_info.user_cardname)
        if user_nickname and session.user_nickname != user_nickname:
            session.user_nickname = user_nickname
            changed = True
        if user_cardname != session.user_cardname:
            session.user_cardname = user_cardname
            changed = True
        return changed