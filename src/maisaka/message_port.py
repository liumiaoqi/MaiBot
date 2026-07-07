"""核心消息端口 — 组件兼容核心的接口契约。

核心 = 智能体 + 消息管道。消息管道的接口只有两个：
- send: 核心向外部发送消息（回复、提醒、插话、主动发言）
- receive: 外部向核心投递消息（用户消息、通知）

组件（NapCat、WebUI、CLI）实现此接口，核心不依赖组件内部细节。
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol, runtime_checkable

from src.common.logger import get_logger

logger = get_logger("core.message_port")


@runtime_checkable
class MessagePort(Protocol):
    """核心消息端口协议 — 组件实现此接口。

    send: 核心 → 外部（回复、提醒、插话、主动发言）
    核心模块（管家、提醒、Orchestrator）只通过此接口发消息，
    不直接依赖 send_service / chat_manager / NapCat。
    """

    async def send(
        self,
        session_id: str,
        text: str,
        *,
        agent_id: str = "",
        source: str = "core",
    ) -> bool:
        """向指定会话发送文本消息。

        Args:
            session_id: 目标会话 ID
            text: 消息文本
            agent_id: 发言智能体 ID（用于日志和路由）
            source: 消息来源标识（reply/interjection/reminder/proactive）

        Returns:
            是否发送成功
        """


class SendServicePort:
    """基于 send_service 的 MessagePort 实现。

    这是当前唯一的实现，包装已有的 send_service.text_to_stream。
    未来可以有 WebUIPort、CLIPort 等。
    """

    def __init__(self) -> None:
        self._initialized = False

    def _ensure_import(self) -> None:
        if self._initialized:
            return
        from src.services.send_service import text_to_stream
        self._text_to_stream = text_to_stream
        self._initialized = True

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


_port_instance: Optional[MessagePort] = None


def get_message_port() -> MessagePort:
    """获取全局 MessagePort 实例。"""
    global _port_instance
    if _port_instance is None:
        _port_instance = SendServicePort()
    return _port_instance


def set_message_port(port: MessagePort) -> None:
    """设置全局 MessagePort 实例（用于测试或替换实现）。"""
    global _port_instance
    _port_instance = port