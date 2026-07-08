from __future__ import annotations

from typing import Any, Dict

from .base import BaseAdminHandler


class SourceAdminHandler(BaseAdminHandler):
    """来源管理 Admin Handler — 从 memory_source_admin 提取。"""

    def __init__(self, kernel: Any) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        assert self._kernel.metadata_store

        act = self._str_action(action)
        if act == "list":
            return self._list_sources()
        if act == "delete":
            return await self._delete_source(kwargs)
        if act == "batch_delete":
            return await self._batch_delete_sources(kwargs)
        return self._unsupported("source", act)

    def _list_sources(self) -> Dict[str, Any]:
        sources = self._kernel.metadata_store.get_all_sources()
        items = []
        for row in sources:
            source_name = str(row.get("source", "") or "").strip()
            items.append(
                {
                    **row,
                    "episode_rebuild_blocked": self._kernel.metadata_store.is_episode_source_query_blocked(source_name),
                }
            )
        return {"success": True, "items": items, "count": len(items)}

    async def _delete_source(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        source = str(kwargs.get("source", "") or "").strip()
        result = await self._kernel._execute_delete_action(
            mode="source",
            selector={"sources": [source]},
            requested_by=str(kwargs.get("requested_by", "") or "memory_source_admin"),
            reason=str(kwargs.get("reason", "") or "source_delete"),
        )
        await self._kernel._invalidate_import_manifest_for_sources(result)
        return result

    async def _batch_delete_sources(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        result = await self._kernel._execute_delete_action(
            mode="source",
            selector={"sources": list(kwargs.get("sources") or [])},
            requested_by=str(kwargs.get("requested_by", "") or "memory_source_admin"),
            reason=str(kwargs.get("reason", "") or "source_batch_delete"),
        )
        await self._kernel._invalidate_import_manifest_for_sources(result)
        return result