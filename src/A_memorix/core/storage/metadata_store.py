"""
元数据存储模块 - 基于SQLite的元数据管理，存储段落、实体、关系等信息。

MetadataStore 作为门面，将具体操作委托给 5 个子 Store：
  - SchemaManager  — schema 版本管理 & 建表
  - ParagraphStore — 段落 CRUD + FTS5 + N-gram
  - EntityStore    — 实体 CRUD + 段落实体关联
  - RelationStore  — 关系 CRUD + V5 状态 + 保护/修剪 + FTS
  - ProfileStore   — 人物画像开关/快照/覆盖/刷新队列
"""

import json
import re
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from src.common.logger import get_logger
from ..utils.hash import compute_hash, normalize_text
from .stores import (
    SchemaManager, SCHEMA_VERSION,
    ParagraphStore, EntityStore, RelationStore, ProfileStore,
)
from .stores._utils import (
    canonicalize_name,
    dedupe_episode_sources,
    iter_sql_batches,
    json_dumps,
    json_loads,
    as_optional_float,
    normalize_episode_source,
    normalize_hash_sequence,
    row_to_dict,
)

try:
    import jieba  # type: ignore
    HAS_JIEBA = True
except Exception:
    HAS_JIEBA = False

logger = get_logger("A_Memorix.MetadataStore")

# 重新导出 SCHEMA_VERSION 保持向后兼容（迁移脚本等直接 import）
__all__ = ["MetadataStore", "SCHEMA_VERSION"]


class MetadataStore:
    """
    元数据存储门面（Facade）

    对外保持全部原有方法签名不变，内部委托给子 Store。
    """

    def __init__(
        self,
        data_dir: Optional[Union[str, Path]] = None,
        db_name: str = "metadata.db",
    ) -> None:
        self.data_dir = Path(data_dir) if data_dir else None
        self.db_name = db_name
        self._conn: Optional[sqlite3.Connection] = None
        self._is_initialized = False
        self._db_path: Optional[Path] = None

        # 子 Store（connect() 时注入连接）
        self.paragraphs: Optional[ParagraphStore] = None
        self.entities: Optional[EntityStore] = None
        self.relations: Optional[RelationStore] = None
        self.profiles: Optional[ProfileStore] = None
        self.schema = SchemaManager()

        logger.debug(f"元数据存储初始化: db={db_name}")

    # =========================================================================
    # 连接管理
    # =========================================================================

    def connect(
        self,
        data_dir: Optional[Union[str, Path]] = None,
        *,
        enforce_schema: bool = True,
    ) -> None:
        if data_dir is None:
            data_dir = self.data_dir
        if data_dir is None:
            raise ValueError("未指定数据目录")

        data_dir = Path(data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        db_path = data_dir / self.db_name
        db_existed = db_path.exists()
        self._db_path = db_path

        self._conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-64000")
        self._conn.execute("PRAGMA temp_store=MEMORY")
        self._conn.execute("PRAGMA foreign_keys = ON")

        logger.info(f"数据库已连接: {db_path}")

        # 创建子 Store 实例
        self.paragraphs = ParagraphStore(self._conn)
        self.entities = EntityStore(self._conn)
        self.relations = RelationStore(self._conn)
        self.profiles = ProfileStore(self._conn)

        # 初始化或校验 schema
        if not self._is_initialized:
            self.schema.ensure(self._conn, db_existed=db_existed)
            self._is_initialized = True

        # 初始化 FTS schema（幂等）
        try:
            self.paragraphs.ensure_fts_schema()
        except Exception as e:
            logger.warning(f"初始化 FTS schema 失败，将跳过 BM25 检索: {e}")

    def _resolve_conn(self, conn: Optional[sqlite3.Connection] = None) -> sqlite3.Connection:
        resolved = conn or self._conn
        if resolved is None:
            raise RuntimeError("MetadataStore 未连接数据库")
        return resolved

    def get_db_path(self) -> Path:
        if self._db_path is not None:
            return self._db_path
        if self.data_dir is None:
            raise RuntimeError("MetadataStore 未配置 data_dir")
        return Path(self.data_dir) / self.db_name

    def get_connection(self) -> sqlite3.Connection:
        return self._resolve_conn()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
            self.paragraphs = None
            self.entities = None
            self.relations = None
            self.profiles = None
            logger.info("数据库连接已关闭")

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def __repr__(self) -> str:
        stats = self.get_statistics() if self.is_connected else {}
        return (
            f"MetadataStore(paragraphs={stats.get('paragraph_count', 0)}, "
            f"entities={stats.get('entity_count', 0)}, "
            f"relations={stats.get('relation_count', 0)})"
        )

    def has_data(self) -> bool:
        if self.data_dir is None:
            return False
        return (self.data_dir / self.db_name).exists()

    # =========================================================================
    # Schema（委托 SchemaManager）
    # =========================================================================

    def get_schema_version(self) -> int:
        return self.schema.get_schema_version(self._conn)

    def set_schema_version(self, version: int = SCHEMA_VERSION) -> None:
        self.schema.set_schema_version(self._conn, version)

    def has_table(self, table_name: str) -> bool:
        if not self._conn:
            return False
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (table_name,),
        )
        return cursor.fetchone() is not None

    # =========================================================================
    # 段落（委托 ParagraphStore）
    # =========================================================================

    def add_paragraph(
        self,
        content: str,
        vector_index: Optional[int] = None,
        source: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        knowledge_type: str = "mixed",
        time_meta: Optional[Dict[str, Any]] = None,
    ) -> str:
        hash_value = self.paragraphs.add_paragraph(
            content,
            vector_index=vector_index,
            source=source,
            metadata=metadata,
            knowledge_type=knowledge_type,
            time_meta=time_meta,
        )
        try:
            self.enqueue_episode_source_rebuild(source=source, reason="paragraph_added")
        except Exception as e:
            logger.warning(f"Episode source 重建入队失败: hash={hash_value[:16]}..., err={e}")
        return hash_value

    def get_paragraph(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self.paragraphs.get_paragraph(hash_value)

    def get_paragraphs_by_hashes(
        self, hash_values: Sequence[str]
    ) -> Dict[str, Dict[str, Any]]:
        return self.paragraphs.get_paragraphs_by_hashes(hash_values)

    def update_paragraph_time_meta(
        self, paragraph_hash: str, time_meta: Dict[str, Any]
    ) -> bool:
        source_to_rebuild = self.paragraphs._get_sources_for_paragraph_hashes(
            [paragraph_hash], include_deleted=True
        )
        changed = self.paragraphs.update_paragraph_time_meta(paragraph_hash, time_meta)
        if changed:
            self._enqueue_episode_source_rebuilds(
                source_to_rebuild, reason="paragraph_time_updated"
            )
        return changed

    def update_paragraph_metadata(
        self,
        paragraph_hash: str,
        patch: Dict[str, Any],
        *,
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        updated = self.paragraphs.update_paragraph_metadata(paragraph_hash, patch, merge=merge)
        if updated is not None:
            self._enqueue_episode_source_rebuilds(
                self.paragraphs._get_sources_for_paragraph_hashes(
                    [paragraph_hash], include_deleted=True
                ),
                reason="paragraph_metadata_updated",
            )
        return updated

    def delete_paragraph(self, hash_value: str) -> bool:
        return self.paragraphs.delete_paragraph(hash_value)

    def delete_paragraph_atomic(self, paragraph_hash: str) -> Dict[str, Any]:
        cleanup_plan = self.paragraphs.delete_paragraph_atomic(paragraph_hash)
        if cleanup_plan.get("episode_sources_to_rebuild"):
            self._enqueue_episode_source_rebuilds(
                cleanup_plan["episode_sources_to_rebuild"],
                reason="paragraph_deleted",
            )
        return cleanup_plan

    def query_paragraphs_temporal(
        self,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        person: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
        allow_created_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        return self.paragraphs.query_paragraphs_temporal(
            start_ts=start_ts,
            end_ts=end_ts,
            person=person,
            source=source,
            limit=limit,
            allow_created_fallback=allow_created_fallback,
        )

    def get_paragraphs_by_source(self, source: str) -> List[Dict[str, Any]]:
        return self.paragraphs.get_paragraphs_by_source(source)

    def get_all_sources(self) -> List[Dict[str, Any]]:
        return self.paragraphs.get_all_sources()

    def get_live_paragraphs_by_source(self, source: str) -> List[Dict[str, Any]]:
        return self.paragraphs.get_live_paragraphs_by_source(source)

    def search_paragraphs_by_content(self, content_query: str) -> List[Dict[str, Any]]:
        return self.paragraphs.search_paragraphs_by_content(content_query)

    def count_paragraphs(
        self, include_deleted: bool = False, only_deleted: bool = False
    ) -> int:
        return self.paragraphs.count_paragraphs(
            include_deleted=include_deleted, only_deleted=only_deleted
        )

    # =========================================================================
    # 实体（委托 EntityStore）
    # =========================================================================

    def add_entity(
        self,
        name: str,
        vector_index: Optional[int] = None,
        source_paragraph: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.entities.add_entity(
            name,
            vector_index=vector_index,
            source_paragraph=source_paragraph,
            metadata=metadata,
        )

    def get_entity(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self.entities.get_entity(hash_value)

    def get_entities_by_hashes(
        self, hash_values: Sequence[str]
    ) -> Dict[str, Dict[str, Any]]:
        return self.entities.get_entities_by_hashes(hash_values)

    def delete_entity(self, hash_or_name: str) -> bool:
        return self.entities.delete_entity(hash_or_name)

    def count_entities(self) -> int:
        return self.entities.count_entities()

    def is_entity_still_referenced(
        self, entity_hash: str, entity_name: str = ""
    ) -> bool:
        return self.entities.is_entity_still_referenced(entity_hash, entity_name)

    def link_paragraph_entity(
        self, paragraph_hash: str, entity_hash: str, mention_count: int = 1
    ) -> bool:
        result = self.entities.link_paragraph_entity(
            paragraph_hash, entity_hash, mention_count
        )
        if result:
            self._enqueue_episode_source_rebuilds(
                self.paragraphs._get_sources_for_paragraph_hashes(
                    [paragraph_hash], include_deleted=True
                ),
                reason="paragraph_entity_linked",
            )
        return result

    # =========================================================================
    # 关系（委托 RelationStore）
    # =========================================================================

    def compute_relation_hash(self, subject: str, predicate: str, obj: str) -> str:
        return self.relations.compute_relation_hash(subject, predicate, obj)

    def add_relation(
        self,
        subject: str,
        predicate: str,
        obj: str,
        vector_index: Optional[int] = None,
        confidence: float = 1.0,
        source_paragraph: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        return self.relations.add_relation(
            subject, predicate, obj,
            vector_index=vector_index,
            confidence=confidence,
            source_paragraph=source_paragraph,
            metadata=metadata,
        )

    def get_relation(
        self, hash_value: str, include_inactive: bool = True
    ) -> Optional[Dict[str, Any]]:
        return self.relations.get_relation(hash_value, include_inactive=include_inactive)

    def get_relations_by_hashes(
        self, hash_values: Sequence[str], include_inactive: bool = True
    ) -> Dict[str, Dict[str, Any]]:
        return self.relations.get_relations_by_hashes(
            hash_values, include_inactive=include_inactive
        )

    def delete_relation(self, hash_value: str) -> bool:
        return self.relations.delete_relation(hash_value)

    def get_relations(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
        include_inactive: bool = True,
    ) -> List[Dict[str, Any]]:
        return self.relations.get_relations(
            subject=subject,
            predicate=predicate,
            object=object,
            include_inactive=include_inactive,
        )

    def get_all_triples(self) -> List[Tuple[str, str, str, str]]:
        return self.relations.get_all_triples()

    def count_relations(
        self, include_deleted: bool = False, only_deleted: bool = False
    ) -> int:
        return self.relations.count_relations(
            include_deleted=include_deleted, only_deleted=only_deleted
        )

    def get_relation_db_snapshot(self) -> Tuple[int, float, str]:
        return self.relations.get_relation_db_snapshot()

    def link_paragraph_relation(self, paragraph_hash: str, relation_hash: str) -> bool:
        result = self.relations.link_paragraph_relation(paragraph_hash, relation_hash)
        if result:
            self._enqueue_episode_source_rebuilds(
                self.paragraphs._get_sources_for_paragraph_hashes(
                    [paragraph_hash], include_deleted=True
                ),
                reason="paragraph_relation_linked",
            )
        return result

    def update_relation_metadata(
        self,
        relation_hash: str,
        patch: Dict[str, Any],
        *,
        merge: bool = True,
    ) -> Optional[Dict[str, Any]]:
        return self.relations.update_relation_metadata(relation_hash, patch, merge=merge)

    def update_relation_timestamp(
        self, hash_value: str, access_count_delta: int = 1
    ) -> None:
        self.relations.update_relation_timestamp(hash_value, access_count_delta)

    def set_relation_vector_state(
        self,
        hash_value: str,
        state: str,
        error: Optional[str] = None,
        bump_retry: bool = False,
    ) -> bool:
        return self.relations.set_relation_vector_state(
            hash_value, state, error=error, bump_retry=bump_retry
        )

    def list_relations_by_vector_state(
        self,
        states: List[str],
        limit: int = 200,
        max_retry: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        return self.relations.list_relations_by_vector_state(
            states, limit=limit, max_retry=max_retry
        )

    def count_relations_by_vector_state(self) -> Dict[str, int]:
        return self.relations.count_relations_by_vector_state()

    def search_relations_by_subject_or_object(
        self,
        query: str,
        *,
        limit: int = 5,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        return self.relations.search_relations_by_subject_or_object(
            query, limit=limit, include_deleted=include_deleted
        )

    def get_relations_subject_object_map(
        self, hashes: List[str]
    ) -> Dict[str, Tuple[str, str]]:
        return self.relations.get_relations_subject_object_map(hashes)

    def get_relation_status_batch(
        self, hashes: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        return self.relations.get_relation_status_batch(hashes)

    def mark_relations_active(
        self, hashes: List[str], boost_weight: Optional[float] = None
    ) -> None:
        self.relations.mark_relations_active(hashes, boost_weight=boost_weight)

    def mark_relations_inactive(
        self, hashes: List[str], inactive_since: Optional[float] = None
    ) -> None:
        self.relations.mark_relations_inactive(hashes, inactive_since=inactive_since)

    def update_relations_protection(
        self,
        hashes: List[str],
        protected_until: Optional[float] = None,
        is_pinned: Optional[bool] = None,
        last_reinforced: Optional[float] = None,
    ) -> None:
        self.relations.update_relations_protection(
            hashes,
            protected_until=protected_until,
            is_pinned=is_pinned,
            last_reinforced=last_reinforced,
        )

    def reinforce_relations(self, hashes: List[str]) -> None:
        self.relations.reinforce_relations(hashes)

    def protect_relations(
        self, hashes: List[str], is_pinned: bool = False, ttl_seconds: float = 0
    ) -> None:
        self.relations.protect_relations(hashes, is_pinned=is_pinned, ttl_seconds=ttl_seconds)

    def get_protected_relations_hashes(self) -> List[str]:
        return self.relations.get_protected_relations_hashes()

    def get_memory_status_summary(
        self, now_ts: Optional[float] = None
    ) -> Dict[str, int]:
        return self.relations.get_memory_status_summary(now_ts=now_ts)

    def get_prune_candidates(
        self, cutoff_time: float, limit: int = 1000
    ) -> List[str]:
        return self.relations.get_prune_candidates(cutoff_time, limit=limit)

    def backup_and_delete_relations(self, hashes: List[str]) -> int:
        return self.relations.backup_and_delete_relations(hashes)

    def restore_relation_metadata(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self.relations.restore_relation_metadata(hash_value)

    def restore_relation(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self.relations.restore_relation(hash_value)

    def restore_relation_status_from_snapshot(
        self,
        hash_value: str,
        snapshot: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return self.relations.restore_relation_status_from_snapshot(hash_value, snapshot)

    def get_deleted_relations(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.relations.get_deleted_relations(limit=limit)

    def get_deleted_relation(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self.relations.get_deleted_relation(hash_value)

    def purge_deleted_relations(
        self, *, cutoff_time: float, limit: int = 1000
    ) -> List[str]:
        return self.relations.purge_deleted_relations(cutoff_time=cutoff_time, limit=limit)

    def get_orphan_deleted_relation_hashes(self, limit: int = 200) -> List[str]:
        return self.relations.get_orphan_deleted_relation_hashes(limit=limit)

    def resolve_relation_hash_alias(
        self, value: str, *, include_deleted: bool = False
    ) -> List[str]:
        return self.relations.resolve_relation_hash_alias(
            value, include_deleted=include_deleted
        )

    def rebuild_relation_hash_aliases(self) -> Dict[str, Any]:
        return self.relations.rebuild_relation_hash_aliases()

    def search_relation_hashes_by_text(
        self, query: str, limit: int = 5
    ) -> List[str]:
        return self.relations.search_relation_hashes_by_text(query, limit=limit)

    def search_deleted_relation_hashes_by_text(
        self, query: str, limit: int = 5
    ) -> List[str]:
        return self.relations.search_deleted_relation_hashes_by_text(query, limit=limit)

    # =========================================================================
    # 人物画像（委托 ProfileStore）
    # =========================================================================

    def set_person_profile_switch(
        self,
        stream_id: str,
        user_id: str,
        enabled: bool,
        updated_at: Optional[float] = None,
    ) -> None:
        self.profiles.set_person_profile_switch(stream_id, user_id, enabled, updated_at)

    def get_person_profile_switch(
        self, stream_id: str, user_id: str, default: bool = False
    ) -> bool:
        return self.profiles.get_person_profile_switch(stream_id, user_id, default)

    def get_enabled_person_profile_switches(
        self, limit: int = 1000
    ) -> List[Dict[str, Any]]:
        return self.profiles.get_enabled_person_profile_switches(limit=limit)

    def mark_person_profile_active(
        self,
        stream_id: str,
        user_id: str,
        person_id: str,
        seen_at: Optional[float] = None,
    ) -> None:
        self.profiles.mark_person_profile_active(stream_id, user_id, person_id, seen_at)

    def get_active_person_ids_for_enabled_switches(
        self, active_after: Optional[float] = None, limit: int = 200
    ) -> List[str]:
        return self.profiles.get_active_person_ids_for_enabled_switches(
            active_after=active_after, limit=limit
        )

    def get_latest_person_profile_snapshot(
        self, person_id: str
    ) -> Optional[Dict[str, Any]]:
        return self.profiles.get_latest_person_profile_snapshot(person_id)

    def upsert_person_profile_snapshot(
        self,
        person_id: str,
        profile_text: str,
        aliases: Optional[List[str]] = None,
        relation_edges: Optional[List[Dict[str, Any]]] = None,
        vector_evidence: Optional[List[Dict[str, Any]]] = None,
        evidence_ids: Optional[List[str]] = None,
        expires_at: Optional[float] = None,
        source_note: str = "",
        updated_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self.profiles.upsert_person_profile_snapshot(
            person_id,
            profile_text,
            aliases=aliases,
            relation_edges=relation_edges,
            vector_evidence=vector_evidence,
            evidence_ids=evidence_ids,
            expires_at=expires_at,
            source_note=source_note,
            updated_at=updated_at,
        )

    def get_person_profile_override(self, person_id: str) -> Optional[Dict[str, Any]]:
        return self.profiles.get_person_profile_override(person_id)

    def set_person_profile_override(
        self,
        person_id: str,
        override_text: str,
        updated_by: str = "",
        source: str = "webui",
        updated_at: Optional[float] = None,
    ) -> Dict[str, Any]:
        return self.profiles.set_person_profile_override(
            person_id, override_text,
            updated_by=updated_by, source=source, updated_at=updated_at,
        )

    def delete_person_profile_override(self, person_id: str) -> bool:
        return self.profiles.delete_person_profile_override(person_id)

    def get_person_profile_refresh_request(
        self, person_id: str
    ) -> Optional[Dict[str, Any]]:
        return self.profiles.get_person_profile_refresh_request(person_id)

    def enqueue_person_profile_refresh(
        self,
        *,
        person_id: str,
        reason: str = "",
        source_query_tool_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        return self.profiles.enqueue_person_profile_refresh(
            person_id=person_id,
            reason=reason,
            source_query_tool_id=source_query_tool_id,
        )

    def fetch_person_profile_refresh_batch(
        self,
        *,
        limit: int = 20,
        max_retry: int = 3,
        debounce_seconds: float = 0.0,
        retry_backoff_seconds: float = 0.0,
    ) -> List[Dict[str, Any]]:
        return self.profiles.fetch_person_profile_refresh_batch(
            limit=limit,
            max_retry=max_retry,
            debounce_seconds=debounce_seconds,
            retry_backoff_seconds=retry_backoff_seconds,
        )

    def mark_person_profile_refresh_running(
        self, person_id: str, *, requested_at: Optional[float] = None
    ) -> bool:
        return self.profiles.mark_person_profile_refresh_running(
            person_id, requested_at=requested_at
        )

    def mark_person_profile_refresh_done(
        self, person_id: str, *, requested_at: Optional[float] = None
    ) -> bool:
        return self.profiles.mark_person_profile_refresh_done(
            person_id, requested_at=requested_at
        )

    def mark_person_profile_refresh_failed(
        self,
        person_id: str,
        error: str = "",
        *,
        requested_at: Optional[float] = None,
    ) -> bool:
        return self.profiles.mark_person_profile_refresh_failed(
            person_id, error, requested_at=requested_at
        )

    def list_person_profile_refresh_requests(
        self, *, statuses: Optional[List[str]] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        return self.profiles.list_person_profile_refresh_requests(
            statuses=statuses, limit=limit
        )

    def get_person_profile_refresh_summary(
        self, failed_limit: int = 20
    ) -> Dict[str, Any]:
        return self.profiles.get_person_profile_refresh_summary(failed_limit=failed_limit)

    # =========================================================================
    # FTS — 段落（委托 ParagraphStore）
    # =========================================================================

    def ensure_fts_schema(self, conn: Optional[sqlite3.Connection] = None) -> bool:
        return self.paragraphs.ensure_fts_schema()

    def ensure_fts_backfilled(self, conn: Optional[sqlite3.Connection] = None) -> bool:
        return self.paragraphs.ensure_fts_backfilled()

    def fts_upsert_paragraph(
        self, paragraph_hash: str, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.fts_upsert_paragraph(paragraph_hash)

    def fts_delete_paragraph(
        self, paragraph_hash: str, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.fts_delete_paragraph(paragraph_hash)

    def fts_search_bm25(
        self,
        match_query: str,
        limit: int = 20,
        max_doc_len: int = 2000,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        return self.paragraphs.fts_search_bm25(
            match_query, limit=limit, max_doc_len=max_doc_len
        )

    def fts_doc_count(self, conn: Optional[sqlite3.Connection] = None) -> int:
        return self.paragraphs.fts_doc_count()

    def ensure_paragraph_tokenized_fts_schema(
        self, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.ensure_paragraph_tokenized_fts_schema()

    def ensure_paragraph_tokenized_fts_backfilled(
        self, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.ensure_paragraph_tokenized_fts_backfilled()

    def fts_upsert_tokenized_paragraph(
        self, paragraph_hash: str, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.fts_upsert_tokenized_paragraph(paragraph_hash)

    def fts_delete_tokenized_paragraph(
        self, paragraph_hash: str, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.fts_delete_tokenized_paragraph(paragraph_hash)

    def fts_search_tokenized_paragraphs_bm25(
        self,
        match_query: str,
        limit: int = 20,
        max_doc_len: int = 2000,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        return self.paragraphs.fts_search_tokenized_paragraphs_bm25(
            match_query, limit=limit, max_doc_len=max_doc_len
        )

    def ensure_paragraph_ngram_schema(
        self, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.ensure_paragraph_ngram_schema()

    def is_paragraph_ngram_ready(
        self, n: int = 2, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.is_paragraph_ngram_ready(n)

    def ensure_paragraph_ngram_backfilled(
        self, n: int = 2, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.paragraphs.ensure_paragraph_ngram_backfilled(n)

    def ngram_search_paragraphs(
        self,
        tokens: List[str],
        limit: int = 20,
        max_doc_len: int = 2000,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        return self.paragraphs.ngram_search_paragraphs(
            tokens, limit=limit, max_doc_len=max_doc_len
        )

    # =========================================================================
    # FTS — 关系（委托 RelationStore）
    # =========================================================================

    def ensure_relations_fts_schema(
        self, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.relations.ensure_relations_fts_schema()

    def ensure_relations_fts_backfilled(
        self, conn: Optional[sqlite3.Connection] = None
    ) -> bool:
        return self.relations.ensure_relations_fts_backfilled()

    def fts_search_relations_bm25(
        self,
        match_query: str,
        limit: int = 20,
        max_doc_len: int = 512,
        include_inactive: bool = True,
        conn: Optional[sqlite3.Connection] = None,
    ) -> List[Dict[str, Any]]:
        return self.relations.fts_search_relations_bm25(
            match_query,
            limit=limit,
            max_doc_len=max_doc_len,
            include_inactive=include_inactive,
        )

    # =========================================================================
    # 向量 / 记忆标记 / 访问记录（直接操作，不委托）
    # =========================================================================

    def update_vector_index(
        self, item_type: str, hash_value: str, vector_index: int
    ) -> bool:
        valid_types = ["paragraph", "entity", "relation"]
        if item_type not in valid_types:
            raise ValueError(f"无效的类型: {item_type}")
        table_map = {
            "paragraph": "paragraphs",
            "entity": "entities",
            "relation": "relations",
        }
        cursor = self._conn.cursor()
        cursor.execute(
            f"UPDATE {table_map[item_type]} SET vector_index = ? WHERE hash = ?",
            (vector_index, hash_value),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def set_permanence(
        self, hash_value: str, item_type: str, is_permanent: bool
    ) -> bool:
        table_map = {"paragraph": "paragraphs", "relation": "relations"}
        if item_type not in table_map:
            raise ValueError(f"类型 {item_type} 不支持设置永久性")
        cursor = self._conn.cursor()
        cursor.execute(
            f"UPDATE {table_map[item_type]} SET is_permanent = ? WHERE hash = ?",
            (1 if is_permanent else 0, hash_value),
        )
        self._conn.commit()
        if cursor.rowcount > 0:
            logger.debug(f"设置永久记忆: {item_type}/{hash_value[:8]} -> {is_permanent}")
            return True
        return False

    def record_access(self, hash_value: str, item_type: str) -> bool:
        table_map = {"paragraph": "paragraphs", "relation": "relations"}
        if item_type not in table_map:
            return False
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            UPDATE {table_map[item_type]}
            SET last_accessed = ?, access_count = access_count + 1
            WHERE hash = ?
            """,
            (now, hash_value),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # =========================================================================
    # 通用查询
    # =========================================================================

    def query(
        self, sql: str, params: Optional[Tuple] = None
    ) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        return [dict(row) for row in cursor.fetchall()]

    def get_statistics(self) -> Dict[str, int]:
        cursor = self._conn.cursor()
        stats = {}
        cursor.execute("SELECT COUNT(*) FROM paragraphs")
        stats["paragraph_count"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM entities")
        stats["entity_count"] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM relations")
        stats["relation_count"] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM person_profile_refresh_queue "
            "WHERE status IN ('pending', 'running', 'failed')"
        )
        stats["person_profile_refresh_pending_count"] = cursor.fetchone()[0]
        cursor.execute(
            "SELECT COUNT(*) FROM person_profile_refresh_queue WHERE status = 'failed'"
        )
        stats["person_profile_refresh_failed_count"] = cursor.fetchone()[0]
        cursor.execute("SELECT SUM(word_count) FROM paragraphs")
        result = cursor.fetchone()[0]
        stats["total_words"] = result if result else 0
        return stats

    def vacuum(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute("VACUUM")
        self._conn.commit()
        logger.info("数据库优化完成")

    def clear_all(self) -> None:
        cursor = self._conn.cursor()
        tables = [
            "paragraphs", "entities", "relations",
            "paragraph_relations", "paragraph_entities",
            "episodes", "episode_paragraphs",
            "episode_rebuild_sources", "episode_pending_paragraphs",
            "paragraph_vector_backfill",
            "person_profile_refresh_queue",
        ]
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")
        self._conn.commit()
        logger.info("元数据存储所有表已清空")

    def list_hashes(self, table: str) -> List[str]:
        allowed = {"paragraphs", "entities", "relations", "deleted_relations"}
        token = str(table or "").strip().lower()
        if token not in allowed:
            raise ValueError(f"unsupported table for list_hashes: {table}")
        cursor = self._conn.cursor()
        cursor.execute(f"SELECT hash FROM {token}")
        return [str(row[0]) for row in cursor.fetchall()]

    def shrink_memory(self, conn: Optional[sqlite3.Connection] = None) -> None:
        c = self._resolve_conn(conn)
        try:
            c.execute("PRAGMA shrink_memory")
        except sqlite3.OperationalError:
            pass

    # =========================================================================
    # 软删除 / GC（委托子 Store + 门面协调）
    # =========================================================================

    def mark_as_deleted(self, hashes: List[str], type_: str) -> int:
        if not hashes:
            return 0
        if type_ == "entity":
            return self.entities.mark_as_deleted(hashes)
        else:
            touched_sources = self.paragraphs._get_sources_for_paragraph_hashes(
                hashes, include_deleted=True
            )
            count = self.paragraphs.mark_as_deleted(hashes)
            if count > 0:
                self._enqueue_episode_source_rebuilds(
                    touched_sources, reason="paragraph_soft_deleted"
                )
            return count

    def sweep_deleted_items(
        self, type_: str, grace_period_seconds: float
    ) -> List[Tuple[str, str]]:
        if type_ == "entity":
            return self.entities.sweep_deleted_items(grace_period_seconds)
        return self.paragraphs.sweep_deleted_items(grace_period_seconds)

    def physically_delete_entities(self, hashes: List[str]) -> int:
        return self.entities.physically_delete_entities(hashes)

    def physically_delete_paragraphs(self, hashes: List[str]) -> int:
        touched_sources = self.paragraphs._get_sources_for_paragraph_hashes(
            hashes, include_deleted=True
        )
        count = self.paragraphs.physically_delete_paragraphs(hashes)
        if count > 0:
            self._enqueue_episode_source_rebuilds(
                touched_sources, reason="paragraph_physically_deleted"
            )
        return count

    def revive_if_deleted(
        self,
        entity_hashes: List[str] = None,
        paragraph_hashes: List[str] = None,
    ) -> int:
        count = 0
        touched_sources: List[str] = []

        if entity_hashes:
            count += self.entities.revive_if_deleted(entity_hashes)

        if paragraph_hashes:
            touched_sources = self.paragraphs._get_sources_for_paragraph_hashes(
                paragraph_hashes, include_deleted=True
            )
            count += self.paragraphs.revive_if_deleted(paragraph_hashes)

        if count > 0:
            if touched_sources:
                self._enqueue_episode_source_rebuilds(
                    touched_sources, reason="paragraph_revived"
                )
            logger.info(f"自动复活: {count} 项 (Soft Delete Revived)")
        return count

    def revive_entities_by_names(self, names: List[str]) -> int:
        return self.entities.revive_entities_by_names(names)

    def restore_entity_by_hash(self, entity_hash: str) -> bool:
        return self.entities.restore_entity_by_hash(entity_hash)

    def restore_paragraph_by_hash(self, paragraph_hash: str) -> bool:
        return self.paragraphs.restore_paragraph_by_hash(paragraph_hash)

    def get_entity_status_batch(
        self, hashes: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        return self.entities.get_entity_status_batch(hashes)

    def get_deleted_entities(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.has_table("entities"):
            return []
        return self.entities.get_deleted_entities(limit=limit)

    def get_entity_gc_candidates(
        self, isolated_hashes: List[str], retention_seconds: float
    ) -> List[str]:
        return self.entities.get_entity_gc_candidates(isolated_hashes, retention_seconds)

    def get_paragraph_gc_candidates(self, retention_seconds: float) -> List[str]:
        return self.paragraphs.get_paragraph_gc_candidates(retention_seconds)

    # =========================================================================
    # 外部记忆引用
    # =========================================================================

    def get_external_memory_ref(self, external_id: str) -> Optional[Dict[str, Any]]:
        token = str(external_id or "").strip()
        if not token:
            return None
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT external_id, paragraph_hash, source_type, created_at, metadata_json
            FROM external_memory_refs WHERE external_id = ? LIMIT 1
            """,
            (token,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        payload = dict(row)
        raw_metadata = payload.get("metadata_json")
        if raw_metadata:
            try:
                payload["metadata"] = json.loads(raw_metadata)
            except Exception:
                payload["metadata"] = {}
        else:
            payload["metadata"] = {}
        return payload

    def upsert_external_memory_ref(
        self,
        *,
        external_id: str,
        paragraph_hash: str,
        source_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        external_token = str(external_id or "").strip()
        paragraph_token = str(paragraph_hash or "").strip()
        if not external_token:
            raise ValueError("external_id 不能为空")
        if not paragraph_token:
            raise ValueError("paragraph_hash 不能为空")

        now = datetime.now().timestamp()
        metadata_json_val = json.dumps(metadata or {}, ensure_ascii=False)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO external_memory_refs (
                external_id, paragraph_hash, source_type, created_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(external_id) DO UPDATE SET
                paragraph_hash = excluded.paragraph_hash,
                source_type = excluded.source_type,
                metadata_json = excluded.metadata_json
            """,
            (
                external_token,
                paragraph_token,
                str(source_type or "").strip() or None,
                now,
                metadata_json_val,
            ),
        )
        self._conn.commit()
        return self.get_external_memory_ref(external_token) or {
            "external_id": external_token,
            "paragraph_hash": paragraph_token,
            "source_type": str(source_type or "").strip(),
            "created_at": now,
            "metadata": metadata or {},
        }

    def list_external_memory_refs_by_paragraphs(
        self, paragraph_hashes: List[str]
    ) -> List[Dict[str, Any]]:
        hashes = [
            str(item or "").strip()
            for item in (paragraph_hashes or [])
            if str(item or "").strip()
        ]
        if not hashes:
            return []
        placeholders = ",".join(["?"] * len(hashes))
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            SELECT external_id, paragraph_hash, source_type, created_at, metadata_json
            FROM external_memory_refs
            WHERE paragraph_hash IN ({placeholders})
            ORDER BY created_at ASC, external_id ASC
            """,
            tuple(hashes),
        )
        items: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            payload = dict(row)
            payload["metadata"] = json_loads(payload.get("metadata_json"), {})
            items.append(payload)
        return items

    def delete_external_memory_refs_by_paragraphs(
        self, paragraph_hashes: List[str]
    ) -> List[Dict[str, Any]]:
        items = self.list_external_memory_refs_by_paragraphs(paragraph_hashes)
        hashes = [
            str(item or "").strip()
            for item in (paragraph_hashes or [])
            if str(item or "").strip()
        ]
        if not hashes:
            return items
        placeholders = ",".join(["?"] * len(hashes))
        cursor = self._conn.cursor()
        cursor.execute(
            f"DELETE FROM external_memory_refs WHERE paragraph_hash IN ({placeholders})",
            tuple(hashes),
        )
        self._conn.commit()
        return items

    def restore_external_memory_refs(self, refs: List[Dict[str, Any]]) -> int:
        count = 0
        for item in refs or []:
            external_id = str(item.get("external_id", "")).strip()
            paragraph_hash = str(item.get("paragraph_hash", "")).strip()
            if not external_id or not paragraph_hash:
                continue
            created_at = float(item.get("created_at") or datetime.now().timestamp())
            metadata_json_val = json_dumps(item.get("metadata") or {})
            cursor = self._conn.cursor()
            cursor.execute(
                """
                INSERT INTO external_memory_refs (
                    external_id, paragraph_hash, source_type, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(external_id) DO UPDATE SET
                    paragraph_hash = excluded.paragraph_hash,
                    source_type = excluded.source_type,
                    created_at = excluded.created_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    external_id,
                    paragraph_hash,
                    str(item.get("source_type", "")).strip() or None,
                    created_at,
                    metadata_json_val,
                ),
            )
            count += max(0, int(cursor.rowcount or 0))
        self._conn.commit()
        return count

    # =========================================================================
    # V5 操作日志 / 删除操作记录
    # =========================================================================

    def record_v5_operation(
        self,
        *,
        action: str,
        target: str,
        resolved_hashes: List[str],
        reason: str = "",
        updated_by: str = "",
        result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        operation_id = f"v5_{uuid.uuid7().hex}"
        created_at = datetime.now().timestamp()
        payload = {
            "operation_id": operation_id,
            "action": str(action or "").strip(),
            "target": str(target or "").strip(),
            "reason": str(reason or "").strip(),
            "updated_by": str(updated_by or "").strip(),
            "created_at": created_at,
            "resolved_hashes": [
                str(item or "").strip()
                for item in (resolved_hashes or [])
                if str(item or "").strip()
            ],
            "result": result or {},
        }
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory_v5_operations (
                operation_id, action, target, reason, updated_by, created_at,
                resolved_hashes_json, result_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                operation_id,
                payload["action"],
                payload["target"] or None,
                payload["reason"] or None,
                payload["updated_by"] or None,
                created_at,
                json_dumps(payload["resolved_hashes"]),
                json_dumps(payload["result"]),
            ),
        )
        self._conn.commit()
        return payload

    def create_delete_operation(
        self,
        *,
        mode: str,
        selector: Any,
        items: List[Dict[str, Any]],
        reason: str = "",
        requested_by: str = "",
        status: str = "executed",
        summary: Optional[Dict[str, Any]] = None,
        operation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        op_id = str(operation_id or f"del_{uuid.uuid7().hex}").strip()
        created_at = datetime.now().timestamp()
        normalized_items: List[Dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("item_type", "")).strip()
            if not item_type:
                continue
            normalized_items.append(
                {
                    "item_type": item_type,
                    "item_hash": str(item.get("item_hash", "")).strip() or None,
                    "item_key": str(
                        item.get("item_key", "") or item.get("item_hash", "") or ""
                    ).strip()
                    or None,
                    "payload": (
                        item.get("payload")
                        if isinstance(item.get("payload"), dict)
                        else {}
                    ),
                }
            )
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO delete_operations (
                operation_id, mode, selector, reason, requested_by,
                status, created_at, restored_at, summary_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                op_id,
                str(mode or "").strip(),
                json_dumps(selector if selector is not None else {}),
                str(reason or "").strip() or None,
                str(requested_by or "").strip() or None,
                str(status or "executed").strip(),
                created_at,
                json_dumps(summary or {}),
            ),
        )
        if normalized_items:
            cursor.executemany(
                """
                INSERT INTO delete_operation_items (
                    operation_id, item_type, item_hash, item_key, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        op_id,
                        item["item_type"],
                        item["item_hash"],
                        item["item_key"],
                        json_dumps(item["payload"]),
                        created_at,
                    )
                    for item in normalized_items
                ],
            )
        self._conn.commit()
        return self.get_delete_operation(op_id) or {
            "operation_id": op_id,
            "mode": str(mode or "").strip(),
            "selector": selector,
            "reason": str(reason or "").strip(),
            "requested_by": str(requested_by or "").strip(),
            "status": str(status or "executed").strip(),
            "created_at": created_at,
            "summary": summary or {},
            "items": normalized_items,
        }

    def mark_delete_operation_restored(
        self,
        operation_id: str,
        *,
        summary: Optional[Dict[str, Any]] = None,
    ) -> bool:
        token = str(operation_id or "").strip()
        if not token:
            return False
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE delete_operations
            SET status = ?, restored_at = ?, summary_json = ?
            WHERE operation_id = ?
            """,
            ("restored", datetime.now().timestamp(), json_dumps(summary or {}), token),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_delete_operations(
        self, *, limit: int = 50, mode: str = ""
    ) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        params: List[Any] = []
        where = ""
        mode_token = str(mode or "").strip().lower()
        if mode_token:
            where = "WHERE LOWER(mode) = ?"
            params.append(mode_token)
        params.append(max(1, int(limit or 50)))
        cursor.execute(
            f"""
            SELECT operation_id, mode, selector, reason, requested_by, status,
                   created_at, restored_at, summary_json
            FROM delete_operations
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(params),
        )
        items: List[Dict[str, Any]] = []
        for row in cursor.fetchall():
            payload = dict(row)
            payload["selector"] = json_loads(payload.get("selector"), {})
            payload["summary"] = json_loads(payload.get("summary_json"), {})
            items.append(payload)
        return items

    def get_delete_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        token = str(operation_id or "").strip()
        if not token:
            return None
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT operation_id, mode, selector, reason, requested_by, status,
                   created_at, restored_at, summary_json
            FROM delete_operations
            WHERE operation_id = ?
            LIMIT 1
            """,
            (token,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        payload = dict(row)
        payload["selector"] = json_loads(payload.get("selector"), {})
        payload["summary"] = json_loads(payload.get("summary_json"), {})
        cursor.execute(
            """
            SELECT item_type, item_hash, item_key, payload_json, created_at
            FROM delete_operation_items
            WHERE operation_id = ?
            ORDER BY id ASC
            """,
            (token,),
        )
        payload["items"] = [
            {
                "item_type": str(item["item_type"] or ""),
                "item_hash": str(item["item_hash"] or ""),
                "item_key": str(item["item_key"] or ""),
                "payload": json_loads(item["payload_json"], {}),
                "created_at": item["created_at"],
            }
            for item in cursor.fetchall()
        ]
        return payload

    # =========================================================================
    # 跨表查询方法（门面层直接使用 self._conn）
    # =========================================================================

    def get_paragraph_relations(self, paragraph_hash: str) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT r.* FROM relations r
            JOIN paragraph_relations pr ON r.hash = pr.relation_hash
            WHERE pr.paragraph_hash = ?
            """,
            (paragraph_hash,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_paragraph_hashes_by_relation_hashes(
        self, relation_hashes: List[str]
    ) -> Dict[str, List[str]]:
        normalized = normalize_hash_sequence(relation_hashes)
        if not normalized:
            return {}
        placeholders = ",".join(["?"] * len(normalized))
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            SELECT pr.relation_hash, pr.paragraph_hash
            FROM paragraph_relations pr
            JOIN paragraphs p ON p.hash = pr.paragraph_hash
            WHERE pr.relation_hash IN ({placeholders})
              AND (p.is_deleted IS NULL OR p.is_deleted = 0)
            ORDER BY pr.relation_hash ASC, p.updated_at DESC, p.created_at DESC, pr.paragraph_hash ASC
            """,
            tuple(normalized),
        )
        grouped: Dict[str, List[str]] = {token: [] for token in normalized}
        for row in cursor.fetchall():
            relation_hash = str(row["relation_hash"] or "").strip()
            paragraph_hash = str(row["paragraph_hash"] or "").strip()
            if not relation_hash or not paragraph_hash:
                continue
            if paragraph_hash not in grouped.setdefault(relation_hash, []):
                grouped[relation_hash].append(paragraph_hash)
        return grouped

    def get_paragraph_entities(self, paragraph_hash: str) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT e.*, pe.mention_count
            FROM entities e
            JOIN paragraph_entities pe ON e.hash = pe.entity_hash
            WHERE pe.paragraph_hash = ?
            """,
            (paragraph_hash,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_paragraph_entities_by_hashes(
        self, paragraph_hashes: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        normalized = normalize_hash_sequence(paragraph_hashes)
        if not normalized:
            return {}
        grouped: Dict[str, List[Dict[str, Any]]] = {
            hash_value: [] for hash_value in normalized
        }
        cursor = self._conn.cursor()
        for batch in iter_sql_batches(normalized):
            placeholders = ",".join(["?"] * len(batch))
            cursor.execute(
                f"""
                SELECT pe.paragraph_hash, e.*, pe.mention_count
                FROM paragraph_entities pe
                JOIN entities e ON e.hash = pe.entity_hash
                WHERE pe.paragraph_hash IN ({placeholders})
                """,
                tuple(batch),
            )
            for row in cursor.fetchall():
                paragraph_hash = str(row["paragraph_hash"] or "").strip()
                if not paragraph_hash:
                    continue
                grouped.setdefault(paragraph_hash, []).append(row_to_dict(row))
        return grouped

    def get_paragraphs_by_entity(self, entity_name: str) -> List[Dict[str, Any]]:
        name_canon = canonicalize_name(entity_name)
        if not name_canon:
            return []
        entity_hash = compute_hash(name_canon)
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT p.* FROM paragraphs p
            JOIN paragraph_entities pe ON p.hash = pe.paragraph_hash
            WHERE pe.entity_hash = ?
            """,
            (entity_hash,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_paragraph_hashes_by_entity_hashes(
        self, entity_hashes: Sequence[str]
    ) -> Dict[str, List[str]]:
        normalized = normalize_hash_sequence(entity_hashes)
        if not normalized:
            return {}
        grouped: Dict[str, List[str]] = {hash_value: [] for hash_value in normalized}
        cursor = self._conn.cursor()
        for batch in iter_sql_batches(normalized):
            placeholders = ",".join(["?"] * len(batch))
            cursor.execute(
                f"""
                SELECT pe.entity_hash, pe.paragraph_hash
                FROM paragraph_entities pe
                JOIN paragraphs p ON p.hash = pe.paragraph_hash
                WHERE pe.entity_hash IN ({placeholders})
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                ORDER BY pe.entity_hash ASC, p.updated_at DESC, p.created_at DESC, pe.paragraph_hash ASC
                """,
                tuple(batch),
            )
            for row in cursor.fetchall():
                entity_hash = str(row["entity_hash"] or "").strip()
                paragraph_hash = str(row["paragraph_hash"] or "").strip()
                if not entity_hash or not paragraph_hash:
                    continue
                if paragraph_hash not in grouped.setdefault(entity_hash, []):
                    grouped[entity_hash].append(paragraph_hash)
        return grouped

    def get_paragraphs_by_entity_hashes(
        self, entity_hashes: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        normalized = normalize_hash_sequence(entity_hashes)
        if not normalized:
            return {}
        grouped: Dict[str, List[Dict[str, Any]]] = {
            hash_value: [] for hash_value in normalized
        }
        cursor = self._conn.cursor()
        for batch in iter_sql_batches(normalized):
            placeholders = ",".join(["?"] * len(batch))
            cursor.execute(
                f"""
                SELECT pe.entity_hash, p.*
                FROM paragraph_entities pe
                JOIN paragraphs p ON p.hash = pe.paragraph_hash
                WHERE pe.entity_hash IN ({placeholders})
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                ORDER BY pe.entity_hash ASC, p.updated_at DESC, p.created_at DESC, pe.paragraph_hash ASC
                """,
                tuple(batch),
            )
            for row in cursor.fetchall():
                entity_hash = str(row["entity_hash"] or "").strip()
                if not entity_hash:
                    continue
                grouped.setdefault(entity_hash, []).append(row_to_dict(row))
        return grouped

    def get_paragraphs_by_relation(self, relation_hash: str) -> List[Dict[str, Any]]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT p.* FROM paragraphs p
            JOIN paragraph_relations pr ON p.hash = pr.paragraph_hash
            WHERE pr.relation_hash = ?
            """,
            (relation_hash,),
        )
        return [row_to_dict(row) for row in cursor.fetchall()]

    def get_paragraphs_by_relation_hashes(
        self, relation_hashes: Sequence[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        normalized = normalize_hash_sequence(relation_hashes)
        if not normalized:
            return {}
        grouped: Dict[str, List[Dict[str, Any]]] = {
            hash_value: [] for hash_value in normalized
        }
        cursor = self._conn.cursor()
        for batch in iter_sql_batches(normalized):
            placeholders = ",".join(["?"] * len(batch))
            cursor.execute(
                f"""
                SELECT pr.relation_hash, p.*
                FROM paragraph_relations pr
                JOIN paragraphs p ON p.hash = pr.paragraph_hash
                WHERE pr.relation_hash IN ({placeholders})
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                ORDER BY pr.relation_hash ASC, p.updated_at DESC, p.created_at DESC, pr.paragraph_hash ASC
                """,
                tuple(batch),
            )
            for row in cursor.fetchall():
                relation_hash = str(row["relation_hash"] or "").strip()
                if not relation_hash:
                    continue
                grouped.setdefault(relation_hash, []).append(row_to_dict(row))
        return grouped

    # =========================================================================
    # Episode 内部辅助（门面私有）
    # =========================================================================

    def _enqueue_episode_source_rebuilds(
        self, sources: List[Any], reason: str = ""
    ) -> int:
        normalized_sources = dedupe_episode_sources(sources)
        if not normalized_sources:
            return 0
        now = datetime.now().timestamp()
        reason_text = str(reason or "").strip()[:200] or None
        cursor = self._conn.cursor()
        cursor.executemany(
            """
            INSERT INTO episode_rebuild_sources (
                source, status, retry_count, last_error, reason, requested_at, updated_at
            ) VALUES (?, 'pending', 0, NULL, ?, ?, ?)
            ON CONFLICT(source) DO UPDATE SET
                status = 'pending',
                last_error = NULL,
                reason = excluded.reason,
                requested_at = excluded.requested_at,
                updated_at = excluded.updated_at
            """,
            [(source, reason_text, now, now) for source in normalized_sources],
        )
        self._conn.commit()
        return len(normalized_sources)

    # =========================================================================
    # Episode MVP（方法体保持不变，直接使用 self._conn）
    # =========================================================================

    def enqueue_episode_source_rebuild(self, source: str, reason: str = "") -> bool:
        return bool(self._enqueue_episode_source_rebuilds([source], reason=reason))

    def fetch_episode_source_rebuild_batch(
        self, limit: int = 20, max_retry: int = 3
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit))
        safe_retry = max(0, int(max_retry))
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT source, status, retry_count, last_error, reason, requested_at, updated_at
            FROM episode_rebuild_sources
            WHERE status = 'pending'
               OR (status = 'failed' AND retry_count < ?)
            ORDER BY requested_at ASC, updated_at ASC
            LIMIT ?
            """,
            (safe_retry, safe_limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def mark_episode_source_running(
        self, source: str, *, requested_at: Optional[float] = None
    ) -> bool:
        token = normalize_episode_source(source)
        if not token:
            return False
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        params: List[Any] = [now, token]
        sql = """
            UPDATE episode_rebuild_sources
            SET status = 'running', updated_at = ?
            WHERE source = ? AND status IN ('pending', 'failed')
        """
        if requested_at is not None:
            sql += " AND requested_at = ?"
            params.append(float(requested_at))
        cursor.execute(sql, tuple(params))
        self._conn.commit()
        return cursor.rowcount > 0

    def mark_episode_source_done(
        self, source: str, *, requested_at: Optional[float] = None
    ) -> bool:
        token = normalize_episode_source(source)
        if not token:
            return False
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        if requested_at is None:
            cursor.execute(
                """
                UPDATE episode_rebuild_sources
                SET status = 'done', last_error = NULL, updated_at = ?
                WHERE source = ?
                """,
                (now, token),
            )
        else:
            req_ts = float(requested_at)
            cursor.execute(
                """
                UPDATE episode_rebuild_sources
                SET status = CASE WHEN requested_at > ? THEN 'pending' ELSE 'done' END,
                    last_error = NULL, updated_at = ?
                WHERE source = ?
                """,
                (req_ts, now, token),
            )
        self._conn.commit()
        return cursor.rowcount > 0

    def mark_episode_source_failed(
        self, source: str, error: str = "", *, requested_at: Optional[float] = None
    ) -> bool:
        token = normalize_episode_source(source)
        if not token:
            return False
        err_text = str(error or "").strip()[:500]
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        if requested_at is None:
            cursor.execute(
                """
                UPDATE episode_rebuild_sources
                SET status = 'failed',
                    retry_count = COALESCE(retry_count, 0) + 1,
                    last_error = ?, updated_at = ?
                WHERE source = ?
                """,
                (err_text, now, token),
            )
        else:
            req_ts = float(requested_at)
            cursor.execute(
                """
                UPDATE episode_rebuild_sources
                SET status = CASE WHEN requested_at > ? THEN 'pending' ELSE 'failed' END,
                    retry_count = CASE
                        WHEN requested_at > ? THEN COALESCE(retry_count, 0)
                        ELSE COALESCE(retry_count, 0) + 1
                    END,
                    last_error = CASE WHEN requested_at > ? THEN NULL ELSE ? END,
                    updated_at = ?
                WHERE source = ?
                """,
                (req_ts, req_ts, req_ts, err_text, now, token),
            )
        self._conn.commit()
        return cursor.rowcount > 0

    def list_episode_source_rebuilds(
        self, *, statuses: Optional[List[str]] = None, limit: int = 100
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit))
        params: List[Any] = []
        conditions: List[str] = []
        normalized_statuses = [
            str(item or "").strip().lower()
            for item in (statuses or [])
            if str(item or "").strip().lower()
            in {"pending", "running", "done", "failed"}
        ]
        if normalized_statuses:
            placeholders = ",".join(["?"] * len(normalized_statuses))
            conditions.append(f"status IN ({placeholders})")
            params.extend(normalized_statuses)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(safe_limit)
        cursor = self._conn.cursor()
        cursor.execute(
            f"""
            SELECT source, status, retry_count, last_error, reason, requested_at, updated_at
            FROM episode_rebuild_sources
            {where_sql}
            ORDER BY updated_at DESC, source ASC
            LIMIT ?
            """,
            tuple(params),
        )
        return [dict(row) for row in cursor.fetchall()]

    def get_episode_source_rebuild_summary(
        self, failed_limit: int = 20
    ) -> Dict[str, Any]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT status, COUNT(*) AS cnt FROM episode_rebuild_sources GROUP BY status"
        )
        counts = {"pending": 0, "running": 0, "done": 0, "failed": 0, "total": 0}
        for row in cursor.fetchall():
            status = str(row["status"] or "").strip().lower()
            cnt = int(row["cnt"] or 0)
            counts[status] = counts.get(status, 0) + cnt
            counts["total"] += cnt
        running = self.list_episode_source_rebuilds(statuses=["running"], limit=20)
        failed = self.list_episode_source_rebuilds(
            statuses=["failed"], limit=max(1, int(failed_limit))
        )
        return {"counts": counts, "running": running, "failed": failed}

    def list_episode_sources_for_rebuild(self) -> List[str]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT DISTINCT source
            FROM (
                SELECT TRIM(source) AS source
                FROM paragraphs
                WHERE TRIM(COALESCE(source, '')) != ''
                  AND (is_deleted IS NULL OR is_deleted = 0)
                UNION
                SELECT TRIM(source) AS source
                FROM episodes
                WHERE TRIM(COALESCE(source, '')) != ''
            )
            WHERE TRIM(COALESCE(source, '')) != ''
            ORDER BY source ASC
            """
        )
        return dedupe_episode_sources([row["source"] for row in cursor.fetchall()])

    def is_episode_source_query_blocked(self, source: str) -> bool:
        token = normalize_episode_source(source)
        if not token:
            return False
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT 1 FROM episode_rebuild_sources
            WHERE source = ? AND status IN ('pending', 'running', 'failed')
            LIMIT 1
            """,
            (token,),
        )
        return cursor.fetchone() is not None

    def replace_episodes_for_source(
        self, source: str, episodes_payloads: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        token = normalize_episode_source(source)
        if not token:
            return {"source": "", "episode_count": 0}
        payloads = [
            dict(item) for item in (episodes_payloads or []) if isinstance(item, dict)
        ]
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        try:
            cursor.execute("BEGIN IMMEDIATE")
            cursor.execute(
                "SELECT episode_id, created_at FROM episodes WHERE TRIM(COALESCE(source, '')) = ?",
                (token,),
            )
            existing_created_at = {
                str(row["episode_id"]): as_optional_float(row["created_at"])
                for row in cursor.fetchall()
            }
            cursor.execute(
                "DELETE FROM episodes WHERE TRIM(COALESCE(source, '')) = ?", (token,)
            )
            inserted_count = 0
            for raw_payload in payloads:
                title = str(raw_payload.get("title", "")).strip()
                summary = str(raw_payload.get("summary", "")).strip()
                evidence_ids = [
                    str(item).strip()
                    for item in (raw_payload.get("evidence_ids") or [])
                    if str(item).strip()
                ]
                evidence_ids = list(dict.fromkeys(evidence_ids))
                if not title or not summary or not evidence_ids:
                    continue
                episode_id = str(raw_payload.get("episode_id", "")).strip()
                if not episode_id:
                    seed = json.dumps(
                        {
                            "source": token,
                            "title": title,
                            "summary": summary,
                            "event_time_start": raw_payload.get("event_time_start"),
                            "event_time_end": raw_payload.get("event_time_end"),
                            "evidence_ids": evidence_ids,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    episode_id = compute_hash(seed)
                participants = [
                    str(item).strip()
                    for item in (raw_payload.get("participants") or [])
                    if str(item).strip()
                ][:16]
                keywords = [
                    str(item).strip()
                    for item in (raw_payload.get("keywords") or [])
                    if str(item).strip()
                ][:20]
                paragraph_count = raw_payload.get(
                    "paragraph_count", len(evidence_ids)
                )
                try:
                    paragraph_count = max(0, int(paragraph_count))
                except Exception:
                    paragraph_count = len(evidence_ids)
                if paragraph_count <= 0:
                    continue
                time_confidence = raw_payload.get("time_confidence", 1.0)
                llm_confidence = raw_payload.get("llm_confidence", 0.0)
                try:
                    time_confidence = float(time_confidence)
                except Exception:
                    time_confidence = 1.0
                try:
                    llm_confidence = float(llm_confidence)
                except Exception:
                    llm_confidence = 0.0
                created_at = existing_created_at.get(episode_id)
                created_ts = created_at if created_at is not None else now
                updated_ts = as_optional_float(raw_payload.get("updated_at")) or now
                cursor.execute(
                    """
                    INSERT INTO episodes (
                        episode_id, source, title, summary,
                        event_time_start, event_time_end, time_granularity, time_confidence,
                        participants_json, keywords_json, evidence_ids_json,
                        paragraph_count, llm_confidence, segmentation_model, segmentation_version,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        episode_id, token, title[:120], summary[:2000],
                        as_optional_float(raw_payload.get("event_time_start")),
                        as_optional_float(raw_payload.get("event_time_end")),
                        str(raw_payload.get("time_granularity", "")).strip() or None,
                        time_confidence,
                        json.dumps(participants, ensure_ascii=False),
                        json.dumps(keywords, ensure_ascii=False),
                        json.dumps(evidence_ids, ensure_ascii=False),
                        paragraph_count, llm_confidence,
                        str(raw_payload.get("segmentation_model", "")).strip() or None,
                        str(raw_payload.get("segmentation_version", "")).strip() or None,
                        created_ts, updated_ts,
                    ),
                )
                cursor.executemany(
                    """
                    INSERT OR IGNORE INTO episode_paragraphs (episode_id, paragraph_hash, position)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (episode_id, hash_value, idx)
                        for idx, hash_value in enumerate(evidence_ids)
                    ],
                )
                inserted_count += 1
            self._conn.commit()
            return {"source": token, "episode_count": inserted_count}
        except Exception:
            self._conn.rollback()
            raise

    def enqueue_episode_pending(
        self,
        paragraph_hash: str,
        source: Optional[str] = None,
        created_at: Optional[float] = None,
    ) -> None:
        token = str(paragraph_hash or "").strip()
        if not token:
            return
        now = datetime.now().timestamp()
        created_ts = float(created_at) if created_at is not None else now
        src = str(source or "").strip() or None
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO episode_pending_paragraphs (
                paragraph_hash, source, created_at, status, retry_count, last_error, updated_at
            ) VALUES (?, ?, ?, 'pending', 0, NULL, ?)
            ON CONFLICT(paragraph_hash) DO UPDATE SET
                source = excluded.source,
                created_at = COALESCE(episode_pending_paragraphs.created_at, excluded.created_at),
                status = CASE
                    WHEN episode_pending_paragraphs.status = 'done' THEN 'done'
                    ELSE 'pending'
                END,
                last_error = CASE
                    WHEN episode_pending_paragraphs.status = 'done'
                    THEN episode_pending_paragraphs.last_error
                    ELSE NULL
                END,
                updated_at = excluded.updated_at
            """,
            (token, src, created_ts, now),
        )
        self._conn.commit()

    def fetch_episode_pending_batch(
        self, limit: int = 20, max_retry: int = 3
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit))
        safe_retry = max(0, int(max_retry))
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT paragraph_hash, source, created_at, status, retry_count, last_error, updated_at
            FROM episode_pending_paragraphs
            WHERE status = 'pending'
               OR (status = 'failed' AND retry_count < ?)
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (safe_retry, safe_limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def mark_episode_pending_running(self, hashes: List[str]) -> None:
        if not hashes:
            return
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        chunk_size = 500
        uniq = list(
            dict.fromkeys([str(h).strip() for h in hashes if str(h).strip()])
        )
        for i in range(0, len(uniq), chunk_size):
            chunk = uniq[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            cursor.execute(
                f"""
                UPDATE episode_pending_paragraphs
                SET status = 'running', updated_at = ?
                WHERE paragraph_hash IN ({placeholders})
                  AND status IN ('pending', 'failed')
                """,
                [now] + chunk,
            )
        self._conn.commit()

    def mark_episode_pending_done(self, hashes: List[str]) -> None:
        if not hashes:
            return
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        chunk_size = 500
        uniq = list(
            dict.fromkeys([str(h).strip() for h in hashes if str(h).strip()])
        )
        for i in range(0, len(uniq), chunk_size):
            chunk = uniq[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            cursor.execute(
                f"""
                UPDATE episode_pending_paragraphs
                SET status = 'done', last_error = NULL, updated_at = ?
                WHERE paragraph_hash IN ({placeholders})
                """,
                [now] + chunk,
            )
        self._conn.commit()

    def mark_episode_pending_failed(self, hash_value: str, error: str = "") -> None:
        token = str(hash_value or "").strip()
        if not token:
            return
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE episode_pending_paragraphs
            SET status = 'failed',
                retry_count = COALESCE(retry_count, 0) + 1,
                last_error = ?, updated_at = ?
            WHERE paragraph_hash = ?
            """,
            (str(error or ""), now, token),
        )
        self._conn.commit()

    def get_episode_pending_status_counts(self, source: str) -> Dict[str, int]:
        token = normalize_episode_source(source)
        if not token:
            return {"pending": 0, "running": 0, "failed": 0, "done": 0}
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM episode_pending_paragraphs
            WHERE TRIM(COALESCE(source, '')) = ?
            GROUP BY status
            """,
            (token,),
        )
        counts = {"pending": 0, "running": 0, "failed": 0, "done": 0}
        for row in cursor.fetchall():
            status = str(row["status"] or "").strip().lower()
            if status in counts:
                counts[status] = int(row["count"] or 0)
        return counts

    # =========================================================================
    # 段落向量回填队列
    # =========================================================================

    def enqueue_paragraph_vector_backfill(
        self,
        paragraph_hash: str,
        *,
        created_at: Optional[float] = None,
        error: str = "",
    ) -> None:
        token = str(paragraph_hash or "").strip()
        if not token:
            return
        now = datetime.now().timestamp()
        created_ts = float(created_at) if created_at is not None else now
        error_text = str(error or "").strip() or None
        cursor = self._conn.cursor()
        cursor.execute(
            """
            INSERT INTO paragraph_vector_backfill (
                paragraph_hash, status, retry_count, last_error, created_at, updated_at
            ) VALUES (?, 'pending', 0, ?, ?, ?)
            ON CONFLICT(paragraph_hash) DO UPDATE SET
                status = CASE
                    WHEN paragraph_vector_backfill.status = 'done' THEN 'done'
                    ELSE 'pending'
                END,
                last_error = CASE
                    WHEN paragraph_vector_backfill.status = 'done'
                    THEN paragraph_vector_backfill.last_error
                    ELSE excluded.last_error
                END,
                created_at = COALESCE(paragraph_vector_backfill.created_at, excluded.created_at),
                updated_at = excluded.updated_at
            """,
            (token, error_text, created_ts, now),
        )
        self._conn.commit()

    def fetch_paragraph_vector_backfill_batch(
        self, limit: int = 64, max_retry: int = 5
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit))
        safe_retry = max(0, int(max_retry))
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT paragraph_hash, status, retry_count, last_error, created_at, updated_at
            FROM paragraph_vector_backfill
            WHERE status = 'pending'
               OR (status = 'failed' AND retry_count < ?)
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (safe_retry, safe_limit),
        )
        return [dict(row) for row in cursor.fetchall()]

    def mark_paragraph_vector_backfill_running(self, hashes: List[str]) -> None:
        if not hashes:
            return
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        uniq = list(
            dict.fromkeys([str(h or "").strip() for h in hashes if str(h or "").strip()])
        )
        if not uniq:
            return
        chunk_size = 500
        for i in range(0, len(uniq), chunk_size):
            chunk = uniq[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            cursor.execute(
                f"""
                UPDATE paragraph_vector_backfill
                SET status = 'running', updated_at = ?
                WHERE paragraph_hash IN ({placeholders})
                  AND status IN ('pending', 'failed')
                """,
                [now] + chunk,
            )
        self._conn.commit()

    def mark_paragraph_vector_backfill_done(self, hashes: List[str]) -> None:
        if not hashes:
            return
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        uniq = list(
            dict.fromkeys([str(h or "").strip() for h in hashes if str(h or "").strip()])
        )
        if not uniq:
            return
        chunk_size = 500
        for i in range(0, len(uniq), chunk_size):
            chunk = uniq[i : i + chunk_size]
            placeholders = ",".join(["?"] * len(chunk))
            cursor.execute(
                f"""
                UPDATE paragraph_vector_backfill
                SET status = 'done', last_error = NULL, updated_at = ?
                WHERE paragraph_hash IN ({placeholders})
                """,
                [now] + chunk,
            )
        self._conn.commit()

    def mark_paragraph_vector_backfill_failed(
        self, paragraph_hash: str, error: str = ""
    ) -> None:
        token = str(paragraph_hash or "").strip()
        if not token:
            return
        now = datetime.now().timestamp()
        cursor = self._conn.cursor()
        cursor.execute(
            """
            UPDATE paragraph_vector_backfill
            SET status = 'failed',
                retry_count = COALESCE(retry_count, 0) + 1,
                last_error = ?, updated_at = ?
            WHERE paragraph_hash = ?
            """,
            (str(error or ""), now, token),
        )
        self._conn.commit()

    def get_paragraph_vector_backfill_status_counts(self) -> Dict[str, int]:
        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT status, COUNT(*) AS count FROM paragraph_vector_backfill GROUP BY status"
        )
        counts = {"pending": 0, "running": 0, "failed": 0, "done": 0}
        for row in cursor.fetchall():
            status = str(row["status"] or "").strip().lower()
            if status in counts:
                counts[status] = int(row["count"] or 0)
        return counts

    # =========================================================================
    # Episode 查询
    # =========================================================================

    def _episode_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        data = dict(row)

        def _load_list(raw: Any) -> List[Any]:
            if not raw:
                return []
            try:
                val = json.loads(raw)
                return val if isinstance(val, list) else []
            except Exception:
                return []

        data["participants"] = _load_list(data.pop("participants_json", None))
        data["keywords"] = _load_list(data.pop("keywords_json", None))
        data["evidence_ids"] = _load_list(data.pop("evidence_ids_json", None))
        return data

    def upsert_episode(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("payload 必须是字典")
        title = str(payload.get("title", "")).strip()
        summary = str(payload.get("summary", "")).strip()
        if not title:
            raise ValueError("episode.title 不能为空")
        if not summary:
            raise ValueError("episode.summary 不能为空")

        source = str(payload.get("source", "")).strip() or None
        participants_raw = payload.get("participants", []) or []
        keywords_raw = payload.get("keywords", []) or []
        evidence_ids_raw = payload.get("evidence_ids", []) or []
        participants = [str(x).strip() for x in participants_raw if str(x).strip()]
        keywords = [str(x).strip() for x in keywords_raw if str(x).strip()]
        evidence_ids = [str(x).strip() for x in evidence_ids_raw if str(x).strip()]

        now = datetime.now().timestamp()
        created_at = as_optional_float(payload.get("created_at"))
        updated_at = as_optional_float(payload.get("updated_at"))
        created_ts = created_at if created_at is not None else now
        updated_ts = updated_at if updated_at is not None else now

        episode_id = str(payload.get("episode_id", "")).strip()
        if not episode_id:
            seed = json.dumps(
                {
                    "source": source,
                    "title": title,
                    "summary": summary,
                    "event_time_start": payload.get("event_time_start"),
                    "event_time_end": payload.get("event_time_end"),
                    "evidence_ids": evidence_ids,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            episode_id = compute_hash(seed)

        paragraph_count = payload.get("paragraph_count")
        if paragraph_count is None:
            paragraph_count = len(evidence_ids)
        try:
            paragraph_count = int(paragraph_count)
        except Exception:
            paragraph_count = len(evidence_ids)
        time_conf = payload.get("time_confidence", 1.0)
        llm_conf = payload.get("llm_confidence", 0.0)
        try:
            time_conf = float(time_conf)
        except Exception:
            time_conf = 1.0
        try:
            llm_conf = float(llm_conf)
        except Exception:
            llm_conf = 0.0

        cursor = self._conn.cursor()
        cursor.execute(
            "SELECT created_at FROM episodes WHERE episode_id = ? LIMIT 1", (episode_id,)
        )
        existed = cursor.fetchone()
        if existed and existed[0] is not None:
            created_ts = float(existed[0])

        cursor.execute(
            """
            INSERT INTO episodes (
                episode_id, source, title, summary,
                event_time_start, event_time_end, time_granularity, time_confidence,
                participants_json, keywords_json, evidence_ids_json,
                paragraph_count, llm_confidence, segmentation_model, segmentation_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(episode_id) DO UPDATE SET
                source = excluded.source,
                title = excluded.title,
                summary = excluded.summary,
                event_time_start = excluded.event_time_start,
                event_time_end = excluded.event_time_end,
                time_granularity = excluded.time_granularity,
                time_confidence = excluded.time_confidence,
                participants_json = excluded.participants_json,
                keywords_json = excluded.keywords_json,
                evidence_ids_json = excluded.evidence_ids_json,
                paragraph_count = excluded.paragraph_count,
                llm_confidence = excluded.llm_confidence,
                segmentation_model = excluded.segmentation_model,
                segmentation_version = excluded.segmentation_version,
                updated_at = excluded.updated_at
            """,
            (
                episode_id, source, title, summary,
                as_optional_float(payload.get("event_time_start")),
                as_optional_float(payload.get("event_time_end")),
                str(payload.get("time_granularity", "")).strip() or None,
                time_conf,
                json.dumps(participants, ensure_ascii=False),
                json.dumps(keywords, ensure_ascii=False),
                json.dumps(evidence_ids, ensure_ascii=False),
                max(0, paragraph_count),
                llm_conf,
                str(payload.get("segmentation_model", "")).strip() or None,
                str(payload.get("segmentation_version", "")).strip() or None,
                created_ts, updated_ts,
            ),
        )
        self._conn.commit()
        return self.get_episode_by_id(episode_id) or {"episode_id": episode_id}

    def bind_episode_paragraphs(
        self, episode_id: str, paragraph_hashes_ordered: List[str]
    ) -> int:
        token = str(episode_id or "").strip()
        if not token:
            raise ValueError("episode_id 不能为空")
        normalized: List[str] = []
        seen = set()
        for item in paragraph_hashes_ordered or []:
            h = str(item or "").strip()
            if not h or h in seen:
                continue
            seen.add(h)
            normalized.append(h)
        cursor = self._conn.cursor()
        cursor.execute("DELETE FROM episode_paragraphs WHERE episode_id = ?", (token,))
        if normalized:
            cursor.executemany(
                """
                INSERT OR IGNORE INTO episode_paragraphs (episode_id, paragraph_hash, position)
                VALUES (?, ?, ?)
                """,
                [(token, h, idx) for idx, h in enumerate(normalized)],
            )
        now = datetime.now().timestamp()
        cursor.execute(
            "UPDATE episodes SET paragraph_count = ?, updated_at = ? WHERE episode_id = ?",
            (len(normalized), now, token),
        )
        self._conn.commit()
        return len(normalized)

    def _build_episode_query_components(
        self,
        *,
        time_from: Optional[float] = None,
        time_to: Optional[float] = None,
        person: Optional[str] = None,
        source: Optional[str] = None,
    ) -> Tuple[str, str, str, List[str], List[Any]]:
        source_expr = "TRIM(COALESCE(e.source, ''))"
        effective_start = "COALESCE(e.event_time_start, e.event_time_end, e.updated_at)"
        effective_end = "COALESCE(e.event_time_end, e.event_time_start, e.updated_at)"
        conditions: List[str] = []
        params: List[Any] = []
        conditions.append(f"{source_expr} != ''")
        conditions.append("COALESCE(e.paragraph_count, 0) > 0")
        conditions.append(
            """
            NOT EXISTS (
                SELECT 1 FROM episode_rebuild_sources ers
                WHERE ers.source = TRIM(COALESCE(e.source, ''))
                  AND ers.status IN ('pending', 'running')
            )
            """
        )
        if source:
            token = normalize_episode_source(source)
            if not token:
                return source_expr, effective_start, effective_end, ["1 = 0"], []
            conditions.append(f"{source_expr} = ?")
            params.append(token)
        p = str(person or "").strip().lower()
        if p:
            like_person = f"%{p}%"
            conditions.append(
                """
                (
                    LOWER(COALESCE(e.participants_json, '')) LIKE ?
                    OR EXISTS (
                        SELECT 1 FROM episode_paragraphs ep_person
                        JOIN paragraph_entities pe ON pe.paragraph_hash = ep_person.paragraph_hash
                        JOIN entities en ON en.hash = pe.entity_hash
                        WHERE ep_person.episode_id = e.episode_id
                          AND LOWER(en.name) LIKE ?
                    )
                )
                """
            )
            params.extend([like_person, like_person])
        if time_from is not None and time_to is not None:
            conditions.append(f"({effective_end} >= ? AND {effective_start} <= ?)")
            params.extend([float(time_from), float(time_to)])
        elif time_from is not None:
            conditions.append(f"({effective_end} >= ?)")
            params.append(float(time_from))
        elif time_to is not None:
            conditions.append(f"({effective_start} <= ?)")
            params.append(float(time_to))
        return source_expr, effective_start, effective_end, conditions, params

    @staticmethod
    def _tokenize_episode_query(query: str) -> Tuple[str, List[str]]:
        normalized = normalize_text(str(query or "")).strip().lower()
        if not normalized:
            return "", []
        tokens: List[str] = []
        seen = set()

        def _push(token: str) -> None:
            clean = str(token or "").strip().lower()
            if len(clean) < 2 or clean in seen:
                return
            seen.add(clean)
            tokens.append(clean)

        for span in re.findall(r"[A-Za-z0-9_]+|[一-鿿]+", normalized):
            if re.fullmatch(r"[A-Za-z0-9_]+", span):
                _push(span)
                continue
            segmented: List[str] = []
            if HAS_JIEBA:
                try:
                    segmented = [
                        str(item).strip().lower()
                        for item in jieba.cut_for_search(span)  # type: ignore[union-attr]
                        if len(str(item).strip()) >= 2
                    ]
                except Exception:
                    pass
            if not segmented:
                compact = span.strip()
                if len(compact) <= 3:
                    segmented = [compact]
                else:
                    for n in range(2, min(4, len(compact)) + 1):
                        segmented.extend(
                            compact[i : i + n] for i in range(0, len(compact) - n + 1)
                        )
            for token in segmented:
                _push(token)
        if not tokens and len(normalized) >= 2:
            tokens = [normalized]
        return normalized, tokens

    def get_episode_rows_by_paragraph_hashes(
        self,
        paragraph_hashes: List[str],
        *,
        time_from: Optional[float] = None,
        time_to: Optional[float] = None,
        person: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized = normalize_hash_sequence(paragraph_hashes)
        if not normalized:
            return []
        _, _, _, conditions, params = self._build_episode_query_components(
            time_from=time_from, time_to=time_to, person=person, source=source
        )
        placeholders = ",".join(["?"] * len(normalized))
        conditions.append(f"ep.paragraph_hash IN ({placeholders})")
        conditions.append("(p.is_deleted IS NULL OR p.is_deleted = 0)")
        where_sql = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT e.*, ep.paragraph_hash AS matched_paragraph_hash
            FROM episodes e
            JOIN episode_paragraphs ep ON ep.episode_id = e.episode_id
            JOIN paragraphs p ON p.hash = ep.paragraph_hash
            {where_sql}
            ORDER BY e.updated_at DESC
        """
        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(params + normalized))
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in cursor.fetchall():
            episode_id = str(row["episode_id"] or "").strip()
            if not episode_id:
                continue
            payload = grouped.get(episode_id)
            if payload is None:
                payload = self._episode_row_to_dict(row)
                payload["matched_paragraph_hashes"] = []
                grouped[episode_id] = payload
            matched_hash = str(row["matched_paragraph_hash"] or "").strip()
            if matched_hash and matched_hash not in payload["matched_paragraph_hashes"]:
                payload["matched_paragraph_hashes"].append(matched_hash)
        out = list(grouped.values())
        for item in out:
            item["matched_paragraph_count"] = len(item.get("matched_paragraph_hashes", []))
        return out

    def get_episode_rows_by_relation_hashes(
        self,
        relation_hashes: List[str],
        *,
        time_from: Optional[float] = None,
        time_to: Optional[float] = None,
        person: Optional[str] = None,
        source: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        normalized = normalize_hash_sequence(relation_hashes)
        if not normalized:
            return []
        _, _, _, conditions, params = self._build_episode_query_components(
            time_from=time_from, time_to=time_to, person=person, source=source
        )
        placeholders = ",".join(["?"] * len(normalized))
        conditions.append(f"pr.relation_hash IN ({placeholders})")
        conditions.append("(p.is_deleted IS NULL OR p.is_deleted = 0)")
        where_sql = "WHERE " + " AND ".join(conditions)
        sql = f"""
            SELECT
                e.*,
                p.hash AS matched_paragraph_hash,
                pr.relation_hash AS matched_relation_hash
            FROM episodes e
            JOIN episode_paragraphs ep ON ep.episode_id = e.episode_id
            JOIN paragraphs p ON p.hash = ep.paragraph_hash
            JOIN paragraph_relations pr ON pr.paragraph_hash = p.hash
            {where_sql}
            ORDER BY e.updated_at DESC
        """
        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(params + normalized))
        grouped: Dict[str, Dict[str, Any]] = {}
        for row in cursor.fetchall():
            episode_id = str(row["episode_id"] or "").strip()
            if not episode_id:
                continue
            payload = grouped.get(episode_id)
            if payload is None:
                payload = self._episode_row_to_dict(row)
                payload["matched_paragraph_hashes"] = []
                payload["matched_relation_hashes"] = []
                grouped[episode_id] = payload
            matched_paragraph = str(row["matched_paragraph_hash"] or "").strip()
            matched_relation = str(row["matched_relation_hash"] or "").strip()
            if matched_paragraph and matched_paragraph not in payload["matched_paragraph_hashes"]:
                payload["matched_paragraph_hashes"].append(matched_paragraph)
            if matched_relation and matched_relation not in payload["matched_relation_hashes"]:
                payload["matched_relation_hashes"].append(matched_relation)
        out = list(grouped.values())
        for item in out:
            item["matched_paragraph_count"] = len(item.get("matched_paragraph_hashes", []))
            item["matched_relation_count"] = len(item.get("matched_relation_hashes", []))
        return out

    def query_episodes(
        self,
        query: str = "",
        time_from: Optional[float] = None,
        time_to: Optional[float] = None,
        person: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        safe_limit = max(1, int(limit))
        _, effective_start, effective_end, conditions, params = (
            self._build_episode_query_components(
                time_from=time_from, time_to=time_to, person=person, source=source
            )
        )
        q, tokens = self._tokenize_episode_query(query)
        select_score_sql = "0.0 AS lexical_score"
        order_sql = f"{effective_end} DESC, e.updated_at DESC"
        select_params: List[Any] = []
        query_params: List[Any] = []
        if q:
            field_exprs = {
                "title": "LOWER(COALESCE(e.title, ''))",
                "summary": "LOWER(COALESCE(e.summary, ''))",
                "keywords": "LOWER(COALESCE(e.keywords_json, ''))",
                "participants": "LOWER(COALESCE(e.participants_json, ''))",
            }
            score_parts: List[str] = []
            phrase_like = f"%{q}%"
            score_parts.extend(
                [
                    f"CASE WHEN {field_exprs['title']} LIKE ? THEN 6.0 ELSE 0.0 END",
                    f"CASE WHEN {field_exprs['keywords']} LIKE ? THEN 4.5 ELSE 0.0 END",
                    f"CASE WHEN {field_exprs['summary']} LIKE ? THEN 3.0 ELSE 0.0 END",
                    f"CASE WHEN {field_exprs['participants']} LIKE ? THEN 2.0 ELSE 0.0 END",
                ]
            )
            select_params.extend([phrase_like, phrase_like, phrase_like, phrase_like])
            token_predicates: List[str] = []
            for token in tokens:
                like = f"%{token}%"
                token_any = (
                    f"({field_exprs['title']} LIKE ? OR "
                    f"{field_exprs['summary']} LIKE ? OR "
                    f"{field_exprs['keywords']} LIKE ? OR "
                    f"{field_exprs['participants']} LIKE ?)"
                )
                token_predicates.append(token_any)
                query_params.extend([like, like, like, like])
                score_parts.append(
                    "("
                    f"CASE WHEN {field_exprs['title']} LIKE ? THEN 3.0 ELSE 0.0 END + "
                    f"CASE WHEN {field_exprs['keywords']} LIKE ? THEN 2.5 ELSE 0.0 END + "
                    f"CASE WHEN {field_exprs['summary']} LIKE ? THEN 2.0 ELSE 0.0 END + "
                    f"CASE WHEN {field_exprs['participants']} LIKE ? THEN 1.5 ELSE 0.0 END + "
                    f"CASE WHEN {token_any.replace('?', '?')} THEN 2.0 ELSE 0.0 END"
                    ")"
                )
                select_params.extend([like, like, like, like, like, like, like, like])
            if token_predicates:
                conditions.append("(" + " OR ".join(token_predicates) + ")")
            select_score_sql = f"({' + '.join(score_parts)}) AS lexical_score"
            order_sql = f"lexical_score DESC, {effective_end} DESC, e.updated_at DESC"

        where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"""
            SELECT e.*, {select_score_sql}
            FROM episodes e
            {where_sql}
            ORDER BY {order_sql}
            LIMIT ?
        """
        final_params = list(select_params) + list(params) + list(query_params) + [safe_limit]
        cursor = self._conn.cursor()
        cursor.execute(sql, tuple(final_params))
        return [self._episode_row_to_dict(row) for row in cursor.fetchall()]

    def get_episode_by_id(self, episode_id: str) -> Optional[Dict[str, Any]]:
        token = str(episode_id or "").strip()
        if not token:
            return None
        cursor = self._conn.cursor()
        cursor.execute("SELECT * FROM episodes WHERE episode_id = ? LIMIT 1", (token,))
        row = cursor.fetchone()
        if not row:
            return None
        return self._episode_row_to_dict(row)

    def get_episode_paragraphs(
        self, episode_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        token = str(episode_id or "").strip()
        if not token:
            return []
        safe_limit = max(1, int(limit))
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT p.*, ep.position
            FROM episode_paragraphs ep
            JOIN paragraphs p ON p.hash = ep.paragraph_hash
            WHERE ep.episode_id = ?
              AND (p.is_deleted IS NULL OR p.is_deleted = 0)
            ORDER BY ep.position ASC
            LIMIT ?
            """,
            (token, safe_limit),
        )
        items = []
        for row in cursor.fetchall():
            payload = row_to_dict(row)
            payload["position"] = row["position"]
            items.append(payload)
        return items

    # =========================================================================
    # 时间元数据回填
    # =========================================================================

    def backfill_temporal_metadata_from_created_at(
        self,
        *,
        limit: int = 100000,
        dry_run: bool = False,
        no_created_fallback: bool = False,
    ) -> Dict[str, int]:
        cursor = self._conn.cursor()
        cursor.execute(
            """
            SELECT hash, created_at, source FROM paragraphs
            WHERE (event_time IS NULL AND event_time_start IS NULL AND event_time_end IS NULL)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (int(max(1, limit)),),
        )
        rows = cursor.fetchall()
        candidates = len(rows)
        if dry_run:
            return {"candidates": candidates, "updated": 0}
        if no_created_fallback:
            return {"candidates": candidates, "updated": 0}
        updated = 0
        touched_sources: List[str] = []
        for row in rows:
            created_at = row["created_at"]
            if created_at is None:
                continue
            cursor.execute(
                """
                UPDATE paragraphs
                SET event_time = ?, time_granularity = ?, time_confidence = ?, updated_at = ?
                WHERE hash = ?
                """,
                (float(created_at), "day", 0.2, float(created_at), row["hash"]),
            )
            if cursor.rowcount > 0:
                updated += 1
                touched_sources.append(row["source"])
        self._conn.commit()
        if updated > 0:
            self._enqueue_episode_source_rebuilds(
                touched_sources, reason="paragraph_time_backfill"
            )
        return {"candidates": candidates, "updated": updated}
