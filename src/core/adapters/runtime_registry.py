"""HeartflowRuntimeRegistry — ChatRuntimeRegistry 的 heartflow_manager 适配器。"""

from __future__ import annotations

from typing import Optional

from src.common.logger import get_logger
from src.core.protocols import ChatRuntime, ChatRuntimeRegistry

logger = get_logger("core.adapters.runtime_registry")


class HeartflowRuntimeRegistry:
    """通过 heartflow_manager 实现 ChatRuntimeRegistry Protocol。

    返回的 ChatRuntime 实际是 MaisakaHeartFlowChatting 实例，
    它通过 Python Protocol 结构化子类型满足 ChatRuntime 接口。
    """

    def _ensure_manager(self):
        from src.chat.heart_flow.heartflow_manager import heartflow_manager

        return heartflow_manager

    async def get_runtime(self, session_id: str) -> Optional[ChatRuntime]:
        manager = self._ensure_manager()
        runtime = manager.heartflow_chat_list.get(session_id)
        return runtime

    async def get_or_create_runtime(self, session_id: str) -> ChatRuntime:
        manager = self._ensure_manager()
        return await manager.get_or_create_heartflow_chat(session_id)