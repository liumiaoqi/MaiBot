"""MessagePortV2 桥接适配器 — 新接口内部调用旧 send_service。

阶段1 实现：零风险引入新 Protocol，内部桥接到 custom_reply_set_to_stream。
核心转变：
1. MessageSequence 直接传递，不做 dict 序列化/反序列化
2. reply_to_id → (set_reply, reply_message) 转换
3. 找不到被引用消息时 set_reply=False（降级为不引用，不丢弃消息）
"""

from __future__ import annotations

from typing import Any, Optional

from src.common.data_models.message_component_data_model import MessageSequence
from src.common.logger import get_logger
from src.core.types import SendMessageResult

logger = get_logger("core.adapters.message_port_v2")


class BridgedMessagePortV2:
    """MessagePortV2 桥接实现 — 新接口内部调用旧 send_service。

    关键发现：custom_reply_set_to_stream 已经接受 MessageSequence！
    因此桥接层不需要做 MessageSequence → dict → MessageSequence 的转换，
    只需要处理 reply_to_id → (set_reply, reply_message) 的转换。
    """

    def __init__(self) -> None:
        self._initialized = False

    def _ensure_import(self) -> None:
        if self._initialized:
            return
        from src.services.send_service import custom_reply_set_to_stream

        self._custom_reply_set_to_stream = custom_reply_set_to_stream
        self._initialized = True

    def _resolve_reply_message(self, reply_to_id: str) -> Any:
        """查找被引用消息的 MaiMessage 对象。

        仅在适配器层导入 chat_manager，核心模块不感知此依赖。
        """
        if not reply_to_id:
            return None

        from src.chat.message_receive.chat_manager import chat_manager

        if "_" in reply_to_id:
            session = chat_manager.get_session_by_session_id(reply_to_id.rsplit("_", 1)[0])
            if session is not None and session.context and session.context.message:
                if session.context.message.message_id == reply_to_id:
                    return session.context.message

        for session in chat_manager.sessions.values():
            if not session.context or not session.context.message:
                continue
            if session.context.message.message_id == reply_to_id:
                return session.context.message
        return None

    async def send_message(
        self,
        session_id: str,
        message: MessageSequence,
        *,
        reply_to_id: str = "",
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        """发送消息 — 统一接口，MessageSequence 直通。

        关键改进：
        1. MessageSequence 直接传给 custom_reply_set_to_stream（不需要转换）
        2. set_reply 基于 reply_message 是否找到（不是 reply_to_id 是否非空）
        3. 找不到被引用消息时降级为不引用，不丢弃整条消息
        """
        self._ensure_import()
        try:
            reply_message = self._resolve_reply_message(reply_to_id) if reply_to_id else None
            set_reply = reply_message is not None

            if reply_to_id and not set_reply:
                logger.debug(
                    f"[message_port_v2] 引用降级: reply_to_id={reply_to_id} "
                    f"未找到，降级为不引用 session={session_id}"
                )

            result = await self._custom_reply_set_to_stream(
                reply_set=message,
                stream_id=session_id,
                set_reply=set_reply,
                reply_message=reply_message,
                storage_message=True,
                show_log=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )

            if result:
                logger.debug(
                    f"[message_port_v2] 发送成功: session={session_id} "
                    f"agent={agent_id} source={source} reply={set_reply}"
                )
                return SendMessageResult.ok()
            return SendMessageResult.failed("发送失败")

        except Exception as e:
            logger.error(
                f"[message_port_v2] 发送失败: session={session_id} "
                f"agent={agent_id} source={source} error={e}"
            )
            return SendMessageResult.failed(str(e))