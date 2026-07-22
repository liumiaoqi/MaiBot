"""HeartflowRuntimeRegistry — ChatRuntimeRegistry 的 heartflow_manager 适配器。"""

from __future__ import annotations

from typing import Any, Optional

from src.common.logger import get_logger
from src.core.protocols import ChatRuntime, ChatRuntimeRegistry

logger = get_logger("core.adapters.runtime_registry")


class HeartflowRuntimeRegistry:
    """通过 heartflow_manager 实现 ChatRuntimeRegistry Protocol。

    返回的 ChatRuntime 实际是 MaisakaHeartFlowChatting 实例，
    它通过 Python Protocol 结构化子类型满足 ChatRuntime 接口。
    """

    def __init__(self, heartflow_manager: Any) -> None:
        self._heartflow_manager = heartflow_manager

    async def get_runtime(self, session_id: str) -> Optional[ChatRuntime]:
        runtime = self._heartflow_manager.heartflow_chat_list.get(session_id)
        return runtime

    async def get_or_create_runtime(self, session_id: str) -> ChatRuntime:
        return await self._heartflow_manager.get_or_create_heartflow_chat(session_id)

    def list_runtimes(self) -> list[ChatRuntime]:
        """列出所有活跃的运行时实例。"""
        return list(self._heartflow_manager.heartflow_chat_list.values())

