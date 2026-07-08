from __future__ import annotations

import time
from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.runtime")


class RuntimeAdminHandler(BaseAdminHandler):

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        act = self._str_action(action)

        if act == "save":
            self._kernel._persist()
            return {"success": True, "saved": True, "data_dir": str(self._kernel.data_dir)}

        if act == "get_config":
            degraded = self._kernel._embedding_health_service.snapshot()
            backfill_counts = self._kernel._paragraph_vector_backfill_counts()
            rebuild_status = self._kernel._vector_rebuild_status()
            vector_pools_status = self._kernel._vector_pools_status()
            return {
                "success": True,
                "config": self._kernel.config,
                "data_dir": str(self._kernel.data_dir),
                "embedding_dimension": int(rebuild_status["embedding_dimension"]),
                "stored_vector_dimension": int(rebuild_status["stored_vector_dimension"]),
                "vector_rebuild_required": bool(rebuild_status["vector_rebuild_required"]),
                "vector_rebuild_message": str(rebuild_status["message"]),
                "embedding_fingerprint": rebuild_status.get("embedding_fingerprint") or {},
                "stored_embedding_fingerprint": rebuild_status.get("stored_embedding_fingerprint") or {},
                "embedding_fingerprint_status": str(rebuild_status.get("embedding_fingerprint_status") or "unknown"),
                "auto_save": bool(self._kernel._cfg("advanced.enable_auto_save", True)),
                "relation_vectors_enabled": bool(self._kernel.relation_vectors_enabled),
                "vector_pools": vector_pools_status,
                "vector_pools_ready": bool(vector_pools_status.get("ready", False)),
                "vector_pools_effective_mode": str(vector_pools_status.get("effective_mode", "single")),
                "runtime_ready": self._kernel.is_runtime_ready(),
                "embedding_degraded": bool(degraded.get("active", False)),
                "embedding_degraded_reason": str(degraded.get("reason", "") or ""),
                "embedding_degraded_since": degraded.get("since"),
                "embedding_last_check": degraded.get("last_check"),
                "paragraph_vector_backfill_pending": int(backfill_counts.get("pending", 0) or 0),
                "paragraph_vector_backfill_running": int(backfill_counts.get("running", 0) or 0),
                "paragraph_vector_backfill_failed": int(backfill_counts.get("failed", 0) or 0),
                "paragraph_vector_backfill_done": int(backfill_counts.get("done", 0) or 0),
            }

        if act == "status":
            return self._kernel._vector_pools_status()

        if act in {"self_check", "refresh_self_check"}:
            report = await self._kernel._embedding_health_service.refresh_self_check(
                sample_text=str(kwargs.get("sample_text", "") or "A_Memorix runtime self check")
            )
            checked_at = float(report.get("checked_at") or time.time())
            dimension_mismatch = self._kernel._apply_self_check_dimension_result(report)
            if dimension_mismatch:
                self._kernel._embedding_health_service.set_degraded(active=True, reason=dimension_mismatch, checked_at=checked_at)
            elif bool(report.get("ok", False)):
                self._kernel._embedding_health_service.set_degraded(active=False, checked_at=checked_at)
            elif self._kernel._embedding_health_service.config.embedding_fallback_enabled:
                self._kernel._embedding_health_service.set_degraded(
                    active=True,
                    reason=str(report.get("message", "runtime self-check failed") or "runtime self-check failed"),
                    checked_at=checked_at,
                )
            return {"success": bool(report.get("ok", False)), "report": report}

        if act == "set_auto_save":
            enabled = bool(kwargs.get("enabled", False))
            self._kernel._set_cfg("advanced.enable_auto_save", enabled)
            return {"success": True, "auto_save": enabled}

        if act == "recover_embedding":
            result = await self._kernel._recover_embedding_once(
                sample_text=str(kwargs.get("sample_text", "") or "A_Memorix runtime self check")
            )
            result["embedding_degraded"] = self._kernel._embedding_health_service.is_degraded
            result["embedding_state"] = self._kernel._embedding_health_service.snapshot()
            result["backfill_counts"] = self._kernel._paragraph_vector_backfill_counts()
            return result

        if act in {"rebuild", "rebuild_all_vectors"}:
            include_relations = kwargs.get("include_relations")
            result = await self._kernel._rebuild_all_vectors(
                batch_size=self._kernel._optional_int(kwargs.get("batch_size")),
                include_relations=include_relations if isinstance(include_relations, bool) else None,
                dry_run=bool(kwargs.get("dry_run", False)),
            )
            result["embedding_degraded"] = self._kernel._embedding_health_service.is_degraded
            result["backfill_counts"] = self._kernel._paragraph_vector_backfill_counts()
            return result

        if act == "paragraph_backfill_once":
            result = await self._kernel._run_paragraph_backfill_once(
                limit=self._kernel._optional_int(kwargs.get("limit")),
                max_retry=self._kernel._optional_int(kwargs.get("max_retry")),
                trigger="manual",
            )
            result["embedding_degraded"] = self._kernel._embedding_health_service.is_degraded
            result["backfill_counts"] = self._kernel._paragraph_vector_backfill_counts()
            return result

        if act == "process_pending":
            result = self._kernel.metadata_store.process_pending_relations(
                limit=max(1, int(kwargs.get("limit", 50) or 50))
            )
            self._kernel._persist()
            return {"success": True, "processed": result}

        return self._unsupported("runtime", act)
