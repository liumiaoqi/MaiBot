from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.relation")


class RelationAdminHandler(BaseAdminHandler):
    """关系管理 Admin Handler — 从 memory_graph_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        assert self._kernel.metadata_store is not None

        act = self._str_action(action)
        if act == "status":
            target = str(kwargs.get("target", "") or kwargs.get("query", "") or "").strip()
            hashes = self._kernel._resolve_relation_hashes(target)
            if not hashes:
                return {"success": False, "error": "未命中关系"}
            result = self._kernel._apply_v5_relation_action(
                action="status",
                hashes=hashes,
                strength=float(kwargs.get("strength", 1.0) or 1.0),
            )
            return {"success": bool(result.get("success", False)), **result}
        if act == "process_pending":
            limit = max(1, int(kwargs.get("limit", 50) or 50))
            result = self._kernel.metadata_store.process_pending_relations(limit=limit)
            self._kernel._persist()
            return {"success": True, "processed": result}
        if act == "query":
            query = str(kwargs.get("query", "") or "").strip()
            limit = max(1, int(kwargs.get("limit", 50) or 50))
            items = self._kernel.metadata_store.query_relations(query, limit=limit)
            return {"success": True, "items": items, "count": len(items)}
        if act == "evidence":
            relation_hash = str(kwargs.get("hash", "") or kwargs.get("id", "") or "").strip()
            if not relation_hash:
                return {"success": False, "error": "hash 不能为空"}
            evidence = self._kernel.metadata_store.get_relation_evidence(relation_hash)
            return {"success": evidence is not None, "evidence": evidence}
        if act == "correct_evidence":
            relation_hash = str(kwargs.get("hash", "") or kwargs.get("id", "") or "").strip()
            correction = str(kwargs.get("correction", "") or "").strip()
            if not relation_hash or not correction:
                return {"success": False, "error": "hash 和 correction 不能为空"}
            result = self._kernel.metadata_store.correct_relation_evidence(relation_hash, correction)
            return {"success": result}

        return self._unsupported("relation", act)