from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.common.logger import get_logger

if TYPE_CHECKING:
    from ..sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.services.kernel_initializer")


class KernelInitializer:
    """Kernel.initialize() 中服务创建逻辑的提取。"""

    @staticmethod
    def init_core_storage(kernel: SDKMemoryKernel) -> None:
        from ..config.vector_pool_config import VectorPoolConfig
        from ..config.feedback_config import FeedbackConfig
        from ..config.fuzzy_modify_config import FuzzyModifyConfig
        from .embedding_health import EmbeddingHealthService
        from .background_scheduler import BackgroundTaskScheduler
        from ...storage import GraphStore, MetadataStore
        from ...retrieval import SparseBM25Index, SparseBM25Config
        from ...embedding import create_embedding_api_adapter
        from .vector_pool import VectorPoolManager
        from ...storage import SparseMatrixFormat

        kernel.data_dir.mkdir(parents=True, exist_ok=True)

        kernel._embedding_health_service = EmbeddingHealthService(
            vector_pool_config=VectorPoolConfig.from_config(kernel.config),
        )
        kernel._background_scheduler = BackgroundTaskScheduler()
        kernel._feedback_config = FeedbackConfig.from_global_config()
        kernel._fuzzy_modify_config = FuzzyModifyConfig.from_global_config()

        kernel.embedding_manager = create_embedding_api_adapter(
            batch_size=int(kernel._cfg("embedding.batch_size", 32)),
            max_concurrent=int(kernel._cfg("embedding.max_concurrent", 5)),
            default_dimension=kernel.embedding_dimension,
            enable_cache=bool(kernel._cfg("embedding.enable_cache", False)),
            model_name=str(kernel._cfg("embedding.model_name", "auto") or "auto"),
            dimension_request_mode=str(kernel._cfg("embedding.dimension_request_mode", "explicit") or "explicit"),
            retry_config=kernel._cfg("embedding.retry", {}) or {},
        )

        kernel._vector_pool_manager = VectorPoolManager(
            config=VectorPoolConfig.from_config(kernel.config),
            data_dir=kernel.data_dir,
            embedding_dimension=kernel.embedding_dimension,
            embedding_manager=kernel.embedding_manager,
            relation_vectors_enabled=kernel.relation_vectors_enabled,
        )

        stored_dimension = kernel._vector_pool_manager.stored_vector_dimension()
        provisional_dimension = stored_dimension or kernel.embedding_dimension
        kernel.embedding_dimension = int(provisional_dimension)

        matrix_format = str(kernel._cfg("graph.sparse_matrix_format", "csr") or "csr").strip().lower()
        graph_format = SparseMatrixFormat.CSC if matrix_format == "csc" else SparseMatrixFormat.CSR

        kernel.vector_store = kernel._vector_pool_manager.make_vector_store(kernel._vector_pool_manager.vectors_root(), dimension=provisional_dimension)
        kernel.paragraph_vector_store = kernel._vector_pool_manager.make_vector_store(
            kernel._vector_pool_manager.paragraph_vector_dir(),
            dimension=provisional_dimension,
        )
        kernel.graph_vector_store = kernel._vector_pool_manager.make_vector_store(
            kernel._vector_pool_manager.graph_vector_dir(),
            dimension=provisional_dimension,
        )
        kernel.graph_store = GraphStore(matrix_format=graph_format, data_dir=kernel.data_dir / "graph")
        kernel.metadata_store = MetadataStore(data_dir=kernel.data_dir / "metadata")
        kernel.metadata_store.connect()

        if kernel.graph_store.has_data():
            kernel.graph_store.load()

        sparse_cfg_raw = kernel._cfg("retrieval.sparse", {}) or {}
        try:
            sparse_cfg = SparseBM25Config(**sparse_cfg_raw)
        except Exception as exc:
            logger.warning(f"sparse 配置非法，回退默认: {exc}")
            sparse_cfg = SparseBM25Config()
        kernel.sparse_index = SparseBM25Index(metadata_store=kernel.metadata_store, config=sparse_cfg)
        if kernel.sparse_index.config.enabled:
            warmup_summary = kernel.sparse_index.warmup()
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

        if kernel.vector_store.has_data():
            kernel.vector_store.load()
            kernel.vector_store.warmup_index(force_train=True)
        kernel._vector_pool_manager.dual_pools_ready = False
        if kernel._vector_pool_manager.config.config_enabled:
            kernel._vector_pool_manager.cleanup_stale_dual_vector_build_dirs()
            kernel._vector_pool_manager.vector_store = kernel.vector_store
            kernel._vector_pool_manager.paragraph_vector_store = kernel.paragraph_vector_store
            kernel._vector_pool_manager.graph_vector_store = kernel.graph_vector_store
            kernel._vector_pool_manager.metadata_store = kernel.metadata_store
            if not kernel._vector_pool_manager.reload_dual_vector_stores_from_disk():
                logger.warning("双池配置已开启，但 ready manifest 不可用，当前按单池检索与写入运行")
            kernel.vector_store = kernel._vector_pool_manager.vector_store
            kernel.paragraph_vector_store = kernel._vector_pool_manager.paragraph_vector_store
            kernel.graph_vector_store = kernel._vector_pool_manager.graph_vector_store

    @staticmethod
    def init_search_runtime(kernel: SDKMemoryKernel) -> None:
        from ..search_runtime_initializer import build_search_runtime
        from ...utils.web_import_manager import ImportTaskManager
        from ...utils.retrieval_tuning_manager import RetrievalTuningManager

        kernel._refresh_relation_write_service()

        runtime_config = kernel._build_runtime_config()
        kernel._runtime_bundle = build_search_runtime(
            plugin_config=runtime_config,
            logger_obj=logger,
            owner_tag="sdk_kernel",
            log_prefix="[sdk]",
        )
        if not kernel._runtime_bundle.ready:
            raise RuntimeError(kernel._runtime_bundle.error or "检索运行时初始化失败")

        kernel.retriever = kernel._runtime_bundle.retriever
        kernel.threshold_filter = kernel._runtime_bundle.threshold_filter
        kernel.sparse_index = kernel._runtime_bundle.sparse_index or kernel.sparse_index
        kernel._apply_runtime_sparse_mode()

        kernel._refresh_runtime_dependents(preserve_managers=True)
        kernel.import_task_manager = ImportTaskManager(kernel)
        kernel.retrieval_tuning_manager = RetrievalTuningManager(
            kernel,
            import_write_blocked_provider=kernel.import_task_manager.is_write_blocked,
        )

    @staticmethod
    def init_admin_handlers(kernel: SDKMemoryKernel) -> None:
        from ..admin import (
            GraphAdminHandler, ParagraphAdminHandler, RelationAdminHandler,
            RuntimeAdminHandler, ImportAdminHandler, TuningAdminHandler,
            V5AdminHandler, DeleteAdminHandler, CorrectionAdminHandler,
            ProfileAdminHandler, FeedbackAdminHandler, EpisodeAdminHandler,
            SourceAdminHandler,
        )
        kernel._admin_handlers = {
            "graph": GraphAdminHandler(kernel),
            "paragraph": ParagraphAdminHandler(kernel),
            "relation": RelationAdminHandler(kernel),
            "runtime": RuntimeAdminHandler(kernel),
            "import": ImportAdminHandler(kernel),
            "tuning": TuningAdminHandler(kernel),
            "v5": V5AdminHandler(kernel),
            "delete": DeleteAdminHandler(kernel),
            "correction": CorrectionAdminHandler(kernel),
            "profile": ProfileAdminHandler(kernel),
            "feedback": FeedbackAdminHandler(kernel),
            "episode": EpisodeAdminHandler(kernel),
            "source": SourceAdminHandler(kernel),
        }

    @staticmethod
    def init_hit_filter_service(kernel: SDKMemoryKernel) -> None:
        from .hit_filter import HitFilterService
        kernel._hit_filter_service = HitFilterService(
            metadata_store=kernel.metadata_store,
            cfg=kernel._cfg,
            optional_float=kernel._optional_float,
            tokens=kernel._tokens,
            chat_source=kernel._chat_source,
            chat_filter_config_allows=kernel._chat_filter_config_allows,
            session_info_port=kernel._session_info_port,
            feedback_cfg_paragraph_hard_filter_enabled=kernel._feedback_config.paragraph_hard_filter_enabled,
            feedback_cfg_episode_query_block_enabled=kernel._feedback_config.episode_query_block_enabled,
            current_effective_filter_cache=lambda: kernel._current_effective_filter_cache,
            update_effective_filter_cache=lambda v: setattr(kernel, '_current_effective_filter_cache', v),
        )

    @staticmethod
    def init_graph_ops_service(kernel: SDKMemoryKernel) -> None:
        from .graph_ops import GraphOpsService
        kernel._graph_ops_service = GraphOpsService(
            metadata_store=kernel.metadata_store,
            graph_store=kernel.graph_store,
            load_paragraph_stale_marks=kernel._hit_filter_service.load_paragraph_stale_marks,
            persist_callback=kernel._persist,
            rebuild_graph_callback=lambda: {"node_count": 0, "edge_count": 0},
        )
        kernel._graph_ops_service._rebuild_graph_from_metadata = kernel._graph_ops_service.rebuild_graph_from_metadata

    @staticmethod
    def init_delete_service(kernel: SDKMemoryKernel) -> None:
        from .delete import DeleteService
        from .graph_ops import GraphOpsService
        kernel._delete_service = DeleteService(
            metadata_store=kernel.metadata_store,
            graph_store=kernel.graph_store,
            merge_tokens=kernel._merge_tokens,
            tokens=kernel._tokens,
            selector_dict=kernel._selector_dict,
            persist=kernel._persist,
            rebuild_graph_from_metadata=kernel._graph_ops_service.rebuild_graph_from_metadata,
            delete_vectors_by_type=kernel._delete_vectors_by_type,
            cfg=kernel._cfg,
            format_relation_text=GraphOpsService._format_relation_text,
            trim_text=GraphOpsService._trim_text,
            resolve_relation_hashes=kernel._resolve_relation_hashes,
            resolve_deleted_relation_hashes=kernel._resolve_deleted_relation_hashes,
            resolve_source_targets=kernel._resolve_source_targets,
            restore_relation_hashes=kernel._restore_relation_hashes,
            relation_has_remaining_paragraphs=kernel._relation_has_remaining_paragraphs,
            ensure_entity_vector=kernel._ensure_entity_vector,
            ensure_paragraph_vector=kernel._ensure_paragraph_vector,
            ensure_relation_vector=kernel._ensure_relation_vector,
            optional_float=kernel._optional_float,
            import_task_manager_getter=lambda: kernel.import_task_manager,
        )

    @staticmethod
    def init_fuzzy_modify_service(kernel: SDKMemoryKernel) -> None:
        from .fuzzy_modify import FuzzyModifyService
        from .graph_ops import GraphOpsService
        kernel._fuzzy_modify_service = FuzzyModifyService(
            metadata_store=kernel.metadata_store,
            fuzzy_modify_config=kernel._fuzzy_modify_config,
            fuzzy_modify_planner=kernel._fuzzy_modify_planner,
            tokens=kernel._tokens,
            merge_tokens=kernel._merge_tokens,
            argument_tokens=kernel._argument_tokens,
            merge_argument_tokens=kernel._merge_argument_tokens,
            optional_float=kernel._optional_float,
            trim_text=GraphOpsService._trim_text,
            safe_json_loads=kernel._safe_json_loads,
            persist=kernel._persist,
            rebuild_graph_from_metadata=kernel._graph_ops_service.rebuild_graph_from_metadata,
            relation_has_remaining_paragraphs=kernel._relation_has_remaining_paragraphs,
            execute_delete_action=kernel._delete_service.execute_delete_action,
            search_memory=kernel._fuzzy_modify_search_memory_adapter,
            ingest_text=kernel.ingest_text,
            refresh_person_profile=kernel.refresh_person_profile,
            profile_evidence_admin=lambda *a, **kw: kernel._profile_evidence_service.profile_evidence_admin(*a, **kw),
            person_profile_service=kernel.person_profile_service,
            invalidate_filter_cache=lambda: setattr(kernel, '_current_effective_filter_cache', {"checked_at": 0.0, "needed": True}),
        )

    @staticmethod
    def init_feedback_correction_service(kernel: SDKMemoryKernel) -> None:
        from .feedback_correction import FeedbackCorrectionService
        from .graph_ops import GraphOpsService
        kernel._feedback_correction_service = FeedbackCorrectionService(
            metadata_store=kernel.metadata_store,
            feedback_config=kernel._feedback_config,
            feedback_classifier=kernel._feedback_classifier,
            person_profile_service=kernel.person_profile_service,
            episode_service=kernel.episode_service,
            background_scheduler=kernel._background_scheduler,
            delete_service=kernel._delete_service,
            tokens=kernel._tokens,
            merge_tokens=kernel._merge_tokens,
            argument_tokens=kernel._argument_tokens,
            persist=kernel._persist,
            rebuild_graph_from_metadata=kernel._graph_ops_service.rebuild_graph_from_metadata,
            cfg=kernel._cfg,
            safe_json_loads=kernel._safe_json_loads,
            chat_source=kernel._chat_source,
            format_relation_text=GraphOpsService._format_relation_text,
            load_paragraph_rows=kernel._graph_ops_service.load_paragraph_rows,
            query_relation_rows_by_hashes=kernel._graph_ops_service.query_relation_rows_by_hashes,
            apply_v5_relation_action=lambda *a, **kw: kernel._v5_memory_service.apply_v5_relation_action(*a, **kw),
            ingest_text=kernel.ingest_text,
            refresh_person_profile=kernel.refresh_person_profile,
            soft_delete_feedback_correction_paragraphs=kernel._delete_service.soft_delete_feedback_correction_paragraphs,
            person_profile_refresh_max_retry=kernel._person_profile_refresh_max_retry,
            process_person_profile_refresh_queue_batch=kernel._process_person_profile_refresh_queue_batch,
            initialize=kernel.initialize,
        )

    @staticmethod
    def init_profile_evidence_service(kernel: SDKMemoryKernel) -> None:
        from .profile_evidence import ProfileEvidenceService
        from .graph_ops import GraphOpsService
        kernel._profile_evidence_service = ProfileEvidenceService(
            metadata_store=kernel.metadata_store,
            person_profile_service=kernel.person_profile_service,
            tokens=kernel._tokens,
            trim_text=GraphOpsService._trim_text,
            query_person_profile_with_feedback_refresh=kernel._feedback_correction_service._query_person_profile_with_feedback_refresh,
            execute_delete_action=kernel._delete_service.execute_delete_action,
            invalidate_import_manifest_for_sources=kernel._invalidate_import_manifest_for_sources,
        )

    @staticmethod
    def init_v5_memory_service(kernel: SDKMemoryKernel) -> None:
        from .v5_memory import V5MemoryService
        kernel._v5_memory_service = V5MemoryService(
            metadata_store=kernel.metadata_store,
            cfg=kernel._cfg,
            resolve_relation_hashes=kernel._resolve_relation_hashes,
            resolve_deleted_relation_hashes=kernel._resolve_deleted_relation_hashes,
            rebuild_graph_from_metadata=kernel._graph_ops_service.rebuild_graph_from_metadata,
            persist_callback=kernel._persist,
            last_maintenance_at_getter=lambda: kernel._last_maintenance_at,
            last_maintenance_at_setter=lambda v: setattr(kernel, '_last_maintenance_at', v),
        )

    @staticmethod
    def init_search_service(kernel: SDKMemoryKernel) -> None:
        from .search import SearchService
        kernel._search_service = SearchService(
            hit_filter_service=kernel._hit_filter_service,
            get_retriever=lambda: kernel.retriever,
            get_episode_retriever=lambda: kernel.episode_retriever,
            get_aggregate_query_service=lambda: kernel.aggregate_query_service,
            get_threshold_filter=lambda: kernel.threshold_filter,
            build_runtime_config=kernel._build_runtime_config,
            is_chat_filtered=kernel._is_chat_filtered,
            get_config_value=kernel._cfg,
        )

    @staticmethod
    def init_ingest_service(kernel: SDKMemoryKernel) -> None:
        from .hit_filter import HitFilterService
        from .ingest import IngestService
        kernel._ingest_service = IngestService(
            get_metadata_store=lambda: kernel.metadata_store,
            get_vector_store=lambda: kernel.vector_store,
            get_graph_store=lambda: kernel.graph_store,
            get_embedding_manager=lambda: kernel.embedding_manager,
            get_relation_write_service=lambda: kernel.relation_write_service,
            get_summary_importer=lambda: kernel.summary_importer,
            get_episode_service=lambda: kernel.episode_service,
            is_chat_filtered=kernel._is_chat_filtered,
            cfg=kernel._cfg,
            tokens=kernel._tokens,
            merge_tokens=kernel._merge_tokens,
            time_meta=kernel._time_meta,
            resolve_knowledge_type=HitFilterService.resolve_knowledge_type,
            write_paragraph_vector_or_enqueue=kernel.write_paragraph_vector_or_enqueue,
            ensure_entity_vector=kernel._ensure_entity_vector,
            should_auto_enqueue_episode=kernel._should_auto_enqueue_episode,
            persist=kernel._persist,
            mark_person_active=kernel._mark_person_active,
            enqueue_person_profile_refresh=kernel._enqueue_person_profile_refresh,
            optional_int=kernel._optional_int,
            background_scheduler=kernel._background_scheduler,
            argument_tokens=kernel._argument_tokens,
        )

    @staticmethod
    def init_maintenance_service(kernel: SDKMemoryKernel) -> None:
        from .maintenance import MaintenanceService
        kernel._maintenance_service = MaintenanceService(
            get_metadata_store=lambda: kernel.metadata_store,
            get_graph_store=lambda: kernel.graph_store,
            cfg=kernel._cfg,
            persist=kernel._persist,
            rebuild_graph_from_metadata=kernel._graph_ops_service.rebuild_graph_from_metadata,
            resolve_relation_hashes=kernel._resolve_relation_hashes,
            resolve_deleted_relation_hashes=kernel._resolve_deleted_relation_hashes,
            delete_vectors_by_type=kernel._delete_vectors_by_type,
            background_scheduler=kernel._background_scheduler,
        )

    @staticmethod
    def init_vector_rebuild_service(kernel: SDKMemoryKernel) -> None:
        from .vector_rebuild import VectorRebuildService
        kernel._vector_rebuild_service = VectorRebuildService(
            vector_pool_manager=kernel._vector_pool_manager,
            embedding_manager_getter=lambda: kernel.embedding_manager,
            metadata_store_getter=lambda: kernel.metadata_store,
            vector_store_getter=lambda: kernel.vector_store,
            paragraph_vector_store_getter=lambda: kernel.paragraph_vector_store,
            graph_vector_store_getter=lambda: kernel.graph_vector_store,
            relation_vectors_enabled_getter=lambda: kernel.relation_vectors_enabled,
            embedding_dimension_getter=lambda: kernel.embedding_dimension,
            embedding_dimension_setter=lambda v: setattr(kernel, 'embedding_dimension', v),
            cfg=kernel._cfg,
            active_row_filter_sql=kernel._active_row_filter_sql,
            count_vector_rebuild_targets=kernel._count_vector_rebuild_targets,
            refresh_relation_write_service=kernel._refresh_relation_write_service,
            set_embedding_degraded=kernel._set_embedding_degraded,
            refresh_runtime_self_check=kernel._refresh_runtime_self_check,
            apply_self_check_dimension_result=kernel._apply_self_check_dimension_result,
            refresh_runtime_dependents=kernel._refresh_runtime_dependents,
            apply_runtime_sparse_mode=kernel._apply_runtime_sparse_mode,
            build_runtime_config=kernel._build_runtime_config,
            persist=kernel._persist,
            reload_dual_vector_stores_from_disk=kernel._reload_dual_vector_stores_from_disk,
            write_dual_vector_ready_manifest=kernel._write_dual_vector_ready_manifest,
            clear_legacy_single_vector_files_after_dual_ready=kernel._clear_legacy_single_vector_files_after_dual_ready,
            backfill_missing_dual_vector_pool_entries=kernel._backfill_missing_dual_vector_pool_entries,
            update_dual_vector_auto_migration_stage=kernel._update_dual_vector_auto_migration_stage,
            vector_rebuild_status_getter=kernel._vector_rebuild_status,
            vector_persist_blocked_getter=lambda: kernel._vector_persist_blocked_until_rebuild,
            vector_persist_blocked_setter=lambda v: setattr(kernel, '_vector_persist_blocked_until_rebuild', v),
            vector_rebuild_source_dimension_getter=lambda: kernel._vector_rebuild_source_dimension,
            vector_rebuild_source_dimension_setter=lambda v: setattr(kernel, '_vector_rebuild_source_dimension', v),
            vector_rebuild_lock_getter=lambda: kernel._vector_rebuild_lock,
            runtime_bundle_setter=lambda v: setattr(kernel, '_runtime_bundle', v),
            retriever_setter=lambda v: setattr(kernel, 'retriever', v),
            threshold_filter_setter=lambda v: setattr(kernel, 'threshold_filter', v),
            sparse_index_setter=lambda v: setattr(kernel, 'sparse_index', v),
            paragraph_vector_store_setter=lambda v: setattr(kernel, 'paragraph_vector_store', v),
            graph_vector_store_setter=lambda v: setattr(kernel, 'graph_vector_store', v),
            vector_store_setter=lambda v: setattr(kernel, 'vector_store', v),
            sparse_index_getter=lambda: kernel.sparse_index,
        )

    @staticmethod
    def init_dual_vector_migration_service(kernel: SDKMemoryKernel) -> None:
        from .dual_vector_migration import DualVectorMigrationService
        kernel._dual_vector_migration_service = DualVectorMigrationService(
            vector_pool_manager=kernel._vector_pool_manager,
            background_scheduler=kernel._background_scheduler,
            cfg=kernel._cfg,
            active_row_filter_sql=kernel._active_row_filter_sql,
            dual_vector_pools_enabled=kernel._dual_vector_pools_enabled,
            set_embedding_degraded=kernel._set_embedding_degraded,
            copy_or_encode_dual_rebuild_vectors=kernel._vector_rebuild_service._copy_or_encode_dual_rebuild_vectors,
            graph_vector_id=kernel._graph_vector_id,
            rebuild_all_vectors=kernel._rebuild_all_vectors,
            vector_rebuild_lock_getter=lambda: kernel._vector_rebuild_lock,
            sleep_background=kernel._sleep_background,
            metadata_store_getter=lambda: kernel.metadata_store,
            vector_store_getter=lambda: kernel.vector_store,
            paragraph_vector_store_getter=lambda: kernel.paragraph_vector_store,
            graph_vector_store_getter=lambda: kernel.graph_vector_store,
            relation_vectors_enabled_getter=lambda: kernel.relation_vectors_enabled,
            paragraph_vector_store_setter=lambda v: setattr(kernel, 'paragraph_vector_store', v),
            graph_vector_store_setter=lambda v: setattr(kernel, 'graph_vector_store', v),
        )

    @staticmethod
    def init_all_services(kernel: SDKMemoryKernel) -> None:
        KernelInitializer.init_admin_handlers(kernel)
        KernelInitializer.init_hit_filter_service(kernel)
        KernelInitializer.init_graph_ops_service(kernel)
        KernelInitializer.init_delete_service(kernel)
        KernelInitializer.init_fuzzy_modify_service(kernel)
        KernelInitializer.init_feedback_correction_service(kernel)
        KernelInitializer.init_profile_evidence_service(kernel)
        KernelInitializer.init_v5_memory_service(kernel)
        KernelInitializer.init_search_service(kernel)
        KernelInitializer.init_ingest_service(kernel)
        KernelInitializer.init_maintenance_service(kernel)
        KernelInitializer.init_vector_rebuild_service(kernel)
        KernelInitializer.init_dual_vector_migration_service(kernel)
        KernelInitializer.init_vector_ensure_service(kernel)

    @staticmethod
    def init_vector_ensure_service(kernel: SDKMemoryKernel) -> None:
        from .vector_ensure import VectorEnsureService
        kernel._vector_ensure_service = VectorEnsureService(
            embedding_manager_getter=lambda: kernel.embedding_manager,
            vector_store_getter=lambda: kernel.vector_store,
            paragraph_vector_store_getter=lambda: kernel.paragraph_vector_store,
            graph_vector_store_getter=lambda: kernel.graph_vector_store,
            relation_vectors_enabled_getter=lambda: kernel.relation_vectors_enabled,
            dual_vector_pools_enabled=kernel._dual_vector_pools_enabled,
            graph_vector_id=kernel._graph_vector_id,
            relation_write_service_getter=lambda: kernel.relation_write_service,
            vector_pool_manager=kernel._vector_pool_manager,
        )

    @staticmethod
    def build_runtime_config(kernel: SDKMemoryKernel, base_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        runtime_config = dict(base_config if isinstance(base_config, dict) else kernel.config)
        runtime_cfg = runtime_config.get("runtime")
        runtime_config["runtime"] = dict(runtime_cfg) if isinstance(runtime_cfg, dict) else {}
        runtime_config["runtime"]["vector_pools_ready"] = kernel._dual_vector_pools_enabled()
        runtime_config.update(
            {
                "vector_store": kernel.vector_store,
                "paragraph_vector_store": kernel.paragraph_vector_store or kernel.vector_store,
                "graph_vector_store": kernel.graph_vector_store or kernel.vector_store,
                "graph_store": kernel.graph_store,
                "metadata_store": kernel.metadata_store,
                "embedding_manager": kernel.embedding_manager,
                "sparse_index": kernel.sparse_index,
                "relation_write_service": kernel.relation_write_service,
                "plugin_instance": kernel,
            }
        )
        return runtime_config

    @staticmethod
    def merge_runtime_config_patch(base: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
        import copy
        merged = copy.deepcopy(base)
        for key, value in (patch or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = KernelInitializer.merge_runtime_config_patch(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    @staticmethod
    def refresh_relation_write_service(kernel: SDKMemoryKernel) -> None:
        from ...utils.relation_write_service import RelationWriteService
        if (
            kernel.metadata_store is None
            or kernel.graph_store is None
            or kernel.vector_store is None
            or kernel.embedding_manager is None
        ):
            kernel.relation_write_service = None
            return
        kernel.relation_write_service = RelationWriteService(
            metadata_store=kernel.metadata_store,
            graph_store=kernel.graph_store,
            vector_store=kernel.vector_store,
            graph_vector_store=kernel._graph_vector_store(),
            embedding_manager=kernel.embedding_manager,
            use_typed_relation_ids=kernel._dual_vector_pools_enabled(),
        )

    @staticmethod
    def refresh_runtime_dependents(kernel: SDKMemoryKernel, *, preserve_managers: bool = True) -> None:
        from ...utils.episode_retrieval_service import EpisodeRetrievalService
        from ...utils.aggregate_query_service import AggregateQueryService
        from ...utils.person_profile_service import PersonProfileService
        from ...utils.episode_segmentation_service import EpisodeSegmentationService
        from ...utils.episode_service import EpisodeService
        from ...utils.summary_importer import SummaryImporter
        from ...utils.web_import_manager import ImportTaskManager
        from ...utils.retrieval_tuning_manager import RetrievalTuningManager
        if (
            kernel.metadata_store is None
            or kernel.graph_store is None
            or kernel.vector_store is None
            or kernel.embedding_manager is None
            or kernel.retriever is None
        ):
            return

        runtime_config = KernelInitializer.build_runtime_config(kernel)
        kernel.episode_retriever = EpisodeRetrievalService(metadata_store=kernel.metadata_store, retriever=kernel.retriever)
        kernel.aggregate_query_service = AggregateQueryService(plugin_config=runtime_config)
        kernel.person_profile_service = PersonProfileService(
            metadata_store=kernel.metadata_store,
            graph_store=kernel.graph_store,
            vector_store=kernel.vector_store,
            paragraph_vector_store=kernel.paragraph_vector_store or kernel.vector_store,
            graph_vector_store=kernel.graph_vector_store or kernel.vector_store,
            embedding_manager=kernel.embedding_manager,
            sparse_index=kernel.sparse_index,
            plugin_config=runtime_config,
            retriever=kernel.retriever,
        )
        kernel.episode_segmentation_service = EpisodeSegmentationService(plugin_config=runtime_config)
        kernel.episode_service = EpisodeService(
            metadata_store=kernel.metadata_store,
            plugin_config=runtime_config,
            segmentation_service=kernel.episode_segmentation_service,
        )
        kernel.summary_importer = SummaryImporter(
            vector_store=kernel.vector_store,
            graph_store=kernel.graph_store,
            metadata_store=kernel.metadata_store,
            embedding_manager=kernel.embedding_manager,
            plugin_config=runtime_config,
        )
        if not preserve_managers:
            kernel.import_task_manager = ImportTaskManager(kernel)
            kernel.retrieval_tuning_manager = RetrievalTuningManager(
                kernel,
                import_write_blocked_provider=kernel.import_task_manager.is_write_blocked,
            )

    @staticmethod
    async def apply_retrieval_tuning_profile(
        kernel: SDKMemoryKernel, profile: Dict[str, Any], *, validate: bool = True,
    ) -> Dict[str, Any]:
        from ..search_runtime_initializer import build_search_runtime
        if not isinstance(profile, dict):
            return {
                "success": False,
                "runtime_rebuilt": False,
                "validation_passed": False,
                "error": "profile 必须是字典",
            }

        next_config = KernelInitializer.merge_runtime_config_patch(kernel.config, profile)
        runtime_bundle = build_search_runtime(
            plugin_config=KernelInitializer.build_runtime_config(kernel, next_config),
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
            kernel.config.clear()
            kernel.config.update(next_config)
            kernel._runtime_bundle = runtime_bundle
            kernel.retriever = runtime_bundle.retriever
            kernel.threshold_filter = runtime_bundle.threshold_filter
            kernel.sparse_index = runtime_bundle.sparse_index or kernel.sparse_index
            KernelInitializer.refresh_runtime_dependents(kernel, preserve_managers=True)
            kernel._apply_runtime_sparse_mode()
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

    @staticmethod
    async def start_background_tasks(kernel: SDKMemoryKernel) -> None:
        registrations = {
            "auto_save": kernel._auto_save_loop,
            "episode_pending": kernel._ingest_service.episode_pending_loop,
            "embedding_probe": kernel._embedding_probe_loop,
            "paragraph_vector_backfill": kernel._paragraph_vector_backfill_loop,
            "memory_maintenance": kernel._maintenance_service.memory_maintenance_loop,
            "person_profile_refresh": kernel._person_profile_refresh_loop,
            "person_profile_refresh_queue": kernel._person_profile_refresh_queue_loop,
            "feedback_correction": kernel._feedback_correction_service._feedback_correction_loop,
            "feedback_correction_reconcile": kernel._feedback_correction_service._feedback_correction_reconcile_loop,
        }
        if kernel._should_start_dual_vector_auto_migration():
            registrations["dual_vector_auto_migration"] = kernel._dual_vector_auto_migration_loop
        await kernel._background_scheduler.start_all(registrations)

    @staticmethod
    async def auto_save_loop(kernel: SDKMemoryKernel) -> None:
        import asyncio
        try:
            while not kernel._background_scheduler.stopping:
                interval_minutes = max(1.0, float(kernel._cfg("advanced.auto_save_interval_minutes", 5) or 5))
                await asyncio.sleep(interval_minutes * 60.0)
                if kernel._background_scheduler.stopping:
                    break
                if bool(kernel._cfg("advanced.enable_auto_save", True)):
                    kernel._persist()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"auto_save loop 异常: {exc}")

    @staticmethod
    def persist(kernel: SDKMemoryKernel, *, force_vectors: bool = False) -> None:
        rebuild_required = False if force_vectors else bool(
            kernel._vector_rebuild_status().get("vector_rebuild_required", False)
        )
        if kernel.vector_store is not None and not kernel._dual_vector_pools_enabled():
            if rebuild_required:
                logger.debug("检测到向量库需要重建，跳过向量库持久化以保留重建提示")
            else:
                kernel._vector_pool_manager.save_vector_store(kernel.vector_store)
        if kernel._dual_vector_pools_enabled() and not rebuild_required:
            if kernel.paragraph_vector_store is not None:
                kernel._vector_pool_manager.save_vector_store(kernel.paragraph_vector_store)
            if kernel.graph_vector_store is not None:
                kernel._vector_pool_manager.save_vector_store(kernel.graph_vector_store)
        if kernel.graph_store is not None:
            kernel.graph_store.save()
        if kernel.sparse_index is not None and kernel.sparse_index.config.enabled:
            kernel.sparse_index.ensure_loaded()
