"""ChatBotMessageIngestionPort — 将 ChatBot 包装为 MessageIngestionPort Protocol。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from src.core.protocols import MessageIngestionPort
    from src.core.types import SessionMessage

from src.common.logger import get_logger

logger = get_logger("core.adapters.message_ingestion_port")

_provider: MessageIngestionPort | None = None


def get_message_ingestion_port() -> MessageIngestionPort:
    if _provider is None:
        raise RuntimeError("MessageIngestionPort 未注册，请先调用 set_message_ingestion_port()")
    return _provider


def set_message_ingestion_port(port: MessageIngestionPort) -> None:
    global _provider
    if _provider is not None:
        logger.warning("MessageIngestionPort 已注册，将被覆盖")
    _provider = port


def reset_message_ingestion_port() -> None:
    global _provider
    _provider = None


class ChatBotMessageIngestionPort:
    """纯委托适配器，包裹 ChatBot 实现 MessageIngestionPort Protocol。"""

    def __init__(self, chat_bot: Any) -> None:
        self._chat_bot = chat_bot

    async def receive_message(self, message: SessionMessage) -> None:
        await self._chat_bot.receive_message(message)

    async def message_process(self, message_data: Dict[str, Any]) -> None:
        await self._chat_bot.message_process(message_data)
