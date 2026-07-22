from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


from src.common.logger import get_logger
from src.core.memory_utils import coerce_search_result, coerce_write_result
from src.core.types import MemoryHit, MemorySearchResult, MemoryWriteResult


logger = get_logger("memory_service")


__all__ = [
    "MemoryHit",
    "MemorySearchResult",
    "MemoryWriteResult",
    "PersonProfileResult",
    "MemoryService",
    "memory_service",
]


@dataclass
class PersonProfileResult:

    summary: str = ""
    traits: List[str] = field(default_factory=list)
    evidence: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"summary": self.summary, "traits": self.traits, "evidence": self.evidence}


class MemoryService:
    def _get_host_service(self) -> Any:
        from src.A_memorix.host_service import a_memorix_host_service
        return a_memorix_host_service

    async def _invoke(self, component_name: str, args: Optional[Dict[str, Any]] = None, *, timeout_ms: int = 30000) -> Any:
        response = await self._get_host_service().invoke(
            component_name,
            args or {},
            timeout_ms=max(1000, int(timeout_ms or 30000)),
        )
        if isinstance(response, dict):
            return response
        payload = getattr(response, "payload", None)
        if isinstance(payload, dict):
            if isinstance(payload.get("result"), dict):
                return payload["result"]
            return payload
        model_dump = getattr(response, "model_dump", None)
        if callable(model_dump):
            dumped = model_dump()
            if isinstance(dumped, dict):
                inner_payload = dumped.get("payload")
                if isinstance(inner_payload, dict):
                    if isinstance(inner_payload.get("result"), dict):
                        return inner_payload["result"]
                    return inner_payload
        return response

    async def _invoke_admin(
        self,
        component_name: str,
        *,
        action: str,
        timeout_ms: int = 30000,
        **kwargs,
    ) -> Dict[str, Any]:
        payload = await self._invoke(component_name, {"action": action, **kwargs}, timeout_ms=timeout_ms)
        return payload if isinstance(payload, dict) else {"success": False, "error": "invalid_payload"}

    @staticmethod
    def _coerce_write_result(payload: Any) -> MemoryWriteResult:
        return coerce_write_result(payload)

    @staticmethod
    def _coerce_search_result(payload: Any) -> MemorySearchResult:
        return coerce_search_result(payload)

    @staticmethod
    def _coerce_profile_result(payload: Any) -> PersonProfileResult:
        if not isinstance(payload, dict):
            return PersonProfileResult()
        return PersonProfileResult(
            summary=payload.get("summary", ""),
            traits=[str(item) for item in (payload.get("traits") or []) if str(item).strip()],
            evidence=[item for item in (payload.get("evidence") or []) if isinstance(item, dict)],
        )

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
        clean_query = str(query or "").strip()
        normalized_time_start = None if time_start in {None, ""} else time_start
        normalized_time_end = None if time_end in {None, ""} else time_end
        if not clean_query and normalized_time_start is None and normalized_time_end is None:
            return MemorySearchResult()
        payload = await self._invoke(
            "search_memory",
            {
                "query": clean_query,
                "limit": max(1, int(limit)),
                "mode": mode,
                "chat_id": chat_id,
                "person_id": person_id,
                "time_start": normalized_time_start,
                "time_end": normalized_time_end,
                "respect_filter": bool(respect_filter),
                "user_id": str(user_id or "").strip(),
                "group_id": str(group_id or "").strip(),
            },
        )
        return self._coerce_search_result(payload)

    async def enqueue_feedback_task(
        self,
        *,
        query_tool_id: str,
        session_id: str,
        query_timestamp: Any = None,
        structured_content: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = await self._invoke(
            "enqueue_feedback_task",
            {
                "query_tool_id": str(query_tool_id or "").strip(),
                "session_id": str(session_id or "").strip(),
                "query_timestamp": query_timestamp,
                "structured_content": structured_content if isinstance(structured_content, dict) else {},
            },
            timeout_ms=10000,
        )
        return payload if isinstance(payload, dict) else {"success": False, "queued": False, "reason": "invalid_payload"}

    async def ingest_summary(
        self,
        *,
        external_id: str,
        chat_id: str,
        text: str,
        participants: Optional[List[str]] = None,
        time_start: float | None = None,
        time_end: float | None = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> MemoryWriteResult:
        payload = await self._invoke(
            "ingest_summary",
            {
                "external_id": external_id,
                "chat_id": chat_id,
                "text": text,
                "participants": participants or [],
                "time_start": time_start,
                "time_end": time_end,
                "tags": tags or [],
                "metadata": metadata or {},
                "respect_filter": bool(respect_filter),
                "user_id": str(user_id or "").strip(),
                "group_id": str(group_id or "").strip(),
            },
        )
        return self._coerce_write_result(payload)

    async def ingest_text(
        self,
        *,
        external_id: str,
        source_type: str,
        text: str,
        chat_id: str = "",
        person_ids: Optional[List[str]] = None,
        participants: Optional[List[str]] = None,
        timestamp: float | None = None,
        time_start: float | None = None,
        time_end: float | None = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        entities: Optional[List[str]] = None,
        relations: Optional[List[Dict[str, Any]]] = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> MemoryWriteResult:
        import warnings
        import warnings
        warnings.warn("ingest_text 已废弃，请使用 observe()", DeprecationWarning, stacklevel=2)
        payload = await self._invoke(
            "ingest_text",
            {
                "external_id": external_id,
                "source_type": source_type,
                "text": text,
                "chat_id": chat_id,
                "person_ids": person_ids or [],
                "participants": participants or [],
                "timestamp": timestamp,
                "time_start": time_start,
                "time_end": time_end,
                "tags": tags or [],
                "metadata": metadata or {},
                "entities": entities or [],
                "relations": relations or [],
                "respect_filter": bool(respect_filter),
                "user_id": str(user_id or "").strip(),
                "group_id": str(group_id or "").strip(),
            },
        )
        return self._coerce_write_result(payload)

    async def get_person_profile(self, person_id: str, *, chat_id: str = "", limit: int = 10) -> PersonProfileResult:
        clean_person_id = str(person_id or "").strip()
        if not clean_person_id:
            return PersonProfileResult()
        payload = await self._invoke(
            "get_person_profile",
            {"person_id": clean_person_id, "chat_id": chat_id, "limit": max(1, int(limit))},
        )
        return self._coerce_profile_result(payload)

    async def observe(
        self,
        *,
        text: str,
        valence: str = "neutral",
        timestamp: float | None = None,
        source_id: str = "",
        session_id: str = "",
        agent_id: str = "",
        participants: list[str] | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryWriteResult:
        payload: dict[str, Any] = {
            "text": text,
            "valence": valence,
            "source_id": source_id,
            "session_id": session_id,
            "agent_id": agent_id,
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        if participants:
            payload["participants"] = list(participants)
        if tags:
            payload["tags"] = list(tags)
        if metadata:
            payload["metadata"] = metadata
        result = await self._invoke("observe", payload)
        return coerce_write_result(result)

    async def maintain_memory(
        self,
        *,
        action: str,
        target: str = "",
        hours: float | None = None,
        reason: str = "",
        limit: int = 50,
    ) -> MemoryWriteResult:
        payload = await self._invoke(
            "maintain_memory",
            {"action": action, "target": target, "hours": hours, "reason": reason, "limit": limit},
        )
        if not isinstance(payload, dict):
            return MemoryWriteResult(success=False, detail="invalid_payload")
        return MemoryWriteResult(success=bool(payload.get("success")), detail=payload.get("detail", ""))

    async def memory_stats(self) -> Dict[str, Any]:
        payload = await self._invoke("memory_stats", {})
        return payload if isinstance(payload, dict) else {}

    async def graph_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_graph_admin", action=action, **kwargs)

    async def source_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_source_admin", action=action, **kwargs)

    async def episode_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_episode_admin", action=action, **kwargs)

    async def profile_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_profile_admin", action=action, **kwargs)

    async def feedback_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_feedback_admin", action=action, **kwargs)

    async def runtime_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_runtime_admin", action=action, **kwargs)

    async def import_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_import_admin", action=action, timeout_ms=timeout_ms, **kwargs)

    async def tuning_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_tuning_admin", action=action, timeout_ms=timeout_ms, **kwargs)

    async def v5_admin(self, *, action: str, timeout_ms: int = 30000, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_v5_admin", action=action, timeout_ms=timeout_ms, **kwargs)

    async def delete_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_delete_admin", action=action, timeout_ms=timeout_ms, **kwargs)

    async def memory_correction_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs) -> Dict[str, Any]:
        return await self._invoke_admin("memory_correction_admin", action=action, timeout_ms=timeout_ms, **kwargs)

    async def fuzzy_modify_admin(self, *, action: str, timeout_ms: int = 120000, **kwargs) -> Dict[str, Any]:
        return await self.memory_correction_admin(action=action, timeout_ms=timeout_ms, **kwargs)

    async def get_recycle_bin(self, *, limit: int = 50) -> Dict[str, Any]:
        payload = await self._invoke("maintain_memory", {"action": "recycle_bin", "limit": max(1, int(limit or 50))})
        return payload if isinstance(payload, dict) else {"success": False, "error": "invalid_payload"}

    async def restore_memory(self, *, target: str) -> MemoryWriteResult:
        return await self.maintain_memory(action="restore", target=target)

    async def reinforce_memory(self, *, target: str) -> MemoryWriteResult:
        return await self.maintain_memory(action="reinforce", target=target)

    async def freeze_memory(self, *, target: str) -> MemoryWriteResult:
        return await self.maintain_memory(action="freeze", target=target)

    async def protect_memory(self, *, target: str, hours: float | None = None) -> MemoryWriteResult:
        return await self.maintain_memory(action="protect", target=target, hours=hours)

    async def get_paragraphs_by_source(self, source: str) -> List[Dict[str, Any]]:
        """按来源查询段落元数据，替代直接访问 kernel.metadata_store。"""
        clean_source = str(source or "").strip()
        if not clean_source:
            return []
        payload = await self._invoke(
            "metadata_get_paragraphs_by_source",
            {"source": clean_source},
        )
        return payload if isinstance(payload, list) else []

    async def query_metadata(self, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """只读 SQL 查询元数据存储，替代直接访问 kernel.metadata_store.query()。"""
        clean_sql = str(sql or "").strip()
        if not clean_sql:
            return []
        payload = await self._invoke(
            "metadata_query",
            {"sql": clean_sql, "params": list(params)},
        )
        return payload if isinstance(payload, list) else []

    def get_config_schema(self) -> Dict[str, Any]:
        return self._get_host_service().get_config_schema()

    def get_config(self) -> Dict[str, Any]:
        return self._get_host_service().get_config()

    def get_config_path(self) -> Any:
        return self._get_host_service().get_config_path()

    def get_raw_config_with_meta(self) -> Dict[str, Any]:
        return self._get_host_service().get_raw_config_with_meta()

    async def update_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return await self._get_host_service().update_config(config)

    async def update_raw_config(self, raw_config: str) -> Dict[str, Any]:
        return await self._get_host_service().update_raw_config(raw_config)

    @staticmethod
    def build_profile_injection_text(raw_text: str) -> str:
        from src.A_memorix.host_service import a_memorix_host_service

        return a_memorix_host_service.build_profile_injection_text(raw_text)

    async def migration_search(self, query: str, *, agent_id: str = "", **kwargs) -> MemorySearchResult:
        payload = {"query": query, "agent_id": agent_id, **kwargs}
        result = await self._invoke("migration_search", payload)
        if isinstance(result, MemorySearchResult):
            return result
        return self._coerce_search_result(result)

    async def migration_get_person_profile(self, person_id: str, *, agent_id: str = "", limit: int = 4) -> PersonProfileResult:
        payload = {"person_id": person_id, "agent_id": agent_id, "limit": limit}
        result = await self._invoke("migration_get_person_profile", payload)
        return self._coerce_profile_result(result)

    async def migration_ingest_text(self, text: str, **kwargs) -> MemoryWriteResult:
        payload = {"text": text, **kwargs}
        result = await self._invoke("migration_ingest_text", payload)
        if isinstance(result, MemoryWriteResult):
            return result
        return self._coerce_write_result(result)

    async def migration_build_profile_injection_text(self, raw_text: str, *, agent_id: str = "") -> str:
        payload = {"raw_text": raw_text, "agent_id": agent_id}
        result = await self._invoke("migration_build_profile_injection_text", payload)
        return str(result) if result else ""

    async def register_agent(self, agent_id: str, params: dict[str, Any]) -> Dict[str, Any]:
        payload = {"agent_id": agent_id, **params}
        return await self._invoke("register_agent", payload)


memory_service = MemoryService()
