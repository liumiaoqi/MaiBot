from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict, Iterable, List, Optional, Sequence

import time

from ...storage import GraphStore, MetadataStore
from ...utils.hash import compute_hash
from ...utils.metadata import coerce_metadata_dict
from src.common.logger import get_logger

logger = get_logger("A_memorix.delete_service")


class DeleteService:
    """Delete 域服务 — 从 SDKMemoryKernel 提取的删除/恢复/清理逻辑。"""

    def __init__(
        self,
        *,
        metadata_store: MetadataStore,
        graph_store: GraphStore,
        merge_tokens: Callable[..., List[str]],
        tokens: Callable[..., List[str]],
        selector_dict: Callable[[Any], Dict[str, Any]],
        persist: Callable[[], None],
        rebuild_graph_from_metadata: Callable[[], Dict[str, int]],
        delete_vectors_by_type: Callable[..., int],
        cfg: Callable[[str, Any], Any],
        format_relation_text: Callable[[Any, Any, Any], str],
        trim_text: Callable[[str, int], str],
        resolve_relation_hashes: Callable[[str], List[str]],
        resolve_deleted_relation_hashes: Callable[[str], List[str]],
        resolve_source_targets: Callable[[Any], List[str]],
        restore_relation_hashes: Callable[..., Coroutine[Any, Any, Dict[str, Any]]],
        relation_has_remaining_paragraphs: Callable[[str, Sequence[str]], bool],
        ensure_entity_vector: Callable[[Dict[str, Any]], Coroutine[Any, Any, bool]],
        ensure_paragraph_vector: Callable[[Dict[str, Any]], Coroutine[Any, Any, bool]],
        ensure_relation_vector: Callable[[Dict[str, Any]], Coroutine[Any, Any, bool]],
        optional_float: Callable[[Any], Optional[float]],
    ) -> None:
        self.metadata_store = metadata_store
        self.graph_store = graph_store
        self._merge_tokens = merge_tokens
        self._tokens = tokens
        self._selector_dict = selector_dict
        self._persist = persist
        self._rebuild_graph_from_metadata = rebuild_graph_from_metadata
        self._delete_vectors_by_type = delete_vectors_by_type
        self._cfg = cfg
        self._format_relation_text = format_relation_text
        self._trim_text = trim_text
        self._resolve_relation_hashes = resolve_relation_hashes
        self._resolve_deleted_relation_hashes = resolve_deleted_relation_hashes
        self._resolve_source_targets = resolve_source_targets
        self._restore_relation_hashes = restore_relation_hashes
        self._relation_has_remaining_paragraphs = relation_has_remaining_paragraphs
        self._ensure_entity_vector = ensure_entity_vector
        self._ensure_paragraph_vector = ensure_paragraph_vector
        self._ensure_relation_vector = ensure_relation_vector
        self._optional_float = optional_float

    # ── 快照方法（从 Kernel 一起迁移） ──────────────────────────

    def snapshot_relation_item(self, hash_value: str) -> Optional[Dict[str, Any]]:
        assert self.metadata_store
        relation = self.metadata_store.get_relation(hash_value)
        if relation is None:
            relation = self.metadata_store.get_deleted_relation(hash_value)
        if relation is None:
            return None
        paragraph_hashes = [
            str(row.get("paragraph_hash", "") or "").strip()
            for row in self.metadata_store.query(
                "SELECT paragraph_hash FROM paragraph_relations WHERE relation_hash = ? ORDER BY paragraph_hash ASC",
                (hash_value,),
            )
            if str(row.get("paragraph_hash", "") or "").strip()
        ]
        return {
            "item_type": "relation",
            "item_hash": hash_value,
            "item_key": hash_value,
            "payload": {
                "relation": relation,
                "paragraph_hashes": paragraph_hashes,
            },
        }

    def snapshot_paragraph_item(self, hash_value: str) -> Optional[Dict[str, Any]]:
        assert self.metadata_store
        paragraph = self.metadata_store.get_paragraph(hash_value)
        if paragraph is None:
            return None
        entity_links = [
            {
                "paragraph_hash": hash_value,
                "entity_hash": str(row.get("entity_hash", "") or ""),
                "mention_count": int(row.get("mention_count", 1) or 1),
            }
            for row in self.metadata_store.query(
                """
                SELECT paragraph_hash, entity_hash, mention_count
                FROM paragraph_entities
                WHERE paragraph_hash = ?
                ORDER BY entity_hash ASC
                """,
                (hash_value,),
            )
        ]
        relation_hashes = [
            str(row.get("relation_hash", "") or "").strip()
            for row in self.metadata_store.query(
                """
                SELECT relation_hash
                FROM paragraph_relations
                WHERE paragraph_hash = ?
                ORDER BY relation_hash ASC
                """,
                (hash_value,),
            )
            if str(row.get("relation_hash", "") or "").strip()
        ]
        return {
            "item_type": "paragraph",
            "item_hash": hash_value,
            "item_key": hash_value,
            "payload": {
                "paragraph": paragraph,
                "entity_links": entity_links,
                "relation_hashes": relation_hashes,
                "external_refs": self.metadata_store.list_external_memory_refs_by_paragraphs([hash_value]),
            },
        }

    def snapshot_entity_item(self, hash_value: str) -> Optional[Dict[str, Any]]:
        assert self.metadata_store
        entity = self.metadata_store.get_entity(hash_value)
        if entity is None:
            return None
        paragraph_links = [
            {
                "paragraph_hash": str(row.get("paragraph_hash", "") or ""),
                "entity_hash": hash_value,
                "mention_count": int(row.get("mention_count", 1) or 1),
            }
            for row in self.metadata_store.query(
                """
                SELECT paragraph_hash, mention_count
                FROM paragraph_entities
                WHERE entity_hash = ?
                ORDER BY paragraph_hash ASC
                """,
                (hash_value,),
            )
        ]
        return {
            "item_type": "entity",
            "item_hash": hash_value,
            "item_key": hash_value,
            "payload": {
                "entity": entity,
                "paragraph_links": paragraph_links,
            },
        }

    # ── 目标解析 ──────────────────────────────────────────────

    def resolve_paragraph_targets(self, selector: Any, *, include_deleted: bool = False) -> List[Dict[str, Any]]:
        assert self.metadata_store
        raw = self._selector_dict(selector)
        rows: List[Dict[str, Any]] = []
        hashes = self._merge_tokens(raw.get("hashes"), raw.get("items"), [raw.get("hash")])
        for hash_value in hashes:
            row = self.metadata_store.get_paragraph(hash_value)
            if row is None:
                continue
            if not include_deleted and bool(row.get("is_deleted", 0)):
                continue
            rows.append(row)
        if rows:
            return rows
        query = str(raw.get("query", "") or raw.get("content", "") or "").strip()
        if not query:
            return []
        if len(query) == 64 and all(ch in "0123456789abcdef" for ch in query.lower()):
            row = self.metadata_store.get_paragraph(query)
            if row is None:
                return []
            if not include_deleted and bool(row.get("is_deleted", 0)):
                return []
            return [row]
        matches = self.metadata_store.search_paragraphs_by_content(query)
        return [row for row in matches if include_deleted or not bool(row.get("is_deleted", 0))]

    def resolve_entity_targets(self, selector: Any, *, include_deleted: bool = False) -> List[Dict[str, Any]]:
        assert self.metadata_store
        raw = self._selector_dict(selector)
        rows: List[Dict[str, Any]] = []
        hashes = self._merge_tokens(raw.get("hashes"), raw.get("items"), [raw.get("hash")])
        for hash_value in hashes:
            row = self.metadata_store.get_entity(hash_value)
            if row is None:
                continue
            if not include_deleted and bool(row.get("is_deleted", 0)):
                continue
            rows.append(row)
        names = self._merge_tokens(raw.get("names"), [raw.get("name")], [raw.get("query")])
        for name in names:
            if not name:
                continue
            matches = self.metadata_store.query(
                """
                SELECT *
                FROM entities
                WHERE LOWER(TRIM(name)) = LOWER(TRIM(?))
                   OR hash = ?
                ORDER BY appearance_count DESC, created_at ASC
                """,
                (name, compute_hash(str(name).strip().lower())),
            )
            for row in matches:
                if not include_deleted and bool(row.get("is_deleted", 0)):
                    continue
                rows.append(self.metadata_store._row_to_dict(row, "entity") if hasattr(self.metadata_store, "_row_to_dict") else row)
        dedup: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            token = str(row.get("hash", "") or "").strip()
            if token and token not in dedup:
                dedup[token] = row
        return list(dedup.values())

    # ── 构建预览/结果 ────────────────────────────────────────

    def build_delete_preview_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        item_type = str(item.get("item_type", "") or "").strip()
        item_hash = str(item.get("item_hash", "") or "").strip()
        item_key = str(item.get("item_key", "") or item_hash).strip()
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        preview = {
            "item_type": item_type,
            "item_hash": item_hash,
            "item_key": item_key,
        }
        if item_type == "entity":
            entity = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
            name = str(entity.get("name", "") or item_key).strip()
            preview["label"] = name
            preview["preview"] = name
        elif item_type == "relation":
            relation = payload.get("relation") if isinstance(payload.get("relation"), dict) else {}
            subject = str(relation.get("subject", "") or "").strip()
            predicate = str(relation.get("predicate", "") or "").strip()
            obj = str(relation.get("object", "") or "").strip()
            text = self._format_relation_text(subject, predicate, obj)
            preview["label"] = text or item_key
            preview["preview"] = text or item_key
        elif item_type == "paragraph":
            paragraph = payload.get("paragraph") if isinstance(payload.get("paragraph"), dict) else {}
            content = str(paragraph.get("content", "") or "").strip()
            source = str(paragraph.get("source", "") or "").strip()
            preview["label"] = source or item_key
            preview["preview"] = self._trim_text(content)
            preview["source"] = source
        return preview

    def build_standard_delete_result(
        self,
        *,
        mode: str,
        operation_id: str = "",
        counts: Optional[Dict[str, Any]] = None,
        sources: Optional[Sequence[str]] = None,
        deleted_entity_count: int = 0,
        deleted_relation_count: int = 0,
        deleted_paragraph_count: int = 0,
        deleted_source_count: int = 0,
        deleted_vector_count: int = 0,
        requested_source_count: int = 0,
        matched_source_count: int = 0,
        error: str = "",
    ) -> Dict[str, Any]:
        normalized_counts = dict(counts or {})
        normalized_counts.setdefault("entities", int(normalized_counts.get("entities", 0) or 0))
        normalized_counts.setdefault("relations", int(normalized_counts.get("relations", 0) or 0))
        normalized_counts.setdefault("paragraphs", int(normalized_counts.get("paragraphs", 0) or 0))
        normalized_counts.setdefault("sources", int(normalized_counts.get("sources", 0) or 0))
        if requested_source_count:
            normalized_counts["requested_sources"] = int(requested_source_count or 0)
        if matched_source_count:
            normalized_counts["matched_sources"] = int(matched_source_count or 0)

        deleted_count = (
            int(deleted_entity_count or 0)
            + int(deleted_relation_count or 0)
            + int(deleted_paragraph_count or 0)
            + int(deleted_source_count or 0)
        )
        return {
            "success": bool(not error and deleted_count > 0),
            "mode": str(mode or "").strip().lower(),
            "operation_id": str(operation_id or "").strip(),
            "counts": normalized_counts,
            "sources": [str(item or "").strip() for item in (sources or []) if str(item or "").strip()],
            "deleted_count": deleted_count,
            "deleted_entity_count": int(deleted_entity_count or 0),
            "deleted_relation_count": int(deleted_relation_count or 0),
            "deleted_paragraph_count": int(deleted_paragraph_count or 0),
            "deleted_source_count": int(deleted_source_count or 0),
            "deleted_vector_count": int(deleted_vector_count or 0),
            "requested_source_count": int(requested_source_count or 0),
            "matched_source_count": int(matched_source_count or 0),
            "error": str(error or ""),
        }

    # ── 删除计划 ──────────────────────────────────────────────

    async def build_delete_plan(self, *, mode: str, selector: Any) -> Dict[str, Any]:
        assert self.metadata_store
        act_mode = str(mode or "").strip().lower()
        normalized_selector = self._selector_dict(selector)
        items: List[Dict[str, Any]] = []
        counts = {"relations": 0, "paragraphs": 0, "entities": 0, "sources": 0}
        vector_ids: List[str] = []
        sources: List[str] = []
        target_hashes: Dict[str, List[str]] = {
            "relations": [],
            "paragraphs": [],
            "entities": [],
            "sources": [],
            "matched_sources": [],
        }
        seen_items: set[tuple[str, str]] = set()
        relation_hashes: List[str] = []
        paragraph_hashes: List[str] = []
        entity_hashes: List[str] = []
        paragraph_relation_candidates: List[str] = []

        def append_item(snapshot: Optional[Dict[str, Any]]) -> None:
            if not isinstance(snapshot, dict):
                return
            item_type = str(snapshot.get("item_type", "") or "").strip()
            item_hash = str(snapshot.get("item_hash", "") or snapshot.get("item_key", "") or "").strip()
            if not item_type or not item_hash:
                return
            key = (item_type, item_hash)
            if key in seen_items:
                return
            seen_items.add(key)
            items.append(snapshot)

        def append_relation_hash(hash_value: str) -> None:
            token = str(hash_value or "").strip()
            if not token or token in relation_hashes:
                return
            row = self.metadata_store.get_relation(token)
            if row is None:
                return
            relation_hashes.append(token)
            append_item(self.snapshot_relation_item(token))
            vector_ids.append(token)

        def append_paragraph_row(row: Optional[Dict[str, Any]]) -> None:
            if not isinstance(row, dict):
                return
            paragraph_hash = str(row.get("hash", "") or "").strip()
            if not paragraph_hash or paragraph_hash in paragraph_hashes or bool(row.get("is_deleted", 0)):
                return
            paragraph_hashes.append(paragraph_hash)
            snapshot = self.snapshot_paragraph_item(paragraph_hash)
            append_item(snapshot)
            vector_ids.append(paragraph_hash)
            paragraph = (snapshot or {}).get("payload", {}).get("paragraph") if isinstance((snapshot or {}).get("payload"), dict) else {}
            source = str((paragraph or {}).get("source", "") or "").strip()
            if source:
                sources.append(source)
            paragraph_relation_candidates.extend(self._tokens(((snapshot or {}).get("payload") or {}).get("relation_hashes")))

        def append_entity_row(row: Optional[Dict[str, Any]]) -> None:
            if not isinstance(row, dict):
                return
            entity_hash = str(row.get("hash", "") or "").strip()
            if not entity_hash or entity_hash in entity_hashes or bool(row.get("is_deleted", 0)):
                return
            entity_hashes.append(entity_hash)
            append_item(self.snapshot_entity_item(entity_hash))
            vector_ids.append(entity_hash)

        if act_mode == "relation":
            direct_hashes = self._merge_tokens(
                normalized_selector.get("hashes"),
                normalized_selector.get("items"),
                [normalized_selector.get("hash")],
            )
            query_hashes = self._resolve_relation_hashes(str(normalized_selector.get("query", "") or ""))
            for hash_value in direct_hashes or query_hashes:
                append_relation_hash(hash_value)
            counts["relations"] = len(relation_hashes)
            target_hashes["relations"] = list(relation_hashes)

        elif act_mode in {"paragraph", "source"}:
            paragraph_rows: List[Dict[str, Any]] = []
            if act_mode == "source":
                source_tokens = self._resolve_source_targets(normalized_selector)
                target_hashes["sources"] = source_tokens
                counts["requested_sources"] = len(source_tokens)
                matched_source_tokens: List[str] = []
                for source in source_tokens:
                    source_rows = self.metadata_store.query(
                        """
                        SELECT *
                        FROM paragraphs
                        WHERE source = ?
                          AND (is_deleted IS NULL OR is_deleted = 0)
                        ORDER BY created_at ASC
                        """,
                        (source,),
                    )
                    if source_rows:
                        matched_source_tokens.append(source)
                        sources.append(source)
                        paragraph_rows.extend(source_rows)
                target_hashes["matched_sources"] = matched_source_tokens
                counts["sources"] = len(matched_source_tokens)
                counts["matched_sources"] = len(matched_source_tokens)
            else:
                paragraph_rows = self.resolve_paragraph_targets(normalized_selector, include_deleted=False)
            for row in paragraph_rows:
                append_paragraph_row(row)
            target_hashes["paragraphs"] = list(paragraph_hashes)
            counts["paragraphs"] = len(paragraph_hashes)

            for relation_hash in self._tokens(paragraph_relation_candidates):
                if not self._relation_has_remaining_paragraphs(relation_hash, paragraph_hashes):
                    append_relation_hash(relation_hash)
            target_hashes["relations"] = list(relation_hashes)
            counts["relations"] = len(relation_hashes)

        elif act_mode == "entity":
            entity_rows = self.resolve_entity_targets(normalized_selector, include_deleted=False)
            for row in entity_rows:
                append_entity_row(row)
            target_hashes["entities"] = list(entity_hashes)
            counts["entities"] = len(entity_hashes)
            entity_names = [str(row.get("name", "") or "").strip() for row in entity_rows if str(row.get("name", "") or "").strip()]
            for entity_name in entity_names:
                for relation in self.metadata_store.get_relations(subject=entity_name) + self.metadata_store.get_relations(object=entity_name):
                    append_relation_hash(str(relation.get("hash", "") or "").strip())
            target_hashes["relations"] = list(relation_hashes)
            counts["relations"] = len(relation_hashes)
        elif act_mode == "mixed":
            source_tokens = self._merge_tokens(normalized_selector.get("sources"), [normalized_selector.get("source")])
            target_hashes["sources"] = list(source_tokens)
            counts["requested_sources"] = len(source_tokens)
            matched_source_tokens: List[str] = []

            for row in self.resolve_entity_targets({"hashes": normalized_selector.get("entity_hashes")}, include_deleted=False):
                append_entity_row(row)
            target_hashes["entities"] = list(entity_hashes)
            counts["entities"] = len(entity_hashes)

            for row in self.resolve_paragraph_targets({"hashes": normalized_selector.get("paragraph_hashes")}, include_deleted=False):
                append_paragraph_row(row)

            for source in source_tokens:
                source_rows = self.metadata_store.query(
                    """
                    SELECT *
                    FROM paragraphs
                    WHERE source = ?
                      AND (is_deleted IS NULL OR is_deleted = 0)
                    ORDER BY created_at ASC
                    """,
                    (source,),
                )
                if source_rows:
                    matched_source_tokens.append(source)
                    sources.append(source)
                    for row in source_rows:
                        append_paragraph_row(row)

            target_hashes["paragraphs"] = list(paragraph_hashes)
            counts["paragraphs"] = len(paragraph_hashes)
            target_hashes["matched_sources"] = matched_source_tokens
            counts["sources"] = len(matched_source_tokens)
            counts["matched_sources"] = len(matched_source_tokens)

            for hash_value in self._tokens(normalized_selector.get("relation_hashes")):
                append_relation_hash(hash_value)

            entity_names = [
                str(row.get("name", "") or "").strip()
                for row in self.resolve_entity_targets({"hashes": entity_hashes}, include_deleted=False)
                if str(row.get("name", "") or "").strip()
            ]
            for entity_name in entity_names:
                for relation in self.metadata_store.get_relations(subject=entity_name) + self.metadata_store.get_relations(object=entity_name):
                    append_relation_hash(str(relation.get("hash", "") or "").strip())

            for relation_hash in self._tokens(paragraph_relation_candidates):
                if not self._relation_has_remaining_paragraphs(relation_hash, paragraph_hashes):
                    append_relation_hash(relation_hash)

            target_hashes["relations"] = list(relation_hashes)
            counts["relations"] = len(relation_hashes)
        else:
            return {"success": False, "error": f"不支持的 delete mode: {act_mode}"}

        sources = self._tokens(sources)
        vector_ids = self._tokens(vector_ids)
        primary_count = counts.get(f"{act_mode}s", 0) if act_mode not in {"source", "mixed"} else counts.get("matched_sources", 0)
        success = (
            primary_count > 0 or counts.get("paragraphs", 0) > 0 or counts.get("relations", 0) > 0 or counts.get("entities", 0) > 0
            if act_mode != "source"
            else (counts.get("matched_sources", 0) > 0 and counts.get("paragraphs", 0) > 0)
        )
        return {
            "success": success,
            "mode": act_mode,
            "selector": normalized_selector,
            "items": items,
            "counts": counts,
            "vector_ids": vector_ids,
            "sources": sources,
            "target_hashes": target_hashes,
            "requested_source_count": counts.get("requested_sources", 0) if act_mode == "source" else 0,
            "matched_source_count": counts.get("matched_sources", 0) if act_mode == "source" else 0,
            "error": "" if success else "未命中可删除内容",
        }

    # ── 预览/执行/恢复/清理 ──────────────────────────────────

    async def preview_delete_action(self, *, mode: str, selector: Any) -> Dict[str, Any]:
        plan = await self.build_delete_plan(mode=mode, selector=selector)
        if not plan.get("success", False):
            return {"success": False, "error": plan.get("error", "未命中可删除内容")}
        preview_items = [self.build_delete_preview_item(item) for item in plan.get("items", [])[:100]]
        return {
            "success": True,
            "mode": plan.get("mode"),
            "selector": plan.get("selector"),
            "counts": plan.get("counts", {}),
            "requested_source_count": int(plan.get("requested_source_count", 0) or 0),
            "matched_source_count": int(plan.get("matched_source_count", 0) or 0),
            "sources": plan.get("sources", []),
            "vector_ids": plan.get("vector_ids", []),
            "items": preview_items,
            "item_count": len(plan.get("items", [])),
            "dry_run": True,
        }

    async def execute_delete_action(
        self,
        *,
        mode: str,
        selector: Any,
        requested_by: str = "",
        reason: str = "",
    ) -> Dict[str, Any]:
        assert self.metadata_store
        plan = await self.build_delete_plan(mode=mode, selector=selector)
        if not plan.get("success", False):
            return {"success": False, "error": plan.get("error", "未命中可删除内容")}

        act_mode = str(plan.get("mode", "") or "").strip().lower()
        conn = self.metadata_store.get_connection()
        cursor = conn.cursor()
        paragraph_hashes = self._tokens((plan.get("target_hashes") or {}).get("paragraphs"))
        entity_hashes = self._tokens((plan.get("target_hashes") or {}).get("entities"))
        relation_hashes = self._tokens((plan.get("target_hashes") or {}).get("relations"))
        requested_source_tokens = self._tokens((plan.get("target_hashes") or {}).get("sources"))
        matched_source_tokens = self._tokens((plan.get("target_hashes") or {}).get("matched_sources"))

        try:
            if paragraph_hashes:
                self.metadata_store.mark_as_deleted(paragraph_hashes, "paragraph")
                cursor.execute(
                    f"DELETE FROM paragraph_entities WHERE paragraph_hash IN ({','.join(['?'] * len(paragraph_hashes))})",
                    tuple(paragraph_hashes),
                )
                cursor.execute(
                    f"DELETE FROM paragraph_relations WHERE paragraph_hash IN ({','.join(['?'] * len(paragraph_hashes))})",
                    tuple(paragraph_hashes),
                )
                self.metadata_store.delete_external_memory_refs_by_paragraphs(paragraph_hashes)
            if act_mode == "source" and matched_source_tokens:
                for source in matched_source_tokens:
                    self.metadata_store.replace_episodes_for_source(source, [])

            if entity_hashes:
                self.metadata_store.mark_as_deleted(entity_hashes, "entity")
                cursor.execute(
                    f"DELETE FROM paragraph_entities WHERE entity_hash IN ({','.join(['?'] * len(entity_hashes))})",
                    tuple(entity_hashes),
                )

            conn.commit()

            deleted_relations = self.metadata_store.backup_and_delete_relations(relation_hashes)
            deleted_vectors = self._delete_vectors_by_type(
                paragraph_hashes=paragraph_hashes,
                entity_hashes=entity_hashes,
                relation_hashes=relation_hashes,
            )

            operation = self.metadata_store.create_delete_operation(
                mode=act_mode,
                selector=plan.get("selector"),
                items=plan.get("items", []),
                reason=reason,
                requested_by=requested_by,
                summary={
                    "counts": plan.get("counts", {}),
                    "sources": plan.get("sources", []),
                    "vector_ids": plan.get("vector_ids", []),
                    "deleted_relation_rows": deleted_relations,
                },
            )

            if plan.get("sources"):
                self.metadata_store._enqueue_episode_source_rebuilds(list(plan.get("sources") or []), reason="delete_admin_execute")
            self._rebuild_graph_from_metadata()
            self._persist()
            return self.build_standard_delete_result(
                mode=act_mode,
                operation_id=str(operation.get("operation_id", "") or ""),
                counts=plan.get("counts", {}),
                sources=plan.get("sources", []),
                deleted_entity_count=len(entity_hashes),
                deleted_relation_count=len(relation_hashes),
                deleted_paragraph_count=len(paragraph_hashes),
                deleted_source_count=len(matched_source_tokens),
                deleted_vector_count=int(deleted_vectors or 0),
                requested_source_count=len(requested_source_tokens),
                matched_source_count=len(matched_source_tokens),
                error="" if (entity_hashes or relation_hashes or paragraph_hashes or matched_source_tokens) else "未命中可删除内容",
            )
        except Exception as exc:
            conn.rollback()
            logger.warning(f"delete_admin execute 失败: {exc}")
            return self.build_standard_delete_result(mode=act_mode, error=str(exc))

    async def restore_delete_action(
        self,
        *,
        mode: str,
        selector: Any,
        operation_id: str = "",
        requested_by: str = "",
        reason: str = "",
    ) -> Dict[str, Any]:
        del requested_by
        del reason
        assert self.metadata_store

        op_id = str(operation_id or "").strip()
        if op_id:
            operation = self.metadata_store.get_delete_operation(op_id)
            if operation is None:
                return {"success": False, "error": "operation 不存在"}
            return await self.restore_delete_operation(operation)

        act_mode = str(mode or "").strip().lower()
        if act_mode != "relation":
            return {"success": False, "error": "paragraph/entity/source 恢复必须提供 operation_id"}

        raw = self._selector_dict(selector)
        target = str(raw.get("query", "") or raw.get("target", "") or raw.get("hash", "") or "").strip()
        hashes = self._resolve_deleted_relation_hashes(target)
        if not hashes:
            return {"success": False, "error": "未命中可恢复关系"}
        result = await self._restore_relation_hashes(hashes)
        return {"success": bool(result.get("restored_count", 0) > 0), **result}

    async def restore_delete_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        assert self.metadata_store
        items = operation.get("items") if isinstance(operation.get("items"), list) else []
        entity_payloads: Dict[str, Dict[str, Any]] = {}
        paragraph_payloads: Dict[str, Dict[str, Any]] = {}
        relation_payloads: Dict[str, Dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("item_type", "") or "").strip()
            item_hash = str(item.get("item_hash", "") or "").strip()
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if item_type == "entity" and item_hash:
                entity_payloads[item_hash] = payload
            elif item_type == "paragraph" and item_hash:
                paragraph_payloads[item_hash] = payload
            elif item_type == "relation" and item_hash:
                relation_payloads[item_hash] = payload

        restored_entities: List[str] = []
        restored_paragraphs: List[str] = []
        for hash_value, payload in entity_payloads.items():
            entity_row = payload.get("entity") if isinstance(payload.get("entity"), dict) else {}
            if entity_row:
                self.metadata_store.restore_entity_by_hash(hash_value)
                await self._ensure_entity_vector(entity_row)
                restored_entities.append(hash_value)
        for hash_value, payload in paragraph_payloads.items():
            paragraph_row = payload.get("paragraph") if isinstance(payload.get("paragraph"), dict) else {}
            if paragraph_row:
                self.metadata_store.restore_paragraph_by_hash(hash_value)
                await self._ensure_paragraph_vector(paragraph_row)
                restored_paragraphs.append(hash_value)

        restored_relations = await self._restore_relation_hashes(list(relation_payloads.keys()), payloads=relation_payloads, rebuild_graph=False, persist=False)

        conn = self.metadata_store.get_connection()
        cursor = conn.cursor()
        for payload in entity_payloads.values():
            for link in payload.get("paragraph_links") or []:
                paragraph_hash = str(link.get("paragraph_hash", "") or "").strip()
                entity_hash = str(link.get("entity_hash", "") or "").strip()
                mention_count = max(1, int(link.get("mention_count", 1) or 1))
                if not paragraph_hash or not entity_hash:
                    continue
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO paragraph_entities (paragraph_hash, entity_hash, mention_count)
                    VALUES (?, ?, ?)
                    """,
                    (paragraph_hash, entity_hash, mention_count),
                )
        for payload in paragraph_payloads.values():
            for link in payload.get("entity_links") or []:
                paragraph_hash = str(link.get("paragraph_hash", "") or "").strip()
                entity_hash = str(link.get("entity_hash", "") or "").strip()
                mention_count = max(1, int(link.get("mention_count", 1) or 1))
                if not paragraph_hash or not entity_hash:
                    continue
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO paragraph_entities (paragraph_hash, entity_hash, mention_count)
                    VALUES (?, ?, ?)
                    """,
                    (paragraph_hash, entity_hash, mention_count),
                )
            for relation_hash in self._tokens(payload.get("relation_hashes")):
                paragraph_hash = str((payload.get("paragraph") or {}).get("hash", "") or "").strip()
                if not paragraph_hash or not relation_hash:
                    continue
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO paragraph_relations (paragraph_hash, relation_hash)
                    VALUES (?, ?)
                    """,
                    (paragraph_hash, relation_hash),
                )
            self.metadata_store.restore_external_memory_refs(list(payload.get("external_refs") or []))
        conn.commit()

        sources = self._tokens(
            [
                str(((payload.get("paragraph") or {}).get("source", "") or "")).strip()
                for payload in paragraph_payloads.values()
            ]
        )
        if sources:
            self.metadata_store._enqueue_episode_source_rebuilds(sources, reason="delete_admin_restore")
        self._rebuild_graph_from_metadata()
        self._persist()
        summary = {
            "restored_entities": restored_entities,
            "restored_paragraphs": restored_paragraphs,
            "restored_relations": restored_relations.get("restored_hashes", []),
            "sources": sources,
        }
        self.metadata_store.mark_delete_operation_restored(str(operation.get("operation_id", "") or ""), summary=summary)
        return {
            "success": True,
            "operation_id": str(operation.get("operation_id", "") or ""),
            **summary,
            "restored_relation_count": restored_relations.get("restored_count", 0),
            "relation_failures": restored_relations.get("failures", []),
        }

    async def purge_deleted_memory(self, *, grace_hours: Optional[float], limit: int) -> Dict[str, Any]:
        assert self.metadata_store
        orphan_cfg = self._cfg("memory.orphan", {}) or {}
        grace = float(grace_hours) if grace_hours is not None else max(
            1.0,
            float(orphan_cfg.get("sweep_grace_hours", 24.0) or 24.0),
        )
        cutoff = time.time() - grace * 3600.0
        deleted_relation_hashes = self.metadata_store.purge_deleted_relations(cutoff_time=cutoff, limit=limit)
        dead_paragraphs = self.metadata_store.sweep_deleted_items("paragraph", grace * 3600.0)
        paragraph_hashes = [str(item[0] or "").strip() for item in dead_paragraphs if str(item[0] or "").strip()]
        dead_entities = self.metadata_store.sweep_deleted_items("entity", grace * 3600.0)
        entity_hashes = [str(item[0] or "").strip() for item in dead_entities if str(item[0] or "").strip()]
        entity_names = [str(item[1] or "").strip() for item in dead_entities if str(item[1] or "").strip()]

        if paragraph_hashes:
            self.metadata_store.physically_delete_paragraphs(paragraph_hashes)
        if entity_hashes:
            self.metadata_store.physically_delete_entities(entity_hashes)
        if entity_names:
            self.graph_store.delete_nodes(entity_names)
        self._delete_vectors_by_type(
            paragraph_hashes=paragraph_hashes,
            entity_hashes=entity_hashes,
            relation_hashes=deleted_relation_hashes,
        )
        self._rebuild_graph_from_metadata()
        self._persist()
        return {
            "success": True,
            "grace_hours": grace,
            "purged_deleted_relations": deleted_relation_hashes,
            "purged_paragraph_hashes": paragraph_hashes,
            "purged_entity_hashes": entity_hashes,
            "purged_counts": {
                "relations": len(deleted_relation_hashes),
                "paragraphs": len(paragraph_hashes),
                "entities": len(entity_hashes),
            },
        }

    # ── 反馈纠正软删除 ───────────────────────────────────────

    def soft_delete_feedback_correction_paragraphs(self, paragraph_hashes: Sequence[str]) -> Dict[str, Any]:
        assert self.metadata_store is not None
        hashes = self._tokens(paragraph_hashes)
        if not hashes:
            return {"deleted_hashes": [], "deleted_external_refs": []}

        paragraph_rows = {hash_value: self.metadata_store.get_paragraph(hash_value) for hash_value in hashes}
        self.metadata_store.mark_as_deleted(hashes, "paragraph")
        conn = self.metadata_store.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM paragraph_entities WHERE paragraph_hash IN ({','.join(['?'] * len(hashes))})",
            tuple(hashes),
        )
        cursor.execute(
            f"DELETE FROM paragraph_relations WHERE paragraph_hash IN ({','.join(['?'] * len(hashes))})",
            tuple(hashes),
        )
        conn.commit()
        deleted_external_refs = self.metadata_store.delete_external_memory_refs_by_paragraphs(hashes)
        return {
            "deleted_hashes": hashes,
            "paragraph_rows": paragraph_rows,
            "deleted_external_refs": deleted_external_refs,
        }

    # ── 来源删除 ──────────────────────────────────────────────

    def apply_cleanup_plan(self, cleanup: Dict[str, Any]) -> None:
        if not isinstance(cleanup, dict):
            return
        paragraph_hash = str(cleanup.get("vector_id_to_remove", "") or "").strip()
        relation_hashes = [
            str(relation_hash or "").strip()
            for _, _, relation_hash in cleanup.get("relation_prune_ops", []) or []
            if str(relation_hash or "").strip()
        ]
        self._delete_vectors_by_type(
            paragraph_hashes=[paragraph_hash] if paragraph_hash else [],
            relation_hashes=relation_hashes,
        )

    def delete_sources(self, sources: Iterable[Any]) -> Dict[str, Any]:
        assert self.metadata_store
        source_tokens = self._tokens(sources)
        if not source_tokens:
            return {"success": False, "error": "source 不能为空"}

        deleted_paragraphs = 0
        deleted_sources: List[str] = []
        for source in source_tokens:
            paragraphs = self.metadata_store.get_paragraphs_by_source(source)
            if not paragraphs:
                self.metadata_store.replace_episodes_for_source(source, [])
                continue
            for row in paragraphs:
                paragraph_hash = str(row.get("hash", "") or "").strip()
                if not paragraph_hash:
                    continue
                cleanup = self.metadata_store.delete_paragraph_atomic(paragraph_hash)
                self.apply_cleanup_plan(cleanup)
                deleted_paragraphs += 1
            self.metadata_store.replace_episodes_for_source(source, [])
            deleted_sources.append(source)

        self._rebuild_graph_from_metadata()
        self._persist()
        return {
            "success": True,
            "sources": deleted_sources,
            "deleted_source_count": len(deleted_sources),
            "deleted_paragraph_count": deleted_paragraphs,
        }