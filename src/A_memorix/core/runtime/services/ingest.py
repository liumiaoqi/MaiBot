from __future__ import annotations

from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence

from ...utils.hash import compute_hash, normalize_text
from ...utils.metadata import coerce_metadata_dict
from .types import KernelSearchRequest

from src.common.logger import get_logger

logger = get_logger("A_Memorix.IngestService")


class IngestService:

    def __init__(
        self,
        *,
        get_metadata_store: Callable[[], Any],
        get_vector_store: Callable[[], Any],
        get_graph_store: Callable[[], Any],
        get_embedding_manager: Callable[[], Any],
        get_relation_write_service: Callable[[], Any],
        get_summary_importer: Callable[[], Any],
        get_episode_service: Callable[[], Any],
        is_chat_filtered: Callable[..., bool],
        cfg: Callable[[str, Any], Any],
        tokens: Callable[..., List[str]],
        merge_tokens: Callable[..., List[str]],
        time_meta: Callable[..., Dict[str, Any]],
        resolve_knowledge_type: Callable[[str], str],
        write_paragraph_vector_or_enqueue: Callable[..., Coroutine],
        ensure_entity_vector: Callable[..., Coroutine],
        should_auto_enqueue_episode: Callable[..., bool],
        persist: Callable[[], None],
        mark_person_active: Callable[[str], None],
        enqueue_person_profile_refresh: Callable[[str, str], bool],
        optional_int: Callable[[Any], Optional[int]],
        background_scheduler: Any,
        argument_tokens: Callable[..., List[str]],
    ) -> None:
        self._get_metadata_store = get_metadata_store
        self._get_vector_store = get_vector_store
        self._get_graph_store = get_graph_store
        self._get_embedding_manager = get_embedding_manager
        self._get_relation_write_service = get_relation_write_service
        self._get_summary_importer = get_summary_importer
        self._get_episode_service = get_episode_service
        self._is_chat_filtered = is_chat_filtered
        self._cfg = cfg
        self._tokens = tokens
        self._merge_tokens = merge_tokens
        self._time_meta = time_meta
        self._resolve_knowledge_type = resolve_knowledge_type
        self._write_paragraph_vector_or_enqueue = write_paragraph_vector_or_enqueue
        self._ensure_entity_vector = ensure_entity_vector
        self._should_auto_enqueue_episode = should_auto_enqueue_episode
        self._persist = persist
        self._mark_person_active = mark_person_active
        self._enqueue_person_profile_refresh = enqueue_person_profile_refresh
        self._optional_int = optional_int
        self._background_scheduler = background_scheduler
        self._argument_tokens = argument_tokens

    async def summarize_chat_stream(
        self,
        *,
        chat_id: str,
        context_length: Optional[int] = None,
        include_personality: Optional[bool] = None,
        time_end: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        summary_importer = self._get_summary_importer()
        assert summary_importer
        import_result = await summary_importer.import_from_stream(
            stream_id=str(chat_id or "").strip(),
            context_length=context_length,
            include_personality=include_personality,
            time_end=time_end,
            metadata=metadata,
        )
        success = bool(getattr(import_result, "success", False))
        detail = str(getattr(import_result, "detail", "") or "")
        paragraph_hash = str(getattr(import_result, "paragraph_hash", "") or "").strip()
        source = (
            str(getattr(import_result, "source", "") or "").strip()
            or self.build_source("chat_summary", chat_id, [])
        )
        stored_ids: List[str] = []
        episode_pending_ids: List[str] = []
        if success:
            if not paragraph_hash:
                raise RuntimeError("聊天摘要导入成功但未返回 paragraph_hash，无法执行 Episode 增量入队")
            metadata_store = self._get_metadata_store()
            assert metadata_store is not None
            if self._should_auto_enqueue_episode(source_type="chat_summary"):
                metadata_store.enqueue_episode_pending(paragraph_hash, source=source)
                episode_pending_ids.append(paragraph_hash)
            stored_ids.append(paragraph_hash)
            self._persist()
        payload = {"success": success, "detail": detail}
        if stored_ids:
            payload["stored_ids"] = stored_ids
        if episode_pending_ids:
            payload["episode_pending_ids"] = episode_pending_ids
        return payload

    async def ingest_summary(
        self,
        *,
        external_id: str,
        chat_id: str,
        text: str,
        participants: Optional[Sequence[str]] = None,
        time_start: Optional[float] = None,
        time_end: Optional[float] = None,
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> Dict[str, Any]:
        external_token = str(external_id or "").strip() or compute_hash(f"chat_summary:{chat_id}:{text}")
        if self._is_chat_filtered(
            respect_filter=respect_filter,
            stream_id=chat_id,
            group_id=group_id,
            user_id=user_id,
        ):
            return {
                "success": True,
                "stored_ids": [],
                "skipped_ids": [external_token],
                "detail": "chat_filtered",
            }

        summary_meta = coerce_metadata_dict(metadata)
        summary_meta.setdefault("kind", "chat_summary")
        if not str(text or "").strip() or bool(summary_meta.get("generate_from_chat", False)):
            result = await self.summarize_chat_stream(
                chat_id=chat_id,
                context_length=self._optional_int(summary_meta.get("context_length")),
                include_personality=summary_meta.get("include_personality"),
                time_end=time_end,
                metadata={
                    **summary_meta,
                    "external_id": external_token,
                    "chat_id": str(chat_id or "").strip(),
                    "source_type": "chat_summary",
                },
            )
            result.setdefault("external_id", external_id)
            result.setdefault("chat_id", chat_id)
            return result
        return await self.ingest_text(
            external_id=external_id,
            source_type="chat_summary",
            text=text,
            chat_id=chat_id,
            participants=participants,
            time_start=time_start,
            time_end=time_end,
            tags=tags,
            metadata=summary_meta,
            respect_filter=respect_filter,
            user_id=user_id,
            group_id=group_id,
        )

    async def ingest_text(
        self,
        *,
        external_id: str,
        source_type: str,
        text: str,
        chat_id: str = "",
        person_ids: Optional[Sequence[str]] = None,
        participants: Optional[Sequence[str]] = None,
        timestamp: Optional[float] = None,
        time_start: Optional[float] = None,
        time_end: Optional[float] = None,
        tags: Optional[Sequence[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        entities: Optional[Sequence[str]] = None,
        relations: Optional[Sequence[Dict[str, Any]]] = None,
        respect_filter: bool = True,
        user_id: str = "",
        group_id: str = "",
    ) -> Dict[str, Any]:
        content = normalize_text(text)
        external_token = str(external_id or "").strip() or compute_hash(f"{source_type}:{chat_id}:{content}")
        if self._is_chat_filtered(
            respect_filter=respect_filter,
            stream_id=chat_id,
            group_id=group_id,
            user_id=user_id,
        ):
            return {
                "success": True,
                "stored_ids": [],
                "skipped_ids": [external_token],
                "detail": "chat_filtered",
            }

        metadata_store = self._get_metadata_store()
        vector_store = self._get_vector_store()
        graph_store = self._get_graph_store()
        embedding_manager = self._get_embedding_manager()
        relation_write_service = self._get_relation_write_service()
        assert metadata_store is not None
        assert vector_store is not None
        assert graph_store is not None
        assert embedding_manager is not None
        assert relation_write_service is not None

        if not content:
            return {"stored_ids": [], "skipped_ids": [external_token], "reason": "empty_text"}

        existing_ref = metadata_store.get_external_memory_ref(external_token)
        if existing_ref:
            return {
                "stored_ids": [],
                "skipped_ids": [str(existing_ref.get("paragraph_hash", "") or "")],
                "reason": "exists",
            }

        person_tokens = self._tokens(person_ids)
        participant_tokens = self._tokens(participants)
        entity_tokens = self._merge_tokens(entities, person_tokens, participant_tokens)
        source = self.build_source(source_type, chat_id, person_tokens)
        paragraph_meta = coerce_metadata_dict(metadata)
        paragraph_meta.update(
            {
                "external_id": external_token,
                "source_type": str(source_type or "").strip(),
                "chat_id": str(chat_id or "").strip(),
                "person_ids": person_tokens,
                "participants": participant_tokens,
                "tags": self._tokens(tags),
            }
        )
        warnings: List[str] = []

        paragraph_hash = metadata_store.add_paragraph(
            content=content,
            source=source,
            metadata=paragraph_meta,
            knowledge_type=self._resolve_knowledge_type(source_type),
            time_meta=self._time_meta(timestamp, time_start, time_end),
        )
        vector_result = await self._write_paragraph_vector_or_enqueue(
            paragraph_hash=paragraph_hash,
            content=content,
            context="ingest_text",
        )
        warning = str(vector_result.get("warning", "") or "").strip()
        if warning:
            warnings.append(warning)

        for name in entity_tokens:
            entity_hash = metadata_store.add_entity(name=name, source_paragraph=paragraph_hash)
            await self._ensure_entity_vector({"hash": entity_hash, "name": name})

        stored_relations: List[str] = []
        for row in [dict(item) for item in (relations or []) if isinstance(item, dict)]:
            subject = str(row.get("subject", "") or "").strip()
            predicate = str(row.get("predicate", "") or "").strip()
            obj = str(row.get("object", "") or "").strip()
            if not (subject and predicate and obj):
                continue
            result = await relation_write_service.upsert_relation_with_vector(
                subject=subject,
                predicate=predicate,
                obj=obj,
                confidence=float(row.get("confidence", 1.0) or 1.0),
                source_paragraph=paragraph_hash,
                metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {"external_id": external_token, "source_type": source_type},
                write_vector=bool(self._cfg("retrieval.relation_vectorization.enabled", False)),
            )
            metadata_store.link_paragraph_relation(paragraph_hash, result.hash_value)
            stored_relations.append(result.hash_value)

        metadata_store.upsert_external_memory_ref(
            external_id=external_token,
            paragraph_hash=paragraph_hash,
            source_type=source_type,
            metadata={"chat_id": chat_id, "person_ids": person_tokens},
        )
        if self._should_auto_enqueue_episode(source_type=source_type):
            metadata_store.enqueue_episode_pending(paragraph_hash, source=source)
        self._persist()
        for person_id in person_tokens:
            self._mark_person_active(person_id)
            self._enqueue_person_profile_refresh(person_id, reason=str(source_type or "ingest_text"))
        payload = {"stored_ids": [paragraph_hash, *stored_relations], "skipped_ids": []}
        if warnings:
            payload["warnings"] = warnings
            payload["detail"] = "vector_degraded_write"
        return payload

    async def process_episode_pending_batch(self, *, limit: int = 20, max_retry: int = 3) -> Dict[str, Any]:
        metadata_store = self._get_metadata_store()
        episode_service = self._get_episode_service()
        assert metadata_store is not None
        assert episode_service is not None

        pending_rows = metadata_store.fetch_episode_pending_batch(limit=max(1, int(limit)), max_retry=max(1, int(max_retry)))
        if not pending_rows:
            return {"processed": 0, "episode_count": 0, "fallback_count": 0, "failed": 0}

        source_to_hashes: Dict[str, List[str]] = {}
        pending_hashes = [str(row.get("paragraph_hash", "") or "").strip() for row in pending_rows if str(row.get("paragraph_hash", "") or "").strip()]
        for row in pending_rows:
            paragraph_hash = str(row.get("paragraph_hash", "") or "").strip()
            source = str(row.get("source", "") or "").strip()
            if not paragraph_hash or not source:
                continue
            source_to_hashes.setdefault(source, []).append(paragraph_hash)

        if pending_hashes:
            metadata_store.mark_episode_pending_running(pending_hashes)

        result = await episode_service.process_pending_rows(pending_rows)
        done_hashes = [str(item or "").strip() for item in result.get("done_hashes", []) if str(item or "").strip()]
        failed_hashes = {
            str(hash_value or "").strip(): str(error or "").strip()
            for hash_value, error in (result.get("failed_hashes", {}) or {}).items()
            if str(hash_value or "").strip()
        }

        if done_hashes:
            metadata_store.mark_episode_pending_done(done_hashes)
        for hash_value, error in failed_hashes.items():
            metadata_store.mark_episode_pending_failed(hash_value, error)

        untouched = [hash_value for hash_value in pending_hashes if hash_value not in set(done_hashes) and hash_value not in failed_hashes]
        for hash_value in untouched:
            metadata_store.mark_episode_pending_failed(hash_value, "episode processing finished without explicit status")

        for source, paragraph_hashes in source_to_hashes.items():
            counts = metadata_store.get_episode_pending_status_counts(source)
            if counts.get("failed", 0) > 0:
                source_error = next(
                    (
                        failed_hashes.get(hash_value)
                        for hash_value in paragraph_hashes
                        if failed_hashes.get(hash_value)
                    ),
                    "episode pending source contains failed rows",
                )
                metadata_store.mark_episode_source_failed(source, str(source_error or "episode pending source contains failed rows"))
            elif counts.get("pending", 0) == 0 and counts.get("running", 0) == 0:
                metadata_store.mark_episode_source_done(source)

        self._persist()
        return {
            "processed": len(done_hashes) + len(failed_hashes),
            "episode_count": int(result.get("episode_count") or 0),
            "fallback_count": int(result.get("fallback_count") or 0),
            "failed": len(failed_hashes) + len(untouched),
            "group_count": int(result.get("group_count") or 0),
            "missing_count": int(result.get("missing_count") or 0),
        }

    async def episode_pending_loop(self) -> None:
        try:
            while not self._background_scheduler.stopping:
                import asyncio
                await asyncio.sleep(60.0)
                if self._background_scheduler.stopping:
                    break
                if not bool(self._cfg("episode.enabled", True)):
                    continue
                if not bool(self._cfg("episode.generation_enabled", True)):
                    continue
                await self.process_episode_pending_batch(
                    limit=max(1, int(self._cfg("episode.pending_batch_size", 50) or 50)),
                    max_retry=max(1, int(self._cfg("episode.pending_max_retry", 3) or 3)),
                )
        except Exception as exc:
            logger.warning(f"episode_pending loop 异常: {exc}")

    @staticmethod
    def build_source(source_type: str, chat_id: str, person_ids: Sequence[str]) -> str:
        clean_type = str(source_type or "").strip() or "memory"
        if clean_type == "chat_summary" and chat_id:
            return f"chat_summary:{chat_id}"
        if clean_type == "person_fact" and person_ids:
            return f"person_fact:{person_ids[0]}"
        return f"{clean_type}:{chat_id}" if chat_id else clean_type

    def should_auto_enqueue_episode(self, *, source_type: str) -> bool:
        if not bool(self._cfg("episode.enabled", True)):
            return False
        if not bool(self._cfg("episode.generation_enabled", True)):
            return False

        normalized_source_type = str(source_type or "").strip().lower()
        disabled_types = {
            str(item or "").strip().lower()
            for item in self._argument_tokens(self._cfg("episode.disabled_source_types", ["person_fact"]))
        }
        return normalized_source_type not in disabled_types