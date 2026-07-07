from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.import_handler")


class ImportAdminHandler(BaseAdminHandler):
    """导入任务 Admin Handler — 从 memory_import_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        manager = self._kernel.import_task_manager
        if manager is None:
            return {"success": False, "error": "import manager 未初始化"}

        act = self._str_action(action)
        if act in {"settings", "get_settings", "get_guide"}:
            return {"success": True, "settings": await manager.get_runtime_settings()}
        if act in {"path_aliases", "get_path_aliases"}:
            return {"success": True, "path_aliases": manager.get_path_aliases()}
        if act in {"resolve_path", "resolve"}:
            return await manager.resolve_path_request(kwargs)
        if act == "create_upload":
            task = await manager.create_upload_task(
                list(kwargs.get("staged_files") or kwargs.get("files") or kwargs.get("uploads") or []),
                kwargs,
            )
            return {"success": True, "task": task}
        if act == "create_paste":
            return {"success": True, "task": await manager.create_paste_task(kwargs)}
        if act == "create_raw_scan":
            return {"success": True, "task": await manager.create_raw_scan_task(kwargs)}
        if act == "create_lpmm_openie":
            return {"success": True, "task": await manager.create_lpmm_openie_task(kwargs)}
        if act == "create_lpmm_convert":
            return {"success": True, "task": await manager.create_lpmm_convert_task(kwargs)}
        if act == "create_temporal_backfill":
            return {"success": True, "task": await manager.create_temporal_backfill_task(kwargs)}
        if act == "create_maibot_migration":
            return {"success": True, "task": await manager.create_maibot_migration_task(kwargs)}
        if act == "list":
            items = await manager.list_tasks(limit=max(1, int(kwargs.get("limit", 50) or 50)))
            return {"success": True, "items": items, "count": len(items)}
        if act == "get":
            task = await manager.get_task(
                str(kwargs.get("task_id", "") or ""),
                include_chunks=bool(kwargs.get("include_chunks", False)),
            )
            return {"success": task is not None, "task": task, "error": "" if task is not None else "任务不存在"}
        if act in {"chunks", "get_chunks"}:
            payload = await manager.get_chunks(
                str(kwargs.get("task_id", "") or ""),
                str(kwargs.get("file_id", "") or ""),
                offset=max(0, int(kwargs.get("offset", 0) or 0)),
                limit=max(1, int(kwargs.get("limit", 50) or 50)),
            )
            return {"success": payload is not None, **(payload or {}), "error": "" if payload is not None else "任务或文件不存在"}
        if act == "cancel":
            task = await manager.cancel_task(str(kwargs.get("task_id", "") or ""))
            return {"success": task is not None, "task": task, "error": "" if task is not None else "任务不存在"}
        if act == "retry_failed":
            overrides = kwargs.get("overrides") if isinstance(kwargs.get("overrides"), dict) else kwargs
            task = await manager.retry_failed(str(kwargs.get("task_id", "") or ""), overrides=overrides)
            return {"success": task is not None, "task": task, "error": "" if task is not None else "任务不存在"}

        return self._unsupported("import", act)