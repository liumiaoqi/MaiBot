from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.common.logger import get_logger

if TYPE_CHECKING:
    from ..sdk_memory_kernel import SDKMemoryKernel

logger = get_logger("a_memorix.services.kernel_initializer")


class KernelInitializer:
    """Kernel.initialize() 中服务创建逻辑的提取。"""

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
