import asyncio
import time
import traceback

from typing import Dict

from src.chat.message_receive.chat_manager import chat_manager
from src.common.logger import get_logger
from src.maisaka.runtime import MaisakaHeartFlowChatting

logger = get_logger("heartflow")

HEARTFLOW_RUNTIME_IDLE_TTL_SECONDS = 6 * 60 * 60
HEARTFLOW_RUNTIME_MAX_SESSIONS = 512
HEARTFLOW_RUNTIME_CLEANUP_INTERVAL_SECONDS = 5 * 60


class HeartflowManager:
    """管理 session 级别的 Maisaka 心流实例。"""

    def __init__(self) -> None:
        self.heartflow_chat_list: Dict[str, MaisakaHeartFlowChatting] = {}
        self._chat_create_locks: Dict[str, asyncio.Lock] = {}
        self._last_access_at: Dict[str, float] = {}
        self._last_cleanup_at = 0.0

    async def _stop_runtime(self, session_id: str, chat: MaisakaHeartFlowChatting) -> None:
        try:
            await chat.stop()
        except Exception as exc:
            logger.warning(f"清理心流聊天 {session_id} 时停止 runtime 失败: {exc}", exc_info=True)

    def _prune_runtime_caches(self, chat: MaisakaHeartFlowChatting) -> None:
        prune_runtime_caches = getattr(chat, "prune_runtime_caches", None)
        if callable(prune_runtime_caches):
            prune_runtime_caches()

    async def cleanup_idle_chats(self, *, now: float | None = None, exclude_session_ids: set[str] | None = None) -> None:
        """清理长期空闲或超过容量的 Maisaka runtime。"""
        current_time = time.time() if now is None else now
        excluded_session_ids = exclude_session_ids or set()
        expire_before = current_time - HEARTFLOW_RUNTIME_IDLE_TTL_SECONDS
        session_ids_to_remove = [
            session_id
            for session_id, accessed_at in self._last_access_at.items()
            if accessed_at < expire_before and session_id not in excluded_session_ids
        ]

        active_count_after_idle = len(self.heartflow_chat_list) - len(set(session_ids_to_remove))
        if active_count_after_idle > HEARTFLOW_RUNTIME_MAX_SESSIONS:
            overflow_count = active_count_after_idle - HEARTFLOW_RUNTIME_MAX_SESSIONS
            active_session_ids = [
                session_id
                for session_id in self.heartflow_chat_list
                if session_id not in session_ids_to_remove
                and session_id not in excluded_session_ids
            ]
            active_session_ids.sort(key=lambda session_id: self._last_access_at.get(session_id, 0.0))
            session_ids_to_remove.extend(active_session_ids[:overflow_count])

        self._last_cleanup_at = current_time
        removed_count = 0
        for session_id in dict.fromkeys(session_ids_to_remove):
            chat = self.heartflow_chat_list.pop(session_id, None)
            self._chat_create_locks.pop(session_id, None)
            self._last_access_at.pop(session_id, None)
            if chat is None:
                continue
            await self._stop_runtime(session_id, chat)
            removed_count += 1
        if removed_count > 0:
            logger.info(f"已清理空闲心流聊天: 数量={removed_count} 剩余={len(self.heartflow_chat_list)}")

    async def _cleanup_idle_chats_if_due(self, *, now: float, exclude_session_id: str) -> None:
        cleanup_due = now - self._last_cleanup_at >= HEARTFLOW_RUNTIME_CLEANUP_INTERVAL_SECONDS
        capacity_exceeded = len(self.heartflow_chat_list) >= HEARTFLOW_RUNTIME_MAX_SESSIONS
        if not cleanup_due and not capacity_exceeded:
            return
        await self.cleanup_idle_chats(now=now, exclude_session_ids={exclude_session_id})

    async def get_or_create_heartflow_chat(self, session_id: str) -> MaisakaHeartFlowChatting:
        """获取或创建指定会话对应的 Maisaka runtime。"""
        try:
            current_time = time.time()
            if chat := self.heartflow_chat_list.get(session_id):
                self._last_access_at[session_id] = current_time
                self._prune_runtime_caches(chat)
                await self._cleanup_idle_chats_if_due(now=current_time, exclude_session_id=session_id)
                return chat

            create_lock = self._chat_create_locks.setdefault(session_id, asyncio.Lock())
            async with create_lock:
                current_time = time.time()
                if chat := self.heartflow_chat_list.get(session_id):
                    self._last_access_at[session_id] = current_time
                    self._prune_runtime_caches(chat)
                    await self._cleanup_idle_chats_if_due(now=current_time, exclude_session_id=session_id)
                    return chat

                chat_session = chat_manager.get_session_by_session_id(session_id)
                if not chat_session:
                    raise ValueError(f"未找到 session_id={session_id} 对应的聊天流")

                await self._cleanup_idle_chats_if_due(now=current_time, exclude_session_id=session_id)
                new_chat = MaisakaHeartFlowChatting(session_id=session_id)
                await new_chat.start()
                self.heartflow_chat_list[session_id] = new_chat
                self._last_access_at[session_id] = current_time
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
