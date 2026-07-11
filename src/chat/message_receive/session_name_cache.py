from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .session_store import SessionStore


class SessionNameCache:
    """会话名称查询 — 从 SessionStore 实时推断名称。"""

    def __init__(self, store: "SessionStore") -> None:
        self._store = store

    def get(self, session_id: str) -> Optional[str]:
        """推断会话显示名称（群名/用户昵称+私聊）。"""
        session = self._store.sessions.get(session_id)
        if not session:
            return None
        if session.is_group_session:
            if session.group_name:
                return session.group_name
            if session.context and session.context.message and session.context.message.message_info.group_info:
                return session.context.message.message_info.group_info.group_name
        elif session.user_nickname:
            return f"{session.user_nickname}的私聊"
        elif session.context and session.context.message and session.context.message.message_info.user_info:
            nickname = session.context.message.message_info.user_info.user_nickname
            return f"{nickname}的私聊"
        return None