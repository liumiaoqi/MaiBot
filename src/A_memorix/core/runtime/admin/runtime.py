from __future__ import annotations

import time
from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.runtime")


class RuntimeAdminHandler(BaseAdminHandler):
    """运行时管理 Admin Handler — 从 memory_graph_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()

        act = self._str_action(action)
        if act == "status":
            return self._kernel._vector_pools_status()
        if act == "rebuild":
            include_relations = kwargs.get("include_relations")
            result = await self._kernel._rebuild_all_vectors(
                batch_size=self._kernel._optional_int(kwargs.get("batch_size")),
                include_relations=include_relations if isinstance(include_relations, bool) else None,
                dry_run=bool(kwargs.get("dry_run", False)),
            )
            result["embedding_degraded"] = self._kernel._is_embedding_degraded()
            result["backfill_counts"] = self._kernel._paragraph_vector_backfill_counts()
            return result
        if act == "process_pending":
            result = self._kernel.metadata_store.process_pending_relations(
                limit=max(1, int(kwargs.get("limit", 50) or 50))
            )
            self._kernel._persist()
            return {"success": True, "processed": result}
        if act == "set_auto_save":
            enabled = bool(kwargs.get("enabled", False))
            self._kernel._set_cfg("advanced.enable_auto_save", enabled)
            return {"success": True, "auto_save": enabled}
        if act == "recover_embedding":
            result = await self._kernel._recover_embedding_once(
                sample_text=str(kwargs.get("sample_text", "") or "A_Memorix runtime self check")
            )
            result["embedding_degraded"] = self._kernel._is_embedding_degraded()
            result["embedding_state"] = self._kernel._embedding_degraded_snapshot()
            result["backfill_counts"] = self._kernel._paragraph_vector_backfill_counts()
            return result
        if act == "rebuild_all_vectors":
            include_relations = kwargs.get("include_relations")
            result = await self._kernel._rebuild_all_vectors(
                batch_size=self._kernel._optional_int(kwargs.get("batch_size")),
                include_relations=include_relations if isinstance(include_relations, bool) else None,
                dry_run=bool(kwargs.get("dry_run", False)),
            )
            result["embedding_degraded"] = self._kernel._is_embedding_degraded()
            result["backfill_counts"] = self._kernel._paragraph_vector_backfill_counts()
            return result
        if act == "paragraph_backfill_once":
            result = await self._kernel._run_paragraph_backfill_once(
                limit=self._kernel._optional_int(kwargs.get("limit")),
                max_retry=self._kernel._optional_int(kwargs.get("max_retry")),
                trigger="manual",
            )
            result["embedding_degraded"] = self._kernel._is_embedding_degraded()
            result["backfill_counts"] = self._kernel._paragraph_vector_backfill_counts()
            return result

        return self._unsupported("runtime", act)