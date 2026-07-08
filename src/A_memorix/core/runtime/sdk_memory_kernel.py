from __future__ import annotations


from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Coroutine, Dict, Iterable, List, Optional, Sequence

from json_repair import repair_json
import asyncio
import copy
import json
import numpy as np
import pickle
import shutil
import time


from src.common.logger import get_logger
from src.common.prompt_i18n import load_prompt
from src.config.config import global_config
from src.services import message_service as message_api
from src.services.llm_service import LLMServiceClient

from ...paths import default_data_dir, resolve_repo_path
from ..embedding import create_embedding_api_adapter
from ..retrieval import RetrievalResult, SparseBM25Config, SparseBM25Index
from ..storage import GraphStore, MetadataStore, QuantizationType, SparseMatrixFormat, VectorStore
from ..utils.aggregate_query_service import AggregateQueryService
from ..utils.episode_retrieval_service import EpisodeRetrievalService
from ..utils.episode_segmentation_service import EpisodeSegmentationService
from ..utils.episode_service import EpisodeService
from ..utils.hash import compute_hash, normalize_text
from ..utils.metadata import coerce_metadata_dict
from ..utils.person_profile_service import PersonProfileService
from ..utils.relation_write_service import RelationWriteService
from ..utils.retrieval_tuning_manager import RetrievalTuningManager

from ..utils.search_execution_service import SearchExecutionRequest, SearchExecutionResult, SearchExecutionService
from ..utils.summary_importer import SummaryImporter
from ..utils.time_parser import format_timestamp, parse_query_datetime_to_timestamp
from ..utils.web_import_manager import ImportTaskManager
from .search_runtime_initializer import SearchRuntimeBundle, build_search_runtime
from .services.feedback_correction import FeedbackCorrectionService
from .services.fuzzy_modify import FuzzyModifyService
from .services.graph_ops import GraphOpsService
from .services.hit_filter import HitFilterService
from .services.profile_evidence import ProfileEvidenceService
from .services.types import KernelSearchRequest, NormalizedSearchTimeWindow as _NormalizedSearchTimeWindow

logger = get_logger("A_Memorix.SDKMemoryKernel")



class SDKMemoryKernel:
    def __init__(self, *, plugin_root: Path, config: Optional[Dict[str, Any]] = None) -> None:
        self.plugin_root = Path(plugin_root).resolve()
        self.config = config or {}
        storage_cfg = self._cfg("storage", {}) or {}
        data_dir = str(storage_cfg.get("data_dir", "./data") or "./data")
        self.data_dir = resolve_repo_path(data_dir, fallback=default_data_dir())
        self.embedding_dimension = max(1, int(self._cfg("embedding.dimension", 1024)))
        self.relation_vectors_enabled = bool(self._cfg("retrieval.relation_vectorization.enabled", False))

        self.embedding_manager = None
        self.vector_store: Optional[VectorStore] = None
        self.paragraph_vector_store: Optional[VectorStore] = None
        self.graph_vector_store: Optional[VectorStore] = None
        self.graph_store: Optional[GraphStore] = None
        self.metadata_store: Optional[MetadataStore] = None
        self.relation_write_service: Optional[RelationWriteService] = None
        self.sparse_index: Optional[SparseBM25Index] = None
        self.retriever = None
        self.threshold_filter = None
        self.episode_retriever: Optional[EpisodeRetrievalService] = None
        self.aggregate_query_service: Optional[AggregateQueryService] = None
        self.person_profile_service: Optional[PersonProfileService] = None
        self.episode_segmentation_service: Optional[EpisodeSegmentationService] = None
        self.episode_service: Optional[EpisodeService] = None
        self.summary_importer: Optional[SummaryImporter] = None
        self.import_task_manager: Optional[ImportTaskManager] = None
        self.retrieval_tuning_manager: Optional[RetrievalTuningManager] = None
        self._runtime_bundle: Optional[SearchRuntimeBundle] = None
        self._runtime_self_check_report: Dict[str, Any] = {}
        self._initialized = False
        self._last_maintenance_at: Optional[float] = None
        self._request_dedup_tasks: Dict[str, asyncio.Task] = {}
        self._vector_rebuild_lock = asyncio.Lock()
        self._vector_persist_blocked_until_rebuild = False
        self._vector_rebuild_source_dimension: Optional[int] = None
        self._vector_pool_manager: Optional[Any] = None
        self._background_scheduler: Optional[Any] = None
        self._active_person_timestamps: Dict[str, float] = {}
        self._embedding_health_service: Optional[Any] = None
        self._current_effective_filter_cache: Dict[str, Any] = {"checked_at": 0.0, "needed": False}
        self._feedback_classifier: Optional[LLMServiceClient] = None
        self._fuzzy_modify_planner: Optional[LLMServiceClient] = None
        self._session_info_port: Optional[Any] = None
        self._feedback_config: Optional[Any] = None
        self._fuzzy_modify_config: Optional[Any] = None
        self._admin_handlers: Dict[str, Any] = {}
        self._delete_service: Optional[Any] = None
        self._fuzzy_modify_service: Optional[Any] = None
        self._feedback_correction_service: Optional[Any] = None
        self._profile_evidence_service: Optional[Any] = None
        self._memory_field: Optional[Any] = None
        self._graph_ops_service: Optional[Any] = None
        self._v5_memory_service: Optional[Any] = None
        self._hit_filter_service: Optional[Any] = None
        self._search_service: Optional[Any] = None
        self._ingest_service: Optional[Any] = None
        self._vector_rebuild_service: Optional[Any] = None
        self._dual_vector_migration_service: Optional[Any] = None
        self._embedding_recovery_service: Optional[Any] = None
        self._person_profile_facade: Optional[Any] = None
        self._vector_ensure_service: Optional[Any] = None

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._cfg(key, default)

    def _cfg(self, key: str, default: Any = None) -> Any:
        current: Any = self.config
        if (
            key
            in {
                "storage",
                "embedding",
                "retrieval",
                "graph",
                "episode",
                "web",
                "advanced",
                "threshold",
                "summarization",
                "person_profile",
            }
            and isinstance(current, dict)
        ):
            return current.get(key, default)
        for part in key.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def _set_cfg(self, key: str, value: Any) -> None:
        current: Dict[str, Any] = self.config
        parts = [part for part in str(key or "").split(".") if part]
        if not parts:
            return
        for part in parts[:-1]:
            next_value = current.get(part)
            if not isinstance(next_value, dict):
                next_value = {}
                current[part] = next_value
            current = next_value
        current[parts[-1]] = value

    def _build_runtime_config(self, base_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        runtime_config = dict(base_config if isinstance(base_config, dict) else self.config)
        runtime_cfg = runtime_config.get("runtime")
        runtime_config["runtime"] = dict(runtime_cfg) if isinstance(runtime_cfg, dict) else {}
        runtime_config["runtime"]["vector_pools_ready"] = self._dual_vector_pools_enabled()
        runtime_config.update(
            {
                "vector_store": self.vector_store,
                "paragraph_vector_store": self.paragraph_vector_store or self.vector_store,
                "graph_vector_store": self.graph_vector_store or self.vector_store,
                "graph_store": self.graph_store,
                "metadata_store": self.metadata_store,
                "embedding_manager": self.embedding_manager,
                "sparse_index": self.sparse_index,
                "relation_write_service": self.relation_write_service,
                "plugin_instance": self,
            }
        )
        return runtime_config

    @staticmethod
    def _merge_runtime_config_patch(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        merged = copy.deepcopy(base)
        for key, value in (patch or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = SDKMemoryKernel._merge_runtime_config_patch(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    async def apply_retrieval_tuning_profile(
        self,
        profile: Dict[str, Any],
        *,
        validate: bool = True,
    ) -> Dict[str, Any]:
        if not isinstance(profile, dict):
            return {
                "success": False,
                "runtime_rebuilt": False,
                "validation_passed": False,
                "error": "profile 必须是字典",
            }

        next_config = self._merge_runtime_config_patch(self.config, profile)
        runtime_bundle = build_search_runtime(
            plugin_config=self._build_runtime_config(next_config),
            logger_obj=logger,
            owner_tag="sdk_kernel_tuning_apply",
            log_prefix="[sdk]",
        )
        if validate and not runtime_bundle.ready:
            return {
                "success": False,
                "runtime_rebuilt": False,
                "validation_passed": False,
                "error": runtime_bundle.error or "检索运行时热重建失败",
            }
        if runtime_bundle.ready:
            self.config.clear()
            self.config.update(next_config)
            self._runtime_bundle = runtime_bundle
            self.retriever = runtime_bundle.retriever
            self.threshold_filter = runtime_bundle.threshold_filter
            self.sparse_index = runtime_bundle.sparse_index or self.sparse_index
            self._refresh_runtime_dependents(preserve_managers=True)
            self._apply_runtime_sparse_mode()
            return {
                "success": True,
                "runtime_rebuilt": True,
                "validation_passed": True,
                "error": "",
            }
        return {
            "success": False,
            "runtime_rebuilt": False,
            "validation_passed": False,
            "error": runtime_bundle.error or "检索运行时热重建失败",
        }

    def is_runtime_ready(self) -> bool:
        return bool(
            self._initialized
            and self.vector_store is not None
            and self.graph_store is not None
            and self.metadata_store is not None
            and self.embedding_manager is not None
            and self.retriever is not None
        )

    def is_chat_enabled(self, stream_id: str, group_id: str | None = None, user_id: str | None = None) -> bool:
        return self._hit_filter_service.is_chat_enabled(stream_id, group_id, user_id)

    @staticmethod
    def _chat_filter_config_allows(
        filter_config: Dict[str, Any],
        *,
        stream_id: str = "",
        group_id: str = "",
        user_id: str = "",
        default_when_empty: bool = True,
    ) -> bool:
        from .services.hit_filter import HitFilterService
        return HitFilterService.chat_filter_config_allows(
            filter_config, stream_id=stream_id, group_id=group_id, user_id=user_id, default_when_empty=default_when_empty,
        )

    def _is_chat_filtered(
        self,
        *,
        respect_filter: bool,
        stream_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> bool:
        return self._hit_filter_service.is_chat_filtered(
            respect_filter=respect_filter, stream_id=stream_id, group_id=group_id, user_id=user_id,
        )


    @staticmethod
    def _normalize_embedding_fingerprint(value: Any) -> Optional[Dict[str, Any]]:
        from .services.vector_pool import VectorPoolManager
        return VectorPoolManager.normalize_embedding_fingerprint(value)


    @staticmethod
    def _embedding_fingerprint_status(
        current: Optional[Dict[str, Any]],
        stored: Optional[Dict[str, Any]],
        *,
        has_stored_vectors: bool,
    ) -> str:
        from .services.vector_pool import VectorPoolManager
        return VectorPoolManager.embedding_fingerprint_status(current, stored, has_stored_vectors=has_stored_vectors)


    def _vector_rebuild_status(self) -> Dict[str, Any]:
        if self._vector_rebuild_service is not None:
            return self._vector_rebuild_service.vector_rebuild_status()
        return self._vector_pool_manager.vector_rebuild_status(
            vector_rebuild_lock_locked=self._vector_rebuild_lock.locked(),
            vector_persist_blocked=self._vector_persist_blocked_until_rebuild,
            vector_rebuild_source_dimension=self._vector_rebuild_source_dimension,
        )

    def _vector_pool_mode(self) -> str:
        return self._vector_pool_manager.config.mode

    def _dual_vector_pools_enabled(self) -> bool:
        return self._vector_pool_manager.dual_pools_enabled

    def _write_dual_vector_ready_manifest(self, *, stats: Dict[str, Dict[str, int]], migration_stats: Dict[str, Dict[str, int]]) -> None:
        return self._dual_vector_migration_service.write_dual_vector_ready_manifest(stats=stats, migration_stats=migration_stats)

    def _clear_legacy_single_vector_files_after_dual_ready(self) -> None:
        return self._dual_vector_migration_service.clear_legacy_single_vector_files_after_dual_ready()

    def _reload_dual_vector_stores_from_disk(self) -> bool:
        return self._dual_vector_migration_service.reload_dual_vector_stores_from_disk()


    def _refresh_relation_write_service(self) -> None:
        if (
            self.metadata_store is None
            or self.graph_store is None
            or self.vector_store is None
            or self.embedding_manager is None
        ):
            self.relation_write_service = None
            return
        self.relation_write_service = RelationWriteService(
            metadata_store=self.metadata_store,
            graph_store=self.graph_store,
            vector_store=self.vector_store,
            graph_vector_store=self._graph_vector_store(),
            embedding_manager=self.embedding_manager,
            use_typed_relation_ids=self._dual_vector_pools_enabled(),
        )

    @staticmethod
    def _graph_vector_id(item_type: str, hash_value: str) -> str:
        from .services.vector_pool import VectorPoolManager
        return VectorPoolManager.graph_vector_id(item_type, hash_value)


    def _graph_vector_store(self) -> Optional[VectorStore]:
        return self._vector_pool_manager.graph_vector_store_resolved()

    def _delete_vectors_by_type(
        self,
        *,
        paragraph_hashes: Sequence[str] = (),
        entity_hashes: Sequence[str] = (),
        relation_hashes: Sequence[str] = (),
    ) -> int:
        return self._vector_pool_manager.delete_vectors_by_type(
            paragraph_hashes=paragraph_hashes,
            entity_hashes=entity_hashes,
            relation_hashes=relation_hashes,
            merge_tokens_fn=self._merge_tokens,
        )

    def _set_embedding_degraded(self, *, active: bool, reason: str = "", checked_at: Optional[float] = None) -> None:
        if self._embedding_recovery_service is not None:
            self._embedding_recovery_service.set_embedding_degraded(active=active, reason=reason, checked_at=checked_at)
        else:
            self._embedding_health_service.set_degraded(active=active, reason=reason, checked_at=checked_at)

    def _apply_runtime_sparse_mode(self) -> None:
        if self._embedding_recovery_service is not None:
            self._embedding_recovery_service.apply_runtime_sparse_mode()

    async def _refresh_runtime_self_check(self, *, sample_text: str = "A_Memorix runtime self check") -> Dict[str, Any]:
        return await self._embedding_recovery_service.refresh_runtime_self_check(sample_text=sample_text)

    def _mark_startup_self_check_deferred(self) -> None:
        self._embedding_recovery_service.mark_startup_self_check_deferred()


    @staticmethod
    def _self_check_effective_dimension(report: Dict[str, Any]) -> int:
        from .services.embedding_recovery import EmbeddingRecoveryService
        return EmbeddingRecoveryService.self_check_effective_dimension(report)

    def _apply_self_check_dimension_result(self, report: Dict[str, Any]) -> str:
        return self._embedding_recovery_service.apply_self_check_dimension_result(report)

    async def reinforce_access(self, relation_hashes: Sequence[str]) -> None:
        if self.metadata_store is None:
            return
        hashes = [str(item or "").strip() for item in relation_hashes if str(item or "").strip()]
        if not hashes:
            return
        self.metadata_store.reinforce_relations(hashes)
        self._last_maintenance_at = time.time()

    def enqueue_paragraph_vector_backfill(self, paragraph_hash: str, *, error: str = "") -> None:
        self._embedding_recovery_service.enqueue_paragraph_vector_backfill(paragraph_hash, error=error)

    async def write_paragraph_vector_or_enqueue(
        self,
        *,
        paragraph_hash: str,
        content: str,
        context: str = "",
    ) -> Dict[str, Any]:
        return await self._embedding_recovery_service.write_paragraph_vector_or_enqueue(
            paragraph_hash=paragraph_hash, content=content, context=context,
        )

    def _paragraph_vector_backfill_counts(self) -> Dict[str, int]:
        return self._embedding_recovery_service.paragraph_vector_backfill_counts()

    async def _run_paragraph_backfill_once(
        self,
        *,
        limit: Optional[int] = None,
        max_retry: Optional[int] = None,
        trigger: str = "manual",
    ) -> Dict[str, Any]:
        return await self._embedding_recovery_service.run_paragraph_backfill_once(
            limit=limit, max_retry=max_retry, trigger=trigger,
        )

    def _count_vector_rebuild_targets(self) -> Dict[str, int]:
        self._vector_pool_manager.metadata_store = self.metadata_store
        return self._vector_pool_manager.count_vector_rebuild_targets()

    def _table_has_column(self, table: str, column: str) -> bool:
        if self.metadata_store is None:
            return False
        token = str(table or "").strip()
        col = str(column or "").strip()
        if token not in {"paragraphs", "entities", "relations"} or not col:
            return False
        rows = self.metadata_store.query(f"PRAGMA table_info({token})")
        return any(str(row.get("name", "") or "") == col for row in rows)

    def _active_row_filter_sql(self, table: str) -> str:
        if str(table or "").strip() == "relations" and self._table_has_column("relations", "is_inactive"):
            return "is_inactive IS NULL OR is_inactive = 0"
        return "is_deleted IS NULL OR is_deleted = 0" if self._table_has_column(table, "is_deleted") else "1 = 1"

    async def _backfill_missing_dual_vector_pool_entries(self, *, batch_size: int) -> Dict[str, Any]:
        return await self._dual_vector_migration_service.backfill_missing_dual_vector_pool_entries(batch_size=batch_size)

    def _refresh_runtime_dependents(self, *, preserve_managers: bool = True) -> None:
        if (
            self.metadata_store is None
            or self.graph_store is None
            or self.vector_store is None
            or self.embedding_manager is None
            or self.retriever is None
        ):
            return

        runtime_config = self._build_runtime_config()
        self.episode_retriever = EpisodeRetrievalService(metadata_store=self.metadata_store, retriever=self.retriever)
        self.aggregate_query_service = AggregateQueryService(plugin_config=runtime_config)
        self.person_profile_service = PersonProfileService(
            metadata_store=self.metadata_store,
            graph_store=self.graph_store,
            vector_store=self.vector_store,
            paragraph_vector_store=self.paragraph_vector_store or self.vector_store,
            graph_vector_store=self.graph_vector_store or self.vector_store,
            embedding_manager=self.embedding_manager,
            sparse_index=self.sparse_index,
            plugin_config=runtime_config,
            retriever=self.retriever,
        )
        self.episode_segmentation_service = EpisodeSegmentationService(plugin_config=runtime_config)
        self.episode_service = EpisodeService(
            metadata_store=self.metadata_store,
            plugin_config=runtime_config,
            segmentation_service=self.episode_segmentation_service,
        )
        self.summary_importer = SummaryImporter(
            vector_store=self.vector_store,
            graph_store=self.graph_store,
            metadata_store=self.metadata_store,
            embedding_manager=self.embedding_manager,
            plugin_config=runtime_config,
        )
        if not preserve_managers:
            self.import_task_manager = ImportTaskManager(self)
            self.retrieval_tuning_manager = RetrievalTuningManager(
                self,
                import_write_blocked_provider=self.import_task_manager.is_write_blocked,
            )



    async def _rebuild_all_vectors(
        self,
        *,
        batch_size: Optional[int] = None,
        include_relations: Optional[bool] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        return await self._vector_rebuild_service.rebuild_all_vectors(
            batch_size=batch_size,
            include_relations=include_relations,
            dry_run=dry_run,
        )

    async def _detect_current_embedding_dimension_for_rebuild(self) -> int:
        return await self._vector_rebuild_service._detect_current_embedding_dimension_for_rebuild()

    async def _recover_embedding_once(self, *, sample_text: str = "A_Memorix runtime self check") -> Dict[str, Any]:
        return await self._embedding_recovery_service.recover_embedding_once(sample_text=sample_text)

    async def initialize(self) -> None:
        if self._initialized:
            self._apply_runtime_sparse_mode()
            await self._start_background_tasks()
            return

        self.data_dir.mkdir(parents=True, exist_ok=True)

        from .config.vector_pool_config import VectorPoolConfig
        from .config.feedback_config import FeedbackConfig
        from .config.fuzzy_modify_config import FuzzyModifyConfig
        from .services.embedding_health import EmbeddingHealthService
        from .services.background_scheduler import BackgroundTaskScheduler
        self._embedding_health_service = EmbeddingHealthService(
            vector_pool_config=VectorPoolConfig.from_config(self.config),
        )
        self._background_scheduler = BackgroundTaskScheduler()
        self._feedback_config = FeedbackConfig.from_global_config()
        self._fuzzy_modify_config = FuzzyModifyConfig.from_global_config()

        self.embedding_manager = create_embedding_api_adapter(
            batch_size=int(self._cfg("embedding.batch_size", 32)),
            max_concurrent=int(self._cfg("embedding.max_concurrent", 5)),
            default_dimension=self.embedding_dimension,
            enable_cache=bool(self._cfg("embedding.enable_cache", False)),
            model_name=str(self._cfg("embedding.model_name", "auto") or "auto"),
            dimension_request_mode=str(self._cfg("embedding.dimension_request_mode", "explicit") or "explicit"),
            retry_config=self._cfg("embedding.retry", {}) or {},
        )

        from .services.vector_pool import VectorPoolManager
        self._vector_pool_manager = VectorPoolManager(
            config=VectorPoolConfig.from_config(self.config),
            data_dir=self.data_dir,
            embedding_dimension=self.embedding_dimension,
            embedding_manager=self.embedding_manager,
            relation_vectors_enabled=self.relation_vectors_enabled,
        )

        stored_dimension = self._vector_pool_manager.stored_vector_dimension()
        provisional_dimension = stored_dimension or self.embedding_dimension
        self.embedding_dimension = int(provisional_dimension)

        matrix_format = str(self._cfg("graph.sparse_matrix_format", "csr") or "csr").strip().lower()
        graph_format = SparseMatrixFormat.CSC if matrix_format == "csc" else SparseMatrixFormat.CSR

        self.vector_store = self._vector_pool_manager.make_vector_store(self._vector_pool_manager.vectors_root(), dimension=provisional_dimension)
        self.paragraph_vector_store = self._vector_pool_manager.make_vector_store(
            self._vector_pool_manager.paragraph_vector_dir(),
            dimension=provisional_dimension,
        )
        self.graph_vector_store = self._vector_pool_manager.make_vector_store(
            self._vector_pool_manager.graph_vector_dir(),
            dimension=provisional_dimension,
        )
        self.graph_store = GraphStore(matrix_format=graph_format, data_dir=self.data_dir / "graph")
        self.metadata_store = MetadataStore(data_dir=self.data_dir / "metadata")
        self.metadata_store.connect()

        skip_vector_load = False
        if self.graph_store.has_data():
            self.graph_store.load()

        sparse_cfg_raw = self._cfg("retrieval.sparse", {}) or {}
        try:
            sparse_cfg = SparseBM25Config(**sparse_cfg_raw)
        except Exception as exc:
            logger.warning(f"sparse 配置非法，回退默认: {exc}")
            sparse_cfg = SparseBM25Config()
        self.sparse_index = SparseBM25Index(metadata_store=self.metadata_store, config=sparse_cfg)
        if self.sparse_index.config.enabled:
            warmup_summary = self.sparse_index.warmup()
            if warmup_summary.get("ok"):
                logger.info(
                    "[sdk] 稀疏索引预热完成: "
                    f"backend={warmup_summary.get('backend')}, "
                    f"docs={warmup_summary.get('doc_count')}, "
                    f"duration_ms={float(warmup_summary.get('duration_ms', 0.0)):.2f}"
                )
            else:
                logger.warning(
                    "[sdk] 稀疏索引预热失败，后续检索将按需重试: "
                    f"{warmup_summary.get('error', 'unknown')}"
                )

        if not skip_vector_load and self.vector_store.has_data():
            self.vector_store.load()
            self.vector_store.warmup_index(force_train=True)
        self._vector_pool_manager.dual_pools_ready = False
        if self._vector_pool_manager.config.config_enabled:
            self._vector_pool_manager.cleanup_stale_dual_vector_build_dirs()
            self._vector_pool_manager.vector_store = self.vector_store
            self._vector_pool_manager.paragraph_vector_store = self.paragraph_vector_store
            self._vector_pool_manager.graph_vector_store = self.graph_vector_store
            self._vector_pool_manager.metadata_store = self.metadata_store
            if not self._vector_pool_manager.reload_dual_vector_stores_from_disk():
                logger.warning("双池配置已开启，但 ready manifest 不可用，当前按单池检索与写入运行")
            self.vector_store = self._vector_pool_manager.vector_store
            self.paragraph_vector_store = self._vector_pool_manager.paragraph_vector_store
            self.graph_vector_store = self._vector_pool_manager.graph_vector_store

        self._refresh_relation_write_service()

        runtime_config = self._build_runtime_config()
        self._runtime_bundle = build_search_runtime(
            plugin_config=runtime_config,
            logger_obj=logger,
            owner_tag="sdk_kernel",
            log_prefix="[sdk]",
        )
        if not self._runtime_bundle.ready:
            raise RuntimeError(self._runtime_bundle.error or "检索运行时初始化失败")

        self.retriever = self._runtime_bundle.retriever
        self.threshold_filter = self._runtime_bundle.threshold_filter
        self.sparse_index = self._runtime_bundle.sparse_index or self.sparse_index
        self._apply_runtime_sparse_mode()

        self._refresh_runtime_dependents(preserve_managers=True)
        self.import_task_manager = ImportTaskManager(self)
        self.retrieval_tuning_manager = RetrievalTuningManager(
            self,
            import_write_blocked_provider=self.import_task_manager.is_write_blocked,
        )

        from .services.embedding_recovery import EmbeddingRecoveryService
        self._embedding_recovery_service = EmbeddingRecoveryService(
            embedding_health_service=self._embedding_health_service,
            vector_pool_manager=self._vector_pool_manager,
            cfg=self._cfg,
            build_runtime_config=self._build_runtime_config,
            refresh_runtime_dependents=lambda: None,
            persist=self._persist,
            encode_and_add_rebuild_vectors=lambda *a, **kw: self._vector_rebuild_service._encode_and_add_rebuild_vectors(*a, **kw),
            metadata_store_getter=lambda: self.metadata_store,
            embedding_manager_getter=lambda: self.embedding_manager,
            vector_store_getter=lambda: self.vector_store,
            paragraph_vector_store_getter=lambda: self.paragraph_vector_store,
            embedding_dimension_getter=lambda: self.embedding_dimension,
            embedding_dimension_setter=lambda v: setattr(self, 'embedding_dimension', v),
            vector_persist_blocked_getter=lambda: self._vector_persist_blocked_until_rebuild,
            vector_persist_blocked_setter=lambda v: setattr(self, '_vector_persist_blocked_until_rebuild', v),
            vector_rebuild_source_dimension_getter=lambda: self._vector_rebuild_source_dimension,
            vector_rebuild_source_dimension_setter=lambda v: setattr(self, '_vector_rebuild_source_dimension', v),
            background_scheduler=self._background_scheduler,
            vector_rebuild_status_getter=self._vector_rebuild_status,
            runtime_self_check_report_setter=lambda v: setattr(self, '_runtime_self_check_report', v),
            retriever_getter=lambda: self.retriever,
        )

        self._mark_startup_self_check_deferred()

        from .services.person_profile_facade import PersonProfileFacade
        self._person_profile_facade = PersonProfileFacade(
            cfg=self._cfg,
            metadata_store_getter=lambda: self.metadata_store,
            person_profile_service_getter=lambda: self.person_profile_service,
            feedback_correction_service_getter=lambda: self._feedback_correction_service,
            hit_filter_service_getter=lambda: self._hit_filter_service,
            active_person_timestamps=self._active_person_timestamps,
            background_scheduler=self._background_scheduler,
            initialize=self.initialize,
        )

        from .services.kernel_initializer import KernelInitializer
        KernelInitializer.init_all_services(self)

        self._initialized = True

        from ..connectionist.memory_field import MemoryField
        self._memory_field = MemoryField(self.data_dir)

        await self._start_background_tasks()

    async def shutdown(self) -> None:
        await self._stop_background_tasks()
        if self.import_task_manager is not None:
            try:
                await self.import_task_manager.shutdown()
            except Exception as exc:
                logger.warning(f"关闭导入任务管理器失败: {exc}")
        if self.retrieval_tuning_manager is not None:
            try:
                await self.retrieval_tuning_manager.shutdown()
            except Exception as exc:
                logger.warning(f"关闭调优任务管理器失败: {exc}")
        self.close()

    def close(self) -> None:
        try:
            self._persist()
        finally:
            if self.metadata_store is not None:
                self.metadata_store.close()
            self._initialized = False
            self._request_dedup_tasks.clear()
            self._runtime_self_check_report = {}
            if self._embedding_recovery_service is not None:
                self._embedding_recovery_service._runtime_self_check_report = {}
            self._active_person_timestamps.clear()


    async def execute_request_with_dedup(
        self,
        request_key: str,
        executor: Callable[[], Coroutine[Any, Any, Dict[str, Any]]],
    ) -> tuple[bool, Dict[str, Any]]:
        token = str(request_key or "").strip()
        if not token:
            return False, await executor()

        existing = self._request_dedup_tasks.get(token)
        if existing is not None:
            return True, await existing

        task = asyncio.create_task(executor())
        self._request_dedup_tasks[token] = task
        try:
            payload = await task
            return False, payload
        finally:
            current = self._request_dedup_tasks.get(token)
            if current is task:
                self._request_dedup_tasks.pop(token, None)

    async def summarize_chat_stream(
        self,
        *,
        chat_id: str,
        context_length: Optional[int] = None,
        include_personality: Optional[bool] = None,
        time_end: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        await self.initialize()
        return await self._ingest_service.summarize_chat_stream(
            chat_id=chat_id,
            context_length=context_length,
            include_personality=include_personality,
            time_end=time_end,
            metadata=metadata,
        )


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
        await self.initialize()
        return await self._ingest_service.ingest_summary(
            external_id=external_id,
            chat_id=chat_id,
            text=text,
            participants=participants,
            time_start=time_start,
            time_end=time_end,
            tags=tags,
            metadata=metadata,
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
        await self.initialize()
        return await self._ingest_service.ingest_text(
            external_id=external_id,
            source_type=source_type,
            text=text,
            chat_id=chat_id,
            person_ids=person_ids,
            participants=participants,
            timestamp=timestamp,
            time_start=time_start,
            time_end=time_end,
            tags=tags,
            metadata=metadata,
            entities=entities,
            relations=relations,
            respect_filter=respect_filter,
            user_id=user_id,
            group_id=group_id,
        )


    async def process_episode_pending_batch(self, *, limit: int = 20, max_retry: int = 3) -> Dict[str, Any]:
        await self.initialize()
        return await self._ingest_service.process_episode_pending_batch(limit=limit, max_retry=max_retry)


    async def search_memory(self, request: KernelSearchRequest) -> Dict[str, Any]:
        await self.initialize()
        return await self._search_service.search_memory(request)

    async def _fuzzy_modify_search_memory_adapter(self, request_text: str, limit: int, scope: str, person_id: str, chat_id: str) -> Dict[str, Any]:
        return await self.search_memory(
            KernelSearchRequest(
                query=request_text,
                limit=limit,
                mode="aggregate",
                chat_id=chat_id,
                person_id=person_id,
                respect_filter=True,
            )
        )

    @staticmethod
    def _empty_person_profile_response(*, person_id: str = "", person_name: str = "") -> Dict[str, Any]:
        from .services.person_profile_facade import PersonProfileFacade
        return PersonProfileFacade.empty_person_profile_response(person_id=person_id, person_name=person_name)

    def _build_person_profile_response(
        self,
        profile: Dict[str, Any],
        *,
        requested_person_id: str,
        limit: int,
    ) -> Dict[str, Any]:
        return self._person_profile_facade.build_person_profile_response(
            profile, requested_person_id=requested_person_id, limit=limit,
        )

    async def get_person_profile(self, *, person_id: str, chat_id: str = "", limit: int = 10) -> Dict[str, Any]:
        return await self._person_profile_facade.get_person_profile(person_id=person_id, chat_id=chat_id, limit=limit)

    async def refresh_person_profile(self, person_id: str, limit: int = 10, *, mark_active: bool = True) -> Dict[str, Any]:
        return await self._person_profile_facade.refresh_person_profile(person_id, limit, mark_active=mark_active)

    async def maintain_memory(
        self,
        *,
        action: str,
        target: str = "",
        hours: Optional[float] = None,
        reason: str = "",
        limit: int = 50,
    ) -> Dict[str, Any]:
        await self.initialize()
        return await self._maintenance_service.maintain_memory(
            action=action,
            target=target,
            hours=hours,
            reason=reason,
            limit=limit,
        )


    async def rebuild_episodes_for_sources(self, sources: Iterable[str]) -> Dict[str, Any]:
        await self.initialize()
        assert self.metadata_store is not None
        assert self.episode_service is not None

        items: List[Dict[str, Any]] = []
        failures: List[Dict[str, str]] = []
        for source in self._tokens(sources):
            self.metadata_store.mark_episode_source_running(source)
            try:
                result = await self.episode_service.rebuild_source(source)
                self.metadata_store.mark_episode_source_done(source)
                items.append(result)
            except Exception as exc:
                err = str(exc)[:500]
                self.metadata_store.mark_episode_source_failed(source, err)
                failures.append({"source": source, "error": err})
        self._persist()
        return {
            "rebuilt": len(items),
            "items": items,
            "failures": failures,
            "sources": [str(item.get("source", "") or "") for item in items] or self._tokens(sources),
        }

    def memory_stats(self) -> Dict[str, Any]:
        assert self.metadata_store
        stats = self.metadata_store.get_statistics()
        episodes = self.metadata_store.query("SELECT COUNT(*) AS c FROM episodes")[0]["c"]
        profiles = self.metadata_store.query("SELECT COUNT(*) AS c FROM person_profile_snapshots")[0]["c"]
        pending = self.metadata_store.query(
            "SELECT COUNT(*) AS c FROM episode_pending_paragraphs WHERE status IN ('pending', 'running', 'failed')"
        )[0]["c"]
        backfill = self._paragraph_vector_backfill_counts()
        episode_rebuild_summary = self.metadata_store.get_episode_source_rebuild_summary()
        episode_rebuild_counts = episode_rebuild_summary.get("counts", {}) if isinstance(episode_rebuild_summary, dict) else {}
        return {
            "paragraphs": int(stats.get("paragraph_count", 0) or 0),
            "relations": int(stats.get("relation_count", 0) or 0),
            "episodes": int(episodes or 0),
            "profiles": int(profiles or 0),
            "episode_pending": int(pending or 0),
            "stale_paragraph_marks": int(stats.get("stale_paragraph_mark_count", 0) or 0),
            "profile_refresh_pending": int(stats.get("person_profile_refresh_pending_count", 0) or 0),
            "profile_refresh_failed": int(stats.get("person_profile_refresh_failed_count", 0) or 0),
            "episode_rebuild_pending": int(
                (episode_rebuild_counts.get("pending", 0) or 0)
                + (episode_rebuild_counts.get("running", 0) or 0)
                + (episode_rebuild_counts.get("failed", 0) or 0)
            ),
            "paragraph_vector_backfill_pending": int(backfill.get("pending", 0) or 0),
            "paragraph_vector_backfill_failed": int(backfill.get("failed", 0) or 0),
            "last_maintenance_at": self._last_maintenance_at,
        }

    @staticmethod
    def _vector_store_snapshot(store: Optional[VectorStore]) -> Dict[str, Any]:
        from .services.vector_pool import VectorPoolManager
        return VectorPoolManager.vector_store_snapshot(store)

    def _vector_pools_status(self) -> Dict[str, Any]:
        return self._vector_pool_manager.vector_pools_status()

    def _should_start_dual_vector_auto_migration(self) -> bool:
        return self._dual_vector_migration_service.should_start_dual_vector_auto_migration()

    def _normalize_dual_vector_auto_migration_progress(
        self,
        progress: Optional[Dict[str, Any]] = None,
        *,
        now: Optional[float] = None,
        explicit_processed: bool = False,
        completed: bool = False,
        success: bool = False,
    ) -> Dict[str, Any]:
        return self._dual_vector_migration_service.normalize_dual_vector_auto_migration_progress(
            progress, now=now, explicit_processed=explicit_processed, completed=completed, success=success,
        )

    def _update_dual_vector_auto_migration_stage(self, stage: str, **progress: Any) -> None:
        return self._dual_vector_migration_service.update_dual_vector_auto_migration_stage(stage, **progress)


    def get_import_task_manager(self) -> Optional[ImportTaskManager]:
        return self.import_task_manager

    def get_retrieval_tuning_manager(self) -> Optional[RetrievalTuningManager]:
        return self.retrieval_tuning_manager

    def _persist(self, *, force_vectors: bool = False) -> None:
        rebuild_required = False if force_vectors else bool(
            self._vector_rebuild_status().get("vector_rebuild_required", False)
        )
        if self.vector_store is not None and not self._dual_vector_pools_enabled():
            if rebuild_required:
                logger.debug("检测到向量库需要重建，跳过向量库持久化以保留重建提示")
            else:
                self._vector_pool_manager.save_vector_store(self.vector_store)
        if self._dual_vector_pools_enabled() and not rebuild_required:
            if self.paragraph_vector_store is not None:
                self._vector_pool_manager.save_vector_store(self.paragraph_vector_store)
            if self.graph_vector_store is not None:
                self._vector_pool_manager.save_vector_store(self.graph_vector_store)
        if self.graph_store is not None:
            self.graph_store.save()
        if self.sparse_index is not None and self.sparse_index.config.enabled:
            self.sparse_index.ensure_loaded()

    async def _start_background_tasks(self) -> None:
        registrations = {
            "auto_save": self._auto_save_loop,
            "episode_pending": self._ingest_service.episode_pending_loop,
            "embedding_probe": self._embedding_probe_loop,
            "paragraph_vector_backfill": self._paragraph_vector_backfill_loop,
            "memory_maintenance": self._maintenance_service.memory_maintenance_loop,
            "person_profile_refresh": self._person_profile_refresh_loop,
            "person_profile_refresh_queue": self._person_profile_refresh_queue_loop,
            "feedback_correction": self._feedback_correction_service._feedback_correction_loop,
            "feedback_correction_reconcile": self._feedback_correction_service._feedback_correction_reconcile_loop,
        }
        if self._should_start_dual_vector_auto_migration():
            registrations["dual_vector_auto_migration"] = self._dual_vector_auto_migration_loop
        await self._background_scheduler.start_all(registrations)


    async def _sleep_background(self, seconds: float) -> None:
        await self._background_scheduler.sleep(seconds)

    async def _dual_vector_auto_migration_loop(self) -> None:
        return await self._dual_vector_migration_service.dual_vector_auto_migration_loop()

    async def _stop_background_tasks(self) -> None:

        await self._background_scheduler.stop_all()

    async def _auto_save_loop(self) -> None:
        try:
            while not self._background_scheduler.stopping:
                interval_minutes = max(1.0, float(self._cfg("advanced.auto_save_interval_minutes", 5) or 5))
                await asyncio.sleep(interval_minutes * 60.0)
                if self._background_scheduler.stopping:
                    break
                if bool(self._cfg("advanced.enable_auto_save", True)):
                    self._persist()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"auto_save loop 异常: {exc}")

    async def _embedding_probe_loop(self) -> None:
        await self._embedding_recovery_service.embedding_probe_loop()

    async def _paragraph_vector_backfill_loop(self) -> None:
        await self._embedding_recovery_service.paragraph_vector_backfill_loop()

    async def _person_profile_refresh_loop(self) -> None:
        await self._person_profile_facade.person_profile_refresh_loop()

    async def _person_profile_refresh_queue_loop(self) -> None:
        await self._person_profile_facade.person_profile_refresh_queue_loop()

    @staticmethod
    def _safe_json_loads(raw: Any) -> Dict[str, Any]:

        if isinstance(raw, dict):
            return raw
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            repaired = repair_json(text)
            payload = json.loads(repaired) if isinstance(repaired, str) else repaired
        except Exception:
            payload = None
        return payload if isinstance(payload, dict) else {}


    def _should_auto_enqueue_episode(self, *, source_type: str) -> bool:
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

    def _person_profile_refresh_queue_interval_seconds(self) -> float:
        return self._person_profile_facade._queue_interval_seconds()

    def _person_profile_refresh_queue_batch_size(self) -> int:
        return self._person_profile_facade._queue_batch_size()

    def _person_profile_refresh_debounce_seconds(self) -> float:
        return self._person_profile_facade._debounce_seconds()

    def _person_profile_refresh_retry_backoff_seconds(self) -> float:
        return self._person_profile_facade._retry_backoff_seconds()

    def _person_profile_refresh_max_retry(self) -> int:
        return self._person_profile_facade._max_retry()

    def _enqueue_person_profile_refresh(self, person_id: str, *, reason: str = "") -> bool:
        return self._person_profile_facade.enqueue_person_profile_refresh(person_id, reason=reason)

    def _has_pending_person_profile_refresh(self, person_id: str) -> bool:
        return self._person_profile_facade.has_pending_person_profile_refresh(person_id)

    async def _process_person_profile_refresh_queue_batch(self, *, limit: int) -> Dict[str, Any]:
        return await self._person_profile_facade.process_person_profile_refresh_queue_batch(limit=limit)


    def _mark_person_active(self, person_id: str) -> None:
        self._person_profile_facade.mark_person_active(person_id)

    @staticmethod
    def _tokens(values: Optional[Iterable[Any]]) -> List[str]:
        result: List[str] = []
        seen = set()
        for item in values or []:
            token = str(item or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            result.append(token)
        return result

    @classmethod
    def _merge_tokens(cls, *groups: Optional[Iterable[Any]]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for group in groups:
            for item in cls._tokens(group):
                if item in seen:
                    continue
                seen.add(item)
                merged.append(item)
        return merged

    @classmethod
    def _argument_tokens(cls, value: Any) -> List[str]:
        if isinstance(value, str):
            return cls._tokens([value])
        return cls._tokens(value)

    @classmethod
    def _merge_argument_tokens(cls, *groups: Any) -> List[str]:
        merged: List[str] = []
        seen = set()
        for group in groups:
            for item in cls._argument_tokens(group):
                if item in seen:
                    continue
                seen.add(item)
                merged.append(item)
        return merged

    @staticmethod
    def _chat_source(chat_id: str) -> Optional[str]:
        clean = str(chat_id or "").strip()
        return f"chat_summary:{clean}" if clean else None

    @classmethod
    def _resolve_allowed_chat_ids(cls, chat_id: str, shared_chat_ids: Sequence[str] = ()) -> set[str]:
        allowed_chat_ids = {str(item or "").strip() for item in shared_chat_ids if str(item or "").strip()}
        clean_chat_id = str(chat_id or "").strip()
        if clean_chat_id:
            allowed_chat_ids.add(clean_chat_id)
        return allowed_chat_ids

    @staticmethod
    def _time_meta(timestamp: Optional[float], time_start: Optional[float], time_end: Optional[float]) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if timestamp is not None:
            payload["event_time"] = float(timestamp)
        if time_start is not None:
            payload["event_time_start"] = float(time_start)
        if time_end is not None:
            payload["event_time_end"] = float(time_end)
        if payload:
            payload["time_granularity"] = "minute"
            payload["time_confidence"] = 0.95
        return payload


    def _resolve_relation_hashes(self, target: str) -> List[str]:
        assert self.metadata_store
        token = str(target or "").strip()
        if not token:
            return []
        if len(token) == 64 and all(ch in "0123456789abcdef" for ch in token.lower()):
            return [token]
        hashes = self.metadata_store.search_relation_hashes_by_text(token, limit=10)
        if hashes:
            return hashes
        return [
            str(row.get("hash", "") or "")
            for row in self.metadata_store.get_relations(subject=token)[:10]
            if str(row.get("hash", "")).strip()
        ]

    def _resolve_deleted_relation_hashes(self, target: str) -> List[str]:
        assert self.metadata_store
        token = str(target or "").strip()
        if not token:
            return []
        if len(token) == 64 and all(ch in "0123456789abcdef" for ch in token.lower()):
            return [token]
        return self.metadata_store.search_deleted_relation_hashes_by_text(token, limit=10)

    async def _ensure_vector_for_text(
        self,
        *,
        item_hash: str,
        text: str,
        vector_store: Optional[VectorStore] = None,
    ) -> bool:
        return await self._vector_ensure_service.ensure_vector_for_text(item_hash=item_hash, text=text, vector_store=vector_store)

    async def _ensure_relation_vector(self, relation: Dict[str, Any]) -> bool:
        return await self._vector_ensure_service.ensure_relation_vector(relation)

    async def _ensure_paragraph_vector(self, paragraph: Dict[str, Any]) -> bool:
        return await self._vector_ensure_service.ensure_paragraph_vector(paragraph)

    async def _ensure_entity_vector(self, entity: Dict[str, Any]) -> bool:
        return await self._vector_ensure_service.ensure_entity_vector(entity)

    async def _restore_relation_hashes(
        self,
        hashes: List[str],
        *,
        payloads: Optional[Dict[str, Dict[str, Any]]] = None,
        rebuild_graph: bool = True,
        persist: bool = True,
    ) -> Dict[str, Any]:
        return await self._delete_service.restore_relation_hashes(
            hashes, payloads=payloads, rebuild_graph=rebuild_graph, persist=persist,
        )

    @staticmethod
    def _selector_dict(selector: Any) -> Dict[str, Any]:
        if isinstance(selector, dict):
            return dict(selector)
        if isinstance(selector, (list, tuple)):
            return {"items": list(selector)}
        token = str(selector or "").strip()
        return {"query": token} if token else {}


    def _resolve_source_targets(self, selector: Any) -> List[str]:
        raw = self._selector_dict(selector)
        return self._merge_tokens(raw.get("sources"), [raw.get("source")], [raw.get("query")], raw.get("items"))


    def _relation_has_remaining_paragraphs(self, relation_hash: str, removing_hashes: Sequence[str]) -> bool:
        return self._delete_service.relation_has_remaining_paragraphs(relation_hash, removing_hashes)


    async def _invalidate_import_manifest_for_sources(self, result: Dict[str, Any]) -> None:
        await self._delete_service.invalidate_import_manifest_for_sources(result)

    @staticmethod
    def _optional_float(value: Any) -> Optional[float]:
        if value in {None, ""}:
            return None
        try:
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        if value in {None, ""}:
            return None
        try:
            return int(value)
        except Exception:
            return None
