"""MessagePort 适配器 — 基于 send_service 的 MessagePort 实现。

适配器层是唯一允许导入组件具体类的地方。
SendServicePort 将 send_service.text_to_stream 包装为 MessagePort Protocol 接口。
"""

from __future__ import annotations

import logging
from typing import Optional

from src.common.logger import get_logger

logger = get_logger("core.adapters.message_port")


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