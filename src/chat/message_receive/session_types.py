from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from src.common.data_models.chat_session_data_model import MaiChatSession

if TYPE_CHECKING:
    from .message import SessionMessage


class SessionContext:
    """会话上下文"""

    def __init__(self, message: "SessionMessage"):
        self.message = message
        self.template_name: Optional[str] = None

    def update_template(self, template_name: str):
        """更新当前使用的回复模板"""
        self.template_name = template_name


class BotChatSession(MaiChatSession):
    def __init__(
        self,
        session_id: str,
        platform: str,
        user_id: Optional[str] = None,
        user_nickname: Optional[str] = None,
        user_cardname: Optional[str] = None,
        group_id: Optional[str] = None,
        group_name: Optional[str] = None,
        account_id: Optional[str] = None,
        scope: Optional[str] = None,
        agent_id: Optional[str] = None,
        created_timestamp: Optional[datetime] = None,
        last_active_timestamp: Optional[datetime] = None,
    ):
        self.context: Optional[SessionContext] = None
        self.accept_format: List[str] = []

        super().__init__(
            session_id=session_id,
            platform=platform,
            user_id=user_id,
            user_nickname=user_nickname,
            user_cardname=user_cardname,
            group_id=group_id,
            group_name=group_name,
            account_id=account_id,
            scope=scope,
            agent_id=agent_id,
            created_timestamp=created_timestamp,
            last_active_timestamp=last_active_timestamp,
        )

    def check_types(self, types: List[str]) -> bool:
        """检查消息是否符合可接受类型列表"""
        return all(t in self.accept_format for t in types)

    def update_active_time(self):
        """更新最后活跃时间"""
        self.last_active_timestamp = datetime.now()

    def set_context(self, message: "SessionMessage"):
        """设置会话上下文"""
        self.context = SessionContext(message=message)