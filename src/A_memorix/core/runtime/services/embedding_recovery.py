from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import asyncio
import time

from src.common.logger import get_logger
from src.A_memorix.core.storage import VectorStore

logger = get_logger("a_memorix.services.embedding_recovery")


class EmbeddingRecoveryService:
    """Embedding 恢复与向量回填 — 自检、探测、回填循环。"""

    def __init__(
        self,
        *,
        embedding_health_service: Any,
        vector_pool_manager: Any,
        cfg: Callable[[str, Any], Any],
        build_runtime_config: Callable[..., Dict[str, Any]],

        refresh_runtime_dependents: Callable[..., None],

        persist: Callable[..., None],
        encode_and_add_rebuild_vectors: Callable[..., Any],
        metadata_store_getter: Callable[[], Any],
        embedding_manager_getter: Callable[[], Any],
        vector_store_getter: Callable[[], Optional[VectorStore]],
        paragraph_vector_store_getter: Callable[[], Optional[VectorStore]],
        embedding_dimension_getter: Callable[[], int],
        embedding_dimension_setter: Callable[[int], None],
        vector_persist_blocked_getter: Callable[[], bool],
        vector_persist_blocked_setter: Callable[[bool], None],
        vector_rebuild_source_dimension_getter: Callable[[], Optional[int]],
        vector_rebuild_source_dimension_setter: Callable[[Optional[int]], None],
        background_scheduler: Any,
        vector_rebuild_status_getter: Callable[[], Dict[str, Any]],
        runtime_self_check_report_setter: Callable[[Dict[str, Any]], None],
        retriever_getter: Callable[[], Any],
    ) -> None:
        self._health = embedding_health_service
        self._vpm = vector_pool_manager
        self._cfg = cfg
        self._build_runtime_config = build_runtime_config

        self._refresh_runtime_dependents = refresh_runtime_dependents

        self._persist = persist
        self._encode_and_add = encode_and_add_rebuild_vectors
        self._get_metadata_store = metadata_store_getter
        self._get_embedding_manager = embedding_manager_getter
        self._get_vector_store = vector_store_getter
        self._get_paragraph_vector_store = paragraph_vector_store_getter
        self._get_embedding_dimension = embedding_dimension_getter
        self._set_embedding_dimension = embedding_dimension_setter
        self._get_vector_persist_blocked = vector_persist_blocked_getter
        self._set_vector_persist_blocked = vector_persist_blocked_setter
        self._get_vector_rebuild_source_dimension = vector_rebuild_source_dimension_getter
        self._set_vector_rebuild_source_dimension = vector_rebuild_source_dimension_setter
        self._scheduler = background_scheduler
        self._get_vector_rebuild_status = vector_rebuild_status_getter
        self._set_runtime_self_check_report = runtime_self_check_report_setter
        self._get_retriever = retriever_getter
        self._runtime_self_check_report: Dict[str, Any] = {}

    def set_embedding_degraded(self, *, active: bool, reason: str = "", checked_at: Optional[float] = None) -> None:
        self._health.set_degraded(active=active, reason=reason, checked_at=checked_at)
        self.apply_runtime_sparse_mode()

    def apply_runtime_sparse_mode(self) -> None:
        retriever = self._get_retriever()
        if retriever is None:
            return
        setter = getattr(retriever, "set_runtime_sparse_only", None)
        if not callable(setter):
            return
        try:
            setter(self._health.is_degraded)
        except Exception as exc:
            logger.warning(f"设置 retriever sparse-only 运行时状态失败: {exc}")

    async def refresh_runtime_self_check(self, *, sample_text: str = "A_Memorix runtime self check") -> Dict[str, Any]:
        from ..utils.runtime_self_check import run_embedding_runtime_self_check
        report = await run_embedding_runtime_self_check(
            config=self._build_runtime_config(),
            vector_store=self._get_vector_store(),
            embedding_manager=self._get_embedding_manager(),
            sample_text=sample_text,
        )
        self._runtime_self_check_report = dict(report)
        self._set_runtime_self_check_report(self._runtime_self_check_report)
        checked_at = float(report.get("checked_at") or time.time())
        self._health.update_last_check(checked_at)
        return report

    def mark_startup_self_check_deferred(self) -> None:
        configured_dimension = max(
            1,
            int(self._cfg("embedding.dimension", self._get_embedding_dimension()) or self._get_embedding_dimension()),
        )
        requested_dimension = self._vpm.current_embedding_status_dimension()
        vector_store = self._get_vector_store()
        vector_store_dimension = int(vector_store.dimension if vector_store is not None else 0)
        self._health.mark_startup_self_check_deferred(
            configured_dimension=configured_dimension,
            requested_dimension=requested_dimension,
            vector_store_dimension=vector_store_dimension,
        )
        self._runtime_self_check_report = self._health.runtime_self_check_report
        self._set_runtime_self_check_report(self._runtime_self_check_report)

    @staticmethod
    def self_check_effective_dimension(report: Dict[str, Any]) -> int:
        for key in ("encoded_dimension", "detected_dimension", "requested_dimension"):
            try:
                value = int(report.get(key, 0) or 0)
            except Exception:
                value = 0
            if value > 0:
                return value
        return 0

    def apply_self_check_dimension_result(self, report: Dict[str, Any]) -> str:
        detected_dimension = self.self_check_effective_dimension(report)
        if detected_dimension <= 0:
            return ""
        self._set_embedding_dimension(int(detected_dimension))
        vector_store = self._get_vector_store()
        vector_dimension = int(vector_store.dimension if vector_store is not None else 0)
        if vector_dimension <= 0 or vector_dimension == detected_dimension:
            return ""
        stored_dimension = self._vpm.stored_vector_dimension() or vector_dimension
        message = self._vpm.vector_mismatch_error(
            stored_dimension=int(stored_dimension),
            detected_dimension=int(detected_dimension),
        )
        self._set_vector_persist_blocked(True)
        self._set_vector_rebuild_source_dimension(int(stored_dimension))
        return message

    async def recover_embedding_once(self, *, sample_text: str = "A_Memorix runtime self check") -> Dict[str, Any]:
        report = await self.refresh_runtime_self_check(sample_text=sample_text)
        checked_at = float(report.get("checked_at") or time.time())
        ok = bool(report.get("ok", False))
        dimension_mismatch = self.apply_self_check_dimension_result(report)
        if dimension_mismatch:
            self.set_embedding_degraded(active=True, reason=dimension_mismatch, checked_at=checked_at)
            return {
                "success": False,
                "recovered": False,
                "report": report,
                "detail": "dimension_mismatch",
            }
        if ok:
            self.set_embedding_degraded(active=False, checked_at=checked_at)
            backfill_result: Dict[str, Any] = {}
            if self._health.config.paragraph_vector_backfill_enabled:
                backfill_result = await self.run_paragraph_backfill_once(
                    limit=self._health.config.paragraph_vector_backfill_batch_size,
                    max_retry=self._health.config.paragraph_vector_backfill_max_retry,
                    trigger="embedding_recovered",
                )
            return {
                "success": True,
                "recovered": True,
                "report": report,
                "backfill": backfill_result,
            }
        reason = str(report.get("message", "runtime self-check failed") or "runtime self-check failed")
        if self._health.config.embedding_fallback_enabled:
            self.set_embedding_degraded(active=True, reason=reason, checked_at=checked_at)
            return {
                "success": False,
                "recovered": False,
                "report": report,
                "detail": "still_degraded",
            }
        return {
            "success": False,
            "recovered": False,
            "report": report,
            "detail": "fallback_disabled",
        }

    def enqueue_paragraph_vector_backfill(self, paragraph_hash: str, *, error: str = "") -> None:
        metadata_store = self._get_metadata_store()
        if metadata_store is None:
            return
        try:
            metadata_store.enqueue_paragraph_vector_backfill(
                paragraph_hash,
                error=str(error or ""),
            )
        except Exception as exc:
            logger.warning(f"登记 paragraph 向量回填任务失败: {exc}")

    async def write_paragraph_vector_or_enqueue(
        self,
        *,
        paragraph_hash: str,
        content: str,
        context: str = "",
    ) -> Dict[str, Any]:
        token = str(paragraph_hash or "").strip()
        text = str(content or "").strip()
        if not token or not text:
            return {
                "success": False,
                "vector_written": False,
                "queued": False,
                "warning": "",
                "detail": "invalid_paragraph_input",
            }

        allow_metadata_only = self._health.config.allow_metadata_only_write
        target_store = self._vpm.paragraph_store()
        embedding_manager = self._get_embedding_manager()
        if target_store is None or embedding_manager is None:
            if not allow_metadata_only:
                raise RuntimeError("向量写入依赖未初始化")
            self.enqueue_paragraph_vector_backfill(token, error="vector_runtime_components_missing")
            return {
                "success": True,
                "vector_written": False,
                "queued": True,
                "warning": "vector_degraded_write",
                "detail": "vector_runtime_components_missing",
            }

        if self._health.is_degraded:
            if not allow_metadata_only:
                raise RuntimeError("embedding 降级中，拒绝向量写入")
            self.enqueue_paragraph_vector_backfill(token, error="embedding_degraded")
            return {
                "success": True,
                "vector_written": False,
                "queued": True,
                "warning": "embedding_degraded_write",
                "detail": "embedding_degraded",
            }

        try:
            embedding = await embedding_manager.encode([text])
            embedding_array = embedding
            if getattr(embedding_array, "ndim", 1) == 1:
                embedding_array = embedding_array.reshape(1, -1)
            if getattr(embedding_array, "size", 0) <= 0:
                raise ValueError("embedding 返回空向量")
            target_store.add(vectors=embedding_array, ids=[token])
            return {
                "success": True,
                "vector_written": True,
                "queued": False,
                "warning": "",
                "detail": "",
            }
        except Exception as exc:
            error_msg = str(exc)[:500]
            logger.warning(f"写入 paragraph 向量失败，登记回填: {error_msg}")
            self.set_embedding_degraded(active=True, reason=error_msg, checked_at=time.time())
            if allow_metadata_only:
                self.enqueue_paragraph_vector_backfill(token, error=error_msg)
                return {
                    "success": True,
                    "vector_written": False,
                    "queued": True,
                    "warning": "vector_write_failed_degraded",
                    "detail": error_msg,
                }
            return {
                "success": False,
                "vector_written": False,
                "queued": False,
                "warning": "",
                "detail": error_msg,
            }

    async def run_paragraph_backfill_once(
        self,
        *,
        limit: Optional[int] = None,
        max_retry: Optional[int] = None,
        trigger: str = "manual",
    ) -> Dict[str, Any]:
        target_store = self._vpm.paragraph_store()
        metadata_store = self._get_metadata_store()
        embedding_manager = self._get_embedding_manager()
        if metadata_store is None or target_store is None or embedding_manager is None:
            return {"success": False, "processed": 0, "done": 0, "failed": 0, "trigger": trigger}
        if self._health.is_degraded:
            return {
                "success": False,
                "processed": 0,
                "done": 0,
                "failed": 0,
                "trigger": trigger,
                "detail": "embedding_degraded",
            }

        safe_limit = max(1, int(limit or self._health.config.paragraph_vector_backfill_batch_size))
        safe_retry = max(1, int(max_retry or self._health.config.paragraph_vector_backfill_max_retry))
        rows = metadata_store.fetch_paragraph_vector_backfill_batch(limit=safe_limit, max_retry=safe_retry)
        if not rows:
            return {"success": True, "processed": 0, "done": 0, "failed": 0, "trigger": trigger}

        pending_hashes = [
            str(row.get("paragraph_hash", "") or "").strip()
            for row in rows
            if str(row.get("paragraph_hash", "") or "").strip()
        ]
        if pending_hashes:
            metadata_store.mark_paragraph_vector_backfill_running(pending_hashes)

        done_hashes: List[str] = []
        encode_items: List[tuple[str, str]] = []
        paragraph_map = metadata_store.get_paragraphs_by_hashes(pending_hashes)
        for paragraph_hash in pending_hashes:
            if paragraph_hash in target_store:
                done_hashes.append(paragraph_hash)
                continue
            paragraph = paragraph_map.get(paragraph_hash)
            if paragraph is None:
                done_hashes.append(paragraph_hash)
                continue
            content = str(paragraph.get("content", "") or "").strip()
            if not content:
                done_hashes.append(paragraph_hash)
                continue
            encode_items.append((paragraph_hash, content))

        done_count, failed_count, last_error, encoded_done_hashes, failed_hashes = await self._encode_and_add(
            items=encode_items,
            batch_size=safe_limit,
            vector_store=target_store,
        )
        del done_count
        done_hashes.extend(encoded_done_hashes)
        for paragraph_hash in failed_hashes:
            metadata_store.mark_paragraph_vector_backfill_failed(paragraph_hash, last_error)
        if failed_hashes and self._health.config.embedding_fallback_enabled:
            self.set_embedding_degraded(active=True, reason=last_error[:500], checked_at=time.time())

        if done_hashes:
            metadata_store.mark_paragraph_vector_backfill_done(done_hashes)
            self._persist()

        return {
            "success": failed_count == 0,
            "processed": len(done_hashes) + failed_count,
            "done": len(done_hashes),
            "failed": failed_count,
            "trigger": trigger,
        }

    async def embedding_probe_loop(self) -> None:
        try:
            while not self._scheduler.stopping:
                await asyncio.sleep(self._health.config.embedding_probe_interval_seconds)
                if self._scheduler.stopping:
                    break
                startup_deferred = self._health.is_startup_self_check_deferred
                if not self._health.config.embedding_fallback_enabled and not startup_deferred:
                    continue
                if not self._health.is_degraded and not startup_deferred:
                    continue
                try:
                    await self.recover_embedding_once()
                except Exception as exc:
                    logger.warning(f"embedding 恢复探测失败: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"embedding_probe loop 异常: {exc}")

    async def paragraph_vector_backfill_loop(self) -> None:
        try:
            while not self._scheduler.stopping:
                await asyncio.sleep(self._health.config.paragraph_vector_backfill_interval_seconds)
                if self._scheduler.stopping:
                    break
                if not self._health.config.paragraph_vector_backfill_enabled:
                    continue
                if self._health.is_degraded:
                    continue
                await self.run_paragraph_backfill_once(
                    limit=self._health.config.paragraph_vector_backfill_batch_size,
                    max_retry=self._health.config.paragraph_vector_backfill_max_retry,
                    trigger="loop",
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"paragraph_vector_backfill loop 异常: {exc}")

    def paragraph_vector_backfill_counts(self) -> Dict[str, int]:
        metadata_store = self._get_metadata_store()
        if metadata_store is None:
            return {"pending": 0, "running": 0, "failed": 0, "done": 0}
        try:
            return metadata_store.get_paragraph_vector_backfill_status_counts()
        except Exception as exc:
            logger.warning(f"读取 paragraph 回填状态失败: {exc}")
            return {"pending": 0, "running": 0, "failed": 0, "done": 0}