from __future__ import annotations

from typing import Any, Dict, TYPE_CHECKING

from src.common.logger import get_logger
from .base import BaseAdminHandler

if TYPE_CHECKING:
    from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.admin.paragraph")


class ParagraphAdminHandler(BaseAdminHandler):
    """段落管理 Admin Handler — 从 memory_graph_admin 提取。"""

    def __init__(self, kernel: SDKMemoryKernel) -> None:
        self._kernel = kernel

    async def handle(self, action: str, **kwargs) -> Dict[str, Any]:
        await self._kernel.initialize()
        assert self._kernel.metadata_store is not None

        act = self._str_action(action)
        if act == "list":
            items = self._kernel.metadata_store.get_paragraphs(
                limit=max(1, int(kwargs.get("limit", 50) or 50)),
                offset=max(0, int(kwargs.get("offset", 0) or 0)),
            )
            return {"success": True, "items": items, "count": len(items)}
        if act == "delete":
            paragraph_hash = str(kwargs.get("hash", "") or kwargs.get("id", "") or "").strip()
            if not paragraph_hash:
                return {"success": False, "error": "hash 不能为空"}
            result = await self._kernel._delete_service.execute_delete_action(
                mode="paragraph",
                selector={"query": paragraph_hash},
                requested_by=str(kwargs.get("requested_by", "") or "paragraph_admin"),
                reason=str(kwargs.get("reason", "") or "paragraph_delete"),
            )
            return result
        if act == "batch_delete":
            hashes = [str(h).strip() for h in (kwargs.get("hashes") or []) if str(h).strip()]
            if not hashes:
                return {"success": False, "error": "hashes 不能为空"}
            result = await self._kernel._delete_service.execute_delete_action(
                mode="paragraph",
                selector={"query": "", "hashes": hashes},
                requested_by=str(kwargs.get("requested_by", "") or "paragraph_admin"),
                reason=str(kwargs.get("reason", "") or "paragraph_batch_delete"),
            )
            return result
        if act == "get":
            paragraph_hash = str(kwargs.get("hash", "") or kwargs.get("id", "") or "").strip()
            if not paragraph_hash:
                return {"success": False, "error": "hash 不能为空"}
            paragraphs = self._kernel.metadata_store.get_paragraphs_by_hashes([paragraph_hash])
            paragraph = paragraphs.get(paragraph_hash)
            return {"success": paragraph is not None, "paragraph": paragraph, "error": "" if paragraph is not None else "段落不存在"}

        return self._unsupported("paragraph", act)