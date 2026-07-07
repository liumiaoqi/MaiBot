from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.graph")


class GraphAdminHandler(BaseAdminHandler):
    """图管理 Admin Handler — 从 memory_graph_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        assert self._kernel.metadata_store is not None
        assert self._kernel.graph_store is not None

        act = self._str_action(action)
        if act == "get_graph":
            return {"success": True, **self._kernel._serialize_graph(limit=max(1, int(kwargs.get("limit", 200) or 200)))}
        if act == "search":
            return self._kernel._search_graph(
                query=str(kwargs.get("query", "") or "").strip(),
                limit=max(1, min(200, int(kwargs.get("limit", 50) or 50))),
            )
        if act == "node_detail":
            return self._kernel._build_graph_node_detail(
                node_id=str(kwargs.get("node_id", "") or kwargs.get("node", "") or "").strip(),
                relation_limit=max(1, int(kwargs.get("relation_limit", 20) or 20)),
                paragraph_limit=max(1, int(kwargs.get("paragraph_limit", 20) or 20)),
                evidence_node_limit=max(12, int(kwargs.get("evidence_node_limit", 80) or 80)),
            )
        if act == "edge_detail":
            return self._kernel._build_graph_edge_detail(
                source=str(kwargs.get("source", "") or "").strip(),
                target=str(kwargs.get("target", "") or kwargs.get("object", "") or "").strip(),
                paragraph_limit=max(1, int(kwargs.get("paragraph_limit", 20) or 20)),
                evidence_node_limit=max(12, int(kwargs.get("evidence_node_limit", 80) or 80)),
            )
        if act == "create_node":
            name = str(kwargs.get("name", "") or kwargs.get("node", "") or "").strip()
            if not name:
                return {"success": False, "error": "node name 不能为空"}
            entity_hash = self._kernel.metadata_store.add_entity(name=name, metadata=kwargs.get("metadata") or {})
            self._kernel._rebuild_graph_from_metadata()
            self._kernel._persist()
            return {"success": True, "node": {"name": name, "hash": entity_hash}}
        if act == "delete_node":
            name = str(kwargs.get("name", "") or kwargs.get("node", "") or kwargs.get("hash_or_name", "") or "").strip()
            if not name:
                return {"success": False, "error": "node name 不能为空"}
            result = await self._kernel._execute_delete_action(
                mode="entity",
                selector={"query": name},
                requested_by=str(kwargs.get("requested_by", "") or "memory_graph_admin"),
                reason=str(kwargs.get("reason", "") or "graph_delete_node"),
            )
            return {
                **result,
                "deleted": bool(result.get("deleted_entity_count", 0) or result.get("deleted_count", 0)),
                "node": name,
            }
        if act == "rename_node":
            old_name = str(kwargs.get("old_name", "") or kwargs.get("from", "") or "").strip()
            new_name = str(kwargs.get("new_name", "") or kwargs.get("to", "") or "").strip()
            if not old_name or not new_name:
                return {"success": False, "error": "old_name 和 new_name 不能为空"}
            result = self._kernel.metadata_store.rename_entity(old_name, new_name)
            if result:
                self._kernel._rebuild_graph_from_metadata()
                self._kernel._persist()
            return {"success": result}
        if act == "create_edge":
            source = str(kwargs.get("source", "") or kwargs.get("from", "") or "").strip()
            target = str(kwargs.get("target", "") or kwargs.get("to", "") or kwargs.get("object", "") or "").strip()
            predicate = str(kwargs.get("predicate", "") or kwargs.get("relation", "") or "").strip()
            if not source or not target or not predicate:
                return {"success": False, "error": "source, target, predicate 不能为空"}
            strength = float(kwargs.get("strength", 1.0) or 1.0)
            relation_hash = self._kernel.metadata_store.add_relation(
                subject=source, predicate=predicate, object=target,
                strength=strength, metadata=kwargs.get("metadata") or {},
            )
            self._kernel._rebuild_graph_from_metadata()
            self._kernel._persist()
            return {"success": True, "edge": {"source": source, "target": target, "predicate": predicate, "hash": relation_hash}}
        if act == "delete_edge":
            source = str(kwargs.get("source", "") or "").strip()
            target = str(kwargs.get("target", "") or kwargs.get("object", "") or "").strip()
            predicate = str(kwargs.get("predicate", "") or "").strip()
            if not source or not target or not predicate:
                return {"success": False, "error": "source, target, predicate 不能为空"}
            result = await self._kernel._execute_delete_action(
                mode="relation",
                selector={"query": f"{source} {predicate} {target}"},
                requested_by=str(kwargs.get("requested_by", "") or "memory_graph_admin"),
                reason=str(kwargs.get("reason", "") or "graph_delete_edge"),
            )
            return {
                **result,
                "deleted": bool(result.get("deleted_relation_count", 0) or result.get("deleted_count", 0)),
                "edge": f"{source} {predicate} {target}",
            }
        if act == "update_edge_weight":
            source = str(kwargs.get("source", "") or "").strip()
            target = str(kwargs.get("target", "") or kwargs.get("object", "") or "").strip()
            predicate = str(kwargs.get("predicate", "") or "").strip()
            if not source or not target or not predicate:
                return {"success": False, "error": "source, target, predicate 不能为空"}
            new_strength = float(kwargs.get("strength", 1.0) or 1.0)
            updated = self._kernel.metadata_store.update_relation_strength(
                subject=source, predicate=predicate, object=target, strength=new_strength,
            )
            if updated:
                self._kernel._rebuild_graph_from_metadata()
                self._kernel._persist()
            return {"success": updated}

        return self._unsupported("graph", act)