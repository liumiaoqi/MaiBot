"""MessagePort 适配器 — 基于 send_service 的 MessagePort 实现。

适配器层是唯一允许导入组件具体类的地方。
SendServicePort 将 send_service 函数包装为 MessagePort Protocol 接口。
"""

from __future__ import annotations

from typing import Any, Optional

from src.common.logger import get_logger
from src.core.types import SendMessageResult

logger = get_logger("core.adapters.message_port")


class SendServicePort:
    """基于 send_service 的 MessagePort 实现。

    这是当前唯一的实现，包装已有的 send_service 发送函数。
    未来可以有 WebUIPort、CLIPort 等。
    """

    def __init__(self) -> None:
        self._initialized = False

    def _ensure_import(self) -> None:
        if self._initialized:
            return
        from src.services.send_service import (
            _send_to_target_with_message,
            custom_reply_set_to_stream,
            custom_to_stream,
            emoji_to_stream_with_message,
            image_to_stream,
            text_to_stream,
        )

        self._text_to_stream = text_to_stream
        self._image_to_stream = image_to_stream
        self._emoji_to_stream_with_message = emoji_to_stream_with_message
        self._custom_reply_set_to_stream = custom_reply_set_to_stream
        self._custom_to_stream = custom_to_stream
        self._send_to_target_with_message = _send_to_target_with_message
        self._initialized = True

    def _resolve_reply_message(self, reply_to: str) -> Any:
        """通过 chat_manager 查找被引用消息的 MaiMessage 对象。

        仅在适配器层导入 chat_manager，核心模块不感知此依赖。
        支持两种格式：session_id_messageid（带下划线）或纯消息ID。
        """
        from src.chat.message_receive.chat_manager import chat_manager

        if "_" in reply_to:
            session = chat_manager.get_session_by_session_id(reply_to.rsplit("_", 1)[0])
            if session is not None and session.context and session.context.message:
                if session.context.message.message_id == reply_to:
                    return session.context.message

        for session in chat_manager.sessions.values():
            if not session.context or not session.context.message:
                continue
            if session.context.message.message_id == reply_to:
                return session.context.message
        return None

    def _segments_to_message_sequence(self, segments: list[dict[str, Any]]) -> Any:
        """将 segments 列表转换为 MessageSequence。"""
        from src.core.adapters.message_port_v2 import segments_to_message_sequence
        return segments_to_message_sequence(segments)

    def _forward_nodes_to_message_sequence(self, messages: list[dict[str, Any]]) -> Any:
        """将转发节点列表转换为 MessageSequence。"""
        from src.common.data_models.message_component_data_model import (
            ForwardNodeComponent,
            MessageSequence,
        )

        nodes = []
        for msg in messages:
            nodes.append(
                ForwardNodeComponent(
                    user_id=msg.get("user_id", ""),
                    user_nickname=msg.get("user_nickname", ""),
                    user_cardname=msg.get("user_cardname", ""),
                    message_id=msg.get("message_id", ""),
                    content=msg.get("content", []),
                )
            )
        return MessageSequence(components=nodes)

    async def send(
        self,
        session_id: str,
        text: str,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> bool:
        self._ensure_import()
        try:
            result = await self._text_to_stream(
                text=text,
                stream_id=session_id,
                storage_message=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )
            if result:
                logger.debug(
                    f"[message_port] 发送成功: session={session_id} "
                    f"agent={agent_id} source={source} len={len(text)}"
                )
            return result
        except Exception as e:
            logger.error(
                f"[message_port] 发送失败: session={session_id} "
                f"agent={agent_id} source={source} error={e}"
            )
            return False

    async def send_reply(
        self,
        session_id: str,
        text: str,
        *,
        reply_to: str,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        self._ensure_import()
        try:
            reply_message = self._resolve_reply_message(reply_to) if reply_to else None
            from src.common.data_models.message_component_data_model import MessageSequence, TextComponent

            message_sequence = MessageSequence(components=[TextComponent(text=text)])
            result = await self._send_to_target_with_message(
                message_sequence=message_sequence,
                stream_id=session_id,
                set_reply=reply_message is not None,
                reply_message=reply_message,
                storage_message=True,
                show_log=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )
            if result is not None:
                logger.debug(f"[message_port] 引用回复成功: session={session_id} reply_to={reply_to}")
                return SendMessageResult.ok(message_id=result.message_id)
            return SendMessageResult.failed("发送失败")
        except Exception as e:
            logger.error(f"[message_port] 引用回复失败: session={session_id} error={e}")
            return SendMessageResult.failed(str(e))

    async def send_image(
        self,
        session_id: str,
        image_base64: str,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        self._ensure_import()
        try:
            result = await self._image_to_stream(
                image_base64=image_base64,
                stream_id=session_id,
                storage_message=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )
            if result:
                logger.debug(f"[message_port] 图片发送成功: session={session_id}")
                return SendMessageResult.ok()
            return SendMessageResult.failed("发送失败")
        except Exception as e:
            logger.error(f"[message_port] 图片发送失败: session={session_id} error={e}")
            return SendMessageResult.failed(str(e))

    async def send_emoji(
        self,
        session_id: str,
        emoji_base64: str,
        *,
        reply_to: str = "",
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        self._ensure_import()
        try:
            reply_message = self._resolve_reply_message(reply_to) if reply_to else None
            result = await self._emoji_to_stream_with_message(
                emoji_base64=emoji_base64,
                stream_id=session_id,
                storage_message=True,
                set_reply=reply_message is not None,
                reply_message=reply_message,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )
            if result is not None:
                logger.debug(f"[message_port] 表情发送成功: session={session_id}")
                return SendMessageResult.ok(message_id=result.message_id)
            return SendMessageResult.failed("发送失败")
        except Exception as e:
            logger.error(f"[message_port] 表情发送失败: session={session_id} error={e}")
            return SendMessageResult.failed(str(e))

    async def send_hybrid(
        self,
        session_id: str,
        segments: list[dict[str, Any]],
        *,
        reply_to: str = "",
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        self._ensure_import()
        try:
            message_sequence = self._segments_to_message_sequence(segments)
            reply_message = self._resolve_reply_message(reply_to) if reply_to else None
            result = await self._custom_reply_set_to_stream(
                reply_set=message_sequence,
                stream_id=session_id,
                set_reply=reply_message is not None,
                reply_message=reply_message,
                storage_message=True,
                show_log=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )
            if result:
                logger.debug(f"[message_port] 混合消息发送成功: session={session_id}")
                return SendMessageResult.ok()
            return SendMessageResult.failed("发送失败")
        except Exception as e:
            logger.error(f"[message_port] 混合消息发送失败: session={session_id} error={e}")
            return SendMessageResult.failed(str(e))

    async def send_forward(
        self,
        session_id: str,
        messages: list[dict[str, Any]],
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        self._ensure_import()
        try:
            message_sequence = self._forward_nodes_to_message_sequence(messages)
            result = await self._custom_reply_set_to_stream(
                reply_set=message_sequence,
                stream_id=session_id,
                storage_message=True,
                show_log=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )
            if result:
                logger.debug(f"[message_port] 转发消息发送成功: session={session_id}")
                return SendMessageResult.ok()
            return SendMessageResult.failed("发送失败")
        except Exception as e:
            logger.error(f"[message_port] 转发消息发送失败: session={session_id} error={e}")
            return SendMessageResult.failed(str(e))

    async def send_custom(
        self,
        session_id: str,
        message_type: str,
        content: Any,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> SendMessageResult:
        self._ensure_import()
        try:
            result = await self._custom_to_stream(
                message_type=message_type,
                content=content,
                stream_id=session_id,
                storage_message=True,
                show_log=True,
                sync_to_maisaka_history=True,
                maisaka_source_kind=source,
            )
            if result:
                logger.debug(f"[message_port] 自定义消息发送成功: session={session_id} type={message_type}")
                return SendMessageResult.ok()
            return SendMessageResult.failed("发送失败")
        except Exception as e:
            logger.error(f"[message_port] 自定义消息发送失败: session={session_id} error={e}")
            return SendMessageResult.failed(str(e))
