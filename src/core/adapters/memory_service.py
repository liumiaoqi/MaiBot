"""A_memorix MemoryServicePort 适配器 — 核心通过此接口访问记忆服务。"""

from __future__ import annotations

from typing import Any, Optional

from src.common.logger import get_logger
from src.core.protocols import MemoryServicePort

logger = get_logger("core.adapters.memory_service")


class AMemorixMemoryServicePort:
    """通过 A_memorix host_service 实现 MemoryServicePort Protocol。"""

    async def search(self, query: str, session_id: str, *, limit: int = 5) -> list[dict[str, Any]]:
        from src.services.memory_service import memory_service

        try:
            result = await memory_service.search(query=query, session_id=session_id, limit=limit)
            if isinstance(result, list):
                return result
            return []
        except Exception as exc:
            logger.warning(f"[memory_port] 搜索失败: query={query} error={exc}")
            return []

    async def get_person_profile(self, person_id: str, *, limit: int = 4) -> Optional[dict[str, Any]]:
        from src.services.memory_service import memory_service

        try:
            result = await memory_service.profile_admin(action="query", person_id=person_id, limit=limit)
            if isinstance(result, dict) and result.get("success"):
                return result
            return None
        except Exception as exc:
            logger.debug(f"[memory_port] 画像查询失败: person_id={person_id} error={exc}")
            return None

    async def build_profile_injection_text(self, raw_text: str) -> str:
        from src.A_memorix.core.utils.profile_text import build_profile_injection_text

        return build_profile_injection_text(raw_text)