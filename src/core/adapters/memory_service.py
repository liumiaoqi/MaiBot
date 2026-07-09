"""A_memorix MemoryServicePort 适配器 — 核心通过此接口访问记忆服务。"""

from __future__ import annotations

from typing import Any, Optional

from src.common.logger import get_logger
from src.core.protocols import MemoryServicePort
from src.core.types import MemorySearchResult, MemoryWriteResult

logger = get_logger("core.adapters.memory_service")


class AMemorixMemoryServicePort:
    """通过 A_memorix memory_service 实现 MemoryServicePort Protocol。"""

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        mode: str = "search",
        chat_id: str = "",
        person_id: str = "",
        time_start: str | float | None = None,
        time_end: str | float | None = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> MemorySearchResult:
        from src.services.memory_service import memory_service

        try:
            return await memory_service.search(
                query=query,
                limit=limit,
                mode=mode,
                chat_id=chat_id,
                person_id=person_id,
                time_start=time_start,
                time_end=time_end,
                respect_filter=respect_filter,
                user_id=user_id,
                group_id=group_id,
            )
        except Exception as exc:
            logger.warning(f"[memory_port] 搜索失败: query={query} error={exc}")
            return MemorySearchResult(success=False, error=str(exc))

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

    async def profile_admin(self, *, action: str, **kwargs: Any) -> dict[str, Any]:
        from src.services.memory_service import memory_service

        try:
            return await memory_service.profile_admin(action=action, **kwargs)
        except Exception as exc:
            logger.warning(f"[memory_port] 画像管理失败: action={action} error={exc}")
            return {"success": False, "error": str(exc)}

    async def ingest_text(
        self,
        *,
        external_id: str,
        source_type: str,
        text: str,
        chat_id: str = "",
        person_ids: Optional[list[str]] = None,
        participants: Optional[list[str]] = None,
        timestamp: Optional[float] = None,
        time_start: Optional[float] = None,
        time_end: Optional[float] = None,
        tags: Optional[list[str]] = None,
        metadata: Optional[dict[str, Any]] = None,
        entities: Optional[list[str]] = None,
        relations: Optional[list[dict[str, Any]]] = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> MemoryWriteResult:
        from src.services.memory_service import memory_service

        try:
            return await memory_service.ingest_text(
                external_id=external_id,
                source_type=source_type,
                text=text,
                chat_id=chat_id,
                person_ids=person_ids,
                participants=participants,
                timestamp=timestamp,
                time_start=time_start,
                time_end=time_end,
                tags=tags,
                metadata=metadata,
                entities=entities,
                relations=relations,
                respect_filter=respect_filter,
                user_id=user_id,
                group_id=group_id,
            )
        except Exception as exc:
            logger.warning(f"[memory_port] 文本摄入失败: external_id={external_id} error={exc}")
            return MemoryWriteResult(success=False, detail=str(exc))

    async def maintain_memory(
        self,
        *,
        action: str,
        target: str = "",
        hours: Optional[float] = None,
        reason: str = "",
        limit: int = 50,
    ) -> MemoryWriteResult:
        from src.services.memory_service import memory_service

        try:
            return await memory_service.maintain_memory(
                action=action, target=target, hours=hours, reason=reason, limit=limit
            )
        except Exception as exc:
            logger.warning(f"[memory_port] 记忆维护失败: action={action} target={target} error={exc}")
            return MemoryWriteResult(success=False, detail=str(exc))

    async def delete_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs: Any) -> dict[str, Any]:
        from src.services.memory_service import memory_service

        try:
            return await memory_service.delete_admin(action=action, timeout_ms=timeout_ms, **kwargs)
        except Exception as exc:
            logger.warning(f"[memory_port] 删除管理失败: action={action} error={exc}")
            return {"success": False, "error": str(exc)}

    async def enqueue_feedback_task(
        self,
        *,
        query_tool_id: str,
        session_id: str,
        query_timestamp: Any = None,
        structured_content: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        from src.services.memory_service import memory_service

        try:
            return await memory_service.enqueue_feedback_task(
                query_tool_id=query_tool_id,
                session_id=session_id,
                query_timestamp=query_timestamp,
                structured_content=structured_content,
            )
        except Exception as exc:
            logger.warning(f"[memory_port] 反馈任务入队失败: session={session_id} error={exc}")
            return {"success": False, "queued": False, "reason": str(exc)}

    async def build_profile_injection_text(self, raw_text: str) -> str:
        from src.A_memorix.host_service import a_memorix_host_service

        return a_memorix_host_service.build_profile_injection_text(raw_text)

    async def set_memory_personality(self, agent_id: str, params: dict[str, Any]) -> None:
        """将智能体记忆性格参数传递给 A_memorix 连接主义记忆系统。"""
        try:
            from src.services.memory_service import memory_service

            await memory_service.invoke(
                "register_agent",
                {
                    "agent_id": agent_id,
                    **params,
                },
            )
        except Exception as exc:
            logger.warning(
                "[memory_port] 设置记忆性格失败: agent=%s error=%s", agent_id, exc
            )
