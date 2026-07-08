from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.delete")


class DeleteAdminHandler(BaseAdminHandler):
    """删除操作 Admin Handler — 从 memory_delete_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        act = self._str_action(action)
        mode = str(kwargs.get("mode", "") or "").strip().lower()
        selector = kwargs.get("selector")
        if selector is None:
            selector = {
                key: value
                for key, value in kwargs.items()
                if key
                not in {
                    "action",
                    "mode",
                    "dry_run",
                    "cascade",
                    "operation_id",
                    "reason",
                    "requested_by",
                }
            }
        reason = str(kwargs.get("reason", "") or "").strip()
        requested_by = str(kwargs.get("requested_by", "") or "").strip()

        if act == "preview":
            return await self._kernel._delete_service.preview_delete_action(mode=mode, selector=selector)
        if act == "execute":
            result = await self._kernel._delete_service.execute_delete_action(
                mode=mode,
                selector=selector,
                requested_by=requested_by,
                reason=reason,
            )
            await self._kernel._invalidate_import_manifest_for_sources(result)
            return result
        if act == "restore":
            return await self._kernel._delete_service.restore_delete_action(
                mode=mode,
                selector=selector,
                operation_id=str(kwargs.get("operation_id", "") or "").strip(),
                requested_by=requested_by,
                reason=reason,
            )
        if act == "get_operation":
            operation = self._kernel.metadata_store.get_delete_operation(str(kwargs.get("operation_id", "") or "").strip())
            return {"success": operation is not None, "operation": operation, "error": "" if operation is not None else "operation 不存在"}
        if act == "list_operations":
            items = self._kernel.metadata_store.list_delete_operations(
                limit=max(1, int(kwargs.get("limit", 50) or 50)),
                mode=mode,
            )
            return {"success": True, "items": items, "count": len(items)}
        if act == "purge":
            return await self._kernel._delete_service.purge_deleted_memory(
                grace_hours=self._kernel._optional_float(kwargs.get("grace_hours")),
                limit=max(1, int(kwargs.get("limit", 1000) or 1000)),
            )

        return self._unsupported("delete", act)