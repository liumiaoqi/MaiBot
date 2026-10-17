from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.v5")


class V5AdminHandler(BaseAdminHandler):
    """V5 关系维护 Admin Handler — 从 memory_v5_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        assert self._kernel.metadata_store

        act = self._str_action(action)
        target = str(kwargs.get("target", "") or kwargs.get("query", "") or "").strip()
        reason = str(kwargs.get("reason", "")).strip()
        updated_by = str(kwargs.get("updated_by", "") or kwargs.get("requested_by", "") or "").strip()
        limit = max(1, int(kwargs.get("limit", 50) or 50))

        if act == "relation_feedback":
            # 0004 真值回路：**唯一把「人的判断」写进系统的入口**（该入口不做任何自动推断，
            # 故只有人按按钮这一种驱动形态；模型侧将来若要参与，应做「agent 建议 + 人确认」）。
            # ⚠️ 载荷键名是 `decision`（raise / lower / neutral）——**不能叫 `action`**：
            # 那个键在本层已被占为「路由键」（见上方 `act = self._str_action(action)`），
            # 同一个键在两个层上各指一物会让下一个人误读。
            decision = str(kwargs.get("decision", "")).strip()
            if not decision:
                # 空 decision 必须**具名出声**：不许把"没传"静默当成 neutral（降级可以、静默不行）。
                return {
                    "success": False,
                    "error": "缺少 decision（人的判断）：需显式传 raise / lower / neutral",
                }
            result = self._kernel._v5_memory_service.record_relation_feedback(
                relation_hash=target,
                action=decision,
                actor=updated_by,
                source_note=reason,
            )
            # 留痕：照下方 restore 分支的既有形态。
            # ⚠️ `record_v5_operation` 的 `resolved_hashes` 是**必填**（`metadata_store.py:1310-1311`，无默认）
            # ⇒ 这里传 `[target]`（本动作只涉及一个 relation_hash）。
            operation = self._kernel.metadata_store.record_v5_operation(
                action=act,
                target=target,
                resolved_hashes=[target],
                reason=reason,
                updated_by=updated_by,
                result=result,
            )
            return {"success": bool(result.get("success", False)), "operation": operation, **result}

        if act == "recycle_bin":
            items = self._kernel.metadata_store.get_deleted_relations(limit=limit)
            return {"success": True, "items": items, "count": len(items)}

        if act == "status":
            return self._kernel._v5_memory_service.memory_v5_status(target=target, limit=limit)

        if act == "restore":
            hashes = self._kernel._resolve_deleted_relation_hashes(target)
            if not hashes:
                return {"success": False, "error": "未命中可恢复关系"}
            result = await self._kernel._restore_relation_hashes(hashes)
            operation = self._kernel.metadata_store.record_v5_operation(
                action=act,
                target=target,
                resolved_hashes=hashes,
                reason=reason,
                updated_by=updated_by,
                result=result,
            )
            return {"success": bool(result.get("restored_count", 0) > 0), "operation": operation, **result}

        hashes = self._kernel._resolve_relation_hashes(target)
        if not hashes:
            return {"success": False, "error": "未命中可维护关系"}

        result = self._kernel._v5_memory_service.apply_v5_relation_action(
            action=act,
            hashes=hashes,
            strength=float(kwargs.get("strength", 1.0) or 1.0),
        )
        operation = self._kernel.metadata_store.record_v5_operation(
            action=act,
            target=target,
            resolved_hashes=hashes,
            reason=reason,
            updated_by=updated_by,
            result=result,
        )
        return {"success": bool(result.get("success", False)), "operation": operation, **result}
