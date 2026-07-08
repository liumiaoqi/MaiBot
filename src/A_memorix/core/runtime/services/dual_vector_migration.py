from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import asyncio
import time

from src.common.logger import get_logger
from src.A_memorix.core.storage import VectorStore
from src.A_memorix.core.utils.relation_write_service import RelationWriteService

logger = get_logger("a_memorix.services.dual_vector_migration")

DUAL_VECTOR_AUTO_MIGRATION_INITIAL_DELAY_SECONDS = 5.0
DUAL_VECTOR_AUTO_MIGRATION_LOCK_RETRY_DELAYS_SECONDS = (2.0, 5.0, 10.0)


class DualVectorMigrationService:
    """双池向量迁移 — 自动迁移循环、增量补齐、manifest 管理。"""

    def __init__(
        self,
        *,
        vector_pool_manager: Any,
        background_scheduler: Any,
        cfg: Callable[[str, Any], Any],
        active_row_filter_sql: Callable[[str], str],
        dual_vector_pools_enabled: Callable[[], bool],
        set_embedding_degraded: Callable[..., None],
        copy_or_encode_dual_rebuild_vectors: Callable[..., Any],
        graph_vector_id: Callable[[str, str], str],
        rebuild_all_vectors: Callable[..., Any],
        vector_rebuild_lock_getter: Callable[[], asyncio.Lock],
        sleep_background: Callable[[float], Any],
        metadata_store_getter: Callable[[], Any],
        vector_store_getter: Callable[[], Optional[VectorStore]],
        paragraph_vector_store_getter: Callable[[], Optional[VectorStore]],
        graph_vector_store_getter: Callable[[], Optional[VectorStore]],
        relation_vectors_enabled_getter: Callable[[], bool],
        paragraph_vector_store_setter: Callable[[Optional[VectorStore]], None],
        graph_vector_store_setter: Callable[[Optional[VectorStore]], None],
    ) -> None:
        self._vpm = vector_pool_manager
        self._scheduler = background_scheduler
        self._cfg = cfg
        self._active_row_filter_sql = active_row_filter_sql
        self._dual_vector_pools_enabled = dual_vector_pools_enabled
        self._set_embedding_degraded = set_embedding_degraded
        self._copy_or_encode = copy_or_encode_dual_rebuild_vectors
        self._graph_vector_id = graph_vector_id
        self._rebuild_all_vectors = rebuild_all_vectors
        self._get_vector_rebuild_lock = vector_rebuild_lock_getter
        self._sleep_background = sleep_background
        self._get_metadata_store = metadata_store_getter
        self._get_vector_store = vector_store_getter
        self._get_paragraph_vector_store = paragraph_vector_store_getter
        self._get_graph_vector_store = graph_vector_store_getter
        self._get_relation_vectors_enabled = relation_vectors_enabled_getter
        self._set_paragraph_vector_store = paragraph_vector_store_setter
        self._set_graph_vector_store = graph_vector_store_setter

    def should_start_dual_vector_auto_migration(self) -> bool:
        return self._vpm.should_start_dual_vector_auto_migration(
            background_stopping=self._scheduler.stopping,
        )

    def normalize_dual_vector_auto_migration_progress(
        self,
        progress: Optional[Dict[str, Any]] = None,
        *,
        now: Optional[float] = None,
        explicit_processed: bool = False,
        completed: bool = False,
        success: bool = False,
    ) -> Dict[str, Any]:
        return self._vpm.normalize_dual_vector_auto_migration_progress(
            progress, now=now, explicit_processed=explicit_processed, completed=completed, success=success,
        )

    def update_dual_vector_auto_migration_stage(self, stage: str, **progress: Any) -> None:
        return self._vpm.update_dual_vector_auto_migration_stage(stage, **progress)

    def reload_dual_vector_stores_from_disk(self) -> bool:
        self._vpm.vector_store = self._get_vector_store()
        self._vpm.paragraph_vector_store = self._get_paragraph_vector_store()
        self._vpm.graph_vector_store = self._get_graph_vector_store()
        self._vpm.metadata_store = self._get_metadata_store()
        result = self._vpm.reload_dual_vector_stores_from_disk()
        self._set_paragraph_vector_store(self._vpm.paragraph_vector_store)
        self._set_graph_vector_store(self._vpm.graph_vector_store)
        return result

    def write_dual_vector_ready_manifest(
        self,
        *,
        stats: Dict[str, Dict[str, int]],
        migration_stats: Dict[str, Dict[str, int]],
    ) -> None:
        return self._vpm.write_dual_vector_ready_manifest(stats=stats, migration_stats=migration_stats)

    def clear_legacy_single_vector_files_after_dual_ready(self) -> None:
        self._vpm.paragraph_vector_store = self._get_paragraph_vector_store()
        self._vpm.graph_vector_store = self._get_graph_vector_store()
        self._vpm.metadata_store = self._get_metadata_store()
        self._vpm.refresh_dual_vector_ready_manifest_from_stores()

    def clear_legacy_single_vector_files_after_dual_ready_v2(self) -> None:
        self._vpm.vector_store = self._get_vector_store()
        return self._vpm.clear_legacy_single_vector_files_after_dual_ready()

    async def backfill_missing_dual_vector_pool_entries(self, *, batch_size: int) -> Dict[str, Any]:
        metadata_store = self._get_metadata_store()
        vector_store = self._get_vector_store()
        paragraph_vector_store = self._get_paragraph_vector_store()
        graph_vector_store = self._get_graph_vector_store()
        if (
            metadata_store is None
            or vector_store is None
            or paragraph_vector_store is None
            or graph_vector_store is None
            or not self._dual_vector_pools_enabled()
        ):
            return {"success": False, "error": "dual_pool_not_ready"}

        safe_batch_size = max(1, int(batch_size or self._cfg("embedding.batch_size", 32) or 32))
        stats = {
            "paragraphs": {"done": 0, "failed": 0},
            "entities": {"done": 0, "failed": 0},
            "relations": {"done": 0, "failed": 0},
        }
        migration_stats = {
            "paragraphs": {"copied": 0, "encoded": 0, "missing": 0},
            "entities": {"copied": 0, "encoded": 0, "missing": 0},
            "relations": {"copied": 0, "encoded": 0, "missing": 0},
        }
        errors: List[str] = []
        source_store = vector_store
        if source_store is not None and not self._vpm.stored_vectors_compatible_with_current_embedding(source_store):
            source_store = None
        if source_store is not None and source_store.has_data():
            try:
                source_store.load()
                source_store.warmup_index(force_train=False)
            except Exception as exc:
                logger.warning(f"加载旧单池向量用于双池增量补齐失败，将回退 embedding 重建: {exc}")

        paragraph_where = self._active_row_filter_sql("paragraphs")
        paragraph_rows = metadata_store.query(
            f"""
            SELECT hash, content
            FROM paragraphs
            WHERE {paragraph_where}
            ORDER BY created_at ASC
            """
        )
        paragraph_items = [
            (str(row.get("hash", "") or ""), str(row.get("content", "") or "").strip())
            for row in paragraph_rows
            if str(row.get("hash", "") or "").strip()
            and str(row.get("content", "") or "").strip()
            and str(row.get("hash", "") or "").strip() not in paragraph_vector_store
        ]
        done, failed, error, _done_ids, _failed_ids, copy_stats = await self._copy_or_encode(
            items=paragraph_items,
            batch_size=safe_batch_size,
            target_store=paragraph_vector_store,
            source_store=source_store,
        )
        stats["paragraphs"] = {"done": done, "failed": failed}
        migration_stats["paragraphs"] = copy_stats
        if error:
            errors.append(f"paragraph_pool_backfill:{error}")

        entity_where = self._active_row_filter_sql("entities")
        entity_rows = metadata_store.query(
            f"""
            SELECT hash, name
            FROM entities
            WHERE {entity_where}
            ORDER BY created_at ASC
            """
        )
        entity_items = []
        for row in entity_rows:
            hash_value = str(row.get("hash", "") or "").strip()
            name = str(row.get("name", "") or "").strip()
            if not hash_value or not name:
                continue
            if self._graph_vector_id("entity", hash_value) in graph_vector_store:
                continue
            entity_items.append((hash_value, name))
        done, failed, error, _done_ids, _failed_ids, copy_stats = await self._copy_or_encode(
            items=entity_items,
            batch_size=safe_batch_size,
            target_store=graph_vector_store,
            target_id_prefix="entity",
            source_store=source_store,
        )
        stats["entities"] = {"done": done, "failed": failed}
        migration_stats["entities"] = copy_stats
        if error:
            errors.append(f"entity_graph_pool_backfill:{error}")

        if self._get_relation_vectors_enabled():
            relation_where = self._active_row_filter_sql("relations")
            relation_rows = metadata_store.query(
                f"""
                SELECT hash, subject, predicate, object
                FROM relations
                WHERE {relation_where}
                ORDER BY created_at ASC
                """
            )
            relation_items = []
            for row in relation_rows:
                hash_value = str(row.get("hash", "") or "").strip()
                if not hash_value:
                    continue
                if self._graph_vector_id("relation", hash_value) in graph_vector_store:
                    continue
                relation_items.append(
                    (
                        hash_value,
                        RelationWriteService.build_relation_vector_text(
                            str(row.get("subject", "") or ""),
                            str(row.get("predicate", "") or ""),
                            str(row.get("object", "") or ""),
                        ),
                    )
                )
            done, failed, error, done_ids, failed_ids, copy_stats = await self._copy_or_encode(
                items=relation_items,
                batch_size=safe_batch_size,
                target_store=graph_vector_store,
                target_id_prefix="relation",
                source_store=source_store,
            )
            stats["relations"] = {"done": done, "failed": failed}
            migration_stats["relations"] = copy_stats
            if error:
                errors.append(f"relation_graph_pool_backfill:{error}")

            if done_ids or failed_ids:
                conn = metadata_store.get_connection()
                cursor = conn.cursor()
                now_ts = time.time()
                for start in range(0, len(done_ids), 500):
                    batch_ids = done_ids[start : start + 500]
                    if not batch_ids:
                        continue
                    placeholders = ",".join("?" for _ in batch_ids)
                    cursor.execute(
                        f"""
                        UPDATE relations
                        SET vector_state = 'ready',
                            vector_updated_at = ?,
                            vector_error = NULL
                        WHERE hash IN ({placeholders})
                        """,
                        (now_ts, *batch_ids),
                    )
                for start in range(0, len(failed_ids), 500):
                    batch_ids = failed_ids[start : start + 500]
                    if not batch_ids:
                        continue
                    placeholders = ",".join("?" for _ in batch_ids)
                    cursor.execute(
                        f"""
                        UPDATE relations
                        SET vector_state = 'failed',
                            vector_updated_at = ?,
                            vector_error = ?,
                            vector_retry_count = COALESCE(vector_retry_count, 0) + 1
                        WHERE hash IN ({placeholders})
                        """,
                        (now_ts, (error or "dual_pool_backfill_failed")[:500], *batch_ids),
                    )
                conn.commit()

        failed_total = sum(int(item["failed"]) for item in stats.values())
        if failed_total:
            self._set_embedding_degraded(
                active=True,
                reason="; ".join(errors)[:500] or "dual_pool_backfill_failed",
                checked_at=time.time(),
            )
        if paragraph_vector_store is not None:
            self._vpm.save_vector_store(paragraph_vector_store)
        if graph_vector_store is not None:
            self._vpm.save_vector_store(graph_vector_store)
        self._vpm.paragraph_vector_store = paragraph_vector_store
        self._vpm.graph_vector_store = graph_vector_store
        self._vpm.metadata_store = metadata_store
        self._vpm.refresh_dual_vector_ready_manifest_from_stores()
        return {
            "success": failed_total == 0,
            "stats": stats,
            "migration": migration_stats,
            "failed": int(failed_total),
            "errors": errors[:5],
        }

    async def dual_vector_auto_migration_loop(self) -> None:
        if not self.should_start_dual_vector_auto_migration():
            return

        self._vpm.auto_migration_attempted = True
        started_at = time.time()
        self._vpm._dual_vector_auto_migration_status.update(
            {
                "running": True,
                "attempted": True,
                "success": False,
                "stage": "initial_delay",
                "progress": self.normalize_dual_vector_auto_migration_progress(
                    {"total": 0, "processed": 0},
                    now=started_at,
                    explicit_processed=True,
                ),
                "last_error": "",
                "started_at": started_at,
                "finished_at": None,
                "updated_at": started_at,
            }
        )
        try:
            await self._sleep_background(DUAL_VECTOR_AUTO_MIGRATION_INITIAL_DELAY_SECONDS)
            if self._scheduler.stopping or self._dual_vector_pools_enabled():
                finished_at = time.time()
                success = self._dual_vector_pools_enabled()
                progress = self.normalize_dual_vector_auto_migration_progress(
                    self._vpm._dual_vector_auto_migration_status.get("progress"),
                    now=finished_at,
                    completed=True,
                    success=success,
                )
                self._vpm._dual_vector_auto_migration_status.update(
                    {
                        "running": False,
                        "success": success,
                        "stage": "skipped",
                        "progress": progress,
                        "finished_at": finished_at,
                        "updated_at": finished_at,
                    }
                )
                return

            retry_delays = [0.0, *DUAL_VECTOR_AUTO_MIGRATION_LOCK_RETRY_DELAYS_SECONDS]
            result: Dict[str, Any] = {}
            for index, delay in enumerate(retry_delays):
                if self._scheduler.stopping or self._dual_vector_pools_enabled():
                    break
                if delay > 0:
                    self.update_dual_vector_auto_migration_stage("retry_delay", retry_index=index, delay_seconds=delay)
                    await self._sleep_background(delay)
                if self._get_vector_rebuild_lock().locked():
                    self.update_dual_vector_auto_migration_stage("waiting_rebuild_lock", retry_index=index)
                    if index == len(retry_delays) - 1:
                        result = {
                            "success": False,
                            "error": "vector_rebuild_running",
                            "detail": "已有向量重建任务正在运行",
                        }
                    continue
                self.update_dual_vector_auto_migration_stage("rebuild_start", retry_index=index)
                result = await self._rebuild_all_vectors()
                if str(result.get("error", "") or "") != "vector_rebuild_running":
                    break

            success = bool(result.get("success", False)) or self._dual_vector_pools_enabled()
            last_error = ""
            if not success:
                errors = result.get("errors") if isinstance(result, dict) else None
                if isinstance(errors, list) and errors:
                    last_error = "; ".join(str(item) for item in errors[:5])
                else:
                    last_error = str(
                        result.get("detail")
                        or result.get("error")
                        or "dual_vector_auto_migration_failed"
                    )
                logger.warning(f"双池后台自动迁移未完成，继续使用单池: {last_error}")
            else:
                logger.info("双池后台自动迁移完成，已切换到双池检索")
            finished_at = time.time()
            progress = {
                **dict(self._vpm._dual_vector_auto_migration_status.get("progress") or {}),
                "result": result,
            }
            progress = self.normalize_dual_vector_auto_migration_progress(
                progress,
                now=finished_at,
                completed=True,
                success=success,
            )
            self._vpm._dual_vector_auto_migration_status.update(
                {
                    "running": False,
                    "success": success,
                    "stage": "completed" if success else "failed",
                    "progress": progress,
                    "last_error": last_error[:500],
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
        except asyncio.CancelledError:
            finished_at = time.time()
            progress = self.normalize_dual_vector_auto_migration_progress(
                self._vpm._dual_vector_auto_migration_status.get("progress"),
                now=finished_at,
                completed=True,
                success=False,
            )
            self._vpm._dual_vector_auto_migration_status.update(
                {
                    "running": False,
                    "stage": "cancelled",
                    "progress": progress,
                    "last_error": "cancelled",
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )
            raise
        except Exception as exc:
            logger.warning(f"双池后台自动迁移异常，继续使用单池: {exc}")
            finished_at = time.time()
            progress = self.normalize_dual_vector_auto_migration_progress(
                self._vpm._dual_vector_auto_migration_status.get("progress"),
                now=finished_at,
                completed=True,
                success=False,
            )
            self._vpm._dual_vector_auto_migration_status.update(
                {
                    "running": False,
                    "success": False,
                    "stage": "exception",
                    "progress": progress,
                    "last_error": str(exc)[:500],
                    "finished_at": finished_at,
                    "updated_at": finished_at,
                }
            )