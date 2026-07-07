from __future__ import annotations

from typing import Any, Dict

from .base import BaseAdminHandler


class FeedbackAdminHandler(BaseAdminHandler):

    def __init__(self, kernel: Any) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        assert self._kernel.metadata_store is not None

        act = self._str_action(action)
        if act == "list":
            items = self._kernel.metadata_store.list_feedback_tasks(
                limit=max(1, int(kwargs.get("limit", 50) or 50)),
                statuses=self._kernel._tokens(kwargs.get("status") or kwargs.get("statuses")),
                rollback_statuses=self._kernel._tokens(kwargs.get("rollback_status") or kwargs.get("rollback_statuses")),
                query=str(kwargs.get("query", "") or "").strip(),
            )
            return {
                "success": True,
                "items": [self._kernel._build_feedback_task_summary(task) for task in items],
                "count": len(items),
            }

        if act == "get":
            task = self._kernel.metadata_store.get_feedback_task_by_id(int(kwargs.get("task_id", 0) or 0))
            if task is None:
                return {"success": False, "error": "反馈纠错任务不存在"}
            return {"success": True, "task": self._kernel._build_feedback_task_detail(task)}

        if act == "rollback":
            return await self._kernel._rollback_feedback_task(
                task_id=int(kwargs.get("task_id", 0) or 0),
                requested_by=str(kwargs.get("requested_by", "") or "").strip(),
                reason=str(kwargs.get("reason", "") or "").strip(),
            )

        return self._unsupported("feedback", act)