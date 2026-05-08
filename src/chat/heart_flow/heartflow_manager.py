import asyncio
import traceback

from typing import Dict

from src.chat.message_receive.chat_manager import chat_manager
from src.common.logger import get_logger
from src.maisaka.runtime import MaisakaHeartFlowChatting

logger = get_logger("heartflow")


class HeartflowManager:
    """管理 session 级别的 Maisaka 心流实例。"""

    def __init__(self) -> None:
        self.heartflow_chat_list: Dict[str, MaisakaHeartFlowChatting] = {}
        self._chat_create_locks: Dict[str, asyncio.Lock] = {}

    async def get_or_create_heartflow_chat(self, session_id: str) -> MaisakaHeartFlowChatting:
        """获取或创建指定会话对应的 Maisaka runtime。"""
        try:
            if chat := self.heartflow_chat_list.get(session_id):
                return chat

            create_lock = self._chat_create_locks.setdefault(session_id, asyncio.Lock())
            async with create_lock:
                if chat := self.heartflow_chat_list.get(session_id):
                    return chat

                chat_session = chat_manager.get_session_by_session_id(session_id)
                if not chat_session:
                    raise ValueError(f"未找到 session_id={session_id} 对应的聊天流")

                new_chat = MaisakaHeartFlowChatting(session_id=session_id)
                await new_chat.start()
                self.heartflow_chat_list[session_id] = new_chat
                return new_chat
        except Exception as exc:
            logger.error(f"创建心流聊天 {session_id} 失败: {exc}", exc_info=True)
            traceback.print_exc()
            raise

    def adjust_talk_frequency(self, session_id: str, frequency: float) -> None:
        """调整指定聊天流的说话频率。"""
        chat = self.heartflow_chat_list.get(session_id)
        if chat:
            chat.adjust_talk_frequency(frequency)
            logger.info(f"已调整聊天 {session_id} 的说话频率为 {frequency}")
        else:
            logger.warning(f"无法调整频率，未找到 session_id={session_id} 的聊天流")


heartflow_manager = HeartflowManager()
