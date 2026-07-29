"""A_memorix MemoryServicePort 适配器 — 核心通过此接口访问记忆服务。"""


import asyncio
import uuid
from typing import Any, Optional

from src.common.logger import get_logger
from src.common.memory_types import (
    COGNITIVE_TYPE_TO_DETAIL,
    MemorySearchResult,
    MemoryWriteResult,
    ProfileView,
    RecallItem,
    RecallResult,
    ReflectResult,
)
from src.core.types import ObserveRequest, PermanentMemoryError, TemporaryMemoryError

logger = get_logger("core.adapters.memory_service")


def _classify_memory_error(message: str, original: Exception) -> MemoryServiceError:
    """根据原始异常类型分类为临时性或永久性。"""
    if isinstance(original, (ConnectionError, TimeoutError, OSError)):
        return TemporaryMemoryError(message, original=original)
    if isinstance(original, asyncio.TimeoutError):
        return TemporaryMemoryError(message, original=original)
    exc_name = type(original).__name__.lower()
    if any(kw in exc_name for kw in ("timeout", "connection", "network")):
        return TemporaryMemoryError(message, original=original)
    return PermanentMemoryError(message, original=original)


class AMemorixMemoryServicePort:
    """通过 A_memorix memory_service 实现 MemoryServicePort Protocol。"""

    def __init__(self, memory_service: Any = None) -> None:
        self._memory_service = memory_service

    def _get_memory_service(self) -> Any:
        if self._memory_service is None:
            from src.services.memory_service import memory_service
            self._memory_service = memory_service
        return self._memory_service

    async def observe_experience(self, request: ObserveRequest) -> MemoryWriteResult:
        trace_id = uuid.uuid7().hex[:12]
        effective_source_id = request.source_id or f"trace:{trace_id}"
        result = await self._get_memory_service().observe(
            text=request.text,
            valence=request.valence,
            timestamp=request.timestamp,
            source_id=effective_source_id,
            session_id=request.session_id,
            agent_id=request.agent_id,
            participants=list(request.participants) if request.participants else None,
            tags=list(request.tags) if request.tags else None,
            metadata=request.metadata,
        )
        result.trace_id = trace_id
        return result

    async def search(
        self,
        query: str,
        *,
        limit: int = 5,
        mode: str = "search",
        chat_id: str = "",
        person_id: str = "",
        agent_id: str = "",
        time_start: str | float | None = None,
        time_end: str | float | None = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> MemorySearchResult:
        try:
            effective_agent = agent_id or person_id
            return await self._get_memory_service().migration_search(query, agent_id=effective_agent)
        except Exception as exc:
            raise _classify_memory_error(f"搜索失败: query={query}", original=exc) from exc

    async def get_person_profile(self, person_id: str, *, limit: int = 4) -> dict[str, Any]:
        try:
            result = await self._get_memory_service().migration_get_person_profile(person_id, limit=limit)
            if result and (result.summary or result.evidence):
                return result.to_dict()
            return {}
        except Exception as exc:
            raise PermanentMemoryError(
                f"画像查询失败: person_id={person_id}", original=exc,
            ) from exc

    async def profile_admin(self, *, action: str, **kwargs: Any) -> dict[str, Any]:
        try:
            return await self._get_memory_service().profile_admin(action=action, **kwargs)
        except Exception as exc:
            raise _classify_memory_error(
                f"画像管理失败: action={action}", original=exc,
            ) from exc

    async def maintain_memory(
        self,
        *,
        action: str,
        target: str = "",
        hours: Optional[float] = None,
        reason: str = "",
        limit: int = 50,
    ) -> MemoryWriteResult:
        try:
            return await self._get_memory_service().maintain_memory(
                action=action, target=target, hours=hours, reason=reason, limit=limit,
            )
        except Exception as exc:
            raise _classify_memory_error(
                f"记忆维护失败: action={action} target={target}", original=exc,
            ) from exc

    async def delete_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs: Any) -> dict[str, Any]:
        try:
            return await self._get_memory_service().delete_admin(
                action=action, timeout_ms=timeout_ms, **kwargs,
            )
        except Exception as exc:
            raise _classify_memory_error(
                f"删除管理失败: action={action}", original=exc,
            ) from exc

    async def build_profile_injection_text(self, raw_text: str) -> str:
        return await self._get_memory_service().migration_build_profile_injection_text(raw_text)

    async def set_memory_personality(self, agent_id: str, params: dict[str, Any]) -> None:
        try:
            await self._get_memory_service().register_agent(agent_id, params)
        except Exception as exc:
            raise PermanentMemoryError(
                f"设置记忆性格失败: agent={agent_id}", original=exc,
            ) from exc

    async def recall(
        self, seeds: list[str], *, agent_id: str = "", min_weight: float = 0.05, max_results: int = 20,
    ) -> list[RecallItem]:
        try:
            raw = await self._get_memory_service().recall(
                seeds=seeds, agent_id=agent_id, min_weight=min_weight, max_results=max_results,
            )
            if isinstance(raw, list):
                return [RecallItem(**item) if isinstance(item, dict) else item for item in raw]
            return []
        except Exception as exc:
            raise _classify_memory_error(f"概念召回失败: agent={agent_id}", original=exc) from exc

    async def recall_with_intuition(
        self, seeds: list[str], context_text: str, *, agent_id: str = "",
        min_weight: float = 0.05, max_results: int = 20, max_tokens: int = 800,
    ) -> RecallResult:
        try:
            raw = await self._get_memory_service().recall_with_intuition(
                seeds=seeds, context_text=context_text, agent_id=agent_id,
                min_weight=min_weight, max_results=max_results, max_tokens=max_tokens,
            )
            if isinstance(raw, dict):
                items = raw.get("recall_items", []) or []
                intuition = raw.get("intuition")
                recall_items: list[RecallItem] = []
                for i in items:
                    item = RecallItem(**i) if isinstance(i, dict) else i
                    if item.cognitive_type and item.cognitive_type in COGNITIVE_TYPE_TO_DETAIL:
                        item.detail_level = COGNITIVE_TYPE_TO_DETAIL[item.cognitive_type]
                    recall_items.append(item)
                return RecallResult(
                    recall_items=recall_items,
                    intuition=intuition,
                )
            return RecallResult()
        except Exception as exc:
            raise _classify_memory_error(f"直觉召回失败: agent={agent_id}", original=exc) from exc

    async def derive_profile(self, subject: str, *, observer: str = "") -> ProfileView:
        try:
            raw = await self._get_memory_service().derive_profile(subject=subject, observer=observer)
            if isinstance(raw, dict):
                return ProfileView(**raw)
            return ProfileView(subject=subject, observer=observer)
        except Exception as exc:
            raise _classify_memory_error(f"画像视图失败: subject={subject}", original=exc) from exc

    async def reflect(self, subject: str, *, agent_id: str = "") -> ReflectResult:
        try:
            raw = await self._get_memory_service().reflect(subject=subject, agent_id=agent_id)
            if isinstance(raw, dict):
                return ReflectResult(**raw)
            return ReflectResult(subject=subject, agent_id=agent_id)
        except Exception as exc:
            raise _classify_memory_error(f"反思失败: subject={subject}", original=exc) from exc

    async def weave_narrative(self, *, agent_id: str = "") -> dict[str, Any]:
        try:
            return await self._get_memory_service().weave_narrative(agent_id=agent_id)
        except Exception as exc:
            raise _classify_memory_error(f"叙事编织失败: agent={agent_id}", original=exc) from exc

    async def heartbeat_maintenance(self, *, agent_id: str = "", elapsed_hours: float = 1.0) -> dict[str, Any]:
        try:
            return await self._get_memory_service().heartbeat_maintenance(
                agent_id=agent_id, elapsed_hours=elapsed_hours,
            )
        except Exception as exc:
            raise _classify_memory_error(f"心跳维护失败: agent={agent_id}", original=exc) from exc


# ── 模块级单例 ──────────────────────────────────

_instance: AMemorixMemoryServicePort | None = None


def get_memory_service_port() -> AMemorixMemoryServicePort:
    global _instance
    if _instance is None:
        from src.services.memory_service import memory_service
        _instance = AMemorixMemoryServicePort(memory_service=memory_service)
    return _instance


def reset_memory_service_port() -> None:
    global _instance
    _instance = None
