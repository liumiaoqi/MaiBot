from typing import Any, Callable, Dict, List, Optional

from src.common.logger import get_logger

logger = get_logger("A_Memorix.MaintenanceService")


class MaintenanceService:

    def __init__(
        self,
        *,
        get_metadata_store: Callable[[], Any],
        get_graph_store: Callable[[], Any],
        cfg: Callable[[str, Any], Any],
        persist: Callable[[], None],
        rebuild_graph_from_metadata: Callable[[], None],
        resolve_relation_hashes: Callable[[str], List[str]],
        resolve_deleted_relation_hashes: Callable[[str], List[str]],
        delete_vectors_by_type: Callable[..., None],
        background_scheduler: Any,
        trigger_vector_compaction: Optional[Callable[[], int]] = None,
    ) -> None:
        self._get_metadata_store = get_metadata_store
        self._get_graph_store = get_graph_store
        self._cfg = cfg
        self._persist = persist
        self._rebuild_graph_from_metadata = rebuild_graph_from_metadata
        self._resolve_relation_hashes = resolve_relation_hashes
        self._resolve_deleted_relation_hashes = resolve_deleted_relation_hashes
        self._delete_vectors_by_type = delete_vectors_by_type
        self._background_scheduler = background_scheduler
        self._trigger_vector_compaction = trigger_vector_compaction
        self._last_maintenance_at: Optional[float] = None
        self._last_vector_compaction_at: float = 0.0
        self._last_vacuum_at: float = 0.0

    async def maintain_memory(
        self,
        *,
        action: str,
        target: str = "",
        hours: Optional[float] = None,
        reason: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        del reason
        metadata_store = self._get_metadata_store()
        assert metadata_store
        act = str(action or "").strip().lower()
        if act == "recycle_bin":
            items = metadata_store.get_deleted_relations(limit=max(1, int(limit or 50)))
            return {"success": True, "items": items, "count": len(items)}

        hashes = self._resolve_deleted_relation_hashes(target) if act == "restore" else self._resolve_relation_hashes(target)
        if not hashes:
            return {"success": False, "detail": "未命中可维护关系"}

        if act == "reinforce":
            metadata_store.reinforce_relations(hashes)
        elif act == "freeze":
            metadata_store.mark_relations_inactive(hashes)
            self._rebuild_graph_from_metadata()
        elif act == "protect":
            ttl_seconds = max(0.0, float(hours or 0.0)) * 3600.0
            metadata_store.protect_relations(hashes, ttl_seconds=ttl_seconds, is_pinned=ttl_seconds <= 0)
        elif act == "restore":
            restored = sum(1 for hash_value in hashes if metadata_store.restore_relation(hash_value))
            if restored <= 0:
                return {"success": False, "detail": "未恢复任何关系"}
            self._rebuild_graph_from_metadata()
        else:
            return {"success": False, "detail": f"不支持的维护动作: {act}"}

        import time
        self._last_maintenance_at = time.time()
        self._persist()
        return {"success": True, "detail": f"{act} {len(hashes)} 条关系"}

    async def memory_maintenance_loop(self) -> None:
        import asyncio
        try:
            while not self._background_scheduler.stopping:
                interval_hours = max(1.0 / 60.0, float(self._cfg("memory.base_decay_interval_hours", 1.0) or 1.0))
                await asyncio.sleep(max(60.0, interval_hours * 3600.0))
                if self._background_scheduler.stopping:
                    break
                if not bool(self._cfg("memory.enabled", True)):
                    continue
                await self._run_memory_maintenance_cycle(interval_hours=interval_hours)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "memory_maintenance 循环异常", exception=exc)
            logger.warning(f"memory_maintenance loop 异常: {exc}")

    async def _run_memory_maintenance_cycle(self, *, interval_hours: float) -> None:
        import time
        graph_store = self._get_graph_store()
        metadata_store = self._get_metadata_store()
        assert graph_store is not None
        assert metadata_store is not None
        half_life = float(self._cfg("memory.half_life_hours", 24.0) or 24.0)
        if half_life > 0:
            factor = 0.5 ** (float(interval_hours) / half_life)
            graph_store.decay(factor)

        await self._process_freeze_and_prune()
        await self._orphan_gc_phase()
        await self._purge_deleted_relations_phase()
        await self._vector_compaction_phase()
        await self._vacuum_phase()
        await self._compensate_graph_sync(metadata_store, graph_store)
        self._last_maintenance_at = time.time()
        self._persist()

    async def _purge_deleted_relations_phase(self) -> None:
        """P0-1: 清理过期 deleted_relations（ZG-29）。

        对标 Linux kernel/exit.c:411 do_exit——删除路径必须级联清理，
        不能"删一半留一半"。deleted_relations 是 backup_and_delete_relations
        的备份表，需定期物理清理。
        """
        import time
        metadata_store = self._get_metadata_store()
        assert metadata_store is not None
        retention_days = max(1.0, float(self._cfg("memory.deleted_relations_retention_days", 30.0) or 30.0))
        batch_size = max(1, int(self._cfg("memory.purge_batch_size", 500) or 500))
        cutoff = time.time() - retention_days * 86400.0
        try:
            purged = metadata_store.purge_deleted_relations(cutoff_time=cutoff, limit=batch_size)
            if purged:
                logger.info(f"purge_deleted_relations: 清理 {len(purged)} 条过期记录")
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "purge_deleted_relations 异常", exception=exc)
            logger.warning(f"purge_deleted_relations cycle 异常: {exc}")

    async def _vector_compaction_phase(self) -> None:
        """定期强制向量 compaction（ZG-29 P1-4）。

        对标 Linux slab shrinker 定期扫描——不能只靠阈值触发，需周期性兜底。
        """
        import time
        if self._trigger_vector_compaction is None:
            return
        interval_days = max(1.0, float(self._cfg("memory.vector_compaction_interval_days", 7.0) or 7.0))
        now = time.time()
        if self._last_vector_compaction_at > 0 and now - self._last_vector_compaction_at < interval_days * 86400.0:
            return
        try:
            compacted = self._trigger_vector_compaction()
            self._last_vector_compaction_at = now
            if compacted > 0:
                logger.info(f"vector compaction: 压缩 {compacted} 个 store")
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "vector compaction 异常", exception=exc)
            logger.warning(f"vector compaction cycle 异常: {exc}")

    async def _vacuum_phase(self) -> None:
        """定期 VACUUM 回收 SQLite 物理空间（P2 批2.4）。

        对标 Linux mm/vmscan.c slab shrinker——DELETE 不回收空间，需 VACUUM 才能缩小 db 文件。
        VACUUM 需独占锁，在大 db 上耗时，故频率低（默认 7 天）且在 purge/compaction 后执行。
        """
        import time
        if self._last_vacuum_at > 0:
            interval_days = max(1.0, float(self._cfg("memory.vacuum_interval_days", 7.0) or 7.0))
            if time.time() - self._last_vacuum_at < interval_days * 86400.0:
                return
        metadata_store = self._get_metadata_store()
        if metadata_store is None:
            return
        try:
            metadata_store.vacuum()
            self._last_vacuum_at = time.time()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "metadata VACUUM 异常", exception=exc)
            logger.warning(f"metadata VACUUM cycle 异常: {exc}")

    async def _compensate_graph_sync(self, metadata_store: Any, graph_store: Any) -> None:
        """P0-3: 补偿 graph_synced=false 的 relation（ZG-30）。

        对标 dsh "Dispose must reach quiescence"——失败不孤儿，需补偿。
        在 _process_freeze_and_prune/_orphan_gc_phase 之后执行。
        """
        try:
            pending = metadata_store.relations.get_relations_pending_graph_sync(limit=50)
            for rel in pending:
                for attempt in range(5):
                    try:
                        graph_store.add_edges(
                            [(rel["subject"], rel["object"])],
                            weights=[rel["confidence"]],
                            relation_hashes=[rel["hash"]],
                        )
                        metadata_store.relations.set_graph_synced(rel["hash"], True)
                        break
                    except Exception as e:
                        if attempt == 4:
                            logger.error(
                                f"graph sync compensation failed after 5 retries, hash={rel['hash']}, err={e}"
                            )
                        continue
        except Exception as exc:
            logger.warning(f"graph sync compensation cycle 异常: {exc}")

    async def _process_freeze_and_prune(self) -> None:
        import time
        metadata_store = self._get_metadata_store()
        graph_store = self._get_graph_store()
        assert metadata_store is not None
        assert graph_store is not None
        prune_threshold = max(0.0, float(self._cfg("memory.prune_threshold", 0.1) or 0.1))
        freeze_duration = max(0.0, float(self._cfg("memory.freeze_duration_hours", 24.0) or 24.0)) * 3600.0
        now = time.time()

        low_edges = graph_store.get_low_weight_edges(prune_threshold)
        hashes_to_freeze: List[str] = []
        edges_to_deactivate: List[tuple[str, str]] = []
        for src, tgt in low_edges:
            relation_hashes = list(graph_store.get_relation_hashes_for_edge(src, tgt))
            if not relation_hashes:
                continue
            statuses = metadata_store.get_relation_status_batch(relation_hashes)
            current_hashes: List[str] = []
            protected = False
            for hash_value, status in statuses.items():
                if bool(status.get("is_pinned")) or float(status.get("protected_until") or 0.0) > now:
                    protected = True
                    break
                current_hashes.append(hash_value)
            if protected or not current_hashes:
                continue
            hashes_to_freeze.extend(current_hashes)
            edges_to_deactivate.append((src, tgt))

        if hashes_to_freeze:
            metadata_store.mark_relations_inactive(hashes_to_freeze, inactive_since=now)
            graph_store.deactivate_edges(edges_to_deactivate)

        cutoff = now - freeze_duration
        expired_hashes = metadata_store.get_prune_candidates(cutoff)
        if not expired_hashes:
            return
        relation_info = metadata_store.get_relations_subject_object_map(expired_hashes)
        operations = [(src, tgt, hash_value) for hash_value, (src, tgt) in relation_info.items()]
        if operations:
            graph_store.prune_relation_hashes(operations)
        deleted_hashes = [hash_value for hash_value in expired_hashes if hash_value in relation_info]
        if deleted_hashes:
            metadata_store.backup_and_delete_relations(deleted_hashes)
            self._delete_vectors_by_type(relation_hashes=deleted_hashes)

    async def _orphan_gc_phase(self) -> None:
        metadata_store = self._get_metadata_store()
        graph_store = self._get_graph_store()
        assert metadata_store is not None
        assert graph_store is not None
        orphan_cfg = self._cfg("memory.orphan", {}) or {}
        if not bool(orphan_cfg.get("enable_soft_delete", True)):
            return
        entity_retention = max(0.0, float(orphan_cfg.get("entity_retention_days", 7.0) or 7.0)) * 86400.0
        paragraph_retention = max(0.0, float(orphan_cfg.get("paragraph_retention_days", 7.0) or 7.0)) * 86400.0
        grace_period = max(0.0, float(orphan_cfg.get("sweep_grace_hours", 24.0) or 24.0)) * 3600.0

        isolated = graph_store.get_isolated_nodes(include_inactive=True)
        if isolated:
            entity_hashes = metadata_store.get_entity_gc_candidates(isolated, retention_seconds=entity_retention)
            if entity_hashes:
                metadata_store.mark_as_deleted(entity_hashes, "entity")

        paragraph_hashes = metadata_store.get_paragraph_gc_candidates(retention_seconds=paragraph_retention)
        if paragraph_hashes:
            metadata_store.mark_as_deleted(paragraph_hashes, "paragraph")

        dead_paragraphs = metadata_store.sweep_deleted_items("paragraph", grace_period)
        if dead_paragraphs:
            hashes = [str(item[0] or "").strip() for item in dead_paragraphs if item and str(item[0] or "").strip()]
            if hashes:
                metadata_store.physically_delete_paragraphs(hashes)
                self._delete_vectors_by_type(paragraph_hashes=hashes)

        dead_entities = metadata_store.sweep_deleted_items("entity", grace_period)
        if dead_entities:
            entity_hashes = [str(item[0] or "").strip() for item in dead_entities if item and str(item[0] or "").strip()]
            entity_names = [str(item[1] or "").strip() for item in dead_entities if item and str(item[1] or "").strip()]
            if entity_names:
                graph_store.delete_nodes(entity_names)
            if entity_hashes:
                metadata_store.physically_delete_entities(entity_hashes)
                self._delete_vectors_by_type(entity_hashes=entity_hashes)
