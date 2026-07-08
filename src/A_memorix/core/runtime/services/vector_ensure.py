from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from src.A_memorix.core.storage import VectorStore
from src.common.logger import get_logger

logger = get_logger("a_memorix.services.vector_ensure")


class VectorEnsureService:
    """向量确保写入 — encode + add 的统一入口。"""

    def __init__(
        self,
        *,
        embedding_manager_getter: Callable[[], Any],
        vector_store_getter: Callable[[], Optional[VectorStore]],
        paragraph_vector_store_getter: Callable[[], Optional[VectorStore]],
        graph_vector_store_getter: Callable[[], Optional[VectorStore]],
        relation_vectors_enabled_getter: Callable[[], bool],
        dual_vector_pools_enabled: Callable[[], bool],
        graph_vector_id: Callable[[str, str], str],
        relation_write_service_getter: Callable[[], Any],
        vector_pool_manager: Any,
    ) -> None:
        self._get_embedding_manager = embedding_manager_getter
        self._get_vector_store = vector_store_getter
        self._get_paragraph_vector_store = paragraph_vector_store_getter
        self._get_graph_vector_store = graph_vector_store_getter
        self._get_relation_vectors_enabled = relation_vectors_enabled_getter
        self._dual_vector_pools_enabled = dual_vector_pools_enabled
        self._graph_vector_id = graph_vector_id
        self._get_relation_write_service = relation_write_service_getter
        self._vpm = vector_pool_manager

    async def ensure_vector_for_text(
        self,
        *,
        item_hash: str,
        text: str,
        vector_store: Optional[VectorStore] = None,
    ) -> bool:
        target_store = vector_store or self._get_vector_store()
        embedding_manager = self._get_embedding_manager()
        if target_store is None or embedding_manager is None:
            return False
        token = str(item_hash or "").strip()
        content = str(text or "").strip()
        if not token or not content:
            return False
        embedding = await embedding_manager.encode([content])
        if getattr(embedding, "ndim", 1) == 1:
            embedding = embedding.reshape(1, -1)
        if getattr(embedding, "size", 0) <= 0:
            return False
        try:
            target_store.add(embedding, [token])
            return True
        except Exception as exc:
            logger.warning(f"重建向量失败: {exc}")
            return False

    async def ensure_relation_vector(self, relation: Dict[str, Any]) -> bool:
        if not bool(self._get_relation_vectors_enabled()):
            return False
        relation_service = self._get_relation_write_service()
        if relation_service is not None:
            result = await relation_service.ensure_relation_vector(
                hash_value=str(relation.get("hash", "") or ""),
                subject=str(relation.get("subject", "") or "").strip(),
                predicate=str(relation.get("predicate", "") or "").strip(),
                obj=str(relation.get("object", "") or "").strip(),
                typed_id=self._dual_vector_pools_enabled(),
            )
            return bool(result.vector_written or result.vector_already_exists)
        from src.A_memorix.core.utils.relation_write_service import RelationWriteService
        return await self.ensure_vector_for_text(
            item_hash=str(relation.get("hash", "") or ""),
            text=RelationWriteService.build_relation_vector_text(
                str(relation.get("subject", "") or "").strip(),
                str(relation.get("predicate", "") or "").strip(),
                str(relation.get("object", "") or "").strip(),
            ),
        )

    async def ensure_paragraph_vector(self, paragraph: Dict[str, Any]) -> bool:
        return await self.ensure_vector_for_text(
            item_hash=str(paragraph.get("hash", "") or ""),
            text=str(paragraph.get("content", "") or ""),
            vector_store=self._vpm.paragraph_store(),
        )

    async def ensure_entity_vector(self, entity: Dict[str, Any]) -> bool:
        if self._dual_vector_pools_enabled():
            return await self.ensure_vector_for_text(
                item_hash=self._graph_vector_id("entity", str(entity.get("hash", "") or "")),
                text=str(entity.get("name", "") or ""),
                vector_store=self._get_graph_vector_store(),
            )
        return await self.ensure_vector_for_text(
            item_hash=str(entity.get("hash", "") or ""),
            text=str(entity.get("name", "") or ""),
        )