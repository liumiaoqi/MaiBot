from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.correction")


class CorrectionAdminHandler(BaseAdminHandler):
    """记忆修正 Admin Handler — 从 memory_correction_admin / memory_fuzzy_modify_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        assert self._kernel.metadata_store is not None

        act = self._str_action(action)
        if act in {"preview", "plan"}:
            return await self._kernel._preview_fuzzy_modify_action(
                request_text=str(kwargs.get("request_text", "") or kwargs.get("text", "") or "").strip(),
                scope=str(kwargs.get("scope", "") or "person_profile").strip(),
                person_id=str(kwargs.get("person_id", "") or "").strip(),
                person_keyword=str(kwargs.get("person_keyword", "") or kwargs.get("keyword", "") or "").strip(),
                chat_id=str(kwargs.get("chat_id", "") or "").strip(),
                limit=max(1, int(kwargs.get("limit", self._kernel._fuzzy_modify_cfg_candidate_limit()) or self._kernel._fuzzy_modify_cfg_candidate_limit())),
                requested_by=str(kwargs.get("requested_by", "") or "webui").strip(),
                reason=str(kwargs.get("reason", "") or "").strip(),
            )
        if act == "execute":
            return await self._kernel._execute_fuzzy_modify_action(
                plan_id=str(kwargs.get("plan_id", "") or "").strip(),
                confirmed=bool(kwargs.get("confirmed", False)),
                requested_by=str(kwargs.get("requested_by", "") or "webui").strip(),
                reason=str(kwargs.get("reason", "") or "").strip(),
            )
        if act == "get":
            plan = self._kernel.metadata_store.get_fuzzy_modify_plan(str(kwargs.get("plan_id", "") or "").strip())
            return {"success": plan is not None, "plan": plan, "error": "" if plan is not None else "修改计划不存在"}
        if act == "list":
            raw_statuses = kwargs.get("statuses")
            if raw_statuses is None:
                raw_statuses = kwargs.get("status")
            statuses = self._kernel._tokens([raw_statuses] if isinstance(raw_statuses, str) else raw_statuses)
            items = self._kernel.metadata_store.list_fuzzy_modify_plans(
                limit=max(1, int(kwargs.get("limit", 50) or 50)),
                statuses=statuses,
                scope=str(kwargs.get("scope", "") or "").strip(),
            )
            return {"success": True, "items": items, "count": len(items)}
        if act == "rollback":
            return await self._kernel._rollback_fuzzy_modify_action(
                plan_id=str(kwargs.get("plan_id", "") or "").strip(),
                requested_by=str(kwargs.get("requested_by", "") or "webui").strip(),
                reason=str(kwargs.get("reason", "") or "").strip(),
            )

        return self._unsupported("correction", act)