from __future__ import annotations

import json
import pickle
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from src.common.logger import get_logger
from src.A_memorix.core.runtime.config.vector_pool_config import VectorPoolConfig
from src.A_memorix.core.storage import VectorStore

logger = get_logger("a_memorix.services.vector_pool")


class VectorPoolManager:
    """向量池管理 — 双池/单池向量存储的生命周期协调。"""

    def __init__(
        self,
        *,
        config: VectorPoolConfig,
        data_dir: Path,
        embedding_dimension: int,
        embedding_manager: Any = None,
        vector_store: Optional[VectorStore] = None,
        paragraph_vector_store: Optional[VectorStore] = None,
        graph_vector_store: Optional[VectorStore] = None,
        metadata_store: Any = None,
        relation_vectors_enabled: bool = False,
    ) -> None:
        self._config = config
        self._data_dir = data_dir
        self._embedding_dimension = embedding_dimension
        self.embedding_manager = embedding_manager
        self.vector_store = vector_store
        self.paragraph_vector_store = paragraph_vector_store
        self.graph_vector_store = graph_vector_store
        self.metadata_store = metadata_store
        self.relation_vectors_enabled = relation_vectors_enabled
        self._dual_vector_pools_ready: bool = False
        self._dual_vector_auto_migration_attempted: bool = False
        self._dual_vector_auto_migration_status: Dict[str, Any] = {
            "running": False,
            "attempted": False,
            "success": False,
            "stage": "idle",
            "progress": {
                "total": 0,
                "processed": 0,
                "percent": 0.0,
                "elapsed_seconds": 0.0,
                "estimated_remaining_seconds": None,
            },
            "last_error": "",
            "started_at": None,
            "finished_at": None,
            "updated_at": None,
        }

    @property
    def config(self) -> VectorPoolConfig:
        return self._config

    @property
    def dual_pools_ready(self) -> bool:
        return self._dual_vector_pools_ready

    @dual_pools_ready.setter
    def dual_pools_ready(self, value: bool) -> None:
        self._dual_vector_pools_ready = value

    @property
    def dual_pools_enabled(self) -> bool:
        return self._config.config_enabled and self._dual_vector_pools_ready

    @property
    def auto_migration_status(self) -> Dict[str, Any]:
        return dict(self._dual_vector_auto_migration_status)

    @property
    def auto_migration_attempted(self) -> bool:
        return self._dual_vector_auto_migration_attempted

    @auto_migration_attempted.setter
    def auto_migration_attempted(self, value: bool) -> None:
        self._dual_vector_auto_migration_attempted = value

    # ── 路径方法 ──

    def vectors_root(self) -> Path:
        return self._data_dir / "vectors"

    def paragraph_vector_dir(self) -> Path:
        return self.vectors_root() / "paragraph"

    def graph_vector_dir(self) -> Path:
        return self.vectors_root() / "graph"

    def dual_vector_ready_manifest_path(self) -> Path:
        return self.vectors_root() / "dual_ready.json"

    # ── 向量存储工厂 ──

    def make_vector_store(self, data_dir: Path, *, dimension: Optional[int] = None) -> VectorStore:
        from src.A_memorix.core.storage import QuantizationType

        return VectorStore(
            dimension=max(1, int(dimension or self._embedding_dimension)),
            quantization_type=QuantizationType.INT8,
            data_dir=data_dir,
        )

    def save_vector_store(self, store: Optional[VectorStore]) -> None:
        if store is None:
            return
        store.save(embedding_fingerprint=self.current_embedding_fingerprint())

    # ── Manifest 读写 ──

    def read_dual_vector_ready_manifest(self) -> Optional[Dict[str, Any]]:
        path = self.dual_vector_ready_manifest_path()
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"读取双池 ready manifest 失败: {exc}")
            return None
        return payload if isinstance(payload, dict) else None

    def write_dual_vector_ready_manifest(
        self,
        *,
        stats: Dict[str, Dict[str, int]],
        migration_stats: Dict[str, Dict[str, int]],
    ) -> None:
        current_dimension = self.current_embedding_status_dimension()
        embedding_fingerprint = self.current_embedding_fingerprint(dimension=current_dimension)
        payload = {
            "status": "ready",
            "version": 1,
            "mode": "dual",
            "dimension": int(current_dimension),
            "created_at": time.time(),
            "paragraph_vectors": int(stats.get("paragraphs", {}).get("done", 0) or 0),
            "graph_vectors": int(stats.get("entities", {}).get("done", 0) or 0)
            + int(stats.get("relations", {}).get("done", 0) or 0),
            "stats": stats,
            "migration": migration_stats,
        }
        if embedding_fingerprint is not None:
            payload["embedding_fingerprint"] = embedding_fingerprint
        path = self.dual_vector_ready_manifest_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def remove_dual_vector_ready_manifest(self) -> None:
        try:
            self.dual_vector_ready_manifest_path().unlink(missing_ok=True)
        except Exception as exc:
            logger.warning(f"删除双池 ready manifest 失败: {exc}")

    def dual_vector_ready(self, *, expected_dimension: Optional[int] = None) -> bool:
        manifest = self.read_dual_vector_ready_manifest()
        if not manifest or manifest.get("status") != "ready":
            return False
        dimension = int(expected_dimension or self.current_embedding_status_dimension() or 0)
        manifest_dimension = int(manifest.get("dimension", 0) or 0)
        if dimension > 0 and manifest_dimension not in {0, dimension}:
            logger.warning(
                "双池 ready manifest 维度不匹配: "
                f"manifest={manifest_dimension}, expected={dimension}"
            )
            return False
        paragraph_count = int(manifest.get("paragraph_vectors", 0) or 0)
        graph_count = int(manifest.get("graph_vectors", 0) or 0)
        if paragraph_count < 0 or graph_count < 0:
            return False
        current_fingerprint = self.current_embedding_fingerprint()
        manifest_fingerprint = self.normalize_embedding_fingerprint(manifest.get("embedding_fingerprint"))
        if current_fingerprint is None or manifest_fingerprint is None:
            logger.warning("双池 ready manifest 缺少可校验 embedding 指纹，保持单池降级")
            return False
        if str(current_fingerprint.get("hash", "") or "") != str(manifest_fingerprint.get("hash", "") or ""):
            logger.warning(
                "双池 ready manifest embedding 指纹不匹配，保持单池降级: "
                f"manifest={manifest_fingerprint.get('hash', '')}, "
                f"current={current_fingerprint.get('hash', '')}"
            )
            return False
        return self.paragraph_vector_dir().exists() and self.graph_vector_dir().exists()

    def refresh_dual_vector_ready_manifest_from_stores(self) -> None:
        paragraph_count = int(getattr(self.paragraph_vector_store, "num_vectors", 0) or 0)
        graph_count = int(getattr(self.graph_vector_store, "num_vectors", 0) or 0)
        entity_count = graph_count
        relation_count = 0
        if self.metadata_store is not None:
            try:
                target_counts = self.count_vector_rebuild_targets()
                entity_count = min(graph_count, int(target_counts.get("entities", 0) or 0))
                relation_count = max(0, graph_count - entity_count)
            except Exception as exc:
                logger.warning(f"刷新双池 ready manifest 统计失败，使用向量池计数: {exc}")
        stats = {
            "paragraphs": {"done": paragraph_count, "failed": 0},
            "entities": {"done": entity_count, "failed": 0},
            "relations": {"done": relation_count, "failed": 0},
        }
        migration_stats = {
            "paragraphs": {"copied": 0, "encoded": 0, "missing": 0},
            "entities": {"copied": 0, "encoded": 0, "missing": 0},
            "relations": {"copied": 0, "encoded": 0, "missing": 0},
        }
        self.write_dual_vector_ready_manifest(stats=stats, migration_stats=migration_stats)

    # ── 构建目录管理 ──

    def prepare_dual_vector_build_dirs(self) -> tuple[Path, Path, Path]:
        build_root = self.vectors_root() / f"dual_build_{int(time.time() * 1000)}"
        if build_root.exists():
            shutil.rmtree(build_root, ignore_errors=True)
        paragraph_dir = build_root / "paragraph"
        graph_dir = build_root / "graph"
        paragraph_dir.mkdir(parents=True, exist_ok=True)
        graph_dir.mkdir(parents=True, exist_ok=True)
        return build_root, paragraph_dir, graph_dir

    def activate_dual_vector_build_dirs(self, build_root: Path) -> None:
        paragraph_src = build_root / "paragraph"
        graph_src = build_root / "graph"
        if not paragraph_src.exists() or not graph_src.exists():
            raise RuntimeError("dual vector build dirs missing")

        backup_root = self.vectors_root() / f"dual_backup_{int(time.time() * 1000)}"
        backup_paragraph = backup_root / "paragraph"
        backup_graph = backup_root / "graph"
        backup_root.mkdir(parents=True, exist_ok=True)
        paragraph_dst = self.paragraph_vector_dir()
        graph_dst = self.graph_vector_dir()
        try:
            if paragraph_dst.exists():
                shutil.move(str(paragraph_dst), str(backup_paragraph))
            if graph_dst.exists():
                shutil.move(str(graph_dst), str(backup_graph))
            shutil.move(str(paragraph_src), str(paragraph_dst))
            shutil.move(str(graph_src), str(graph_dst))
            shutil.rmtree(build_root, ignore_errors=True)
            shutil.rmtree(backup_root, ignore_errors=True)
        except Exception:
            if paragraph_dst.exists():
                shutil.rmtree(paragraph_dst, ignore_errors=True)
            if graph_dst.exists():
                shutil.rmtree(graph_dst, ignore_errors=True)
            if backup_paragraph.exists():
                shutil.move(str(backup_paragraph), str(paragraph_dst))
            if backup_graph.exists():
                shutil.move(str(backup_graph), str(graph_dst))
            raise

    def cleanup_stale_dual_vector_build_dirs(self) -> None:
        vectors_root = self.vectors_root()
        if not vectors_root.exists():
            return
        for child in vectors_root.iterdir():
            if child.is_dir() and child.name.startswith("dual_build_"):
                shutil.rmtree(child, ignore_errors=True)
            elif child.is_dir() and child.name.startswith("dual_backup_"):
                shutil.rmtree(child, ignore_errors=True)

    def drop_dual_build_root(self, build_root: Optional[Path]) -> None:
        if build_root is None:
            return
        try:
            shutil.rmtree(build_root, ignore_errors=True)
        except Exception as exc:
            logger.warning(f"清理双池临时构建目录失败: {exc}")

    def clear_legacy_single_vector_files_after_dual_ready(self) -> None:
        root = self.vectors_root()
        for filename in ("vectors.bin", "vectors_ids.bin", "vectors.index", "vectors_metadata.pkl"):
            try:
                (root / filename).unlink(missing_ok=True)
            except Exception as exc:
                logger.warning(f"清理旧单池向量文件失败: file={filename}, error={exc}")
        if self.vector_store is not None:
            self.vector_store = self.make_vector_store(root)

    # ── Embedding 指纹 / 维度 ──

    def current_embedding_status_dimension(self) -> int:
        manager = self.embedding_manager
        getter = getattr(manager, "get_requested_dimension", None)
        if callable(getter):
            try:
                requested_dimension = int(getter())
            except Exception:
                requested_dimension = 0
            if requested_dimension > 0:
                return requested_dimension
        try:
            default_dimension = int(getattr(manager, "default_dimension", 0) or 0)
        except Exception:
            default_dimension = 0
        if default_dimension > 0:
            return default_dimension
        return max(1, self._embedding_dimension)

    @staticmethod
    def normalize_embedding_fingerprint(value: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(value, dict):
            return None
        hash_value = str(value.get("hash", "") or "").strip()
        if not hash_value:
            return None
        payload = dict(value)
        payload["hash"] = hash_value
        return payload

    def current_embedding_fingerprint(self, *, dimension: Optional[int] = None) -> Optional[Dict[str, Any]]:
        manager = self.embedding_manager
        getter = getattr(manager, "get_embedding_fingerprint", None)
        if not callable(getter):
            return None
        try:
            effective_dimension = int(dimension or self.current_embedding_status_dimension())
            return self.normalize_embedding_fingerprint(getter(dimension=effective_dimension))
        except Exception as exc:
            logger.warning(f"生成 embedding 指纹失败: {exc}")
            return None

    def stored_embedding_fingerprint(self, store: Optional[VectorStore] = None) -> Optional[Dict[str, Any]]:
        ready_manifest = (
            self.read_dual_vector_ready_manifest()
            if store is None and self._config.config_enabled
            else None
        )
        if ready_manifest is not None:
            manifest_fingerprint = self.normalize_embedding_fingerprint(
                ready_manifest.get("embedding_fingerprint")
            )
            if manifest_fingerprint is not None:
                return manifest_fingerprint

        vector_dir = Path(store.data_dir) if store is not None and store.data_dir is not None else self.vectors_root()
        meta_path = vector_dir / "vectors_metadata.pkl"
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "rb") as handle:
                meta = pickle.load(handle)
        except Exception as exc:
            logger.warning(f"读取向量指纹元数据失败: {exc}")
            return None
        if not isinstance(meta, dict):
            return None
        return self.normalize_embedding_fingerprint(meta.get("embedding_fingerprint"))

    def stored_vector_dimension(self, store: Optional[VectorStore] = None) -> Optional[int]:
        ready_manifest = (
            self.read_dual_vector_ready_manifest()
            if store is None and self._config.config_enabled
            else None
        )
        if ready_manifest is not None:
            try:
                manifest_dimension = int(ready_manifest.get("dimension") or 0)
            except Exception:
                manifest_dimension = 0
            if manifest_dimension > 0:
                return manifest_dimension
        vector_dir = Path(store.data_dir) if store is not None and store.data_dir is not None else self.vectors_root()
        meta_path = vector_dir / "vectors_metadata.pkl"
        if not meta_path.exists():
            return None
        try:
            with open(meta_path, "rb") as handle:
                meta = pickle.load(handle)
        except Exception as exc:
            logger.warning(f"读取向量元数据失败，将回退到 runtime self-check: {exc}")
            return None
        try:
            value = int(meta.get("dimension") or 0)
        except Exception:
            return None
        return value if value > 0 else None

    def stamp_missing_embedding_fingerprint_if_dimension_matches(self, store: Optional[VectorStore]) -> bool:
        if store is None:
            return False
        stored_dimension = self.stored_vector_dimension(store)
        current_dimension = self.current_embedding_status_dimension()
        if stored_dimension is None or int(stored_dimension) != int(current_dimension):
            return False
        current_fingerprint = self.current_embedding_fingerprint(dimension=current_dimension)
        if current_fingerprint is None:
            return False
        stored_fingerprint = self.stored_embedding_fingerprint(store)
        if stored_fingerprint is not None:
            return False
        store.save(embedding_fingerprint=current_fingerprint)
        logger.warning("旧向量库缺少 embedding 指纹且维度匹配，已写入当前模型指纹以复用旧向量")
        stamped_fingerprint = self.stored_embedding_fingerprint(store)
        return (
            stamped_fingerprint is not None
            and str(stamped_fingerprint.get("hash", "") or "") == str(current_fingerprint.get("hash", "") or "")
        )

    @staticmethod
    def embedding_fingerprint_status(
        current: Optional[Dict[str, Any]],
        stored: Optional[Dict[str, Any]],
        *,
        has_stored_vectors: bool,
    ) -> str:
        if not has_stored_vectors:
            return "none"
        if current is None:
            return "unknown"
        if stored is None:
            return "missing"
        return "matched" if str(current.get("hash", "")) == str(stored.get("hash", "")) else "mismatched"

    def stored_vectors_compatible_with_current_embedding(self, store: Optional[VectorStore] = None) -> bool:
        current = self.current_embedding_fingerprint()
        stored = self.stored_embedding_fingerprint(store)
        if current is None:
            return False
        if stored is None:
            stamped = self.stamp_missing_embedding_fingerprint_if_dimension_matches(store or self.vector_store)
            if not stamped:
                return False
            stored = self.stored_embedding_fingerprint(store)
            if stored is None:
                return False
        return str(current.get("hash", "") or "") == str(stored.get("hash", "") or "")

    @staticmethod
    def vector_mismatch_error(*, stored_dimension: int, detected_dimension: int) -> str:
        return (
            "检测到现有向量库与当前 embedding 输出维度不一致："
            f"stored={stored_dimension}, encoded={detected_dimension}。"
            " 当前版本不会兼容 hash 时代或其他维度的旧向量，请改回原 embedding 配置，"
            "或执行重嵌入/重建向量。"
        )

    def vector_rebuild_status(self, *, vector_rebuild_lock_locked: bool = False, vector_persist_blocked: bool = False, vector_rebuild_source_dimension: Optional[int] = None) -> Dict[str, Any]:
        if self.vector_store is not None and not vector_rebuild_lock_locked:
            self.stamp_missing_embedding_fingerprint_if_dimension_matches(self.vector_store)
        stored_dimension = self.stored_vector_dimension()
        if vector_persist_blocked and vector_rebuild_source_dimension is not None:
            stored_dimension = int(vector_rebuild_source_dimension)
        current_dimension = self.current_embedding_status_dimension()
        dimension_rebuild_required = stored_dimension is not None and stored_dimension != current_dimension
        current_fingerprint = self.current_embedding_fingerprint()
        stored_fingerprint = self.stored_embedding_fingerprint()
        fingerprint_status = self.embedding_fingerprint_status(
            current_fingerprint,
            stored_fingerprint,
            has_stored_vectors=stored_dimension is not None,
        )
        fingerprint_rebuild_required = fingerprint_status in {"missing", "mismatched"}
        rebuild_required = dimension_rebuild_required or fingerprint_rebuild_required
        if dimension_rebuild_required:
            message = self.vector_mismatch_error(
                stored_dimension=int(stored_dimension or 0),
                detected_dimension=current_dimension,
            )
        elif fingerprint_status == "mismatched":
            message = "检测到 embedding 模型指纹与现有向量库不一致，请重建向量。"
        elif fingerprint_status == "missing":
            message = "现有向量库缺少 embedding 模型指纹，无法确认模型一致性，建议重建向量。"
        elif fingerprint_status == "unknown":
            message = "当前 embedding 模型指纹不可用，无法确认向量库模型一致性。"
        else:
            message = ""
        return {
            "stored_vector_dimension": int(stored_dimension or 0),
            "embedding_dimension": current_dimension,
            "vector_rebuild_required": bool(rebuild_required),
            "fingerprint_status": fingerprint_status,
            "fingerprint_rebuild_required": fingerprint_rebuild_required,
            "message": message,
            "embedding_fingerprint": current_fingerprint or {},
            "stored_embedding_fingerprint": stored_fingerprint or {},
            "embedding_fingerprint_status": fingerprint_status,
        }

    # ── 双池加载 / 恢复 ──

    def reload_dual_vector_stores_from_disk(self) -> bool:
        current_dimension = self.current_embedding_status_dimension()
        if not self.dual_vector_ready(expected_dimension=current_dimension):
            self.try_recover_dual_ready_manifest()
        if not self.dual_vector_ready(expected_dimension=current_dimension):
            self.paragraph_vector_store = self.make_vector_store(self.paragraph_vector_dir())
            self.graph_vector_store = self.make_vector_store(self.graph_vector_dir())
            self._dual_vector_pools_ready = False
            return False
        try:
            paragraph_store = self.make_vector_store(self.paragraph_vector_dir())
            graph_store = self.make_vector_store(self.graph_vector_dir())
            if paragraph_store.has_data():
                paragraph_store.load()
                paragraph_store.warmup_index(force_train=True)
            if graph_store.has_data():
                graph_store.load()
                graph_store.warmup_index(force_train=True)
        except Exception as exc:
            logger.warning(f"加载双池向量失败，将暂时回退单池: {exc}")
            self._dual_vector_pools_ready = False
            return False
        self.paragraph_vector_store = paragraph_store
        self.graph_vector_store = graph_store
        self._dual_vector_pools_ready = True
        return True

    def try_recover_dual_ready_manifest(self) -> bool:
        if not self._config.config_enabled or self.metadata_store is None:
            return False
        if self.dual_vector_ready_manifest_path().exists():
            return False
        paragraph_dir = self.paragraph_vector_dir()
        graph_dir = self.graph_vector_dir()
        if not paragraph_dir.exists() or not graph_dir.exists():
            return False
        paragraph_store = self.make_vector_store(paragraph_dir)
        graph_store = self.make_vector_store(graph_dir)
        if not paragraph_store.has_data() or not graph_store.has_data():
            return False
        try:
            if paragraph_store.has_data():
                paragraph_store.load()
            if graph_store.has_data():
                graph_store.load()
        except Exception as exc:
            logger.warning(f"双池 ready manifest 自愈失败，加载向量池异常: {exc}")
            return False

        if (
            not self.stored_vectors_compatible_with_current_embedding(paragraph_store)
            or not self.stored_vectors_compatible_with_current_embedding(graph_store)
        ):
            logger.warning("双池 ready manifest 缺失且向量池指纹无法确认或不匹配，保持单池降级")
            return False

        counts = self.count_vector_rebuild_targets()
        expected_paragraphs = int(counts.get("paragraphs", 0) or 0)
        expected_graph = int(counts.get("entities", 0) or 0)
        if bool(self.relation_vectors_enabled):
            expected_graph += int(counts.get("relations", 0) or 0)
        if paragraph_store.num_vectors != expected_paragraphs or graph_store.num_vectors != expected_graph:
            logger.warning(
                "双池 ready manifest 缺失且向量数量不匹配，保持单池降级: "
                f"paragraph={paragraph_store.num_vectors}/{expected_paragraphs}, "
                f"graph={graph_store.num_vectors}/{expected_graph}"
            )
            return False

        stats = {
            "paragraphs": {"done": expected_paragraphs, "failed": 0},
            "entities": {"done": int(counts.get("entities", 0) or 0), "failed": 0},
            "relations": {"done": int(counts.get("relations", 0) or 0) if bool(self.relation_vectors_enabled) else 0, "failed": 0},
        }
        migration_stats = {
            "paragraphs": {"copied": 0, "encoded": 0, "missing": 0},
            "entities": {"copied": 0, "encoded": 0, "missing": 0},
            "relations": {"copied": 0, "encoded": 0, "missing": 0},
        }
        self.write_dual_vector_ready_manifest(stats=stats, migration_stats=migration_stats)
        logger.warning("检测到双池目录完整但 ready manifest 缺失，已自动重建 manifest")
        return True

    # ── 向量池查询 ──

    @staticmethod
    def graph_vector_id(item_type: str, hash_value: str) -> str:
        return f"{str(item_type or '').strip()}:{str(hash_value or '').strip()}"

    def paragraph_store(self) -> Optional[VectorStore]:
        if self.dual_pools_enabled:
            return self.paragraph_vector_store or self.vector_store
        return self.vector_store

    def graph_vector_store_resolved(self) -> Optional[VectorStore]:
        if self.dual_pools_enabled:
            return self.graph_vector_store or self.vector_store
        return self.vector_store

    def delete_vectors_by_type(
        self,
        *,
        paragraph_hashes: Sequence[str] = (),
        entity_hashes: Sequence[str] = (),
        relation_hashes: Sequence[str] = (),
        merge_tokens_fn: Any = None,
    ) -> int:
        if merge_tokens_fn is None:
            return 0
        deleted = 0
        legacy_ids = merge_tokens_fn(paragraph_hashes, entity_hashes, relation_hashes)
        if self.vector_store is not None and legacy_ids:
            deleted += int(self.vector_store.delete(legacy_ids) or 0)
        if not self.dual_pools_enabled:
            return deleted
        paragraph_ids = merge_tokens_fn(paragraph_hashes)
        if self.paragraph_vector_store is not None and paragraph_ids:
            deleted += int(self.paragraph_vector_store.delete(paragraph_ids) or 0)
        graph_ids = [
            self.graph_vector_id("entity", hash_value)
            for hash_value in merge_tokens_fn(entity_hashes)
        ]
        graph_ids.extend(
            self.graph_vector_id("relation", hash_value)
            for hash_value in merge_tokens_fn(relation_hashes)
        )
        if self.graph_vector_store is not None and graph_ids:
            deleted += int(self.graph_vector_store.delete(graph_ids) or 0)
        return deleted

    # ── 状态快照 ──

    @staticmethod
    def vector_store_snapshot(store: Optional[VectorStore]) -> Dict[str, Any]:
        if store is None:
            return {
                "available": False,
                "dimension": 0,
                "num_vectors": 0,
                "has_data": False,
            }
        has_data = False
        try:
            has_data = bool(store.has_data())
        except Exception:
            has_data = False
        return {
            "available": True,
            "dimension": int(getattr(store, "dimension", 0) or 0),
            "num_vectors": int(getattr(store, "num_vectors", 0) or 0),
            "has_data": has_data,
        }

    def vector_pools_status(self) -> Dict[str, Any]:
        configured_mode = self._config.mode
        ready = self.dual_pools_enabled
        return {
            "configured_mode": configured_mode,
            "effective_mode": "dual" if configured_mode == "dual" and ready else "single",
            "ready": ready,
            "single_pool": self.vector_store_snapshot(self.vector_store),
            "paragraph_pool": self.vector_store_snapshot(self.paragraph_vector_store),
            "graph_pool": self.vector_store_snapshot(self.graph_vector_store),
            "ready_manifest": str(self.dual_vector_ready_manifest_path()),
            "auto_migration": dict(self._dual_vector_auto_migration_status),
        }

    # ── 自动迁移进度 ──

    def should_start_dual_vector_auto_migration(self, *, background_stopping: bool = False) -> bool:
        return (
            self._config.config_enabled
            and not self.dual_pools_enabled
            and not self._dual_vector_auto_migration_attempted
            and not background_stopping
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
        payload: Dict[str, Any] = dict(progress or {})
        now_ts = float(now if now is not None else time.time())
        started_at = self._dual_vector_auto_migration_status.get("started_at")
        elapsed_seconds = 0.0
        if isinstance(started_at, (int, float)):
            elapsed_seconds = max(0.0, now_ts - float(started_at))

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

    def update_dual_vector_auto_migration_stage(self, stage: str, **progress: Any) -> None:
        if not bool(self._dual_vector_auto_migration_status.get("running", False)):
            return
        now_ts = time.time()
        explicit_processed = "processed" in progress
        payload = dict(self._dual_vector_auto_migration_status.get("progress") or {})
        payload.update(progress)
        payload = self.normalize_dual_vector_auto_migration_progress(
            payload,
            now=now_ts,
            explicit_processed=explicit_processed,
        )
        self._dual_vector_auto_migration_status.update(
            {
                "stage": str(stage or "unknown"),
                "progress": payload,
                "updated_at": now_ts,
            }
        )

    def update_auto_migration_status(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            if key in self._dual_vector_auto_migration_status:
                self._dual_vector_auto_migration_status[key] = value
        self._dual_vector_auto_migration_status["updated_at"] = time.time()

    # ── 辅助：向量重建目标计数 ──

    def count_vector_rebuild_targets(self) -> Dict[str, int]:
        if self.metadata_store is None:
            return {"paragraphs": 0, "entities": 0, "relations": 0}
        paragraph_where = self._active_row_filter_sql("paragraphs")
        entity_where = self._active_row_filter_sql("entities")
        relation_where = self._active_row_filter_sql("relations")
        rows = self.metadata_store.query(
            f"""
            SELECT
                (SELECT COUNT(*) FROM paragraphs WHERE {paragraph_where}) AS paragraphs,
                (SELECT COUNT(*) FROM entities WHERE {entity_where}) AS entities,
                (SELECT COUNT(*) FROM relations WHERE {relation_where}) AS relations
            """
        )
        row = rows[0] if rows else {}
        return {
            "paragraphs": int(row.get("paragraphs", 0) or 0),
            "entities": int(row.get("entities", 0) or 0),
            "relations": int(row.get("relations", 0) or 0),
        }

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
