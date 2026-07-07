from __future__ import annotations

from dataclasses import dataclass
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
from ..utils.runtime_self_check import run_embedding_runtime_self_check
from ..utils.search_execution_service import SearchExecutionRequest, SearchExecutionResult, SearchExecutionService
from ..utils.summary_importer import SummaryImporter
from ..utils.time_parser import format_timestamp, parse_query_datetime_to_timestamp
from ..utils.web_import_manager import ImportTaskManager
from .search_runtime_initializer import SearchRuntimeBundle, build_search_runtime
from .services.feedback_correction import FeedbackCorrectionService
from .services.fuzzy_modify import FuzzyModifyService
from .services.graph_ops import GraphOpsService
from .services.profile_evidence import ProfileEvidenceService

logger = get_logger("A_Memorix.SDKMemoryKernel")

DUAL_VECTOR_AUTO_MIGRATION_INITIAL_DELAY_SECONDS = 5.0
DUAL_VECTOR_AUTO_MIGRATION_LOCK_RETRY_DELAYS_SECONDS = (2.0, 5.0, 10.0)


@dataclass
class KernelSearchRequest:
    query: str = ""
    limit: int = 5
    mode: str = "search"
    chat_id: str = ""
    shared_chat_ids: Sequence[str] = ()
    person_id: str = ""
    time_start: Optional[str | float] = None
    time_end: Optional[str | float] = None
    respect_filter: bool = True
    user_id: str = ""
    group_id: str = ""


@dataclass
class _NormalizedSearchTimeWindow:
    numeric_start: Optional[float] = None
    numeric_end: Optional[float] = None
    query_start: Optional[str] = None
    query_end: Optional[str] = None


class _KernelRuntimeFacade:
    def __init__(self, kernel: "SDKMemoryKernel") -> None:
        self._kernel = kernel
        self.config = kernel.config
        self._plugin_config = kernel.config
        self._runtime_self_check_report: Dict[str, Any] = {}

    def get_config(self, key: str, default: Any = None) -> Any:
        return self._kernel._cfg(key, default)

    def is_runtime_ready(self) -> bool:
        return self._kernel.is_runtime_ready()

    def is_chat_enabled(self, stream_id: str, group_id: str | None = None, user_id: str | None = None) -> bool:
        return self._kernel.is_chat_enabled(stream_id=stream_id, group_id=group_id, user_id=user_id)

    async def reinforce_access(self, relation_hashes: Sequence[str]) -> None:
        if self._kernel.metadata_store is None:
            return
        hashes = [str(item or "").strip() for item in relation_hashes if str(item or "").strip()]
        if not hashes:
            return
        self._kernel.metadata_store.reinforce_relations(hashes)
        self._kernel._last_maintenance_at = time.time()

    async def execute_request_with_dedup(
        self,
        request_key: str,
        executor: Callable[[], Coroutine[Any, Any, Dict[str, Any]]],
    ) -> tuple[bool, Dict[str, Any]]:
        return await self._kernel.execute_request_with_dedup(request_key, executor)

    async def apply_retrieval_tuning_profile(
        self,
        profile: Dict[str, Any],
        *,
        validate: bool = True,
    ) -> Dict[str, Any]:
        return await self._kernel.apply_retrieval_tuning_profile(profile, validate=validate)

    @property
    def vector_store(self) -> Optional[VectorStore]:
        return self._kernel.vector_store

    @property
    def paragraph_vector_store(self) -> Optional[VectorStore]:
        return self._kernel.paragraph_vector_store

    @property
    def graph_vector_store(self) -> Optional[VectorStore]:
        return self._kernel.graph_vector_store

    @property
    def graph_store(self) -> Optional[GraphStore]:
        return self._kernel.graph_store

    @property
    def metadata_store(self) -> Optional[MetadataStore]:
        return self._kernel.metadata_store

    @property
    def embedding_manager(self):
        return self._kernel.embedding_manager

    @property
    def sparse_index(self):
        return self._kernel.sparse_index

    @property
    def relation_write_service(self) -> Optional[RelationWriteService]:
        return self._kernel.relation_write_service

    def is_embedding_degraded(self) -> bool:
        return self._kernel._is_embedding_degraded()

    def _dual_vector_pools_enabled(self) -> bool:
        return self._kernel._dual_vector_pools_enabled()

    def allow_metadata_only_write(self) -> bool:
        return self._kernel._allow_metadata_only_write()

    async def write_paragraph_vector_or_enqueue(
        self,
        *,
        paragraph_hash: str,
        content: str,
        context: str = "",
    ) -> Dict[str, Any]:
        return await self._kernel._write_paragraph_vector_or_enqueue(
            paragraph_hash=paragraph_hash,
            content=content,
            context=context,
        )

    def enqueue_paragraph_vector_backfill(
        self,
        paragraph_hash: str,
        *,
        error: str = "",
    ) -> None:
        self._kernel._enqueue_paragraph_vector_backfill(paragraph_hash, error=error)


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
        self._runtime_facade = _KernelRuntimeFacade(self)
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
        self._graph_ops_service: Optional[Any] = None
        self._v5_memory_service: Optional[Any] = None

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
                "plugin_instance": self._runtime_facade,
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
        filter_config = self._cfg("filter", {}) or {}
        if not isinstance(filter_config, dict) or not filter_config:
            return True

        return self._chat_filter_config_allows(
            filter_config,
            stream_id=stream_id,
            group_id=group_id,
            user_id=user_id,
            default_when_empty=True,
        )

    @staticmethod
    def _chat_filter_config_allows(
        filter_config: Dict[str, Any],
        *,
        stream_id: str = "",
        group_id: str = "",
        user_id: str = "",
        default_when_empty: bool = True,
    ) -> bool:
        if not bool(filter_config.get("enabled", True)):
            return True

        mode = str(filter_config.get("mode", "blacklist") or "blacklist").strip().lower()
        patterns = filter_config.get("chats") or []
        if not isinstance(patterns, list):
            patterns = []

        if not patterns:
            return bool(default_when_empty) if mode == "blacklist" else False

        stream_token = str(stream_id or "").strip()
        group_token = str(group_id or "").strip()
        user_token = str(user_id or "").strip()
        candidates = {token for token in (stream_token, group_token, user_token) if token}

        matched = False
        for raw_pattern in patterns:
            pattern = str(raw_pattern or "").strip()
            if not pattern:
                continue
            if ":" in pattern:
                prefix, value = pattern.split(":", 1)
                prefix = prefix.strip().lower()
                value = value.strip()
                if prefix == "group" and value and value == group_token:
                    matched = True
                elif prefix in {"user", "private"} and value and value == user_token:
                    matched = True
                elif prefix == "stream" and value and value == stream_token:
                    matched = True
            elif pattern in candidates:
                matched = True

            if matched:
                break

        if mode == "blacklist":
            return not matched
        return matched

    def _is_chat_filtered(
        self,
        *,
        respect_filter: bool,
        stream_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> bool:
        if not bool(respect_filter):
            return False

        stream_token = str(stream_id or "").strip()
        group_token = str(group_id or "").strip()
        user_token = str(user_id or "").strip()
        if not (stream_token or group_token or user_token):
            return False
        return not self.is_chat_enabled(stream_token, group_token, user_token)

    def _stored_vector_dimension(self, store: Optional[VectorStore] = None) -> Optional[int]:
        return self._vector_pool_manager.stored_vector_dimension(store)

    @staticmethod
    def _normalize_embedding_fingerprint(value: Any) -> Optional[Dict[str, Any]]:
        from .services.vector_pool import VectorPoolManager
        return VectorPoolManager.normalize_embedding_fingerprint(value)

    def _current_embedding_status_dimension(self) -> int:
        return self._vector_pool_manager.current_embedding_status_dimension()

    def _current_embedding_fingerprint(self, *, dimension: Optional[int] = None) -> Optional[Dict[str, Any]]:
        return self._vector_pool_manager.current_embedding_fingerprint(dimension=dimension)

    def _stored_embedding_fingerprint(self, store: Optional[VectorStore] = None) -> Optional[Dict[str, Any]]:
        return self._vector_pool_manager.stored_embedding_fingerprint(store)

    def _stamp_missing_embedding_fingerprint_if_dimension_matches(self, store: Optional[VectorStore]) -> bool:
        return self._vector_pool_manager.stamp_missing_embedding_fingerprint_if_dimension_matches(store)

    @staticmethod
    def _embedding_fingerprint_status(
        current: Optional[Dict[str, Any]],
        stored: Optional[Dict[str, Any]],
        *,
        has_stored_vectors: bool,
    ) -> str:
        from .services.vector_pool import VectorPoolManager
        return VectorPoolManager.embedding_fingerprint_status(current, stored, has_stored_vectors=has_stored_vectors)

    def _stored_vectors_compatible_with_current_embedding(self, store: Optional[VectorStore] = None) -> bool:
        return self._vector_pool_manager.stored_vectors_compatible_with_current_embedding(store)

    def _vector_mismatch_error(self, *, stored_dimension: int, detected_dimension: int) -> str:
        return self._vector_pool_manager.vector_mismatch_error(stored_dimension=stored_dimension, detected_dimension=detected_dimension)

    def _vector_rebuild_status(self) -> Dict[str, Any]:
        return self._vector_pool_manager.vector_rebuild_status(
            vector_rebuild_lock_locked=self._vector_rebuild_lock.locked(),
            vector_persist_blocked=self._vector_persist_blocked_until_rebuild,
            vector_rebuild_source_dimension=self._vector_rebuild_source_dimension,
        )

    def _embedding_fallback_enabled(self) -> bool:
        return self._embedding_health_service.config.embedding_fallback_enabled

    def _allow_metadata_only_write(self) -> bool:
        return self._embedding_health_service.config.allow_metadata_only_write

    def _embedding_probe_interval_seconds(self) -> float:
        return self._embedding_health_service.config.embedding_probe_interval_seconds

    def _paragraph_vector_backfill_enabled(self) -> bool:
        return self._embedding_health_service.config.paragraph_vector_backfill_enabled

    def _paragraph_vector_backfill_interval_seconds(self) -> float:
        return self._embedding_health_service.config.paragraph_vector_backfill_interval_seconds

    def _paragraph_vector_backfill_batch_size(self) -> int:
        return self._embedding_health_service.config.paragraph_vector_backfill_batch_size

    def _paragraph_vector_backfill_max_retry(self) -> int:
        return self._embedding_health_service.config.paragraph_vector_backfill_max_retry

    def _vector_pool_mode(self) -> str:
        return self._vector_pool_manager.config.mode

    def _dual_vector_pools_config_enabled(self) -> bool:
        return self._vector_pool_manager.config.config_enabled

    def _dual_vector_pools_enabled(self) -> bool:
        return self._vector_pool_manager.dual_pools_enabled

    def _vectors_root(self) -> Path:
        return self._vector_pool_manager.vectors_root()

    def _paragraph_vector_dir(self) -> Path:
        return self._vector_pool_manager.paragraph_vector_dir()

    def _graph_vector_dir(self) -> Path:
        return self._vector_pool_manager.graph_vector_dir()

    def _dual_vector_ready_manifest_path(self) -> Path:
        return self._vector_pool_manager.dual_vector_ready_manifest_path()

    def _read_dual_vector_ready_manifest(self) -> Optional[Dict[str, Any]]:
        return self._vector_pool_manager.read_dual_vector_ready_manifest()

    def _dual_vector_ready(self, *, expected_dimension: Optional[int] = None) -> bool:
        return self._vector_pool_manager.dual_vector_ready(expected_dimension=expected_dimension)

    def _write_dual_vector_ready_manifest(
        self,
        *,
        stats: Dict[str, Dict[str, int]],
        migration_stats: Dict[str, Dict[str, int]],
    ) -> None:
        return self._vector_pool_manager.write_dual_vector_ready_manifest(stats=stats, migration_stats=migration_stats)

    def _remove_dual_vector_ready_manifest(self) -> None:
        return self._vector_pool_manager.remove_dual_vector_ready_manifest()

    def _refresh_dual_vector_ready_manifest_from_stores(self) -> None:
        self._vector_pool_manager.paragraph_vector_store = self.paragraph_vector_store
        self._vector_pool_manager.graph_vector_store = self.graph_vector_store
        self._vector_pool_manager.metadata_store = self.metadata_store
        return self._vector_pool_manager.refresh_dual_vector_ready_manifest_from_stores()

    def _clear_legacy_single_vector_files_after_dual_ready(self) -> None:
        self._vector_pool_manager.vector_store = self.vector_store
        return self._vector_pool_manager.clear_legacy_single_vector_files_after_dual_ready()

    def _prepare_dual_vector_build_dirs(self) -> tuple[Path, Path, Path]:
        return self._vector_pool_manager.prepare_dual_vector_build_dirs()

    def _activate_dual_vector_build_dirs(self, build_root: Path) -> None:
        return self._vector_pool_manager.activate_dual_vector_build_dirs(build_root)

    def _cleanup_stale_dual_vector_build_dirs(self) -> None:
        return self._vector_pool_manager.cleanup_stale_dual_vector_build_dirs()

    def _make_vector_store(self, data_dir: Path, *, dimension: Optional[int] = None) -> VectorStore:
        return self._vector_pool_manager.make_vector_store(data_dir, dimension=dimension)

    def _save_vector_store(self, store: Optional[VectorStore]) -> None:
        return self._vector_pool_manager.save_vector_store(store)

    def _reload_dual_vector_stores_from_disk(self) -> bool:
        self._vector_pool_manager.vector_store = self.vector_store
        self._vector_pool_manager.paragraph_vector_store = self.paragraph_vector_store
        self._vector_pool_manager.graph_vector_store = self.graph_vector_store
        self._vector_pool_manager.metadata_store = self.metadata_store
        result = self._vector_pool_manager.reload_dual_vector_stores_from_disk()
        self.vector_store = self._vector_pool_manager.vector_store
        self.paragraph_vector_store = self._vector_pool_manager.paragraph_vector_store
        self.graph_vector_store = self._vector_pool_manager.graph_vector_store
        return result

    def _try_recover_dual_ready_manifest(self) -> bool:
        self._vector_pool_manager.metadata_store = self.metadata_store
        return self._vector_pool_manager.try_recover_dual_ready_manifest()

    def _drop_dual_build_root(self, build_root: Optional[Path]) -> None:
        return self._vector_pool_manager.drop_dual_build_root(build_root)

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

    def _paragraph_store(self) -> Optional[VectorStore]:
        return self._vector_pool_manager.paragraph_store()

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

    def _is_embedding_degraded(self) -> bool:
        return self._embedding_health_service.is_degraded

    def _embedding_degraded_snapshot(self) -> Dict[str, Any]:
        return self._embedding_health_service.snapshot()

    def _set_embedding_degraded(self, *, active: bool, reason: str = "", checked_at: Optional[float] = None) -> None:
        self._embedding_health_service.set_degraded(active=active, reason=reason, checked_at=checked_at)
        self._apply_runtime_sparse_mode()

    def _apply_runtime_sparse_mode(self) -> None:
        retriever = self.retriever
        if retriever is None:
            return
        setter = getattr(retriever, "set_runtime_sparse_only", None)
        if not callable(setter):
            return
        try:
            setter(self._is_embedding_degraded())
        except Exception as exc:
            logger.warning(f"设置 retriever sparse-only 运行时状态失败: {exc}")

    async def _refresh_runtime_self_check(self, *, sample_text: str = "A_Memorix runtime self check") -> Dict[str, Any]:
        report = await run_embedding_runtime_self_check(
            config=self._build_runtime_config(),
            vector_store=self.vector_store,
            embedding_manager=self.embedding_manager,
            sample_text=sample_text,
        )
        self._runtime_facade._runtime_self_check_report = dict(report)
        checked_at = float(report.get("checked_at") or time.time())
        self._embedding_health_service.update_last_check(checked_at)

    def _mark_startup_self_check_deferred(self) -> None:
        """记录启动阶段跳过真实 embedding encode 自检，避免阻塞主启动流程。"""
        configured_dimension = max(
            1,
            int(self._cfg("embedding.dimension", self.embedding_dimension) or self.embedding_dimension),
        )
        requested_dimension = self._current_embedding_status_dimension()
        vector_store_dimension = int(getattr(self.vector_store, "dimension", 0) or 0)
        self._embedding_health_service.mark_startup_self_check_deferred(
            configured_dimension=configured_dimension,
            requested_dimension=requested_dimension,
            vector_store_dimension=vector_store_dimension,
        )
        self._runtime_facade._runtime_self_check_report = self._embedding_health_service.runtime_self_check_report

    def _is_startup_self_check_deferred(self) -> bool:
        return self._embedding_health_service.is_startup_self_check_deferred()

    @staticmethod
    def _self_check_effective_dimension(report: Dict[str, Any]) -> int:
        for key in ("encoded_dimension", "detected_dimension", "requested_dimension"):
            try:
                value = int(report.get(key, 0) or 0)
            except Exception:
                value = 0
            if value > 0:
                return value
        return 0

    def _apply_self_check_dimension_result(self, report: Dict[str, Any]) -> str:
        detected_dimension = self._self_check_effective_dimension(report)
        if detected_dimension <= 0:
            return ""

        self.embedding_dimension = int(detected_dimension)
        vector_dimension = int(getattr(self.vector_store, "dimension", 0) or 0)
        if vector_dimension <= 0 or vector_dimension == detected_dimension:
            return ""

        stored_dimension = self._stored_vector_dimension() or vector_dimension
        message = self._vector_mismatch_error(
            stored_dimension=int(stored_dimension),
            detected_dimension=int(detected_dimension),
        )
        self._vector_persist_blocked_until_rebuild = True
        self._vector_rebuild_source_dimension = int(stored_dimension)
        return message

    def _enqueue_paragraph_vector_backfill(self, paragraph_hash: str, *, error: str = "") -> None:
        if self.metadata_store is None:
            return
        try:
            self.metadata_store.enqueue_paragraph_vector_backfill(
                paragraph_hash,
                error=str(error or ""),
            )
        except Exception as exc:
            logger.warning(f"登记 paragraph 向量回填任务失败: {exc}")

    async def _write_paragraph_vector_or_enqueue(
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

        allow_metadata_only = self._allow_metadata_only_write()

        target_store = self._paragraph_store()
        if target_store is None or self.embedding_manager is None:
            if not allow_metadata_only:
                raise RuntimeError("向量写入依赖未初始化")
            self._enqueue_paragraph_vector_backfill(token, error="vector_runtime_components_missing")
            return {
                "success": True,
                "vector_written": False,
                "queued": True,
                "warning": "vector_degraded_write",
                "detail": "vector_runtime_components_missing",
            }

        if self._is_embedding_degraded():
            if not allow_metadata_only:
                raise RuntimeError("embedding 处于降级态，metadata-only 写入已禁用")
            self._enqueue_paragraph_vector_backfill(token, error="embedding_degraded")
            return {
                "success": True,
                "vector_written": False,
                "queued": True,
                "warning": "vector_degraded_write",
                "detail": "embedding_degraded",
            }

        if token in target_store:
            return {
                "success": True,
                "vector_written": True,
                "queued": False,
                "warning": "",
                "detail": "vector_already_exists",
            }

        try:
            embedding = await self.embedding_manager.encode(text)
            if getattr(embedding, "ndim", 1) == 1:
                embedding = embedding.reshape(1, -1)
            target_store.add(vectors=embedding, ids=[token])
            return {
                "success": True,
                "vector_written": True,
                "queued": False,
                "warning": "",
                "detail": "",
            }
        except Exception as exc:
            error_text = str(exc)
            if self._embedding_fallback_enabled():
                self._set_embedding_degraded(active=True, reason=error_text[:500], checked_at=time.time())
            if not allow_metadata_only:
                raise
            self._enqueue_paragraph_vector_backfill(token, error=error_text)
            return {
                "success": True,
                "vector_written": False,
                "queued": True,
                "warning": "vector_degraded_write",
                "detail": f"{str(context or 'paragraph')} vector write failed: {error_text}",
            }

    def _paragraph_vector_backfill_counts(self) -> Dict[str, int]:
        if self.metadata_store is None:
            return {"pending": 0, "running": 0, "failed": 0, "done": 0}
        try:
            return self.metadata_store.get_paragraph_vector_backfill_status_counts()
        except Exception as exc:
            logger.warning(f"读取 paragraph 回填状态失败: {exc}")
            return {"pending": 0, "running": 0, "failed": 0, "done": 0}

    async def _run_paragraph_backfill_once(
        self,
        *,
        limit: Optional[int] = None,
        max_retry: Optional[int] = None,
        trigger: str = "manual",
    ) -> Dict[str, Any]:
        target_store = self._paragraph_store()
        if self.metadata_store is None or target_store is None or self.embedding_manager is None:
            return {"success": False, "processed": 0, "done": 0, "failed": 0, "trigger": trigger}
        if self._is_embedding_degraded():
            return {
                "success": False,
                "processed": 0,
                "done": 0,
                "failed": 0,
                "trigger": trigger,
                "detail": "embedding_degraded",
            }

        safe_limit = max(1, int(limit or self._paragraph_vector_backfill_batch_size()))
        safe_retry = max(1, int(max_retry or self._paragraph_vector_backfill_max_retry()))
        rows = self.metadata_store.fetch_paragraph_vector_backfill_batch(limit=safe_limit, max_retry=safe_retry)
        if not rows:
            return {"success": True, "processed": 0, "done": 0, "failed": 0, "trigger": trigger}

        pending_hashes = [
            str(row.get("paragraph_hash", "") or "").strip()
            for row in rows
            if str(row.get("paragraph_hash", "") or "").strip()
        ]
        if pending_hashes:
            self.metadata_store.mark_paragraph_vector_backfill_running(pending_hashes)

        done_hashes: List[str] = []
        encode_items: List[tuple[str, str]] = []
        paragraph_map = self.metadata_store.get_paragraphs_by_hashes(pending_hashes)
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

        done_count, failed_count, last_error, encoded_done_hashes, failed_hashes = await self._encode_and_add_rebuild_vectors(
            items=encode_items,
            batch_size=safe_limit,
            vector_store=target_store,
        )
        del done_count
        done_hashes.extend(encoded_done_hashes)
        for paragraph_hash in failed_hashes:
            self.metadata_store.mark_paragraph_vector_backfill_failed(paragraph_hash, last_error)
        if failed_hashes and self._embedding_fallback_enabled():
            self._set_embedding_degraded(active=True, reason=last_error[:500], checked_at=time.time())

        if done_hashes:
            self.metadata_store.mark_paragraph_vector_backfill_done(done_hashes)
            self._persist()

        return {
            "success": failed_count == 0,
            "processed": len(done_hashes) + failed_count,
            "done": len(done_hashes),
            "failed": failed_count,
            "trigger": trigger,
        }

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
        if (
            self.metadata_store is None
            or self.vector_store is None
            or self.paragraph_vector_store is None
            or self.graph_vector_store is None
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
        source_store = self.vector_store
        if source_store is not None and not self._stored_vectors_compatible_with_current_embedding(source_store):
            source_store = None
        if source_store is not None and source_store.has_data():
            try:
                source_store.load()
                source_store.warmup_index(force_train=False)
            except Exception as exc:
                logger.warning(f"加载旧单池向量用于双池增量补齐失败，将回退 embedding 重建: {exc}")

        paragraph_where = self._active_row_filter_sql("paragraphs")
        paragraph_rows = self.metadata_store.query(
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
            and str(row.get("hash", "") or "").strip() not in self.paragraph_vector_store
        ]
        done, failed, error, _done_ids, _failed_ids, copy_stats = await self._copy_or_encode_dual_rebuild_vectors(
            items=paragraph_items,
            batch_size=safe_batch_size,
            target_store=self.paragraph_vector_store,
            source_store=source_store,
        )
        stats["paragraphs"] = {"done": done, "failed": failed}
        migration_stats["paragraphs"] = copy_stats
        if error:
            errors.append(f"paragraph_pool_backfill:{error}")

        entity_where = self._active_row_filter_sql("entities")
        entity_rows = self.metadata_store.query(
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
            if self._graph_vector_id("entity", hash_value) in self.graph_vector_store:
                continue
            entity_items.append((hash_value, name))
        done, failed, error, _done_ids, _failed_ids, copy_stats = await self._copy_or_encode_dual_rebuild_vectors(
            items=entity_items,
            batch_size=safe_batch_size,
            target_store=self.graph_vector_store,
            target_id_prefix="entity",
            source_store=source_store,
        )
        stats["entities"] = {"done": done, "failed": failed}
        migration_stats["entities"] = copy_stats
        if error:
            errors.append(f"entity_graph_pool_backfill:{error}")

        if self.relation_vectors_enabled:
            relation_where = self._active_row_filter_sql("relations")
            relation_rows = self.metadata_store.query(
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
                if self._graph_vector_id("relation", hash_value) in self.graph_vector_store:
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
            done, failed, error, done_ids, failed_ids, copy_stats = await self._copy_or_encode_dual_rebuild_vectors(
                items=relation_items,
                batch_size=safe_batch_size,
                target_store=self.graph_vector_store,
                target_id_prefix="relation",
                source_store=source_store,
            )
            stats["relations"] = {"done": done, "failed": failed}
            migration_stats["relations"] = copy_stats
            if error:
                errors.append(f"relation_graph_pool_backfill:{error}")

            if done_ids or failed_ids:
                conn = self.metadata_store.get_connection()
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
        if self.paragraph_vector_store is not None:
            self._save_vector_store(self.paragraph_vector_store)
        if self.graph_vector_store is not None:
            self._save_vector_store(self.graph_vector_store)
        self._refresh_dual_vector_ready_manifest_from_stores()
        return {
            "success": failed_total == 0,
            "stats": stats,
            "migration": migration_stats,
            "failed": int(failed_total),
            "errors": errors[:5],
        }

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
            self.import_task_manager = ImportTaskManager(self._runtime_facade)
            self.retrieval_tuning_manager = RetrievalTuningManager(
                self._runtime_facade,
                import_write_blocked_provider=self.import_task_manager.is_write_blocked,
            )

    async def _encode_and_add_rebuild_vectors(
        self,
        *,
        items: Sequence[tuple[str, str]],
        batch_size: int,
        vector_store: Optional[VectorStore] = None,
    ) -> tuple[int, int, str, List[str], List[str]]:
        target_store = vector_store or self.vector_store
        if target_store is None or self.embedding_manager is None:
            failed_ids = [item_id for item_id, _ in items]
            return 0, len(items), "vector_runtime_components_missing", [], failed_ids

        done = 0
        failed = 0
        last_error = ""
        done_ids: List[str] = []
        failed_ids: List[str] = []
        safe_batch_size = max(1, int(batch_size))
        for start in range(0, len(items), safe_batch_size):
            batch = list(items[start : start + safe_batch_size])
            ids = [item_id for item_id, _ in batch]
            texts = [text for _, text in batch]
            try:
                encoder = getattr(self.embedding_manager, "encode_batch", None)
                if callable(encoder):
                    embeddings = await encoder(texts, batch_size=safe_batch_size)
                else:
                    embeddings = await self.embedding_manager.encode(texts)
                embedding_array = np.asarray(embeddings, dtype=np.float32)
                if embedding_array.ndim == 1:
                    embedding_array = embedding_array.reshape(1, -1)
                if embedding_array.shape[0] != len(ids):
                    raise ValueError(f"embedding 返回数量异常: expected={len(ids)}, got={embedding_array.shape[0]}")
                target_store.add(vectors=embedding_array, ids=ids)
                done += len(ids)
                done_ids.extend(ids)
            except Exception as exc:
                last_error = str(exc)[:500]
                failed += len(ids)
                failed_ids.extend(ids)
                logger.warning(f"重建向量批次失败: start={start}, count={len(ids)}, error={last_error}")
        return done, failed, last_error, done_ids, failed_ids

    def _copy_rebuild_vectors_from_store(
        self,
        *,
        source_store: Optional[VectorStore],
        target_store: Optional[VectorStore],
        id_pairs: Sequence[tuple[str, str]],
        batch_size: int = 1024,
    ) -> tuple[int, List[str], List[tuple[str, str]]]:
        if source_store is None or target_store is None or not id_pairs:
            return 0, [], list(id_pairs)

        pair_by_source = {source_id: target_id for source_id, target_id in id_pairs}
        source_ids = list(pair_by_source.keys())
        iterator = getattr(source_store, "iter_vectors_by_ids", None)
        getter = getattr(source_store, "get_vectors", None)
        if not callable(iterator) and not callable(getter):
            return 0, [], list(id_pairs)

        try:
            if callable(iterator):
                vector_batches = iterator(source_ids, batch_size=max(1, int(batch_size or 1024)))
            else:
                vector_batches = [getter(source_ids)]
        except Exception as exc:
            logger.warning(f"读取旧向量失败，将回退 embedding 重建: {exc}")
            return 0, [], list(id_pairs)

        copied_source_ids: List[str] = []
        copied_set: set[str] = set()
        try:
            for source_vectors in vector_batches:
                if not isinstance(source_vectors, dict) or not source_vectors:
                    continue
                target_ids: List[str] = []
                vectors: List[np.ndarray] = []
                for source_id, vector in source_vectors.items():
                    target_id = pair_by_source.get(source_id)
                    if target_id is None or source_id in copied_set:
                        continue
                    target_ids.append(target_id)
                    vectors.append(np.asarray(vector, dtype=np.float32))
                    copied_source_ids.append(source_id)
                    copied_set.add(source_id)
                if not target_ids:
                    continue
                vector_array = np.asarray(vectors, dtype=np.float32)
                if vector_array.ndim == 1:
                    vector_array = vector_array.reshape(1, -1)
                added = int(target_store.add(vectors=vector_array, ids=target_ids) or 0)
                if added < len(target_ids):
                    logger.debug(f"复制旧向量到新池时存在已写入项: requested={len(target_ids)} added={added}")
        except Exception as exc:
            logger.warning(f"复制旧向量到新池失败，将回退 embedding 重建: {exc}")
            return 0, [], list(id_pairs)

        missing_pairs = [(source_id, target_id) for source_id, target_id in id_pairs if source_id not in copied_set]
        return len(copied_source_ids), copied_source_ids, missing_pairs

    async def _copy_or_encode_dual_rebuild_vectors(
        self,
        *,
        items: Sequence[tuple[str, str]],
        batch_size: int,
        target_store: Optional[VectorStore],
        target_id_prefix: str = "",
        source_store: Optional[VectorStore] = None,
    ) -> tuple[int, int, str, List[str], List[str], Dict[str, int]]:
        id_pairs = [
            (
                str(item_id or "").strip(),
                f"{target_id_prefix}:{str(item_id or '').strip()}" if target_id_prefix else str(item_id or "").strip(),
            )
            for item_id, _text in items
            if str(item_id or "").strip()
        ]
        copied, copied_source_ids, missing_pairs = self._copy_rebuild_vectors_from_store(
            source_store=source_store,
            target_store=target_store,
            id_pairs=id_pairs,
            batch_size=batch_size,
        )
        missing_source_ids = {source_id for source_id, _target_id in missing_pairs}
        text_by_id = {str(item_id or "").strip(): text for item_id, text in items}
        encode_items = [
            (
                target_id,
                text_by_id.get(source_id, ""),
            )
            for source_id, target_id in missing_pairs
            if str(text_by_id.get(source_id, "") or "").strip()
        ]
        done, failed, error, encoded_done_ids, encoded_failed_ids = await self._encode_and_add_rebuild_vectors(
            items=encode_items,
            batch_size=batch_size,
            vector_store=target_store,
        )

        def _source_id(target_id: str) -> str:
            if target_id_prefix and target_id.startswith(f"{target_id_prefix}:"):
                return target_id.split(":", 1)[1]
            return target_id

        done_source_ids = copied_source_ids + [_source_id(item_id) for item_id in encoded_done_ids]
        failed_source_ids = [_source_id(item_id) for item_id in encoded_failed_ids]
        skipped_missing = len(missing_source_ids) - len(encode_items)
        failed += max(0, skipped_missing)
        return (
            copied + done,
            failed,
            error,
            done_source_ids,
            failed_source_ids,
            {
                "copied": copied,
                "encoded": done,
                "missing": len(missing_pairs),
            },
        )

    async def _rebuild_all_vectors(
        self,
        *,
        batch_size: Optional[int] = None,
        include_relations: Optional[bool] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        if self._vector_rebuild_lock.locked():
            return {
                "success": False,
                "error": "vector_rebuild_running",
                "detail": "已有向量重建任务正在运行",
            }
        async with self._vector_rebuild_lock:
            return await self._rebuild_all_vectors_locked(
                batch_size=batch_size,
                include_relations=include_relations,
                dry_run=dry_run,
            )

    async def _rebuild_all_vectors_locked(
        self,
        *,
        batch_size: Optional[int] = None,
        include_relations: Optional[bool] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        if self.metadata_store is None or self.vector_store is None or self.embedding_manager is None:
            return {"success": False, "error": "runtime_components_missing"}

        target_counts = self._count_vector_rebuild_targets()
        relation_enabled = bool(self.relation_vectors_enabled if include_relations is None else include_relations)
        if not relation_enabled:
            target_counts["relations"] = 0
        total = target_counts["paragraphs"] + target_counts["entities"] + target_counts["relations"]
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "counts": target_counts,
                "total": int(total),
                **self._vector_rebuild_status(),
            }

        started = time.time()
        safe_batch_size = max(1, int(batch_size or self._cfg("embedding.batch_size", 32) or 32))
        detected_dimension = await self._detect_current_embedding_dimension_for_rebuild()
        if detected_dimension > 0:
            self.embedding_dimension = int(detected_dimension)
        self._set_embedding_degraded(
            active=True,
            reason="正在重建全部向量，检索临时降级",
            checked_at=started,
        )

        dual_mode = self._dual_vector_pools_config_enabled()
        legacy_source_store = self.vector_store if dual_mode else None
        self._update_dual_vector_auto_migration_stage(
            "prepare_rebuild",
            dual_mode=dual_mode,
            total=int(total),
            counts=dict(target_counts),
            legacy_source_available=legacy_source_store is not None,
        )
        if legacy_source_store is not None and not self._stored_vectors_compatible_with_current_embedding(
            legacy_source_store
        ):
            legacy_source_store = None
            self._update_dual_vector_auto_migration_stage("legacy_source_incompatible")
        dual_build_root: Optional[Path] = None
        build_paragraph_vector_store: Optional[VectorStore] = None
        build_graph_vector_store: Optional[VectorStore] = None
        if dual_mode and legacy_source_store is not None and legacy_source_store.has_data():
            try:
                self._update_dual_vector_auto_migration_stage("legacy_source_load")
                legacy_source_store.load()
                self._update_dual_vector_auto_migration_stage("legacy_source_warmup")
                legacy_source_store.warmup_index(force_train=False)
                self._update_dual_vector_auto_migration_stage("legacy_source_ready")
            except Exception as exc:
                logger.warning(f"加载旧单池向量用于双池迁移失败，将回退 embedding 重建: {exc}")
        if not dual_mode:
            self._vector_pool_manager.dual_pools_ready = False
            self._remove_dual_vector_ready_manifest()
            self.vector_store = self._make_vector_store(self._vectors_root())
            self.vector_store.clear()
            self.paragraph_vector_store = self._make_vector_store(self._paragraph_vector_dir())
            self.graph_vector_store = self._make_vector_store(self._graph_vector_dir())
            self._refresh_relation_write_service()
        else:
            dual_build_root, paragraph_data_dir, graph_data_dir = self._prepare_dual_vector_build_dirs()
            build_paragraph_vector_store = self._make_vector_store(paragraph_data_dir)
            build_graph_vector_store = self._make_vector_store(graph_data_dir)
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
        paragraph_where = self._active_row_filter_sql("paragraphs")
        entity_where = self._active_row_filter_sql("entities")
        relation_where = self._active_row_filter_sql("relations")

        paragraph_rows = self.metadata_store.query(
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
            if str(row.get("hash", "") or "").strip() and str(row.get("content", "") or "").strip()
        ]
        self._update_dual_vector_auto_migration_stage("paragraphs_start", paragraph_items=len(paragraph_items))
        if dual_mode:
            done, failed, error, _done_ids, _failed_ids, copy_stats = await self._copy_or_encode_dual_rebuild_vectors(
                items=paragraph_items,
                batch_size=safe_batch_size,
                target_store=build_paragraph_vector_store,
                source_store=legacy_source_store,
            )
            migration_stats["paragraphs"] = copy_stats
            if error:
                errors.append(f"paragraph_pool:{error}")
        else:
            done, failed, error, _done_ids, _failed_ids = await self._encode_and_add_rebuild_vectors(
                items=paragraph_items,
                batch_size=safe_batch_size,
            )
            if error:
                errors.append(error)
        stats["paragraphs"] = {"done": done, "failed": failed}
        self._update_dual_vector_auto_migration_stage(
            "paragraphs_done",
            paragraph_done=done,
            paragraph_failed=failed,
            paragraph_migration=dict(migration_stats.get("paragraphs") or {}),
        )

        entity_rows = self.metadata_store.query(
            f"""
            SELECT hash, name
            FROM entities
            WHERE {entity_where}
            ORDER BY created_at ASC
            """
        )
        entity_items = [
            (str(row.get("hash", "") or ""), str(row.get("name", "") or "").strip())
            for row in entity_rows
            if str(row.get("hash", "") or "").strip() and str(row.get("name", "") or "").strip()
        ]
        self._update_dual_vector_auto_migration_stage("entities_start", entity_items=len(entity_items))
        if dual_mode:
            done, failed, error, _done_ids, _failed_ids, copy_stats = await self._copy_or_encode_dual_rebuild_vectors(
                items=entity_items,
                batch_size=safe_batch_size,
                target_store=build_graph_vector_store,
                target_id_prefix="entity",
                source_store=legacy_source_store,
            )
            migration_stats["entities"] = copy_stats
            if error:
                errors.append(f"entity_graph_pool:{error}")
        else:
            done, failed, error, _done_ids, _failed_ids = await self._encode_and_add_rebuild_vectors(
                items=entity_items,
                batch_size=safe_batch_size,
            )
            if error:
                errors.append(error)
        stats["entities"] = {"done": done, "failed": failed}
        self._update_dual_vector_auto_migration_stage(
            "entities_done",
            entity_done=done,
            entity_failed=failed,
            entity_migration=dict(migration_stats.get("entities") or {}),
        )

        if relation_enabled:
            relation_rows = self.metadata_store.query(
                f"""
                SELECT hash, subject, predicate, object
                FROM relations
                WHERE {relation_where}
                ORDER BY created_at ASC
                """
            )
            relation_items = [
                (
                    str(row.get("hash", "") or ""),
                    RelationWriteService.build_relation_vector_text(
                        str(row.get("subject", "") or ""),
                        str(row.get("predicate", "") or ""),
                        str(row.get("object", "") or ""),
                    ),
                )
                for row in relation_rows
                if str(row.get("hash", "") or "").strip()
            ]
            self._update_dual_vector_auto_migration_stage("relations_start", relation_items=len(relation_items))
            if dual_mode:
                done, failed, error, done_ids, failed_ids, copy_stats = await self._copy_or_encode_dual_rebuild_vectors(
                    items=relation_items,
                    batch_size=safe_batch_size,
                    target_store=build_graph_vector_store,
                    target_id_prefix="relation",
                    source_store=legacy_source_store,
                )
                migration_stats["relations"] = copy_stats
                if error:
                    errors.append(f"relation_graph_pool:{error}")
            else:
                done, failed, error, done_ids, failed_ids = await self._encode_and_add_rebuild_vectors(
                    items=relation_items,
                    batch_size=safe_batch_size,
                )
                if error:
                    errors.append(error)
            stats["relations"] = {"done": done, "failed": failed}
            self._update_dual_vector_auto_migration_stage(
                "relations_done",
                relation_done=done,
                relation_failed=failed,
                relation_migration=dict(migration_stats.get("relations") or {}),
            )

            conn = self.metadata_store.get_connection()
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
                        vector_error = ?
                    WHERE hash IN ({placeholders})
                    """,
                    (now_ts, error[:500], *batch_ids),
                )
            conn.commit()

        done_total = sum(int(item["done"]) for item in stats.values())
        failed_total = sum(int(item["failed"]) for item in stats.values())
        activation_ok = True
        if dual_mode:
            expected_paragraph_vectors = int(stats["paragraphs"]["done"])
            expected_graph_vectors = int(stats["entities"]["done"]) + int(stats["relations"]["done"])
            actual_paragraph_vectors = (
                int(build_paragraph_vector_store.num_vectors) if build_paragraph_vector_store else 0
            )
            actual_graph_vectors = int(build_graph_vector_store.num_vectors) if build_graph_vector_store else 0
            self._update_dual_vector_auto_migration_stage(
                "activation_check",
                stats=dict(stats),
                migration=dict(migration_stats),
                actual_paragraph_vectors=actual_paragraph_vectors,
                expected_paragraph_vectors=expected_paragraph_vectors,
                actual_graph_vectors=actual_graph_vectors,
                expected_graph_vectors=expected_graph_vectors,
            )
            if (
                failed_total == 0
                and actual_paragraph_vectors == expected_paragraph_vectors
                and actual_graph_vectors == expected_graph_vectors
            ):
                try:
                    if build_paragraph_vector_store is not None:
                        self._update_dual_vector_auto_migration_stage("paragraph_pool_warmup")
                        build_paragraph_vector_store.warmup_index(force_train=True)
                        self._update_dual_vector_auto_migration_stage("paragraph_pool_save")
                        self._save_vector_store(build_paragraph_vector_store)
                    if build_graph_vector_store is not None:
                        self._update_dual_vector_auto_migration_stage("graph_pool_warmup")
                        build_graph_vector_store.warmup_index(force_train=True)
                        self._update_dual_vector_auto_migration_stage("graph_pool_save")
                        self._save_vector_store(build_graph_vector_store)
                    self._update_dual_vector_auto_migration_stage("activate_dirs")
                    self._activate_dual_vector_build_dirs(dual_build_root)
                    self._update_dual_vector_auto_migration_stage("write_manifest")
                    self._write_dual_vector_ready_manifest(stats=stats, migration_stats=migration_stats)
                    self._update_dual_vector_auto_migration_stage("reload_dual_stores")
                    activation_ok = self._reload_dual_vector_stores_from_disk()
                    if not activation_ok:
                        errors.append("dual_pool_activation:ready_manifest_unusable")
                    else:
                        self._update_dual_vector_auto_migration_stage("dual_backfill")
                        backfill_result = await self._backfill_missing_dual_vector_pool_entries(
                            batch_size=safe_batch_size,
                        )
                        self._update_dual_vector_auto_migration_stage("dual_backfill_done", backfill=backfill_result)
                        if not bool(backfill_result.get("success", False)):
                            for item in backfill_result.get("errors", []) or []:
                                errors.append(str(item))
                        self._update_dual_vector_auto_migration_stage("clear_legacy_single_pool")
                        self._clear_legacy_single_vector_files_after_dual_ready()
                except Exception as exc:
                    activation_ok = False
                    self._vector_pool_manager.dual_pools_ready = False
                    errors.append(f"dual_pool_activation:{str(exc)[:500]}")
                    logger.warning(f"双池临时构建目录切换失败，保留原有向量池: {exc}")
                    self._drop_dual_build_root(dual_build_root)
                    self._reload_dual_vector_stores_from_disk()
            else:
                activation_ok = False
                if failed_total == 0:
                    errors.append(
                        "dual_pool_activation:vector_count_mismatch "
                        f"paragraph={actual_paragraph_vectors}/{expected_paragraph_vectors}, "
                        f"graph={actual_graph_vectors}/{expected_graph_vectors}"
                    )
                self._drop_dual_build_root(dual_build_root)
                self._reload_dual_vector_stores_from_disk()
            self._refresh_relation_write_service()
        else:
            self._update_dual_vector_auto_migration_stage("single_pool_warmup")
            self.vector_store.warmup_index(force_train=True)
            self.paragraph_vector_store = self._make_vector_store(self._paragraph_vector_dir())
            self.graph_vector_store = self._make_vector_store(self._graph_vector_dir())
            self._refresh_relation_write_service()
        self._update_dual_vector_auto_migration_stage("runtime_rebuild")
        self._runtime_bundle = build_search_runtime(
            plugin_config=self._build_runtime_config(),
            logger_obj=logger,
            owner_tag="sdk_kernel",
            log_prefix="[sdk]",
        )
        if self._runtime_bundle.ready:
            self.retriever = self._runtime_bundle.retriever
            self.threshold_filter = self._runtime_bundle.threshold_filter
            self.sparse_index = self._runtime_bundle.sparse_index or self.sparse_index
            self._refresh_runtime_dependents(preserve_managers=True)
            self._apply_runtime_sparse_mode()

        self._update_dual_vector_auto_migration_stage("self_check")
        report = await self._refresh_runtime_self_check(sample_text="A_Memorix vector rebuild self check")
        if bool(report.get("ok", False)) and not errors:
            self._set_embedding_degraded(active=False, checked_at=float(report.get("checked_at") or time.time()))
        else:
            self._set_embedding_degraded(
                active=True,
                reason=str(report.get("message") or "; ".join(errors) or "vector_rebuild_incomplete")[:500],
                checked_at=float(report.get("checked_at") or time.time()),
            )

        elapsed_ms = (time.time() - started) * 1000.0
        rebuild_success = failed_total == 0 and bool(report.get("ok", False)) and (not dual_mode or activation_ok)
        if rebuild_success:
            self._vector_persist_blocked_until_rebuild = False
            self._vector_rebuild_source_dimension = None
        self._update_dual_vector_auto_migration_stage("persist", rebuild_success=rebuild_success, errors=list(errors[:5]))
        self._persist(force_vectors=rebuild_success)
        return {
            "success": rebuild_success,
            "dry_run": False,
            "counts": target_counts,
            "stats": stats,
            "migration": migration_stats,
            "total": int(total),
            "done": int(done_total),
            "failed": int(failed_total),
            "errors": errors[:5],
            "elapsed_ms": elapsed_ms,
            "self_check": report,
            **self._vector_rebuild_status(),
        }

    async def _detect_current_embedding_dimension_for_rebuild(self) -> int:
        if self.embedding_manager is None:
            raise RuntimeError("embedding_manager_missing")
        detector = getattr(self.embedding_manager, "_detect_dimension", None)
        if not callable(detector):
            return max(1, int(self._cfg("embedding.dimension", self.embedding_dimension) or self.embedding_dimension))
        detected_dimension = int(await detector())
        if detected_dimension <= 0:
            raise ValueError(f"embedding 维度检测结果非法: {detected_dimension}")
        return detected_dimension

    async def _recover_embedding_once(self, *, sample_text: str = "A_Memorix runtime self check") -> Dict[str, Any]:
        report = await self._refresh_runtime_self_check(sample_text=sample_text)
        checked_at = float(report.get("checked_at") or time.time())
        ok = bool(report.get("ok", False))
        dimension_mismatch = self._apply_self_check_dimension_result(report)
        if dimension_mismatch:
            self._set_embedding_degraded(active=True, reason=dimension_mismatch, checked_at=checked_at)
            return {
                "success": False,
                "recovered": False,
                "report": report,
                "detail": "dimension_mismatch",
            }

        if ok:
            self._set_embedding_degraded(active=False, checked_at=checked_at)
            backfill_result: Dict[str, Any] = {}
            if self._paragraph_vector_backfill_enabled():
                backfill_result = await self._run_paragraph_backfill_once(
                    limit=self._paragraph_vector_backfill_batch_size(),
                    max_retry=self._paragraph_vector_backfill_max_retry(),
                    trigger="embedding_recovered",
                )
            return {
                "success": True,
                "recovered": True,
                "report": report,
                "backfill": backfill_result,
            }

        reason = str(report.get("message", "runtime self-check failed") or "runtime self-check failed")
        if self._embedding_fallback_enabled():
            self._set_embedding_degraded(active=True, reason=reason, checked_at=checked_at)
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

        stored_dimension = self._stored_vector_dimension()
        provisional_dimension = stored_dimension or self.embedding_dimension
        self.embedding_dimension = int(provisional_dimension)

        matrix_format = str(self._cfg("graph.sparse_matrix_format", "csr") or "csr").strip().lower()
        graph_format = SparseMatrixFormat.CSC if matrix_format == "csc" else SparseMatrixFormat.CSR

        self.vector_store = self._vector_pool_manager.make_vector_store(self._vectors_root(), dimension=provisional_dimension)
        self.paragraph_vector_store = self._vector_pool_manager.make_vector_store(
            self._paragraph_vector_dir(),
            dimension=provisional_dimension,
        )
        self.graph_vector_store = self._vector_pool_manager.make_vector_store(
            self._graph_vector_dir(),
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
        if getattr(self.sparse_index.config, "enabled", False):
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
        if self._dual_vector_pools_config_enabled():
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
        self.import_task_manager = ImportTaskManager(self._runtime_facade)
        self.retrieval_tuning_manager = RetrievalTuningManager(
            self._runtime_facade,
            import_write_blocked_provider=self.import_task_manager.is_write_blocked,
        )

        self._mark_startup_self_check_deferred()

        from .admin import (
            GraphAdminHandler, ParagraphAdminHandler, RelationAdminHandler,
            RuntimeAdminHandler, ImportAdminHandler, TuningAdminHandler,
            V5AdminHandler, DeleteAdminHandler, CorrectionAdminHandler,
        )
        self._admin_handlers = {
            "graph": GraphAdminHandler(self),
            "paragraph": ParagraphAdminHandler(self),
            "relation": RelationAdminHandler(self),
            "runtime": RuntimeAdminHandler(self),
            "import": ImportAdminHandler(self),
            "tuning": TuningAdminHandler(self),
            "v5": V5AdminHandler(self),
            "delete": DeleteAdminHandler(self),
            "correction": CorrectionAdminHandler(self),
        }

        from .services.delete import DeleteService
        self._delete_service = DeleteService(
            metadata_store=self.metadata_store,
            graph_store=self.graph_store,
            merge_tokens=self._merge_tokens,
            tokens=self._tokens,
            selector_dict=self._selector_dict,
            persist=self._persist,
            rebuild_graph_from_metadata=self._rebuild_graph_from_metadata,
            delete_vectors_by_type=self._delete_vectors_by_type,
            cfg=self._cfg,
            format_relation_text=self._format_relation_text,
            trim_text=self._trim_text,
            resolve_relation_hashes=self._resolve_relation_hashes,
            resolve_deleted_relation_hashes=self._resolve_deleted_relation_hashes,
            resolve_source_targets=self._resolve_source_targets,
            restore_relation_hashes=self._restore_relation_hashes,
            relation_has_remaining_paragraphs=self._relation_has_remaining_paragraphs,
            ensure_entity_vector=self._ensure_entity_vector,
            ensure_paragraph_vector=self._ensure_paragraph_vector,
            ensure_relation_vector=self._ensure_relation_vector,
            optional_float=self._optional_float,
        )


        self._fuzzy_modify_service = FuzzyModifyService(
            metadata_store=self.metadata_store,
            fuzzy_modify_config=self._fuzzy_modify_config,
            fuzzy_modify_planner=self._fuzzy_modify_planner,
            tokens=self._tokens,
            merge_tokens=self._merge_tokens,
            argument_tokens=self._argument_tokens,
            merge_argument_tokens=self._merge_argument_tokens,
            optional_float=self._optional_float,
            trim_text=self._trim_text,
            safe_json_loads=self._safe_json_loads,
            persist=self._persist,
            rebuild_graph_from_metadata=self._rebuild_graph_from_metadata,
            relation_has_remaining_paragraphs=self._relation_has_remaining_paragraphs,
            execute_delete_action=self._execute_delete_action,
            search_memory=lambda request_text, limit, scope, person_id, chat_id: self.search_memory(
                KernelSearchRequest(
                    query=request_text,
                    limit=limit,
                    mode="aggregate",
                    chat_id=chat_id,
                    person_id=person_id,
                    respect_filter=True,
                )
            ),
            ingest_text=self.ingest_text,
            refresh_person_profile=self.refresh_person_profile,
            profile_evidence_admin=self._profile_evidence_admin,
            person_profile_service=self.person_profile_service,
            invalidate_filter_cache=lambda: setattr(self, '_current_effective_filter_cache', {"checked_at": 0.0, "needed": True}),
        )

        self._feedback_correction_service = FeedbackCorrectionService(
            metadata_store=self.metadata_store,
            feedback_config=self._feedback_config,
            feedback_classifier=self._feedback_classifier,
            person_profile_service=self.person_profile_service,
            episode_service=self.episode_service,
            background_scheduler=self._background_scheduler,
            delete_service=self._delete_service,
            tokens=self._tokens,
            merge_tokens=self._merge_tokens,
            argument_tokens=self._argument_tokens,
            persist=self._persist,
            rebuild_graph_from_metadata=self._rebuild_graph_from_metadata,
            cfg=self._cfg,
            safe_json_loads=self._safe_json_loads,
            chat_source=self._chat_source,
            format_relation_text=self._format_relation_text,
            load_paragraph_rows=self._load_paragraph_rows,
            query_relation_rows_by_hashes=self._query_relation_rows_by_hashes,
            apply_v5_relation_action=self._apply_v5_relation_action,
            ingest_text=self.ingest_text,
            refresh_person_profile=self.refresh_person_profile,
            soft_delete_feedback_correction_paragraphs=self._delete_service.soft_delete_feedback_correction_paragraphs,
            person_profile_refresh_max_retry=self._person_profile_refresh_max_retry,
            process_person_profile_refresh_queue_batch=self._process_person_profile_refresh_queue_batch,
            initialize=self.initialize,
        )

        self._profile_evidence_service = ProfileEvidenceService(
            metadata_store=self.metadata_store,
            person_profile_service=self.person_profile_service,
            tokens=self._tokens,
            trim_text=self._trim_text,
            query_person_profile_with_feedback_refresh=self._query_person_profile_with_feedback_refresh,
            execute_delete_action=self._execute_delete_action,
            invalidate_import_manifest_for_sources=self._invalidate_import_manifest_for_sources,
        )

        from .services.graph_ops import GraphOpsService
        self._graph_ops_service = GraphOpsService(
            metadata_store=self.metadata_store,
            graph_store=self.graph_store,
            load_paragraph_stale_marks=self._load_paragraph_stale_marks,
            persist_callback=self._persist,
            rebuild_graph_callback=lambda: {"node_count": 0, "edge_count": 0},
        )
        self._graph_ops_service._rebuild_graph_from_metadata = self._graph_ops_service.rebuild_graph_from_metadata

        from .services.v5_memory import V5MemoryService
        self._v5_memory_service = V5MemoryService(
            metadata_store=self.metadata_store,
            cfg=self._cfg,
            resolve_relation_hashes=self._resolve_relation_hashes,
            resolve_deleted_relation_hashes=self._resolve_deleted_relation_hashes,
            rebuild_graph_from_metadata=self._rebuild_graph_from_metadata,
            persist_callback=self._persist,
            last_maintenance_at_getter=lambda: self._last_maintenance_at,
            last_maintenance_at_setter=lambda v: setattr(self, '_last_maintenance_at', v),
        )

        self._initialized = True
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
            self._runtime_facade._runtime_self_check_report = {}
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
        assert self.summary_importer
        import_result = await self.summary_importer.import_from_stream(
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
            or self._build_source("chat_summary", chat_id, [])
        )
        stored_ids: List[str] = []
        episode_pending_ids: List[str] = []
        if success:
            if not paragraph_hash:
                raise RuntimeError("聊天摘要导入成功但未返回 paragraph_hash，无法执行 Episode 增量入队")
            assert self.metadata_store is not None
            if self._should_auto_enqueue_episode(source_type="chat_summary"):
                self.metadata_store.enqueue_episode_pending(paragraph_hash, source=source)
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

        await self.initialize()
        assert self.metadata_store is not None
        assert self.vector_store is not None
        assert self.graph_store is not None
        assert self.embedding_manager is not None
        assert self.relation_write_service is not None

        if not content:
            return {"stored_ids": [], "skipped_ids": [external_token], "reason": "empty_text"}

        existing_ref = self.metadata_store.get_external_memory_ref(external_token)
        if existing_ref:
            return {
                "stored_ids": [],
                "skipped_ids": [str(existing_ref.get("paragraph_hash", "") or "")],
                "reason": "exists",
            }

        person_tokens = self._tokens(person_ids)
        participant_tokens = self._tokens(participants)
        entity_tokens = self._merge_tokens(entities, person_tokens, participant_tokens)
        source = self._build_source(source_type, chat_id, person_tokens)
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

        paragraph_hash = self.metadata_store.add_paragraph(
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
            entity_hash = self.metadata_store.add_entity(name=name, source_paragraph=paragraph_hash)
            await self._ensure_entity_vector({"hash": entity_hash, "name": name})

        stored_relations: List[str] = []
        for row in [dict(item) for item in (relations or []) if isinstance(item, dict)]:
            subject = str(row.get("subject", "") or "").strip()
            predicate = str(row.get("predicate", "") or "").strip()
            obj = str(row.get("object", "") or "").strip()
            if not (subject and predicate and obj):
                continue
            result = await self.relation_write_service.upsert_relation_with_vector(
                subject=subject,
                predicate=predicate,
                obj=obj,
                confidence=float(row.get("confidence", 1.0) or 1.0),
                source_paragraph=paragraph_hash,
                metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {"external_id": external_token, "source_type": source_type},
                write_vector=self.relation_vectors_enabled,
            )
            self.metadata_store.link_paragraph_relation(paragraph_hash, result.hash_value)
            stored_relations.append(result.hash_value)

        self.metadata_store.upsert_external_memory_ref(
            external_id=external_token,
            paragraph_hash=paragraph_hash,
            source_type=source_type,
            metadata={"chat_id": chat_id, "person_ids": person_tokens},
        )
        if self._should_auto_enqueue_episode(source_type=source_type):
            self.metadata_store.enqueue_episode_pending(paragraph_hash, source=source)
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
        await self.initialize()
        assert self.metadata_store is not None
        assert self.episode_service is not None

        pending_rows = self.metadata_store.fetch_episode_pending_batch(limit=max(1, int(limit)), max_retry=max(1, int(max_retry)))
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
            self.metadata_store.mark_episode_pending_running(pending_hashes)

        result = await self.episode_service.process_pending_rows(pending_rows)
        done_hashes = [str(item or "").strip() for item in result.get("done_hashes", []) if str(item or "").strip()]
        failed_hashes = {
            str(hash_value or "").strip(): str(error or "").strip()
            for hash_value, error in (result.get("failed_hashes", {}) or {}).items()
            if str(hash_value or "").strip()
        }

        if done_hashes:
            self.metadata_store.mark_episode_pending_done(done_hashes)
        for hash_value, error in failed_hashes.items():
            self.metadata_store.mark_episode_pending_failed(hash_value, error)

        untouched = [hash_value for hash_value in pending_hashes if hash_value not in set(done_hashes) and hash_value not in failed_hashes]
        for hash_value in untouched:
            self.metadata_store.mark_episode_pending_failed(hash_value, "episode processing finished without explicit status")

        for source, paragraph_hashes in source_to_hashes.items():
            counts = self.metadata_store.get_episode_pending_status_counts(source)
            if counts.get("failed", 0) > 0:
                source_error = next(
                    (
                        failed_hashes.get(hash_value)
                        for hash_value in paragraph_hashes
                        if failed_hashes.get(hash_value)
                    ),
                    "episode pending source contains failed rows",
                )
                self.metadata_store.mark_episode_source_failed(source, str(source_error or "episode pending source contains failed rows"))
            elif counts.get("pending", 0) == 0 and counts.get("running", 0) == 0:
                self.metadata_store.mark_episode_source_done(source)

        self._persist()
        return {
            "processed": len(done_hashes) + len(failed_hashes),
            "episode_count": int(result.get("episode_count") or 0),
            "fallback_count": int(result.get("fallback_count") or 0),
            "failed": len(failed_hashes) + len(untouched),
            "group_count": int(result.get("group_count") or 0),
            "missing_count": int(result.get("missing_count") or 0),
        }

    async def search_memory(self, request: KernelSearchRequest) -> Dict[str, Any]:
        if self._is_chat_filtered(
            respect_filter=request.respect_filter,
            stream_id=request.chat_id,
            group_id=request.group_id,
            user_id=request.user_id,
        ):
            return {"summary": "", "hits": [], "filtered": True}

        await self.initialize()
        assert self.retriever is not None
        assert self.episode_retriever is not None
        assert self.aggregate_query_service is not None

        mode = str(request.mode or "search").strip().lower() or "search"
        query = str(request.query or "").strip()
        limit = max(1, int(request.limit or 5))
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        scoped_limit = self._scoped_search_limit(limit, chat_id=request.chat_id, shared_chat_ids=shared_chat_ids)
        supported_modes = {"search", "time", "hybrid", "episode", "aggregate"}
        if mode not in supported_modes:
            return {
                "summary": "",
                "hits": [],
                "error": (
                    f"不支持的检索模式: {mode}（仅支持 search/time/hybrid/episode/aggregate，"
                    "semantic 已移除）"
                ),
            }
        try:
            time_window = self._normalize_search_time_window(request.time_start, request.time_end)
        except ValueError as exc:
            return {"summary": "", "hits": [], "error": str(exc)}

        if mode == "episode":
            rows = await self._episode_query_for_chat_scope(
                query=query,
                top_k=scoped_limit,
                time_from=time_window.numeric_start,
                time_to=time_window.numeric_end,
                person=request.person_id or None,
                chat_id=request.chat_id,
                shared_chat_ids=shared_chat_ids,
            )
            hits = self._filter_episode_hits([self._episode_hit(row) for row in rows])
            hits = self._filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
            if request.respect_filter:
                hits = self._filter_hits_by_retrieval_type_scope(
                    hits,
                    current_stream_id=request.chat_id,
                    current_group_id=request.group_id,
                    current_user_id=request.user_id,
                )
            hits = hits[:limit]
            return {"summary": self._summary(hits), "hits": hits}

        if mode == "aggregate":
            payload = await self.aggregate_query_service.execute(
                query=query,
                top_k=scoped_limit,
                mix=True,
                mix_top_k=scoped_limit,
                time_from=time_window.query_start,
                time_to=time_window.query_end,
                search_runner=lambda: self._aggregate_search(query, scoped_limit, request),
                time_runner=lambda: self._aggregate_time(query, scoped_limit, request, time_window),
                episode_runner=lambda: self._aggregate_episode(query, scoped_limit, request, time_window),
            )
            hits = [dict(item) for item in payload.get("mixed_results", []) if isinstance(item, dict)]
            for item in hits:
                item.setdefault("metadata", {})
            filtered = self._filter_hits(hits, request.person_id)
            filtered = self._filter_user_visible_hits(filtered)
            filtered = self._filter_hits_by_chat_scope(filtered, request.chat_id, shared_chat_ids)
            if request.respect_filter:
                filtered = self._filter_hits_by_retrieval_type_scope(
                    filtered,
                    current_stream_id=request.chat_id,
                    current_group_id=request.group_id,
                    current_user_id=request.user_id,
                )
            filtered = filtered[:limit]
            return {"summary": self._summary(filtered), "hits": filtered}

        query_type = mode
        runtime_config = self._build_runtime_config()
        result = await self._search_execution_for_chat_scope(
            caller="sdk_memory_kernel",
            query_type=query_type,
            query=query,
            top_k=scoped_limit,
            request=request,
            time_from=time_window.query_start,
            time_to=time_window.query_end,
            plugin_config=runtime_config,
            enforce_chat_filter=bool(request.respect_filter),
        )
        if not result.success:
            return {"summary": "", "hits": [], "error": result.error}
        if result.chat_filtered:
            return {"summary": "", "hits": [], "filtered": True}

        hits = [self._retrieval_result_hit(item) for item in result.results]
        filtered = self._filter_hits(hits, request.person_id)
        filtered = self._filter_user_visible_hits(filtered)
        filtered = self._filter_hits_by_chat_scope(filtered, request.chat_id, shared_chat_ids)
        if request.respect_filter:
            filtered = self._filter_hits_by_retrieval_type_scope(
                filtered,
                current_stream_id=request.chat_id,
                current_group_id=request.group_id,
                current_user_id=request.user_id,
            )
        filtered = filtered[:limit]
        return {"summary": self._summary(filtered), "hits": filtered}

    @staticmethod
    def _empty_person_profile_response(*, person_id: str = "", person_name: str = "") -> Dict[str, Any]:
        return {
            "summary": "",
            "traits": [],
            "evidence": [],
            "person_id": str(person_id or "").strip(),
            "person_name": str(person_name or "").strip(),
            "profile_source": "",
            "has_manual_override": False,
        }

    async def _query_person_profile_with_feedback_refresh(
        self,
        *,
        person_id: str = "",
        person_keyword: str = "",
        limit: int = 10,
        force_refresh: bool = False,
        source_note: str,
    ) -> Dict[str, Any]:
        return await self._feedback_correction_service._query_person_profile_with_feedback_refresh(
            person_id=person_id,
            person_keyword=person_keyword,
            limit=limit,
            force_refresh=force_refresh,
            source_note=source_note,
        )

    def _build_person_profile_response(
        self,
        profile: Dict[str, Any],
        *,
        requested_person_id: str,
        limit: int,
    ) -> Dict[str, Any]:
        assert self.metadata_store is not None
        if not bool(profile.get("success")):
            return self._empty_person_profile_response(
                person_id=str(profile.get("person_id", "") or requested_person_id),
                person_name=str(profile.get("person_name", "") or ""),
            )

        evidence: List[Dict[str, Any]] = []
        evidence_limit = max(1, int(limit or 10))
        for hash_value in profile.get("evidence_ids", [])[:evidence_limit]:
            paragraph = self.metadata_store.get_paragraph(hash_value)
            if paragraph is not None:
                evidence.append(
                    {
                        "hash": hash_value,
                        "content": str(paragraph.get("content", "") or "")[:220],
                        "metadata": paragraph.get("metadata", {}) or {},
                        "type": "paragraph",
                    }
                )
                continue

            relation = self.metadata_store.get_relation(hash_value)
            if relation is not None:
                evidence.append(
                    {
                        "hash": hash_value,
                        "content": " ".join(
                            [
                                str(relation.get("subject", "") or "").strip(),
                                str(relation.get("predicate", "") or "").strip(),
                                str(relation.get("object", "") or "").strip(),
                            ]
                        ).strip(),
                        "metadata": {
                            "confidence": relation.get("confidence"),
                            "source_paragraph": relation.get("source_paragraph"),
                        },
                        "type": "relation",
                    }
                )

        evidence = self._filter_user_visible_hits(evidence)
        text = str(profile.get("profile_text", "") or "").strip()
        traits = [line.strip("- ").strip() for line in text.splitlines() if line.strip()][:8]
        return {
            "summary": text,
            "traits": traits,
            "evidence": evidence,
            "person_id": str(profile.get("person_id", "") or requested_person_id),
            "person_name": str(profile.get("person_name", "") or ""),
            "profile_source": str(profile.get("profile_source", "") or "auto_snapshot"),
            "has_manual_override": bool(profile.get("has_manual_override", False)),
        }

    async def get_person_profile(self, *, person_id: str, chat_id: str = "", limit: int = 10) -> Dict[str, Any]:
        del chat_id
        await self.initialize()
        assert self.metadata_store is not None
        assert self.person_profile_service is not None
        self._mark_person_active(person_id)
        profile = await self._query_person_profile_with_feedback_refresh(
            person_id=person_id,
            limit=max(4, int(limit or 10)),
            source_note="sdk_memory_kernel.get_person_profile",
        )
        return self._build_person_profile_response(profile, requested_person_id=person_id, limit=limit)

    async def refresh_person_profile(self, person_id: str, limit: int = 10, *, mark_active: bool = True) -> Dict[str, Any]:
        await self.initialize()
        assert self.person_profile_service
        if mark_active:
            self._mark_person_active(person_id)
        profile = await self.person_profile_service.query_person_profile(
            person_id=person_id,
            top_k=max(4, int(limit or 10)),
            force_refresh=True,
            source_note="sdk_memory_kernel.refresh_person_profile",
        )
        return profile if isinstance(profile, dict) else {}

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
        await self.initialize()
        assert self.metadata_store
        act = str(action or "").strip().lower()
        if act == "recycle_bin":
            items = self.metadata_store.get_deleted_relations(limit=max(1, int(limit or 50)))
            return {"success": True, "items": items, "count": len(items)}

        hashes = self._resolve_deleted_relation_hashes(target) if act == "restore" else self._resolve_relation_hashes(target)
        if not hashes:
            return {"success": False, "detail": "未命中可维护关系"}

        if act == "reinforce":
            self.metadata_store.reinforce_relations(hashes)
        elif act == "freeze":
            self.metadata_store.mark_relations_inactive(hashes)
            self._rebuild_graph_from_metadata()
        elif act == "protect":
            ttl_seconds = max(0.0, float(hours or 0.0)) * 3600.0
            self.metadata_store.protect_relations(hashes, ttl_seconds=ttl_seconds, is_pinned=ttl_seconds <= 0)
        elif act == "restore":
            restored = sum(1 for hash_value in hashes if self.metadata_store.restore_relation(hash_value))
            if restored <= 0:
                return {"success": False, "detail": "未恢复任何关系"}
            self._rebuild_graph_from_metadata()
        else:
            return {"success": False, "detail": f"不支持的维护动作: {act}"}

        self._last_maintenance_at = time.time()
        self._persist()
        return {"success": True, "detail": f"{act} {len(hashes)} 条关系"}

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
        return self._vector_pool_manager.should_start_dual_vector_auto_migration(
            background_stopping=self._background_scheduler.stopping,
        )

    def _normalize_dual_vector_auto_migration_progress(
        self,
        progress: Optional[Dict[str, Any]] = None,
        *,
        now: Optional[float] = None,
        explicit_processed: bool = False,
        completed: bool = False,
        success: bool = False,
    ) -> Dict[str, Any]:
        return self._vector_pool_manager.normalize_dual_vector_auto_migration_progress(
            progress, now=now, explicit_processed=explicit_processed, completed=completed, success=success,
        )

        def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
            try:
                number = int(float(value))
            except (TypeError, ValueError):
                return default
            return max(0, number)

        total = _coerce_non_negative_int(payload.get("total"), 0)
        if total <= 0:
            counts = payload.get("counts")
            if isinstance(counts, dict):
                total = sum(
                    _coerce_non_negative_int(counts.get(key), 0)
                    for key in ("paragraphs", "entities", "relations")
                )

        processed_keys = (
            "paragraph_done",
            "paragraph_failed",
            "entity_done",
            "entity_failed",
            "relation_done",
            "relation_failed",
        )
        if explicit_processed:
            processed = _coerce_non_negative_int(payload.get("processed"), 0)
        elif any(key in payload for key in processed_keys):
            processed = sum(_coerce_non_negative_int(payload.get(key), 0) for key in processed_keys)
        else:
            processed = _coerce_non_negative_int(payload.get("processed"), 0)
        if total > 0:
            processed = min(processed, total)

        if completed and success:
            if total > 0:
                processed = total
            percent = 100.0
        elif total > 0:
            percent = min(99.5, max(0.0, (float(processed) / float(total)) * 100.0))
        else:
            percent = 0.0

        estimated_remaining_seconds: Optional[int] = None
        if not completed and total > 0 and 0 < processed < total and elapsed_seconds > 0.0:
            rate = float(processed) / elapsed_seconds
            if rate > 0.0:
                remaining = (float(total) - float(processed)) / rate
                estimated_remaining_seconds = max(0, int(remaining + 0.999))

        payload.update(
            {
                "total": int(total),
                "processed": int(processed),
                "percent": round(percent, 2),
                "elapsed_seconds": round(elapsed_seconds, 3),
                "estimated_remaining_seconds": estimated_remaining_seconds,
            }
        )
        return payload

    def _update_dual_vector_auto_migration_stage(self, stage: str, **progress: Any) -> None:
        return self._vector_pool_manager.update_dual_vector_auto_migration_stage(stage, **progress)

    async def memory_graph_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._admin_handlers["graph"].handle(action, **kwargs)

    async def memory_source_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        await self.initialize()
        assert self.metadata_store

        act = str(action or "").strip().lower()
        if act == "list":
            sources = self.metadata_store.get_all_sources()
            items = []
            for row in sources:
                source_name = str(row.get("source", "") or "").strip()
                items.append(
                    {
                        **row,
                        "episode_rebuild_blocked": self.metadata_store.is_episode_source_query_blocked(source_name),
                    }
                )
            return {"success": True, "items": items, "count": len(items)}

        if act == "delete":
            source = str(kwargs.get("source", "") or "").strip()
            result = await self._execute_delete_action(
                mode="source",
                selector={"sources": [source]},
                requested_by=str(kwargs.get("requested_by", "") or "memory_source_admin"),
                reason=str(kwargs.get("reason", "") or "source_delete"),
            )
            await self._invalidate_import_manifest_for_sources(result)
            return result

        if act == "batch_delete":
            result = await self._execute_delete_action(
                mode="source",
                selector={"sources": list(kwargs.get("sources") or [])},
                requested_by=str(kwargs.get("requested_by", "") or "memory_source_admin"),
                reason=str(kwargs.get("reason", "") or "source_batch_delete"),
            )
            await self._invalidate_import_manifest_for_sources(result)
            return result

        return {"success": False, "error": f"不支持的 source action: {act}"}

    async def memory_episode_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        await self.initialize()
        assert self.metadata_store

        act = str(action or "").strip().lower()
        if act in {"query", "list"}:
            items = self.metadata_store.query_episodes(
                query=str(kwargs.get("query", "") or "").strip(),
                time_from=self._optional_float(kwargs.get("time_start", kwargs.get("time_from"))),
                time_to=self._optional_float(kwargs.get("time_end", kwargs.get("time_to"))),
                person=str(kwargs.get("person_id", "") or kwargs.get("person", "") or "").strip() or None,
                source=str(kwargs.get("source", "") or "").strip() or None,
                limit=max(1, int(kwargs.get("limit", 20) or 20)),
            )
            return {"success": True, "items": items, "count": len(items)}

        if act == "get":
            episode_id = str(kwargs.get("episode_id", "") or "").strip()
            if not episode_id:
                return {"success": False, "error": "episode_id 不能为空"}
            episode = self.metadata_store.get_episode_by_id(episode_id)
            if episode is None:
                return {"success": False, "error": "episode 不存在"}
            episode["paragraphs"] = self.metadata_store.get_episode_paragraphs(
                episode_id,
                limit=max(1, int(kwargs.get("paragraph_limit", 100) or 100)),
            )
            return {"success": True, "episode": episode}

        if act == "status":
            summary = self.metadata_store.get_episode_source_rebuild_summary(
                failed_limit=max(1, int(kwargs.get("limit", 20) or 20))
            )
            summary["pending_queue"] = self.metadata_store.query(
                "SELECT COUNT(*) AS c FROM episode_pending_paragraphs WHERE status IN ('pending', 'running', 'failed')"
            )[0]["c"]
            return {"success": True, **summary}

        if act == "rebuild":
            sources = self._tokens(kwargs.get("sources"))
            if not sources:
                source = str(kwargs.get("source", "") or "").strip()
                if source:
                    sources = [source]
            if not sources and bool(kwargs.get("all", False)):
                sources = self.metadata_store.list_episode_sources_for_rebuild()
                if not sources:
                    sources = [str(row.get("source", "") or "").strip() for row in self.metadata_store.get_all_sources()]
            if not sources:
                return {"success": False, "error": "未提供可重建的 source"}
            result = await self.rebuild_episodes_for_sources(sources)
            return {"success": len(result.get("failures", [])) == 0, **result}

        if act == "process_pending":
            result = await self.process_episode_pending_batch(
                limit=max(1, int(kwargs.get("limit", 20) or 20)),
                max_retry=max(1, int(kwargs.get("max_retry", 3) or 3)),
            )
            return {"success": True, **result}

        return {"success": False, "error": f"不支持的 episode action: {act}"}

    async def memory_profile_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        await self.initialize()
        assert self.metadata_store is not None
        assert self.person_profile_service is not None

        act = str(action or "").strip().lower()
        if act == "query":
            profile = await self._query_person_profile_with_feedback_refresh(
                person_id=str(kwargs.get("person_id", "") or "").strip(),
                person_keyword=str(kwargs.get("person_keyword", "") or kwargs.get("keyword", "") or "").strip(),
                limit=max(1, int(kwargs.get("limit", kwargs.get("top_k", 12)) or 12)),
                force_refresh=bool(kwargs.get("force_refresh", False)),
                source_note="sdk_memory_kernel.memory_profile_admin.query",
            )
            return profile if isinstance(profile, dict) else {"success": False, "error": "invalid profile payload"}

        if act == "evidence":
            return await self._profile_evidence_admin(
                person_id=str(kwargs.get("person_id", "") or "").strip(),
                person_keyword=str(kwargs.get("person_keyword", "") or kwargs.get("keyword", "") or "").strip(),
                limit=max(1, int(kwargs.get("limit", kwargs.get("top_k", 12)) or 12)),
                force_refresh=bool(kwargs.get("force_refresh", False)),
            )

        if act == "correct_evidence":
            return await self._profile_correct_evidence_admin(
                person_id=str(kwargs.get("person_id", "") or "").strip(),
                person_keyword=str(kwargs.get("person_keyword", "") or kwargs.get("keyword", "") or "").strip(),
                evidence_type=str(kwargs.get("evidence_type", "") or "").strip(),
                hash_value=str(kwargs.get("hash", "") or kwargs.get("hash_value", "") or "").strip(),
                requested_by=str(kwargs.get("requested_by", "") or "webui").strip(),
                reason=str(kwargs.get("reason", "") or "profile_evidence_correction").strip(),
                refresh=bool(kwargs.get("refresh", True)),
                limit=max(1, int(kwargs.get("limit", kwargs.get("top_k", 12)) or 12)),
            )

        if act == "status":
            summary = self.metadata_store.get_person_profile_refresh_summary(
                failed_limit=max(1, int(kwargs.get("limit", 20) or 20))
            )
            return {"success": True, **summary}

        if act == "process_pending":
            result = await self._process_feedback_profile_refresh_batch(
                limit=max(1, int(kwargs.get("limit", self._feedback_cfg_reconcile_batch_size()) or self._feedback_cfg_reconcile_batch_size()))
            )
            return {"success": True, **result}

        if act == "list":
            limit = max(1, int(kwargs.get("limit", 50) or 50))
            rows = self.metadata_store.query(
                """
                SELECT s.person_id, s.profile_version, s.profile_text, s.updated_at, s.expires_at, s.source_note
                FROM person_profile_snapshots s
                JOIN (
                    SELECT person_id, MAX(profile_version) AS max_version
                    FROM person_profile_snapshots
                    GROUP BY person_id
                ) latest
                  ON latest.person_id = s.person_id
                 AND latest.max_version = s.profile_version
                ORDER BY s.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            items = []
            for row in rows:
                person_id = str(row.get("person_id", "") or "").strip()
                override = self.metadata_store.get_person_profile_override(person_id)
                items.append(
                    {
                        "person_id": person_id,
                        "profile_version": int(row.get("profile_version", 0) or 0),
                        "profile_text": str(row.get("profile_text", "") or ""),
                        "updated_at": row.get("updated_at"),
                        "expires_at": row.get("expires_at"),
                        "source_note": str(row.get("source_note", "") or ""),
                        "has_manual_override": bool(override),
                        "manual_override": override,
                    }
                )
            return {"success": True, "items": items, "count": len(items)}

        if act == "set_override":
            person_id = str(kwargs.get("person_id", "") or "").strip()
            override = self.metadata_store.set_person_profile_override(
                person_id=person_id,
                override_text=str(kwargs.get("override_text", "") or kwargs.get("text", "") or ""),
                updated_by=str(kwargs.get("updated_by", "") or ""),
                source=str(kwargs.get("source", "") or "memory_profile_admin"),
            )
            return {"success": True, "override": override}

        if act == "delete_override":
            person_id = str(kwargs.get("person_id", "") or "").strip()
            deleted = self.metadata_store.delete_person_profile_override(person_id)
            return {"success": bool(deleted), "deleted": bool(deleted), "person_id": person_id}

        return {"success": False, "error": f"不支持的 profile action: {act}"}

    async def memory_feedback_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        await self.initialize()
        assert self.metadata_store is not None

        act = str(action or "").strip().lower()
        if act == "list":
            items = self.metadata_store.list_feedback_tasks(
                limit=max(1, int(kwargs.get("limit", 50) or 50)),
                statuses=self._tokens(kwargs.get("status") or kwargs.get("statuses")),
                rollback_statuses=self._tokens(kwargs.get("rollback_status") or kwargs.get("rollback_statuses")),
                query=str(kwargs.get("query", "") or "").strip(),
            )
            return {
                "success": True,
                "items": [self._build_feedback_task_summary(task) for task in items],
                "count": len(items),
            }

        if act == "get":
            task = self.metadata_store.get_feedback_task_by_id(int(kwargs.get("task_id", 0) or 0))
            if task is None:
                return {"success": False, "error": "反馈纠错任务不存在"}
            return {"success": True, "task": self._build_feedback_task_detail(task)}

        if act == "rollback":
            return await self._rollback_feedback_task(
                task_id=int(kwargs.get("task_id", 0) or 0),
                requested_by=str(kwargs.get("requested_by", "") or "").strip(),
                reason=str(kwargs.get("reason", "") or "").strip(),
            )

        return {"success": False, "error": f"不支持的 feedback action: {act}"}

    async def memory_runtime_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        await self.initialize()
        act = str(action or "").strip().lower()

        if act == "save":
            self._persist()
            return {"success": True, "saved": True, "data_dir": str(self.data_dir)}

        if act == "get_config":
            degraded = self._embedding_degraded_snapshot()
            backfill_counts = self._paragraph_vector_backfill_counts()
            rebuild_status = self._vector_rebuild_status()
            vector_pools_status = self._vector_pools_status()
            return {
                "success": True,
                "config": self.config,
                "data_dir": str(self.data_dir),
                "embedding_dimension": int(rebuild_status["embedding_dimension"]),
                "stored_vector_dimension": int(rebuild_status["stored_vector_dimension"]),
                "vector_rebuild_required": bool(rebuild_status["vector_rebuild_required"]),
                "vector_rebuild_message": str(rebuild_status["message"]),
                "embedding_fingerprint": rebuild_status.get("embedding_fingerprint") or {},
                "stored_embedding_fingerprint": rebuild_status.get("stored_embedding_fingerprint") or {},
                "embedding_fingerprint_status": str(rebuild_status.get("embedding_fingerprint_status") or "unknown"),
                "auto_save": bool(self._cfg("advanced.enable_auto_save", True)),
                "relation_vectors_enabled": bool(self.relation_vectors_enabled),
                "vector_pools": vector_pools_status,
                "vector_pools_ready": bool(vector_pools_status.get("ready", False)),
                "vector_pools_effective_mode": str(vector_pools_status.get("effective_mode", "single")),
                "runtime_ready": self.is_runtime_ready(),
                "embedding_degraded": bool(degraded.get("active", False)),
                "embedding_degraded_reason": str(degraded.get("reason", "") or ""),
                "embedding_degraded_since": degraded.get("since"),
                "embedding_last_check": degraded.get("last_check"),
                "paragraph_vector_backfill_pending": int(backfill_counts.get("pending", 0) or 0),
                "paragraph_vector_backfill_running": int(backfill_counts.get("running", 0) or 0),
                "paragraph_vector_backfill_failed": int(backfill_counts.get("failed", 0) or 0),
                "paragraph_vector_backfill_done": int(backfill_counts.get("done", 0) or 0),
            }

        if act in {"self_check", "refresh_self_check"}:
            report = await self._refresh_runtime_self_check(
                sample_text=str(kwargs.get("sample_text", "") or "A_Memorix runtime self check")
            )
            checked_at = float(report.get("checked_at") or time.time())
            dimension_mismatch = self._apply_self_check_dimension_result(report)
            if dimension_mismatch:
                self._set_embedding_degraded(active=True, reason=dimension_mismatch, checked_at=checked_at)
            elif bool(report.get("ok", False)):
                self._set_embedding_degraded(active=False, checked_at=checked_at)
            elif self._embedding_fallback_enabled():
                self._set_embedding_degraded(
                    active=True,
                    reason=str(report.get("message", "runtime self-check failed") or "runtime self-check failed"),
                    checked_at=checked_at,
                )
            return {"success": bool(report.get("ok", False)), "report": report}

        if act == "set_auto_save":
            enabled = bool(kwargs.get("enabled", False))
            self._set_cfg("advanced.enable_auto_save", enabled)
            return {"success": True, "auto_save": enabled}

        if act == "recover_embedding":
            result = await self._recover_embedding_once(
                sample_text=str(kwargs.get("sample_text", "") or "A_Memorix runtime self check")
            )
            result["embedding_degraded"] = self._is_embedding_degraded()
            result["embedding_state"] = self._embedding_degraded_snapshot()
            result["backfill_counts"] = self._paragraph_vector_backfill_counts()
            return result

        if act == "rebuild_all_vectors":
            include_relations = kwargs.get("include_relations")
            result = await self._rebuild_all_vectors(
                batch_size=self._optional_int(kwargs.get("batch_size")),
                include_relations=include_relations if isinstance(include_relations, bool) else None,
                dry_run=bool(kwargs.get("dry_run", False)),
            )
            result["embedding_degraded"] = self._is_embedding_degraded()
            result["backfill_counts"] = self._paragraph_vector_backfill_counts()
            return result

        if act == "paragraph_backfill_once":
            result = await self._run_paragraph_backfill_once(
                limit=self._optional_int(kwargs.get("limit")),
                max_retry=self._optional_int(kwargs.get("max_retry")),
                trigger="manual",
            )
            result["embedding_degraded"] = self._is_embedding_degraded()
            result["backfill_counts"] = self._paragraph_vector_backfill_counts()
            return result

        return {"success": False, "error": f"不支持的 runtime action: {act}"}

    async def memory_import_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._admin_handlers["import"].handle(action, **kwargs)

    async def memory_tuning_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._admin_handlers["tuning"].handle(action, **kwargs)

    async def memory_v5_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._admin_handlers["v5"].handle(action, **kwargs)

    async def memory_delete_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._admin_handlers["delete"].handle(action, **kwargs)

    async def memory_correction_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._admin_handlers["correction"].handle(action, **kwargs)

    async def memory_fuzzy_modify_admin(self, *, action: str, **kwargs) -> Dict[str, Any]:
        return await self._admin_handlers["correction"].handle(action, **kwargs)
    def get_import_task_manager(self) -> Optional[ImportTaskManager]:
        return self.import_task_manager

    def get_retrieval_tuning_manager(self) -> Optional[RetrievalTuningManager]:
        return self.retrieval_tuning_manager

    async def _aggregate_search(self, query: str, limit: int, request: KernelSearchRequest) -> Dict[str, Any]:
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        result = await self._search_execution_for_chat_scope(
            caller="sdk_memory_kernel.aggregate",
            query_type="search",
            query=query,
            top_k=limit,
            request=request,
            plugin_config=self._build_runtime_config(),
            enforce_chat_filter=False,
        )
        hits = [self._retrieval_result_hit(item) for item in result.results] if result.success else []
        hits = self._filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
        return {"success": result.success, "results": hits, "count": len(hits), "query_type": "search", "error": result.error}

    async def _aggregate_time(
        self,
        query: str,
        limit: int,
        request: KernelSearchRequest,
        time_window: _NormalizedSearchTimeWindow,
    ) -> Dict[str, Any]:
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        result = await self._search_execution_for_chat_scope(
            caller="sdk_memory_kernel.aggregate",
            query_type="time",
            query=query,
            top_k=limit,
            request=request,
            time_from=time_window.query_start,
            time_to=time_window.query_end,
            plugin_config=self._build_runtime_config(),
            enforce_chat_filter=False,
        )
        hits = [self._retrieval_result_hit(item) for item in result.results] if result.success else []
        hits = self._filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
        return {"success": result.success, "results": hits, "count": len(hits), "query_type": "time", "error": result.error}

    async def _aggregate_episode(
        self,
        query: str,
        limit: int,
        request: KernelSearchRequest,
        time_window: _NormalizedSearchTimeWindow,
    ) -> Dict[str, Any]:
        assert self.episode_retriever
        shared_chat_ids = tuple(str(item or "").strip() for item in request.shared_chat_ids if str(item or "").strip())
        rows = await self._episode_query_for_chat_scope(
            query=query,
            top_k=limit,
            time_from=time_window.numeric_start,
            time_to=time_window.numeric_end,
            person=request.person_id or None,
            chat_id=request.chat_id,
            shared_chat_ids=shared_chat_ids,
        )
        hits = self._filter_episode_hits([self._episode_hit(row) for row in rows])
        hits = self._filter_hits_by_chat_scope(hits, request.chat_id, shared_chat_ids)
        return {"success": True, "results": hits, "count": len(hits), "query_type": "episode"}

    def _persist(self, *, force_vectors: bool = False) -> None:
        rebuild_required = False if force_vectors else bool(
            self._vector_rebuild_status().get("vector_rebuild_required", False)
        )
        if self.vector_store is not None and not self._dual_vector_pools_enabled():
            if rebuild_required:
                logger.debug("检测到向量库需要重建，跳过向量库持久化以保留重建提示")
            else:
                self._save_vector_store(self.vector_store)
        if self._dual_vector_pools_enabled() and not rebuild_required:
            if self.paragraph_vector_store is not None:
                self._save_vector_store(self.paragraph_vector_store)
            if self.graph_vector_store is not None:
                self._save_vector_store(self.graph_vector_store)
        if self.graph_store is not None:
            self.graph_store.save()
        if self.sparse_index is not None and getattr(self.sparse_index.config, "enabled", False):
            self.sparse_index.ensure_loaded()

    async def _start_background_tasks(self) -> None:
        registrations = {
            "auto_save": self._auto_save_loop,
            "episode_pending": self._episode_pending_loop,
            "embedding_probe": self._embedding_probe_loop,
            "paragraph_vector_backfill": self._paragraph_vector_backfill_loop,
            "memory_maintenance": self._memory_maintenance_loop,
            "person_profile_refresh": self._person_profile_refresh_loop,
            "person_profile_refresh_queue": self._person_profile_refresh_queue_loop,
            "feedback_correction": self._feedback_correction_service._feedback_correction_loop,
            "feedback_correction_reconcile": self._feedback_correction_service._feedback_correction_reconcile_loop,
        }
        if self._should_start_dual_vector_auto_migration():
            registrations["dual_vector_auto_migration"] = self._dual_vector_auto_migration_loop
        await self._background_scheduler.start_all(registrations)

    def _ensure_background_task(
        self,
        name: str,
        factory: Callable[[], Coroutine[Any, Any, None]],
    ) -> None:
        self._background_scheduler.ensure_task(name, factory)

    async def _sleep_background(self, seconds: float) -> None:
        await self._background_scheduler.sleep(seconds)

    async def _dual_vector_auto_migration_loop(self) -> None:
        if not self._should_start_dual_vector_auto_migration():
            return

        self._vector_pool_manager.auto_migration_attempted = True
        started_at = time.time()
        self._vector_pool_manager._dual_vector_auto_migration_status.update(
            {
                "running": True,
                "attempted": True,
                "success": False,
                "stage": "initial_delay",
                "progress": self._normalize_dual_vector_auto_migration_progress(
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
            if self._background_scheduler.stopping or self._dual_vector_pools_enabled():
                finished_at = time.time()
                success = self._dual_vector_pools_enabled()
                progress = self._normalize_dual_vector_auto_migration_progress(
                    self._vector_pool_manager._dual_vector_auto_migration_status.get("progress"),
                    now=finished_at,
                    completed=True,
                    success=success,
                )
                self._vector_pool_manager._dual_vector_auto_migration_status.update(
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
                if self._background_scheduler.stopping or self._dual_vector_pools_enabled():
                    break
                if delay > 0:
                    self._update_dual_vector_auto_migration_stage("retry_delay", retry_index=index, delay_seconds=delay)
                    await self._sleep_background(delay)
                if self._vector_rebuild_lock.locked():
                    self._update_dual_vector_auto_migration_stage("waiting_rebuild_lock", retry_index=index)
                    if index == len(retry_delays) - 1:
                        result = {
                            "success": False,
                            "error": "vector_rebuild_running",
                            "detail": "已有向量重建任务正在运行",
                        }
                    continue
                self._update_dual_vector_auto_migration_stage("rebuild_start", retry_index=index)
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
                **dict(self._vector_pool_manager._dual_vector_auto_migration_status.get("progress") or {}),
                "result": result,
            }
            progress = self._normalize_dual_vector_auto_migration_progress(
                progress,
                now=finished_at,
                completed=True,
                success=success,
            )
            self._vector_pool_manager._dual_vector_auto_migration_status.update(
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
            progress = self._normalize_dual_vector_auto_migration_progress(
                self._vector_pool_manager._dual_vector_auto_migration_status.get("progress"),
                now=finished_at,
                completed=True,
                success=False,
            )
            self._vector_pool_manager._dual_vector_auto_migration_status.update(
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
            progress = self._normalize_dual_vector_auto_migration_progress(
                self._vector_pool_manager._dual_vector_auto_migration_status.get("progress"),
                now=finished_at,
                completed=True,
                success=False,
            )
            self._vector_pool_manager._dual_vector_auto_migration_status.update(
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

    async def _episode_pending_loop(self) -> None:
        try:
            while not self._background_scheduler.stopping:
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
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"episode_pending loop 异常: {exc}")

    async def _embedding_probe_loop(self) -> None:
        try:
            while not self._background_scheduler.stopping:
                await asyncio.sleep(self._embedding_probe_interval_seconds())
                if self._background_scheduler.stopping:
                    break
                startup_deferred = self._is_startup_self_check_deferred()
                if not self._embedding_fallback_enabled() and not startup_deferred:
                    continue
                if not self._is_embedding_degraded() and not startup_deferred:
                    continue
                try:
                    await self._recover_embedding_once()
                except Exception as exc:
                    logger.warning(f"embedding 恢复探测失败: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"embedding_probe loop 异常: {exc}")

    async def _paragraph_vector_backfill_loop(self) -> None:
        try:
            while not self._background_scheduler.stopping:
                await asyncio.sleep(self._paragraph_vector_backfill_interval_seconds())
                if self._background_scheduler.stopping:
                    break
                if not self._paragraph_vector_backfill_enabled():
                    continue
                if self._is_embedding_degraded():
                    continue
                await self._run_paragraph_backfill_once(
                    limit=self._paragraph_vector_backfill_batch_size(),
                    max_retry=self._paragraph_vector_backfill_max_retry(),
                    trigger="loop",
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"paragraph_vector_backfill loop 异常: {exc}")

    async def _person_profile_refresh_loop(self) -> None:
        try:
            while not self._background_scheduler.stopping:
                interval_minutes = max(1.0, float(self._cfg("person_profile.refresh_interval_minutes", 30) or 30))
                await asyncio.sleep(max(60.0, interval_minutes * 60.0))
                if self._background_scheduler.stopping:
                    break
                if not bool(self._cfg("person_profile.enabled", True)):
                    continue
                active_window_hours = max(1.0, float(self._cfg("person_profile.active_window_hours", 72.0) or 72.0))
                max_refresh = max(1, int(self._cfg("person_profile.max_refresh_per_cycle", 50) or 50))
                cutoff = time.time() - active_window_hours * 3600.0
                candidates = [
                    person_id
                    for person_id, seen_at in sorted(
                        self._active_person_timestamps.items(),
                        key=lambda item: item[1],
                        reverse=True,
                    )
                    if seen_at >= cutoff
                ][:max_refresh]
                for person_id in candidates:
                    try:
                        if self._has_pending_person_profile_refresh(person_id):
                            continue
                        await self.refresh_person_profile(person_id, limit=max(4, int(self._cfg("person_profile.top_k_evidence", 12) or 12)), mark_active=False)
                    except Exception as exc:
                        logger.warning(f"刷新人物画像失败: {exc}")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"person_profile_refresh loop 异常: {exc}")

    async def _person_profile_refresh_queue_loop(self) -> None:
        try:
            while not self._background_scheduler.stopping:
                await asyncio.sleep(self._person_profile_refresh_queue_interval_seconds())
                if self._background_scheduler.stopping:
                    break
                if not bool(self._cfg("person_profile.enabled", True)):
                    continue
                await self._process_person_profile_refresh_queue_batch(
                    limit=self._person_profile_refresh_queue_batch_size()
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"person_profile_refresh_queue loop 异常: {exc}")

    @staticmethod
    def _relation_status_is_inactive(status: Optional[Dict[str, Any]]) -> bool:
        if status is None:
            return True
        return bool(status.get("is_inactive"))

    def _load_paragraph_stale_marks(
        self,
        paragraph_hashes: Sequence[str],
    ) -> tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, Any]]]:
        if self.metadata_store is None:
            return {}, {}
        normalized = self._tokens(paragraph_hashes)
        if not normalized:
            return {}, {}
        marks_by_paragraph = self.metadata_store.get_paragraph_stale_relation_marks_batch(normalized)
        relation_hashes = self._tokens(
            mark.get("relation_hash", "")
            for marks in marks_by_paragraph.values()
            for mark in marks
            if isinstance(mark, dict)
        )
        status_map = self.metadata_store.get_relation_status_batch(relation_hashes) if relation_hashes else {}
        return marks_by_paragraph, status_map

    def _paragraph_hidden_by_stale_marks(
        self,
        paragraph_hash: str,
        *,
        marks_by_paragraph: Optional[Dict[str, List[Dict[str, Any]]]] = None,
        relation_status_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> bool:
        token = str(paragraph_hash or "").strip()
        if not token or self.metadata_store is None or not self._feedback_cfg_paragraph_hard_filter_enabled():
            return False

        marks_map = marks_by_paragraph if isinstance(marks_by_paragraph, dict) else {}
        status_map = relation_status_map if isinstance(relation_status_map, dict) else {}
        if not marks_map:
            marks_map, status_map = self._load_paragraph_stale_marks([token])
        elif not status_map:
            relation_hashes = self._tokens(
                mark.get("relation_hash", "")
                for mark in marks_map.get(token, [])
                if isinstance(mark, dict)
            )
            status_map = self.metadata_store.get_relation_status_batch(relation_hashes) if relation_hashes else {}

        for mark in marks_map.get(token, []):
            relation_hash = str((mark or {}).get("relation_hash", "") or "").strip()
            if not relation_hash:
                continue
            if self._relation_status_is_inactive(status_map.get(relation_hash)):
                return True
        return False

    def _filter_episode_hits(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.metadata_store is None or not self._feedback_cfg_episode_query_block_enabled():
            return hits
        filtered: List[Dict[str, Any]] = []
        for item in hits:
            if str(item.get("type", "") or "").strip() != "episode":
                filtered.append(item)
                continue
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            source = str(metadata.get("source", "") or item.get("source", "") or "").strip()
            if source and self.metadata_store.is_episode_source_query_blocked(source):
                continue
            filtered.append(item)
        return filtered

    def _filter_user_visible_hits(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._filter_current_effective_hits(self._filter_active_relation_hits(self._filter_episode_hits(hits)))

    def _filter_current_effective_hits(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.metadata_store is None:
            return self._filter_hits_by_memory_change_metadata(hits)

        if not self._current_effective_filter_store_check_needed(hits):
            return self._filter_hits_by_memory_change_metadata(hits)

        now = time.time()
        paragraph_hashes: List[str] = []
        relation_hashes: List[str] = []
        for item in hits:
            item_type = str(item.get("type", "") or "").strip()
            hash_value = str(item.get("hash", "") or "").strip()
            if item_type == "paragraph" and hash_value:
                paragraph_hashes.append(hash_value)
            elif item_type == "relation" and hash_value:
                relation_hashes.append(hash_value)

        paragraph_map = self.metadata_store.get_paragraphs_by_hashes(paragraph_hashes) if paragraph_hashes else {}
        relation_map = self.metadata_store.get_relations_by_hashes(relation_hashes) if relation_hashes else {}
        filtered: List[Dict[str, Any]] = []
        for item in hits:
            metadata = coerce_metadata_dict(item.get("metadata"))
            item_type = str(item.get("type", "") or "").strip()
            hash_value = str(item.get("hash", "") or "").strip()
            if hash_value:
                stored: Optional[Dict[str, Any]] = None
                if item_type == "paragraph":
                    stored = paragraph_map.get(hash_value)
                elif item_type == "relation":
                    stored = relation_map.get(hash_value)
                if stored is not None:
                    metadata = coerce_metadata_dict(stored.get("metadata"))
            memory_change = metadata.get("memory_change") if isinstance(metadata.get("memory_change"), dict) else {}
            valid_to = self._optional_float(memory_change.get("valid_to"))
            if valid_to is not None and valid_to <= now:
                continue
            next_item = dict(item)
            next_item["metadata"] = metadata
            filtered.append(next_item)
        return filtered

    def _current_effective_filter_store_check_needed(self, hits: List[Dict[str, Any]]) -> bool:
        if any(isinstance(coerce_metadata_dict(item.get("metadata")).get("memory_change"), dict) for item in hits):
            return True
        cache = self._current_effective_filter_cache
        now = time.time()
        if now - float(cache.get("checked_at", 0.0) or 0.0) < 60.0:
            return bool(cache.get("needed", False))
        needed = False
        try:
            plans = self.metadata_store.list_fuzzy_modify_plans(
                limit=1,
                statuses=["executing", "executed", "rolled_back", "rollback_failed"],
            )
            needed = bool(plans)
        except Exception as exc:
            logger.warning(f"检查当前有效记忆过滤状态失败，将保守启用回表过滤: {exc}")
            needed = True
        cache["checked_at"] = now
        cache["needed"] = needed
        return needed

    def _filter_hits_by_memory_change_metadata(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        now = time.time()
        filtered: List[Dict[str, Any]] = []
        for item in hits:
            metadata = coerce_metadata_dict(item.get("metadata"))
            memory_change = metadata.get("memory_change") if isinstance(metadata.get("memory_change"), dict) else {}
            valid_to = self._optional_float(memory_change.get("valid_to"))
            if valid_to is not None and valid_to <= now:
                continue
            next_item = dict(item)
            next_item["metadata"] = metadata
            filtered.append(next_item)
        return filtered

    def _resolve_feedback_related_person_ids(
        self,
        *,
        old_relation_rows: Sequence[Dict[str, Any]],
        corrected_relations: Sequence[Dict[str, Any]],
    ) -> List[str]:
        return self._feedback_correction_service._resolve_feedback_related_person_ids(
            old_relation_rows=old_relation_rows,
            corrected_relations=corrected_relations,
        )

    def _mark_feedback_stale_paragraphs(
        self,
        *,
        task_id: int,
        query_tool_id: str,
        relation_hashes: Sequence[str],
        reason: str,
    ) -> Dict[str, List[str]]:
        return self._feedback_correction_service._mark_feedback_stale_paragraphs(
            task_id=task_id,
            query_tool_id=query_tool_id,
            relation_hashes=relation_hashes,
            reason=reason,
        )

    def _enqueue_feedback_episode_rebuilds(
        self,
        *,
        paragraph_hashes: Sequence[str],
        session_id: str,
        include_correction_source: bool,
    ) -> List[str]:
        return self._feedback_correction_service._enqueue_feedback_episode_rebuilds(
            paragraph_hashes=paragraph_hashes,
            session_id=session_id,
            include_correction_source=include_correction_source,
        )

    def _enqueue_feedback_profile_refreshes(
        self,
        *,
        person_ids: Sequence[str],
        query_tool_id: str,
    ) -> List[str]:
        return self._feedback_correction_service._enqueue_feedback_profile_refreshes(
            person_ids=person_ids,
            query_tool_id=query_tool_id,
        )

    @staticmethod
    def _feedback_affected_counts(task: Dict[str, Any]) -> Dict[str, int]:
        return FeedbackCorrectionService._feedback_affected_counts(task)

    def _build_feedback_rollback_plan_summary(self, rollback_plan: Dict[str, Any]) -> Dict[str, Any]:
        return self._feedback_correction_service._build_feedback_rollback_plan_summary(rollback_plan)

    def _build_feedback_task_summary(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self._feedback_correction_service._build_feedback_task_summary(task)

    def _build_feedback_task_detail(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return self._feedback_correction_service._build_feedback_task_detail(task)

    def _soft_delete_feedback_correction_paragraphs(self, paragraph_hashes: Sequence[str]) -> Dict[str, Any]:
        return self._feedback_correction_service._soft_delete_feedback_correction_paragraphs(paragraph_hashes)

    async def _rollback_feedback_task(
        self,
        *,
        task_id: int,
        requested_by: str,
        reason: str,
    ) -> Dict[str, Any]:
        return await self._feedback_correction_service._rollback_feedback_task(
            task_id=task_id,
            requested_by=requested_by,
            reason=reason,
        )

    async def _process_feedback_profile_refresh_batch(
        self,
        *,
        limit: int,
        debounce_seconds: float = 0.0,
        retry_backoff_seconds: float = 0.0,
        max_retry: Optional[int] = None,
    ) -> Dict[str, Any]:
        return await self._feedback_correction_service._process_feedback_profile_refresh_batch(
            limit=limit,
            debounce_seconds=debounce_seconds,
            retry_backoff_seconds=retry_backoff_seconds,
            max_retry=max_retry,
        )

    async def _process_feedback_episode_rebuild_batch(self, *, limit: int) -> Dict[str, Any]:
        return await self._feedback_correction_service._process_feedback_episode_rebuild_batch(limit=limit)

    async def _feedback_correction_reconcile_loop(self) -> None:
        await self._feedback_correction_service._feedback_correction_reconcile_loop()

    @staticmethod
    def _coerce_datetime(value: Any) -> Optional[datetime]:
        return FeedbackCorrectionService._coerce_datetime(value)

    @staticmethod
    def _feedback_signal_tokens() -> tuple[str, ...]:
        return FeedbackCorrectionService._feedback_signal_tokens()

    @classmethod
    def _feedback_contains_signal(cls, text: str) -> bool:
        return FeedbackCorrectionService._feedback_contains_signal(text)

    @staticmethod
    def _feedback_noise(text: str) -> bool:
        return FeedbackCorrectionService._feedback_noise(text)

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

    def _feedback_cfg_enabled(self) -> bool:
        return self._feedback_config.enabled

    def _feedback_cfg_window_hours(self) -> float:
        return self._feedback_config.window_hours

    def _feedback_cfg_check_interval_seconds(self) -> float:
        return self._feedback_config.check_interval_seconds

    def _feedback_cfg_batch_size(self) -> int:
        return self._feedback_config.batch_size

    def _feedback_cfg_auto_apply_threshold(self) -> float:
        return self._feedback_config.auto_apply_threshold

    def _feedback_cfg_max_messages(self) -> int:
        return self._feedback_config.max_messages

    def _feedback_cfg_prefilter_enabled(self) -> bool:
        return self._feedback_config.prefilter_enabled

    def _feedback_cfg_paragraph_mark_enabled(self) -> bool:
        return self._feedback_config.paragraph_mark_enabled

    def _feedback_cfg_paragraph_hard_filter_enabled(self) -> bool:
        return self._feedback_config.paragraph_hard_filter_enabled

    def _feedback_cfg_profile_refresh_enabled(self) -> bool:
        return self._feedback_config.profile_refresh_enabled

    def _feedback_cfg_profile_force_refresh_on_read(self) -> bool:
        return self._feedback_config.profile_force_refresh_on_read

    def _feedback_cfg_episode_rebuild_enabled(self) -> bool:
        return self._feedback_config.episode_rebuild_enabled

    def _feedback_cfg_episode_query_block_enabled(self) -> bool:
        return self._feedback_config.episode_query_block_enabled

    def _feedback_cfg_reconcile_interval_seconds(self) -> float:
        return self._feedback_config.reconcile_interval_seconds

    def _feedback_cfg_reconcile_batch_size(self) -> int:
        return self._feedback_config.reconcile_batch_size

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
        return max(1.0, float(self._cfg("person_profile.refresh_queue_interval_seconds", 60) or 60))

    def _person_profile_refresh_queue_batch_size(self) -> int:
        return max(1, int(self._cfg("person_profile.refresh_queue_batch_size", 10) or 10))

    def _person_profile_refresh_debounce_seconds(self) -> float:
        return max(0.0, float(self._cfg("person_profile.refresh_debounce_seconds", 120) or 0))

    def _person_profile_refresh_retry_backoff_seconds(self) -> float:
        return max(0.0, float(self._cfg("person_profile.refresh_retry_backoff_seconds", 300) or 0))

    def _person_profile_refresh_max_retry(self) -> int:
        return max(0, int(self._cfg("person_profile.max_retry", 3) or 0))

    def _enqueue_person_profile_refresh(self, person_id: str, *, reason: str = "") -> bool:
        if self.metadata_store is None or not bool(self._cfg("person_profile.enabled", True)):
            return False
        payload = self.metadata_store.enqueue_person_profile_refresh(
            person_id=person_id,
            reason=str(reason or "").strip() or "memory_ingest",
        )
        return isinstance(payload, dict)

    def _has_pending_person_profile_refresh(self, person_id: str) -> bool:
        if self.metadata_store is None:
            return False
        request = self.metadata_store.get_person_profile_refresh_request(person_id)
        if not isinstance(request, dict):
            return False
        status = str(request.get("status", "") or "").strip().lower()
        if status in {"pending", "running"}:
            return True
        if status != "failed":
            return False
        return int(request.get("retry_count", 0) or 0) < self._person_profile_refresh_max_retry()

    async def _process_person_profile_refresh_queue_batch(self, *, limit: int) -> Dict[str, Any]:
        return await self._process_feedback_profile_refresh_batch(
            limit=limit,
            debounce_seconds=self._person_profile_refresh_debounce_seconds(),
            retry_backoff_seconds=self._person_profile_refresh_retry_backoff_seconds(),
            max_retry=self._person_profile_refresh_max_retry(),
        )

    def _feedback_cfg_window_label(self) -> str:
        return self._feedback_config.window_label

    async def enqueue_feedback_task(
        self,
        *,
        query_tool_id: str,
        session_id: str,
        query_timestamp: Any = None,
        structured_content: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return await self._feedback_correction_service.enqueue_feedback_task(
            query_tool_id=query_tool_id,
            session_id=session_id,
            query_timestamp=query_timestamp,
            structured_content=structured_content,
        )

    @staticmethod
    def _extract_feedback_messages(
        *,
        session_id: str,
        query_time: datetime,
        due_time: datetime,
        max_messages: int,
    ) -> List[str]:
        return FeedbackCorrectionService._extract_feedback_messages(
            session_id=session_id,
            query_time=query_time,
            due_time=due_time,
            max_messages=max_messages,
        )

    def _build_feedback_hit_briefs(self, hits: List[Dict[str, Any]], *, limit: int = 12) -> List[Dict[str, Any]]:
        return self._feedback_correction_service._build_feedback_hit_briefs(hits, limit=limit)

    @staticmethod
    def _should_invoke_feedback_classifier(feedback_messages: List[str]) -> bool:
        return FeedbackCorrectionService._should_invoke_feedback_classifier(feedback_messages)

    async def _classify_feedback(
        self,
        *,
        query_tool_id: str,
        query_text: str,
        hit_briefs: List[Dict[str, Any]],
        feedback_messages: List[str],
    ) -> Dict[str, Any]:
        return await self._feedback_correction_service._classify_feedback(
            query_tool_id=query_tool_id,
            query_text=query_text,
            hit_briefs=hit_briefs,
            feedback_messages=feedback_messages,
        )

    @staticmethod
    def _normalize_feedback_decision(
        payload: Dict[str, Any],
        *,
        hit_hashes: Sequence[str],
    ) -> Dict[str, Any]:
        return FeedbackCorrectionService._normalize_feedback_decision(payload, hit_hashes=hit_hashes)

    @staticmethod
    def _feedback_apply_result_status(apply_result: Dict[str, Any]) -> str:
        return FeedbackCorrectionService._feedback_apply_result_status(apply_result)

    def _restore_feedback_relations_from_snapshots(
        self,
        *,
        task_id: int,
        query_tool_id: str,
        relation_hashes: Sequence[str],
        snapshots: Dict[str, Dict[str, Any]],
        current_statuses: Optional[Dict[str, Dict[str, Any]]] = None,
        reason: str,
    ) -> Dict[str, List[str]]:
        return self._feedback_correction_service._restore_feedback_relations_from_snapshots(
            task_id=task_id,
            query_tool_id=query_tool_id,
            relation_hashes=relation_hashes,
            snapshots=snapshots,
            current_statuses=current_statuses,
            reason=reason,
        )

    async def _ingest_feedback_relations(
        self,
        *,
        query_tool_id: str,
        session_id: str,
        relation_hashes: List[str],
        corrected_relations: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        return await self._feedback_correction_service._ingest_feedback_relations(
            query_tool_id=query_tool_id,
            session_id=session_id,
            relation_hashes=relation_hashes,
            corrected_relations=corrected_relations,
        )

    async def _apply_feedback_decision(
        self,
        *,
        task_id: int,
        query_tool_id: str,
        session_id: str,
        decision: Dict[str, Any],
        hit_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        return await self._feedback_correction_service._apply_feedback_decision(
            task_id=task_id,
            query_tool_id=query_tool_id,
            session_id=session_id,
            decision=decision,
            hit_map=hit_map,
        )

    def _resolve_feedback_relation_hashes(
        self,
        *,
        target_hashes: Sequence[str],
        hit_map: Dict[str, Dict[str, Any]],
    ) -> List[str]:
        return self._feedback_correction_service._resolve_feedback_relation_hashes(
            target_hashes=target_hashes,
            hit_map=hit_map,
        )

    async def _process_feedback_task(self, task: Dict[str, Any]) -> None:
        await self._feedback_correction_service._process_feedback_task(task)

    async def _feedback_correction_loop(self) -> None:
        await self._feedback_correction_service._feedback_correction_loop()

    async def _memory_maintenance_loop(self) -> None:
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
            logger.warning(f"memory_maintenance loop 异常: {exc}")

    async def _run_memory_maintenance_cycle(self, *, interval_hours: float) -> None:
        assert self.graph_store is not None
        assert self.metadata_store is not None
        half_life = float(self._cfg("memory.half_life_hours", 24.0) or 24.0)
        if half_life > 0:
            factor = 0.5 ** (float(interval_hours) / half_life)
            self.graph_store.decay(factor)

        await self._process_freeze_and_prune()
        await self._orphan_gc_phase()
        self._last_maintenance_at = time.time()
        self._persist()

    async def _process_freeze_and_prune(self) -> None:
        assert self.metadata_store is not None
        assert self.graph_store is not None
        prune_threshold = max(0.0, float(self._cfg("memory.prune_threshold", 0.1) or 0.1))
        freeze_duration = max(0.0, float(self._cfg("memory.freeze_duration_hours", 24.0) or 24.0)) * 3600.0
        now = time.time()

        low_edges = self.graph_store.get_low_weight_edges(prune_threshold)
        hashes_to_freeze: List[str] = []
        edges_to_deactivate: List[tuple[str, str]] = []
        for src, tgt in low_edges:
            relation_hashes = list(self.graph_store.get_relation_hashes_for_edge(src, tgt))
            if not relation_hashes:
                continue
            statuses = self.metadata_store.get_relation_status_batch(relation_hashes)
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
            self.metadata_store.mark_relations_inactive(hashes_to_freeze, inactive_since=now)
            self.graph_store.deactivate_edges(edges_to_deactivate)

        cutoff = now - freeze_duration
        expired_hashes = self.metadata_store.get_prune_candidates(cutoff)
        if not expired_hashes:
            return
        relation_info = self.metadata_store.get_relations_subject_object_map(expired_hashes)
        operations = [(src, tgt, hash_value) for hash_value, (src, tgt) in relation_info.items()]
        if operations:
            self.graph_store.prune_relation_hashes(operations)
        deleted_hashes = [hash_value for hash_value in expired_hashes if hash_value in relation_info]
        if deleted_hashes:
            self.metadata_store.backup_and_delete_relations(deleted_hashes)
            self._delete_vectors_by_type(relation_hashes=deleted_hashes)

    async def _orphan_gc_phase(self) -> None:
        assert self.metadata_store is not None
        assert self.graph_store is not None
        orphan_cfg = self._cfg("memory.orphan", {}) or {}
        if not bool(orphan_cfg.get("enable_soft_delete", True)):
            return
        entity_retention = max(0.0, float(orphan_cfg.get("entity_retention_days", 7.0) or 7.0)) * 86400.0
        paragraph_retention = max(0.0, float(orphan_cfg.get("paragraph_retention_days", 7.0) or 7.0)) * 86400.0
        grace_period = max(0.0, float(orphan_cfg.get("sweep_grace_hours", 24.0) or 24.0)) * 3600.0

        isolated = self.graph_store.get_isolated_nodes(include_inactive=True)
        if isolated:
            entity_hashes = self.metadata_store.get_entity_gc_candidates(isolated, retention_seconds=entity_retention)
            if entity_hashes:
                self.metadata_store.mark_as_deleted(entity_hashes, "entity")

        paragraph_hashes = self.metadata_store.get_paragraph_gc_candidates(retention_seconds=paragraph_retention)
        if paragraph_hashes:
            self.metadata_store.mark_as_deleted(paragraph_hashes, "paragraph")

        dead_paragraphs = self.metadata_store.sweep_deleted_items("paragraph", grace_period)
        if dead_paragraphs:
            hashes = [str(item[0] or "").strip() for item in dead_paragraphs if item and str(item[0] or "").strip()]
            if hashes:
                self.metadata_store.physically_delete_paragraphs(hashes)
                self._delete_vectors_by_type(paragraph_hashes=hashes)

        dead_entities = self.metadata_store.sweep_deleted_items("entity", grace_period)
        if dead_entities:
            entity_hashes = [str(item[0] or "").strip() for item in dead_entities if item and str(item[0] or "").strip()]
            entity_names = [str(item[1] or "").strip() for item in dead_entities if item and str(item[1] or "").strip()]
            if entity_names:
                self.graph_store.delete_nodes(entity_names)
            if entity_hashes:
                self.metadata_store.physically_delete_entities(entity_hashes)
                self._delete_vectors_by_type(entity_hashes=entity_hashes)

    def _mark_person_active(self, person_id: str) -> None:
        token = str(person_id or "").strip()
        if not token:
            return
        self._active_person_timestamps[token] = time.time()

    def _serialize_graph(self, *, limit: int = 200) -> Dict[str, Any]:
        return self._graph_ops_service.serialize_graph(limit=limit)

    @staticmethod
    def _graph_search_match_rank(value: str, keyword: str) -> Optional[int]:
        return GraphOpsService._graph_search_match_rank(value, keyword)

    @classmethod
    def _pick_graph_search_match(cls, fields, keyword):
        return GraphOpsService._pick_graph_search_match(fields, keyword)

    def _search_graph(self, *, query: str, limit: int) -> Dict[str, Any]:
        return self._graph_ops_service.search_graph(query=query, limit=limit)

    @staticmethod
    def _dedupe_strings(values: Iterable[Any]) -> List[str]:
        return GraphOpsService._dedupe_strings(values)

    @staticmethod
    def _build_graph_edge_label(predicates: Sequence[str]) -> str:
        return GraphOpsService._build_graph_edge_label(predicates)

    @staticmethod
    def _trim_text(value: str, limit: int = 220) -> str:
        return GraphOpsService._trim_text(value, limit=limit)

    @staticmethod
    def _format_relation_text(subject: Any, predicate: Any, obj: Any) -> str:
        return GraphOpsService._format_relation_text(subject, predicate, obj)

    def _query_relation_rows_by_hashes(
        self,
        relation_hashes: Sequence[str],
        *,
        include_inactive: bool = False,
    ) -> List[Dict[str, Any]]:
        return self._graph_ops_service.query_relation_rows_by_hashes(relation_hashes, include_inactive=include_inactive)

    def _query_distinct_paragraph_hashes_for_relations(
        self,
        relation_hashes: Sequence[str],
        *,
        limit: Optional[int] = None,
    ) -> List[str]:
        return self._graph_ops_service.query_distinct_paragraph_hashes_for_relations(relation_hashes, limit=limit)

    def _load_paragraph_rows(self, paragraph_hashes: Sequence[str]) -> List[Dict[str, Any]]:
        return self._graph_ops_service.load_paragraph_rows(paragraph_hashes)

    def _resolve_graph_node_name(self, node_id: str) -> str:
        return self._graph_ops_service.resolve_graph_node_name(node_id)

    def _get_related_relation_rows_for_entity(self, entity_name: str, *, limit: int) -> List[Dict[str, Any]]:
        return self._graph_ops_service.get_related_relation_rows_for_entity(entity_name, limit=limit)

    def _build_relation_summary(self, row: Dict[str, Any], paragraph_hashes: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        return self._graph_ops_service.build_relation_summary(row, paragraph_hashes=paragraph_hashes)

    def _build_paragraph_summary(self, row: Dict[str, Any]) -> Dict[str, Any]:
        return self._graph_ops_service.build_paragraph_summary(row)

    @staticmethod
    def _evidence_entity_node_id(name: str) -> str:
        return GraphOpsService._evidence_entity_node_id(name)

    @staticmethod
    def _evidence_relation_node_id(hash_value: str) -> str:
        return GraphOpsService._evidence_relation_node_id(hash_value)

    @staticmethod
    def _evidence_paragraph_node_id(hash_value: str) -> str:
        return GraphOpsService._evidence_paragraph_node_id(hash_value)

    def _build_evidence_graph(
        self,
        *,
        focus_entities: Sequence[str],
        relation_rows: Sequence[Dict[str, Any]],
        paragraph_rows: Sequence[Dict[str, Any]],
        node_limit: int,
    ) -> Dict[str, Any]:
        return self._graph_ops_service.build_evidence_graph(
            focus_entities=focus_entities,
            relation_rows=relation_rows,
            paragraph_rows=paragraph_rows,
            node_limit=node_limit,
        )

    def _build_graph_node_detail(
        self,
        *,
        node_id: str,
        relation_limit: int,
        paragraph_limit: int,
        evidence_node_limit: int,
    ) -> Dict[str, Any]:
        return self._graph_ops_service.build_graph_node_detail(
            node_id=node_id,
            relation_limit=relation_limit,
            paragraph_limit=paragraph_limit,
            evidence_node_limit=evidence_node_limit,
        )

    def _build_graph_edge_detail(
        self,
        *,
        source: str,
        target: str,
        paragraph_limit: int,
        evidence_node_limit: int,
    ) -> Dict[str, Any]:
        return self._graph_ops_service.build_graph_edge_detail(
            source=source,
            target=target,
            paragraph_limit=paragraph_limit,
            evidence_node_limit=evidence_node_limit,
        )

    def _rebuild_graph_from_metadata(self) -> Dict[str, int]:
        return self._graph_ops_service.rebuild_graph_from_metadata()

    def _rename_node(self, old_name: str, new_name: str) -> Dict[str, Any]:
        return self._graph_ops_service.rename_node(old_name, new_name)

    def _update_edge_weight(
        self,
        *,
        relation_hash: str,
        subject: str,
        obj: str,
        weight: float,
    ) -> Dict[str, Any]:
        return self._graph_ops_service.update_edge_weight(
            relation_hash=relation_hash,
            subject=subject,
            obj=obj,
            weight=weight,
        )

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
    def _build_source(source_type: str, chat_id: str, person_ids: Sequence[str]) -> str:
        clean_type = str(source_type or "").strip() or "memory"
        if clean_type == "chat_summary" and chat_id:
            return f"chat_summary:{chat_id}"
        if clean_type == "person_fact" and person_ids:
            return f"person_fact:{person_ids[0]}"
        return f"{clean_type}:{chat_id}" if chat_id else clean_type

    @staticmethod
    def _chat_source(chat_id: str) -> Optional[str]:
        clean = str(chat_id or "").strip()
        return f"chat_summary:{clean}" if clean else None

    @classmethod
    def _chat_source_for_search_scope(cls, chat_id: str, shared_chat_ids: Sequence[str] = ()) -> Optional[str]:
        allowed_chat_ids = cls._resolve_allowed_chat_ids(chat_id, shared_chat_ids)
        if len(allowed_chat_ids) > 1:
            return None
        return cls._chat_source(chat_id)

    @staticmethod
    def _scoped_search_limit(limit: int, *, chat_id: str, shared_chat_ids: Sequence[str] = ()) -> int:
        safe_limit = max(1, int(limit or 5))
        allowed_chat_ids = SDKMemoryKernel._resolve_allowed_chat_ids(chat_id, shared_chat_ids)
        if not allowed_chat_ids:
            return safe_limit
        multiplier = max(5, len(allowed_chat_ids) * 5)
        return min(50, max(safe_limit, safe_limit * multiplier))

    @classmethod
    def _resolve_allowed_chat_ids(cls, chat_id: str, shared_chat_ids: Sequence[str] = ()) -> set[str]:
        allowed_chat_ids = {str(item or "").strip() for item in shared_chat_ids if str(item or "").strip()}
        clean_chat_id = str(chat_id or "").strip()
        if clean_chat_id:
            allowed_chat_ids.add(clean_chat_id)
        return allowed_chat_ids

    @staticmethod
    def _rank_score_from_item(item: Any) -> float:
        if isinstance(item, dict):
            raw_score = item.get("score", item.get("final_score", item.get("relevance", 0.0)))
        else:
            raw_score = getattr(item, "score", 0.0)
        try:
            return float(raw_score or 0.0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _dedupe_ranked_items(cls, items: Sequence[Any], *, limit: int) -> List[Any]:
        ranked: Dict[str, Any] = {}
        for index, item in enumerate(items):
            if isinstance(item, dict):
                item_hash = str(item.get("hash", "") or "").strip()
                item_type = str(item.get("type", "") or "").strip()
                content = str(item.get("content", "") or "").strip()
            else:
                item_hash = str(getattr(item, "hash_value", "") or "").strip()
                item_type = str(getattr(item, "result_type", "") or "").strip()
                content = str(getattr(item, "content", "") or "").strip()
            key = item_hash or f"{item_type}:{content}"
            if not key:
                key = f"item:{index}"
            current = ranked.get(key)
            if current is None or cls._rank_score_from_item(item) > cls._rank_score_from_item(current):
                ranked[key] = item
        return sorted(ranked.values(), key=cls._rank_score_from_item, reverse=True)[: max(1, int(limit or 5))]

    async def _search_execution_once(
        self,
        *,
        caller: str,
        query_type: str,
        query: str,
        top_k: int,
        request: KernelSearchRequest,
        plugin_config: dict,
        source: Optional[str],
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        enforce_chat_filter: bool,
    ) -> SearchExecutionResult:
        return await SearchExecutionService.execute(
            retriever=self.retriever,
            threshold_filter=self.threshold_filter,
            plugin_config=plugin_config,
            request=SearchExecutionRequest(
                caller=caller,
                stream_id=str(request.chat_id or "") or None,
                group_id=str(request.group_id or "") or None,
                user_id=str(request.user_id or "") or None,
                query_type=query_type,
                query=query,
                top_k=top_k,
                time_from=time_from,
                time_to=time_to,
                person=str(request.person_id or "") or None,
                source=source,
                use_threshold=True,
                enable_ppr=bool(self._cfg("retrieval.enable_ppr", True)),
            ),
            enforce_chat_filter=enforce_chat_filter,
            reinforce_access=True,
        )

    async def _search_execution_for_chat_scope(
        self,
        *,
        caller: str,
        query_type: str,
        query: str,
        top_k: int,
        request: KernelSearchRequest,
        plugin_config: dict,
        time_from: Optional[str] = None,
        time_to: Optional[str] = None,
        enforce_chat_filter: bool,
    ) -> SearchExecutionResult:
        allowed_chat_ids = self._resolve_allowed_chat_ids(request.chat_id, request.shared_chat_ids)
        if len(allowed_chat_ids) <= 1:
            search_source = self._chat_source_for_search_scope(request.chat_id, request.shared_chat_ids)
            return await self._search_execution_once(
                caller=caller,
                query_type=query_type,
                query=query,
                top_k=top_k,
                request=request,
                plugin_config=plugin_config,
                source=search_source,
                time_from=time_from,
                time_to=time_to,
                enforce_chat_filter=enforce_chat_filter,
            )

        scoped_results: List[RetrievalResult] = []
        errors: List[str] = []
        chat_filtered = False
        for chat_id in sorted(allowed_chat_ids):
            result = await self._search_execution_once(
                caller=caller,
                query_type=query_type,
                query=query,
                top_k=top_k,
                request=request,
                plugin_config=plugin_config,
                source=self._chat_source(chat_id),
                time_from=time_from,
                time_to=time_to,
                enforce_chat_filter=False,
            )
            if result.chat_filtered:
                chat_filtered = True
            if not result.success:
                if result.error:
                    errors.append(result.error)
                continue
            scoped_results.extend(result.results)

        merged_results = self._dedupe_ranked_items(scoped_results, limit=top_k)
        return SearchExecutionResult(
            success=bool(merged_results) or not errors,
            error="; ".join(dict.fromkeys(errors)),
            query_type=query_type,
            query=query,
            top_k=top_k,
            time_from=time_from,
            time_to=time_to,
            person=str(request.person_id or "") or None,
            source=None,
            results=merged_results,
            chat_filtered=chat_filtered and not merged_results,
        )

    async def _episode_query_for_chat_scope(
        self,
        *,
        query: str,
        top_k: int,
        time_from: Optional[float],
        time_to: Optional[float],
        person: Optional[str],
        chat_id: str,
        shared_chat_ids: Sequence[str] = (),
    ) -> List[Any]:
        assert self.episode_retriever is not None
        allowed_chat_ids = self._resolve_allowed_chat_ids(chat_id, shared_chat_ids)
        if len(allowed_chat_ids) <= 1:
            return await self.episode_retriever.query(
                query=query,
                top_k=top_k,
                time_from=time_from,
                time_to=time_to,
                person=person,
                source=self._chat_source_for_search_scope(chat_id, shared_chat_ids),
            )

        rows: List[Any] = []
        for allowed_chat_id in sorted(allowed_chat_ids):
            rows.extend(
                await self.episode_retriever.query(
                    query=query,
                    top_k=top_k,
                    time_from=time_from,
                    time_to=time_to,
                    person=person,
                    source=self._chat_source(allowed_chat_id),
                )
            )
        return self._dedupe_ranked_items(rows, limit=top_k)

    @classmethod
    def _paragraph_matches_chat_scope(cls, paragraph: Optional[Dict[str, Any]], allowed_chat_ids: set[str]) -> bool:
        if not paragraph:
            return False

        if not allowed_chat_ids:
            return True

        metadata = coerce_metadata_dict(paragraph.get("metadata"))
        if cls._metadata_chat_scope_ids(metadata) & allowed_chat_ids:
            return True

        source = str(paragraph.get("source", "") or metadata.get("source", "") or "").strip()
        return any(source == str(cls._chat_source(allowed_chat_id) or "") for allowed_chat_id in allowed_chat_ids)

    @classmethod
    def _hit_metadata_matches_chat_scope(cls, hit: Dict[str, Any], allowed_chat_ids: set[str]) -> Optional[bool]:
        if not allowed_chat_ids:
            return True

        metadata = coerce_metadata_dict(hit.get("metadata"))
        hit_type = str(hit.get("type", "") or "").strip()
        metadata_chat_ids = cls._metadata_chat_scope_ids(metadata)
        if metadata_chat_ids:
            if metadata_chat_ids & allowed_chat_ids:
                return True
            if hit_type in {"paragraph", "relation"}:
                return None
            return False

        source = str(metadata.get("source", "") or hit.get("source", "") or "").strip()
        chat_sources = {str(cls._chat_source(allowed_chat_id) or "") for allowed_chat_id in allowed_chat_ids}
        if hit_type == "episode":
            return source in chat_sources
        if source.startswith("chat_summary:"):
            return source in chat_sources
        return None

    @staticmethod
    def _extend_chat_scope_ids(tokens: set[str], value: Any) -> None:
        if isinstance(value, (list, tuple, set)):
            for item in value:
                SDKMemoryKernel._extend_chat_scope_ids(tokens, item)
            return

        token = str(value or "").strip()
        if token:
            tokens.add(token)

    @classmethod
    def _metadata_chat_scope_ids(cls, metadata: Dict[str, Any]) -> set[str]:
        tokens: set[str] = set()
        for key in ("chat_id", "session_id", "stream_id", "chat_ids", "session_ids", "stream_ids"):
            cls._extend_chat_scope_ids(tokens, metadata.get(key))
        return tokens

    def _filter_hits_by_chat_scope(
        self,
        hits: List[Dict[str, Any]],
        chat_id: str,
        shared_chat_ids: Sequence[str] = (),
    ) -> List[Dict[str, Any]]:
        allowed_chat_ids = self._resolve_allowed_chat_ids(chat_id, shared_chat_ids)
        if not allowed_chat_ids or self.metadata_store is None:
            return hits

        allowed_indexes: set[int] = set()
        unresolved_paragraph_hashes: List[str] = []
        unresolved_relation_hashes: List[str] = []
        pending_indexes: Dict[int, Dict[str, str]] = {}

        for index, item in enumerate(hits):
            hit = dict(item)
            hit_type = str(hit.get("type", "") or "").strip()
            metadata_decision = self._hit_metadata_matches_chat_scope(hit, allowed_chat_ids)
            if metadata_decision is True:
                allowed_indexes.add(index)
                continue
            if metadata_decision is False:
                continue

            hit_hash = str(hit.get("hash", "") or "").strip()
            if hit_type == "paragraph" and hit_hash:
                unresolved_paragraph_hashes.append(hit_hash)
                pending_indexes[index] = {"type": hit_type, "hash": hit_hash}
                continue
            if hit_type == "relation" and hit_hash:
                unresolved_relation_hashes.append(hit_hash)
                pending_indexes[index] = {"type": hit_type, "hash": hit_hash}

        paragraph_map = self.metadata_store.get_paragraphs_by_hashes(unresolved_paragraph_hashes)
        relation_paragraph_map = self.metadata_store.get_paragraphs_by_relation_hashes(unresolved_relation_hashes)
        for index, pending in pending_indexes.items():
            hit_hash = pending["hash"]
            if pending["type"] == "paragraph":
                if self._paragraph_matches_chat_scope(paragraph_map.get(hit_hash), allowed_chat_ids):
                    allowed_indexes.add(index)
                continue
            if any(
                self._paragraph_matches_chat_scope(paragraph, allowed_chat_ids)
                for paragraph in relation_paragraph_map.get(hit_hash, [])
            ):
                allowed_indexes.add(index)

        return [dict(hit) for index, hit in enumerate(hits) if index in allowed_indexes]

    def _filter_hits_by_retrieval_type_scope(
        self,
        hits: List[Dict[str, Any]],
        *,
        current_stream_id: str = "",
        current_group_id: str = "",
        current_user_id: str = "",
    ) -> List[Dict[str, Any]]:
        """按检索结果类型应用跨聊天流过滤，不改变本聊天流读取自身记忆。"""

        if not hits or not self._has_enabled_retrieval_type_filter():
            return hits
        current_context = self._current_retrieval_filter_context(
            stream_id=current_stream_id,
            group_id=current_group_id,
            user_id=current_user_id,
        )

        paragraph_hashes: List[str] = []
        relation_hashes: List[str] = []
        for item in hits:
            item_type = str(item.get("type", "") or "").strip()
            item_hash = str(item.get("hash", "") or "").strip()
            if not item_hash:
                continue
            if item_type == "paragraph":
                paragraph_hashes.append(item_hash)
            elif item_type == "relation":
                relation_hashes.append(item_hash)

        paragraph_map: Dict[str, Dict[str, Any]] = {}
        relation_paragraph_map: Dict[str, List[Dict[str, Any]]] = {}
        if self.metadata_store is not None:
            paragraph_map = self.metadata_store.get_paragraphs_by_hashes(paragraph_hashes)
            relation_paragraph_map = self.metadata_store.get_paragraphs_by_relation_hashes(relation_hashes)

        filtered: List[Dict[str, Any]] = []
        for item in hits:
            contexts = self._retrieval_filter_contexts_for_hit(
                item,
                paragraph_map=paragraph_map,
                relation_paragraph_map=relation_paragraph_map,
            )
            if any(
                self._retrieval_filter_context_is_current_source(context, current_context)
                for context in contexts
            ):
                filtered.append(dict(item))
                continue
            if any(self._retrieval_filter_context_allowed(context) for context in contexts):
                filtered.append(dict(item))
        return filtered

    def _has_enabled_retrieval_type_filter(self) -> bool:
        retrieval_config = self._retrieval_type_filter_root()
        if not retrieval_config:
            return False
        for kind in ("chat_stream", "chat_summary", "episode"):
            type_config = retrieval_config.get(kind)
            if isinstance(type_config, dict) and bool(type_config.get("enabled", False)):
                return True
        return False

    def _retrieval_type_filter_root(self) -> Dict[str, Any]:
        filter_config = self._cfg("filter", {}) or {}
        if not isinstance(filter_config, dict):
            return {}
        retrieval_config = filter_config.get("retrieval") or {}
        return retrieval_config if isinstance(retrieval_config, dict) else {}

    def _retrieval_type_filter_config(self, kind: str) -> Dict[str, Any]:
        retrieval_config = self._retrieval_type_filter_root()
        type_config = retrieval_config.get(str(kind or "").strip())
        return type_config if isinstance(type_config, dict) else {}

    def _retrieval_filter_contexts_for_hit(
        self,
        hit: Dict[str, Any],
        *,
        paragraph_map: Dict[str, Dict[str, Any]],
        relation_paragraph_map: Dict[str, List[Dict[str, Any]]],
    ) -> List[Dict[str, str]]:
        hit_type = str(hit.get("type", "") or "").strip()
        hit_hash = str(hit.get("hash", "") or "").strip()

        if hit_type == "paragraph" and hit_hash in paragraph_map:
            return [self._retrieval_filter_context_from_paragraph(paragraph_map[hit_hash])]

        if hit_type == "relation" and hit_hash in relation_paragraph_map:
            contexts = [
                self._retrieval_filter_context_from_paragraph(paragraph)
                for paragraph in relation_paragraph_map.get(hit_hash, [])
                if isinstance(paragraph, dict)
            ]
            if contexts:
                return contexts

        return [self._retrieval_filter_context_from_hit(hit)]

    def _retrieval_filter_context_from_hit(self, hit: Dict[str, Any]) -> Dict[str, str]:
        metadata = coerce_metadata_dict(hit.get("metadata"))
        source = str(metadata.get("source", "") or hit.get("source", "") or "").strip()
        source_type = str(metadata.get("source_type", "") or "").strip()
        hit_type = str(hit.get("type", "") or "").strip()
        stream_id = str(metadata.get("chat_id", "") or "").strip()
        if not stream_id:
            stream_id = self._source_stream_id(source)
        return self._retrieval_filter_context(
            kind=self._retrieval_filter_kind(hit_type=hit_type, source_type=source_type, source=source),
            stream_id=stream_id,
        )

    def _retrieval_filter_context_from_paragraph(self, paragraph: Dict[str, Any]) -> Dict[str, str]:
        metadata = coerce_metadata_dict(paragraph.get("metadata"))
        source = str(paragraph.get("source", "") or metadata.get("source", "") or "").strip()
        source_type = str(metadata.get("source_type", "") or "").strip()
        stream_id = str(metadata.get("chat_id", "") or "").strip()
        if not stream_id:
            stream_id = self._source_stream_id(source)
        return self._retrieval_filter_context(
            kind=self._retrieval_filter_kind(hit_type="paragraph", source_type=source_type, source=source),
            stream_id=stream_id,
        )

    @staticmethod
    def _retrieval_filter_kind(*, hit_type: str, source_type: str, source: str) -> str:
        if str(hit_type or "").strip() == "episode":
            return "episode"
        clean_source_type = str(source_type or "").strip()
        clean_source = str(source or "").strip()
        if clean_source_type == "chat_summary" or clean_source.startswith("chat_summary:"):
            return "chat_summary"
        if clean_source_type in {"chat_history", "chat_stream", "maibot.chat_history"}:
            return "chat_stream"
        if clean_source.startswith("chat_stream:") or clean_source.startswith("maibot.chat_history:"):
            return "chat_stream"
        return ""

    @staticmethod
    def _source_stream_id(source: str) -> str:
        token = str(source or "").strip()
        for prefix in ("chat_summary:", "chat_stream:", "maibot.chat_history:"):
            if token.startswith(prefix):
                return token[len(prefix):].strip()
        return ""

    def _retrieval_filter_context(self, *, kind: str, stream_id: str) -> Dict[str, str]:
        stream_token = str(stream_id or "").strip()
        group_id = ""
        user_id = ""
        if stream_token and self._session_info_port is not None:
            info = self._session_info_port.get_session_info(stream_token)
            if info is not None:
                group_id = info.group_id or ""
                user_id = info.user_id or ""
        return {
            "kind": str(kind or "").strip(),
            "stream_id": stream_token,
            "group_id": group_id,
            "user_id": user_id,
        }

    def _current_retrieval_filter_context(
        self,
        *,
        stream_id: str,
        group_id: str,
        user_id: str,
    ) -> Dict[str, str]:
        resolved_context = self._retrieval_filter_context(kind="", stream_id=stream_id)
        resolved_context["group_id"] = str(group_id or "").strip() or resolved_context["group_id"]
        resolved_context["user_id"] = str(user_id or "").strip() or resolved_context["user_id"]
        return resolved_context

    @staticmethod
    def _retrieval_filter_context_is_current_source(
        context: Dict[str, str],
        current_context: Dict[str, str],
    ) -> bool:
        current_stream_id = str(current_context.get("stream_id", "") or "").strip()
        source_stream_id = str(context.get("stream_id", "") or "").strip()
        if current_stream_id and source_stream_id and current_stream_id == source_stream_id:
            return True

        current_group_id = str(current_context.get("group_id", "") or "").strip()
        source_group_id = str(context.get("group_id", "") or "").strip()
        if current_group_id and source_group_id and current_group_id == source_group_id:
            return True

        current_user_id = str(current_context.get("user_id", "") or "").strip()
        source_user_id = str(context.get("user_id", "") or "").strip()
        current_is_private = bool(current_user_id) and not current_group_id
        source_is_private = bool(source_user_id) and not source_group_id
        return current_is_private and source_is_private and current_user_id == source_user_id

    def _retrieval_filter_context_allowed(self, context: Dict[str, str]) -> bool:
        kind = str(context.get("kind", "") or "").strip()
        if not kind:
            return True
        type_config = self._retrieval_type_filter_config(kind)
        if not type_config or not bool(type_config.get("enabled", False)):
            return True
        return self._chat_filter_config_allows(
            type_config,
            stream_id=str(context.get("stream_id", "") or "").strip(),
            group_id=str(context.get("group_id", "") or "").strip(),
            user_id=str(context.get("user_id", "") or "").strip(),
            default_when_empty=True,
        )

    @staticmethod
    def _resolve_knowledge_type(source_type: str) -> str:
        clean_type = str(source_type or "").strip().lower()
        if clean_type == "person_fact":
            return "factual"
        if clean_type == "chat_summary":
            return "narrative"
        return "mixed"

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

    @classmethod
    def _normalize_search_time_bound(cls, value: Any, *, is_end: bool) -> tuple[Optional[float], Optional[str]]:
        if value in {None, ""}:
            return None, None
        if isinstance(value, (int, float)):
            ts = float(value)
            return ts, format_timestamp(ts)

        text = str(value or "").strip()
        if not text:
            return None, None

        numeric = cls._optional_float(text)
        if numeric is not None:
            return numeric, format_timestamp(numeric)

        try:
            ts = parse_query_datetime_to_timestamp(text, is_end=is_end)
        except ValueError as exc:
            raise ValueError(f"时间参数错误: {exc}") from exc
        return ts, text

    @classmethod
    def _normalize_search_time_window(cls, time_start: Any, time_end: Any) -> _NormalizedSearchTimeWindow:
        numeric_start, query_start = cls._normalize_search_time_bound(time_start, is_end=False)
        numeric_end, query_end = cls._normalize_search_time_bound(time_end, is_end=True)
        if numeric_start is not None and numeric_end is not None and numeric_start > numeric_end:
            raise ValueError("时间参数错误: time_start 不能晚于 time_end")
        return _NormalizedSearchTimeWindow(
            numeric_start=numeric_start,
            numeric_end=numeric_end,
            query_start=query_start,
            query_end=query_end,
        )

    @staticmethod
    def _retrieval_result_hit(item: RetrievalResult) -> Dict[str, Any]:
        payload = item.to_dict()
        return {
            "hash": payload.get("hash", ""),
            "content": payload.get("content", ""),
            "score": payload.get("score", 0.0),
            "type": payload.get("type", ""),
            "source": payload.get("source", ""),
            "metadata": payload.get("metadata", {}) or {},
        }

    @staticmethod
    def _episode_hit(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "episode",
            "episode_id": str(row.get("episode_id", "") or ""),
            "title": str(row.get("title", "") or ""),
            "content": str(row.get("summary", "") or ""),
            "score": float(row.get("lexical_score", 0.0) or 0.0),
            "source": "episode",
            "metadata": {
                "participants": row.get("participants", []) or [],
                "keywords": row.get("keywords", []) or [],
                "source": row.get("source"),
                "event_time_start": row.get("event_time_start"),
                "event_time_end": row.get("event_time_end"),
            },
        }

    @staticmethod
    def _summary(hits: Sequence[Dict[str, Any]]) -> str:
        if not hits:
            return ""
        lines = []
        for index, item in enumerate(hits[:5], start=1):
            content = str(item.get("content", "") or "").strip().replace("\n", " ")
            lines.append(f"{index}. {(content[:120] + '...') if len(content) > 120 else content}")
        return "\n".join(lines)

    @staticmethod
    def _filter_hits(hits: List[Dict[str, Any]], person_id: str) -> List[Dict[str, Any]]:
        if not person_id:
            return hits
        filtered = []
        for item in hits:
            metadata = item.get("metadata", {}) or {}
            if person_id in (metadata.get("person_ids", []) or []):
                filtered.append(item)
                continue
            if person_id and person_id in str(item.get("content", "") or ""):
                filtered.append(item)
        return filtered or hits

    def _filter_active_relation_hits(self, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if self.metadata_store is None:
            return hits
        relation_hashes: List[str] = []
        paragraph_relation_cache: Dict[str, List[str]] = {}
        paragraph_hashes: List[str] = []
        seen_relation_hashes: set[str] = set()

        for item in hits:
            item_type = str(item.get("type", "") or "").strip()
            item_hash = str(item.get("hash", "") or "").strip()
            if item_type == "relation" and item_hash and item_hash not in seen_relation_hashes:
                seen_relation_hashes.add(item_hash)
                relation_hashes.append(item_hash)
                continue
            if item_type != "paragraph" or not item_hash:
                continue
            paragraph_hashes.append(item_hash)
            linked_relations = self.metadata_store.get_paragraph_relations(item_hash)
            linked_hashes: List[str] = []
            for relation in linked_relations:
                linked_hash = str(relation.get("hash", "") or "").strip()
                if not linked_hash or linked_hash in seen_relation_hashes:
                    continue
                seen_relation_hashes.add(linked_hash)
                relation_hashes.append(linked_hash)
                linked_hashes.append(linked_hash)
            if linked_hashes:
                paragraph_relation_cache[item_hash] = linked_hashes

        marks_by_paragraph, _ = self._load_paragraph_stale_marks(paragraph_hashes)
        stale_relation_hashes = self._tokens(
            mark.get("relation_hash", "")
            for marks in marks_by_paragraph.values()
            for mark in marks
            if isinstance(mark, dict)
        )
        for relation_hash in stale_relation_hashes:
            if relation_hash in seen_relation_hashes:
                continue
            seen_relation_hashes.add(relation_hash)
            relation_hashes.append(relation_hash)

        if not relation_hashes and not marks_by_paragraph:
            return hits

        status_map = self.metadata_store.get_relation_status_batch(relation_hashes)
        filtered: List[Dict[str, Any]] = []
        for item in hits:
            item_type = str(item.get("type", "") or "").strip()
            if item_type == "paragraph":
                paragraph_hash = str(item.get("hash", "") or "").strip()
                if self._paragraph_hidden_by_stale_marks(
                    paragraph_hash,
                    marks_by_paragraph=marks_by_paragraph,
                    relation_status_map=status_map,
                ):
                    continue
                linked_hashes = paragraph_relation_cache.get(paragraph_hash, [])
                if not linked_hashes:
                    filtered.append(item)
                    continue
                if any(
                    not bool((status_map.get(linked_hash) or {}).get("is_inactive"))
                    for linked_hash in linked_hashes
                ):
                    filtered.append(item)
                continue
            if item_type != "relation":
                filtered.append(item)
                continue
            hash_value = str(item.get("hash", "") or "").strip()
            status = status_map.get(hash_value) if isinstance(status_map, dict) else None
            if status is None:
                continue
            if bool(status.get("is_inactive")):
                continue
            filtered.append(item)
        return filtered

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

    def _memory_v5_status(self, *, target: str = "", limit: int = 50) -> Dict[str, Any]:
        return self._v5_memory_service.memory_v5_status(target=target, limit=limit)

    async def _preview_fuzzy_modify_action(self, **kwargs) -> Dict[str, Any]:
        return await self._fuzzy_modify_service.preview_fuzzy_modify_action(**kwargs)

    async def _execute_fuzzy_modify_action(self, **kwargs) -> Dict[str, Any]:
        return await self._fuzzy_modify_service.execute_fuzzy_modify_action(**kwargs)

    async def _rollback_fuzzy_modify_action(self, **kwargs) -> Dict[str, Any]:
        return await self._fuzzy_modify_service.rollback_fuzzy_modify_action(**kwargs)

    async def _collect_fuzzy_modify_candidates(self, **kwargs) -> List[Dict[str, Any]]:
        return await self._fuzzy_modify_service._collect_fuzzy_modify_candidates(**kwargs)

    def _is_fuzzy_modify_candidate_mutable(self, candidate: Dict[str, Any], raw_item: Dict[str, Any]) -> bool:
        return self._fuzzy_modify_service._is_fuzzy_modify_candidate_mutable(candidate, raw_item)

    async def _build_fuzzy_modify_llm_plan(self, **kwargs) -> Dict[str, Any]:
        return await self._fuzzy_modify_service._build_fuzzy_modify_llm_plan(**kwargs)

    def _normalize_fuzzy_modify_plan(self, payload: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        return self._fuzzy_modify_service._normalize_fuzzy_modify_plan(payload, **kwargs)

    def _normalize_fuzzy_modify_candidate(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return self._fuzzy_modify_service._normalize_fuzzy_modify_candidate(item)

    @staticmethod
    def _normalize_fuzzy_modify_relations(value: Any) -> List[Dict[str, Any]]:
        return FuzzyModifyService._normalize_fuzzy_modify_relations(value)

    def _build_fuzzy_modify_cascade_preview(self, *, operations: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        return self._fuzzy_modify_service._build_fuzzy_modify_cascade_preview(operations=operations)

    def _build_fuzzy_modify_paragraph_cascade(self, **kwargs) -> Dict[str, List[Dict[str, Any]]]:
        return self._fuzzy_modify_service._build_fuzzy_modify_paragraph_cascade(**kwargs)

    @staticmethod
    def _fuzzy_modify_stale_source_operation_id(*, plan_id: str, paragraph_hash: str, relation_hash: str) -> str:
        return FuzzyModifyService._fuzzy_modify_stale_source_operation_id(plan_id=plan_id, paragraph_hash=paragraph_hash, relation_hash=relation_hash)

    def _execute_fuzzy_modify_paragraph_cascade(self, **kwargs) -> Dict[str, Any]:
        return self._fuzzy_modify_service._execute_fuzzy_modify_paragraph_cascade(**kwargs)

    async def _apply_fuzzy_modify_plan(self, **kwargs) -> Dict[str, Any]:
        return await self._fuzzy_modify_service._apply_fuzzy_modify_plan(**kwargs)

    def _mark_fuzzy_modify_target_superseded(self, **kwargs) -> Dict[str, Any]:
        return self._fuzzy_modify_service._mark_fuzzy_modify_target_superseded(**kwargs)

    @staticmethod
    def _normalize_fuzzy_modify_scope(scope: str) -> str:
        return FuzzyModifyService._normalize_fuzzy_modify_scope(scope)

    def _fuzzy_modify_cfg_enabled(self) -> bool:
        return self._fuzzy_modify_config.enabled

    def _fuzzy_modify_cfg_auto_execute_enabled(self) -> bool:
        return self._fuzzy_modify_config.auto_execute_enabled

    def _fuzzy_modify_cfg_confirm_threshold(self) -> float:
        return self._fuzzy_modify_config.confirm_threshold

    def _fuzzy_modify_cfg_candidate_limit(self) -> int:
        return self._fuzzy_modify_config.candidate_limit

    def _fuzzy_modify_cfg_max_targets(self) -> int:
        return self._fuzzy_modify_config.max_targets

    def _fuzzy_modify_cfg_allow_global_scope(self) -> bool:
        return self._fuzzy_modify_config.allow_global_scope

    def _adjust_relation_confidence(self, hashes: List[str], *, delta: float) -> Dict[str, float]:
        return self._v5_memory_service.adjust_relation_confidence(hashes, delta=delta)

    def _apply_v5_relation_action(self, *, action: str, hashes: List[str], strength: float = 1.0) -> Dict[str, Any]:
        return self._v5_memory_service.apply_v5_relation_action(action=action, hashes=hashes, strength=strength)

    async def _ensure_vector_for_text(
        self,
        *,
        item_hash: str,
        text: str,
        vector_store: Optional[VectorStore] = None,
    ) -> bool:
        target_store = vector_store or self.vector_store
        if target_store is None or self.embedding_manager is None:
            return False
        token = str(item_hash or "").strip()
        content = str(text or "").strip()
        if not token or not content:
            return False
        embedding = await self.embedding_manager.encode([content])
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

    async def _ensure_relation_vector(self, relation: Dict[str, Any]) -> bool:
        if not bool(self.relation_vectors_enabled):
            return False
        relation_service = self.relation_write_service
        if relation_service is not None:
            result = await relation_service.ensure_relation_vector(
                hash_value=str(relation.get("hash", "") or ""),
                subject=str(relation.get("subject", "") or "").strip(),
                predicate=str(relation.get("predicate", "") or "").strip(),
                obj=str(relation.get("object", "") or "").strip(),
                typed_id=self._dual_vector_pools_enabled(),
            )
            return bool(result.vector_written or result.vector_already_exists)
        return await self._ensure_vector_for_text(
            item_hash=str(relation.get("hash", "") or ""),
            text=RelationWriteService.build_relation_vector_text(
                str(relation.get("subject", "") or "").strip(),
                str(relation.get("predicate", "") or "").strip(),
                str(relation.get("object", "") or "").strip(),
            ),
        )

    async def _ensure_paragraph_vector(self, paragraph: Dict[str, Any]) -> bool:
        return await self._ensure_vector_for_text(
            item_hash=str(paragraph.get("hash", "") or ""),
            text=str(paragraph.get("content", "") or ""),
            vector_store=self._paragraph_store(),
        )

    async def _ensure_entity_vector(self, entity: Dict[str, Any]) -> bool:
        if self._dual_vector_pools_enabled():
            return await self._ensure_vector_for_text(
                item_hash=self._graph_vector_id("entity", str(entity.get("hash", "") or "")),
                text=str(entity.get("name", "") or ""),
                vector_store=self._graph_vector_store(),
            )
        return await self._ensure_vector_for_text(
            item_hash=str(entity.get("hash", "") or ""),
            text=str(entity.get("name", "") or ""),
        )

    async def _restore_relation_hashes(
        self,
        hashes: List[str],
        *,
        payloads: Optional[Dict[str, Dict[str, Any]]] = None,
        rebuild_graph: bool = True,
        persist: bool = True,
    ) -> Dict[str, Any]:
        assert self.metadata_store
        restored: List[str] = []
        failures: List[Dict[str, str]] = []
        conn = self.metadata_store.get_connection()
        cursor = conn.cursor()
        payload_map = payloads or {}
        for hash_value in [str(item or "").strip() for item in hashes if str(item or "").strip()]:
            relation = self.metadata_store.restore_relation(hash_value)
            if relation is None:
                relation = self.metadata_store.get_relation(hash_value)
            if relation is None:
                failures.append({"hash": hash_value, "error": "relation 不存在"})
                continue
            payload = payload_map.get(hash_value) if isinstance(payload_map.get(hash_value), dict) else {}
            paragraph_hashes = self._tokens(payload.get("paragraph_hashes"))
            for paragraph_hash in paragraph_hashes:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO paragraph_relations (paragraph_hash, relation_hash)
                    VALUES (?, ?)
                    """,
                    (paragraph_hash, hash_value),
                )
            await self._ensure_relation_vector({**relation, "hash": hash_value})
            restored.append(hash_value)
        conn.commit()
        if restored and rebuild_graph:
            self._rebuild_graph_from_metadata()
        if restored and persist:
            self._persist()
        return {"restored_hashes": restored, "restored_count": len(restored), "failures": failures}

    @staticmethod
    def _profile_evidence_type_from_source(source: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        return ProfileEvidenceService._profile_evidence_type_from_source(source, metadata)

    @staticmethod
    def _profile_relation_content(relation: Dict[str, Any]) -> str:
        return ProfileEvidenceService._profile_relation_content(relation)

    def _build_profile_relation_evidence_item(self, relation: Dict[str, Any], *, index: int) -> Dict[str, Any]:
        return self._profile_evidence_service._build_profile_relation_evidence_item(relation, index=index)

    def _build_profile_paragraph_evidence_item(
        self,
        item: Dict[str, Any],
        *,
        index: int,
        fallback_hash: str = "",
    ) -> Dict[str, Any]:
        return self._profile_evidence_service._build_profile_paragraph_evidence_item(item, index=index, fallback_hash=fallback_hash)

    def _build_profile_evidence_items(self, profile: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self._profile_evidence_service._build_profile_evidence_items(profile)

    def _profile_evidence_response(self, profile: Dict[str, Any], *, requested_person_id: str, limit: int) -> Dict[str, Any]:
        return self._profile_evidence_service._profile_evidence_response(profile, requested_person_id=requested_person_id, limit=limit)

    async def _profile_evidence_admin(
        self,
        *,
        person_id: str = "",
        person_keyword: str = "",
        limit: int = 12,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        return await self._profile_evidence_service.profile_evidence_admin(
            person_id=person_id,
            person_keyword=person_keyword,
            limit=limit,
            force_refresh=force_refresh,
        )

    async def _profile_correct_evidence_admin(
        self,
        *,
        person_id: str = "",
        person_keyword: str = "",
        evidence_type: str,
        hash_value: str,
        requested_by: str = "webui",
        reason: str = "profile_evidence_correction",
        refresh: bool = True,
        limit: int = 12,
    ) -> Dict[str, Any]:
        return await self._profile_evidence_service.profile_correct_evidence_admin(
            person_id=person_id,
            person_keyword=person_keyword,
            evidence_type=evidence_type,
            hash_value=hash_value,
            requested_by=requested_by,
            reason=reason,
            refresh=refresh,
            limit=limit,
        )

    @staticmethod
    def _selector_dict(selector: Any) -> Dict[str, Any]:
        if isinstance(selector, dict):
            return dict(selector)
        if isinstance(selector, (list, tuple)):
            return {"items": list(selector)}
        token = str(selector or "").strip()
        return {"query": token} if token else {}

    def _resolve_paragraph_targets(self, selector: Any, *, include_deleted: bool = False) -> List[Dict[str, Any]]:
        return self._delete_service.resolve_paragraph_targets(selector, include_deleted=include_deleted)

    def _resolve_entity_targets(self, selector: Any, *, include_deleted: bool = False) -> List[Dict[str, Any]]:
        return self._delete_service.resolve_entity_targets(selector, include_deleted=include_deleted)

    def _resolve_source_targets(self, selector: Any) -> List[str]:
        raw = self._selector_dict(selector)
        return self._merge_tokens(raw.get("sources"), [raw.get("source")], [raw.get("query")], raw.get("items"))

    def _snapshot_relation_item(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self._delete_service.snapshot_relation_item(hash_value)

    def _snapshot_paragraph_item(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self._delete_service.snapshot_paragraph_item(hash_value)

    def _snapshot_entity_item(self, hash_value: str) -> Optional[Dict[str, Any]]:
        return self._delete_service.snapshot_entity_item(hash_value)

    def _relation_has_remaining_paragraphs(self, relation_hash: str, removing_hashes: Sequence[str]) -> bool:
        assert self.metadata_store
        excluded = [str(item or "").strip() for item in removing_hashes if str(item or "").strip()]
        conn = self.metadata_store.get_connection()
        cursor = conn.cursor()
        if excluded:
            placeholders = ",".join(["?"] * len(excluded))
            cursor.execute(
                f"""
                SELECT p.hash, p.metadata
                FROM paragraph_relations pr
                JOIN paragraphs p ON p.hash = pr.paragraph_hash
                WHERE pr.relation_hash = ?
                  AND pr.paragraph_hash NOT IN ({placeholders})
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                """,
                tuple([relation_hash] + excluded),
            )
        else:
            cursor.execute(
                """
                SELECT p.hash, p.metadata
                FROM paragraph_relations pr
                JOIN paragraphs p ON p.hash = pr.paragraph_hash
                WHERE pr.relation_hash = ?
                  AND (p.is_deleted IS NULL OR p.is_deleted = 0)
                """,
                (relation_hash,),
            )
        now = time.time()
        for row in cursor.fetchall():
            paragraph = self.metadata_store._row_to_dict(row, "paragraph")
            metadata = coerce_metadata_dict(paragraph.get("metadata"))
            memory_change = metadata.get("memory_change") if isinstance(metadata.get("memory_change"), dict) else {}
            valid_to = self._optional_float(memory_change.get("valid_to"))
            if valid_to is None or valid_to > now:
                return True
        return False

    def _build_delete_preview_item(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return self._delete_service.build_delete_preview_item(item)

    def _build_standard_delete_result(
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
        return self._delete_service.build_standard_delete_result(
            mode=mode,
            operation_id=operation_id,
            counts=counts,
            sources=sources,
            deleted_entity_count=deleted_entity_count,
            deleted_relation_count=deleted_relation_count,
            deleted_paragraph_count=deleted_paragraph_count,
            deleted_source_count=deleted_source_count,
            deleted_vector_count=deleted_vector_count,
            requested_source_count=requested_source_count,
            matched_source_count=matched_source_count,
            error=error,
        )

    async def _build_delete_plan(self, *, mode: str, selector: Any) -> Dict[str, Any]:
        return await self._delete_service.build_delete_plan(mode=mode, selector=selector)

    async def _preview_delete_action(self, *, mode: str, selector: Any) -> Dict[str, Any]:
        return await self._delete_service.preview_delete_action(mode=mode, selector=selector)

    async def _execute_delete_action(
        self,
        *,
        mode: str,
        selector: Any,
        requested_by: str = "",
        reason: str = "",
    ) -> Dict[str, Any]:
        return await self._delete_service.execute_delete_action(mode=mode, selector=selector, requested_by=requested_by, reason=reason)

    async def _invalidate_import_manifest_for_sources(self, result: Dict[str, Any]) -> None:
        if not isinstance(result, dict) or not result.get("success"):
            return
        manager = self.import_task_manager
        if manager is None:
            return
        sources = self._tokens(result.get("sources"))
        if not sources:
            return
        try:
            manifest_result = await manager.invalidate_manifest_for_sources(sources)
        except Exception as exc:
            logger.warning(f"删除来源后清理导入清单失败: sources={sources}, err={exc}")
            result["manifest_invalidation"] = {"success": False, "error": str(exc), "sources": sources}
            return
        result["manifest_invalidation"] = manifest_result

    async def _restore_delete_action(
        self,
        *,
        mode: str,
        selector: Any,
        operation_id: str = "",
        requested_by: str = "",
        reason: str = "",
    ) -> Dict[str, Any]:
        return await self._delete_service.restore_delete_action(mode=mode, selector=selector, operation_id=operation_id, requested_by=requested_by, reason=reason)

    async def _restore_delete_operation(self, operation: Dict[str, Any]) -> Dict[str, Any]:
        return await self._delete_service.restore_delete_operation(operation)

    async def _purge_deleted_memory(self, *, grace_hours: Optional[float], limit: int) -> Dict[str, Any]:
        return await self._delete_service.purge_deleted_memory(grace_hours=grace_hours, limit=limit)

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
