from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.tuning")


class TuningAdminHandler(BaseAdminHandler):
    """调优管理 Admin Handler — 从 memory_tuning_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        manager = self._kernel.retrieval_tuning_manager
        if manager is None:
            return {"success": False, "error": "tuning manager 未初始化"}

        act = self._str_action(action)
        if act in {"settings", "get_settings"}:
            return {"success": True, "settings": manager.get_runtime_settings()}
        if act == "get_profile":
            profile = manager.get_profile_snapshot()
            persistable_profile = manager.get_persistable_profile(profile)
            return {
                "success": True,
                "profile": profile,
                "runtime_profile": profile,
                "persistable_profile": persistable_profile,
                "toml": manager.export_toml_snippet(persistable_profile),
            }
        if act == "apply_profile":
            profile_raw = kwargs.get("profile")
            if isinstance(profile_raw, dict):
                profile_payload: Dict[str, Any] = dict(profile_raw)
            else:
                profile_payload = {
                    key: value
                    for key, value in kwargs.items()
                    if key not in {"reason", "profile"}
                }
            return {
                "success": True,
                **await manager.apply_profile(
                    profile_payload,
                    reason=str(kwargs.get("reason", "manual") or "manual"),
                    validate=bool(kwargs.get("validate", True)),
                ),
            }
        if act == "rollback_profile":
            return {"success": True, **await manager.rollback_profile()}
        if act == "export_profile":
            profile = manager.get_profile_snapshot()
            persistable_profile = manager.get_persistable_profile(profile)
            return {
                "success": True,
                "profile": profile,
                "runtime_profile": profile,
                "persistable_profile": persistable_profile,
                "toml": manager.export_toml_snippet(persistable_profile),
            }
        if act == "create_task":
            payload = kwargs.get("payload") if isinstance(kwargs.get("payload"), dict) else kwargs
            return {"success": True, "task": await manager.create_task(payload)}
        if act == "list_tasks":
            items = await manager.list_tasks(limit=max(1, int(kwargs.get("limit", 50) or 50)))
            return {"success": True, "items": items, "count": len(items)}
        if act == "get_task":
            task = await manager.get_task(
                str(kwargs.get("task_id", "") or ""),
                include_rounds=bool(kwargs.get("include_rounds", False)),
            )
            return {"success": task is not None, "task": task, "error": "" if task is not None else "任务不存在"}
        if act == "get_rounds":
            payload = await manager.get_rounds(
                str(kwargs.get("task_id", "") or ""),
                offset=max(0, int(kwargs.get("offset", 0) or 0)),
                limit=max(1, int(kwargs.get("limit", 50) or 50)),
            )
            return {"success": payload is not None, **(payload or {}), "error": "" if payload is not None else "任务不存在"}
        if act == "cancel":
            task = await manager.cancel_task(str(kwargs.get("task_id", "") or ""))
            return {"success": task is not None, "task": task, "error": "" if task is not None else "任务不存在"}
        if act == "apply_best":
            return {
                "success": True,
                **await manager.apply_best(
                    str(kwargs.get("task_id", "") or ""),
                    validate=bool(kwargs.get("validate", True)),
                ),
            }
        if act == "get_report":
            report = await manager.get_report(str(kwargs.get("task_id", "") or ""), fmt=str(kwargs.get("format", "md") or "md"))
            return {"success": report is not None, "report": report, "error": "" if report is not None else "任务不存在"}

        return self._unsupported("tuning", act)