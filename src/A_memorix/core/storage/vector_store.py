"""
向量存储模块

基于Faiss的高效向量存储与检索，HNSW索引 + Append-Only磁盘存储。
"""

import asyncio
import pickle
import hashlib
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple, Union
import threading

import numpy as np

try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False

from src.common.logger import get_logger
from ..utils.quantization import QuantizationType
from ..utils.io import atomic_write, atomic_save_path

logger = get_logger("A_Memorix.VectorStore")


class VectorStore:
    """
    向量存储类 (HNSW + Append-Only Disk)

    特性：
    - 索引: IndexIDMap2(IndexHNSWFlat) (M=32, ef_construction=200) — IDMap2 包装以支持 add_with_ids（faiss>=1.13 裸 HNSWFlat 不支持）
    - 搜索: ef_search=50
    - 存储: float16 on-disk binary (vectors.bin)
    - 内存: 索引常驻 RAM
    - ID: SHA1-based stable int64 IDs
    - 一致性: 强制 L2 Normalization (IP == Cosine)
    - 无需训练：HNSW 图索引直接构建
    """

    # HNSW 参数
    HNSW_M = 32
    HNSW_EF_CONSTRUCTION = 200
    HNSW_EF_SEARCH = 50

    # 默认训练触发阈值 (保留用于旧 SQ8 索引迁移，新 HNSW 索引无需训练)
    DEFAULT_MIN_TRAIN = 40

    def __init__(
        self,
        dimension: int,
        quantization_type: QuantizationType = QuantizationType.INT8,
        index_type: str = "sq8",
        data_dir: Optional[Union[str, Path]] = None,
        use_mmap: bool = True,
        buffer_size: int = 1024,
    ):
        if not HAS_FAISS:
            raise ImportError("Faiss 未安装，请安装: pip install faiss-cpu")

        self.dimension = dimension
        self.data_dir = Path(data_dir) if data_dir else None
        if self.data_dir:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        self.quantization_type = QuantizationType.INT8
        self.index_type = "hnsw"
        self.buffer_size = buffer_size
        self.min_train_threshold = self.DEFAULT_MIN_TRAIN

        self._index: Optional[faiss.IndexIDMap2] = None
        self._init_index()

        self._vector_norm = "l2"

        self._known_hashes: Set[str] = set()
        self._deleted_ids: Set[int] = set()

        self._write_buffer_vecs: List[np.ndarray] = []
        self._write_buffer_ids: List[int] = []

        self._total_added = 0
        self._total_deleted = 0
        self._bin_count = 0

        # Thread safety lock
        self._lock = threading.RLock()

        logger.info(f"向量存储初始化: dim={dimension}, mode=HNSW")

    def _init_index(self):
        """初始化空的 HNSW Faiss 索引（IndexIDMap2 包装）"""
        hnsw_index = faiss.IndexHNSWFlat(
            self.dimension,
            self.HNSW_M,
            faiss.METRIC_INNER_PRODUCT,
        )
        hnsw_index.hnsw.efConstruction = self.HNSW_EF_CONSTRUCTION
        hnsw_index.hnsw.efSearch = self.HNSW_EF_SEARCH
        self._index = faiss.IndexIDMap2(hnsw_index)

    @staticmethod
    def _generate_id(key: str) -> int:
        """生成稳定的 int64 ID (SHA1 截断)"""
        h = hashlib.sha1(key.encode("utf-8")).digest()
        val = int.from_bytes(h[:8], byteorder="big", signed=False)
        return val & 0x7FFFFFFFFFFFFFFF

    @property
    def _bin_path(self) -> Path:
        return self.data_dir / "vectors.bin"

    @property
    def _ids_bin_path(self) -> Path:
        return self.data_dir / "vectors_ids.bin"

    @property
    def _int_to_str_map(self) -> Dict[int, str]:
        """Lazy build volatile map from known hashes"""
        # Note: This is read-heavy and cached, might need lock if _known_hashes updates concurrently
        # But add/delete are now locked, so checking len mismatch is somewhat safe-ish for quick dirty cache
        if not hasattr(self, "_cached_map") or len(self._cached_map) != len(self._known_hashes):
            with self._lock: # Protect cache rebuild
                 self._cached_map = {self._generate_id(k): k for k in self._known_hashes}
        return self._cached_map

    def add(self, vectors: np.ndarray, ids: List[str]) -> int:
        with self._lock:
            if vectors.shape[1] != self.dimension:
                raise ValueError(f"Dimension mismatch: {vectors.shape[1]} vs {self.dimension}")

            vectors = np.ascontiguousarray(vectors, dtype=np.float32)
            faiss.normalize_L2(vectors)

            processed_vecs = []
            processed_int_ids = []

            for i, str_id in enumerate(ids):
                if str_id in self._known_hashes:
                    continue

                int_id = self._generate_id(str_id)
                self._known_hashes.add(str_id)

                processed_vecs.append(vectors[i])
                processed_int_ids.append(int_id)

            if not processed_vecs:
                return 0

            batch_vecs = np.array(processed_vecs, dtype=np.float32)
            batch_ids = np.array(processed_int_ids, dtype=np.int64)

            self._write_buffer_vecs.append(batch_vecs)
            self._write_buffer_ids.extend(processed_int_ids)

            if len(self._write_buffer_ids) >= self.buffer_size:
                self._flush_write_buffer_unlocked()

            self._total_added += len(batch_ids)
            return len(batch_ids)

    def _flush_write_buffer(self):
        with self._lock:
            self._flush_write_buffer_unlocked()

    def _flush_write_buffer_unlocked(self):
        if not self._write_buffer_vecs:
            return

        batch_vecs = np.concatenate(self._write_buffer_vecs, axis=0)
        batch_ids = np.array(self._write_buffer_ids, dtype=np.int64)

        vecs_fp16 = batch_vecs.astype(np.float16)

        with open(self._bin_path, "ab") as f:
            f.write(vecs_fp16.tobytes())

        ids_bytes = batch_ids.astype('>i8').tobytes()
        with open(self._ids_bin_path, "ab") as f:
            f.write(ids_bytes)

        self._bin_count += len(batch_ids)

        self._index.add_with_ids(batch_vecs, batch_ids)

        self._write_buffer_vecs.clear()
        self._write_buffer_ids.clear()

    async def search_async(
        self,
        query: np.ndarray,
        k: int = 10,
        filter_deleted: bool = True,
    ) -> Tuple[List[str], List[float]]:
        """异步检索（ZG-11 Phase 1）：FAISS 是 C 扩展释放 GIL，
        ThreadPoolExecutor 即可用多核，事件循环不被阻塞。"""
        return await asyncio.to_thread(
            self.search, query, k=k, filter_deleted=filter_deleted,
        )

    def search(
        self,
        query: np.ndarray,
        k: int = 10,
        filter_deleted: bool = True,
    ) -> Tuple[List[str], List[float]]:
        query_local = np.array(query, dtype=np.float32, order="C", copy=True)
        if query_local.ndim == 1:
            got_dim = int(query_local.shape[0])
            query_local = query_local.reshape(1, -1)
        elif query_local.ndim == 2:
            if query_local.shape[0] != 1:
                raise ValueError(
                    f"query embedding must have shape (D,) or (1, D), got {tuple(query_local.shape)}"
                )
            got_dim = int(query_local.shape[1])
        else:
            raise ValueError(
                f"query embedding must have shape (D,) or (1, D), got {tuple(query_local.shape)}"
            )

        if got_dim != self.dimension:
            raise ValueError(
                f"query embedding dimension mismatch: expected={self.dimension} got={got_dim}"
            )
        if not np.all(np.isfinite(query_local)):
            raise ValueError("query embedding contains non-finite values")

        faiss.normalize_L2(query_local)

        # Faiss 索引在并发 search 下可能出现阻塞，这里串行化检索调用保证稳定性。
        with self._lock:
            self._flush_write_buffer_unlocked()
            if self._index.ntotal == 0:
                logger.warning("Index is empty. No data to search.")
                return [], []
            # 执行检索
            dists, ids = self._index.search(query_local, k * 2)

        # Faiss search 返回的是 (1, K) 的数组，取第一行
        dists = dists[0]
        ids = ids[0]

        results = []
        for id_val, score in zip(ids, dists, strict=True):
            if id_val == -1:
                continue
            if filter_deleted and id_val in self._deleted_ids:
                continue

            str_id = self._int_to_str_map.get(id_val)
            if str_id:
                results.append((str_id, float(score)))

        # Sort and trim just in case filtering reduced count
        results.sort(key=lambda x: x[1], reverse=True)
        results = results[:k]

        if not results:
            return [], []

        return [r[0] for r in results], [r[1] for r in results]

    def get_vectors(self, ids: Sequence[str]) -> Dict[str, np.ndarray]:
        """按字符串 ID 读取已持久化向量，用于无 embedding 的池间迁移。"""
        return {
            key: vector
            for batch in self.iter_vectors_by_ids(ids)
            for key, vector in batch.items()
        }

    def iter_vectors_by_ids(
        self,
        ids: Sequence[str],
        *,
        batch_size: int = 1024,
    ) -> Iterator[Dict[str, np.ndarray]]:
        """按字符串 ID 分批读取持久化向量，避免迁移时把全部向量集中留在内存。"""
        requested_ids = [
            str(item or "").strip()
            for item in ids
            if str(item or "").strip()
        ]
        if not requested_ids:
            return

        safe_batch_size = max(1, int(batch_size or 1024))
        unique_ids = list(dict.fromkeys(requested_ids))
        with self._lock:
            self._flush_write_buffer_unlocked()
            known_hashes = set(self._known_hashes)
            deleted_ids = set(self._deleted_ids)
            bin_path = self._bin_path
            ids_bin_path = self._ids_bin_path
            dimension = int(self.dimension)

        int_to_str: Dict[int, str] = {}
        for str_id in unique_ids:
            if str_id not in known_hashes:
                continue
            int_id = self._generate_id(str_id)
            if int_id in deleted_ids:
                continue
            int_to_str[int_id] = str_id

        if not int_to_str or not bin_path.exists() or not ids_bin_path.exists():
            return

        result: Dict[str, np.ndarray] = {}
        vec_item_size = dimension * 2
        id_item_size = 8
        chunk_size = 10000

        with open(bin_path, "rb") as f_vec, open(ids_bin_path, "rb") as f_id:
            while True:
                vec_data = f_vec.read(chunk_size * vec_item_size)
                id_data = f_id.read(chunk_size * id_item_size)
                if not vec_data:
                    break

                batch_fp16 = np.frombuffer(vec_data, dtype=np.float16).reshape(-1, dimension)
                batch_fp32 = batch_fp16.astype(np.float32)
                faiss.normalize_L2(batch_fp32)
                batch_ids = np.frombuffer(id_data, dtype=">i8").astype(np.int64)

                for index, int_id in enumerate(batch_ids):
                    int_key = int(int_id)
                    key = int_to_str.pop(int_key, None)
                    if key is None or int_key in deleted_ids:
                        continue
                    result[key] = np.array(batch_fp32[index], dtype=np.float32, copy=True)
                    if len(result) >= safe_batch_size:
                        yield result
                        result = {}
                    if not int_to_str:
                        break
                if not int_to_str:
                    break

        if result:
            yield result

    def _get_vectors_chunk(self, requested_ids: Sequence[str]) -> Dict[str, np.ndarray]:
        """读取一批向量，调用方负责控制 batch 大小。"""
        if not requested_ids:
            return {}

        with self._lock:
            self._flush_write_buffer_unlocked()
            int_to_str: Dict[int, str] = {}
            for str_id in requested_ids:
                if str_id not in self._known_hashes:
                    continue
                int_id = self._generate_id(str_id)
                if int_id in self._deleted_ids:
                    continue
                int_to_str[int_id] = str_id

            if not int_to_str or not self._bin_path.exists() or not self._ids_bin_path.exists():
                return {}

            result: Dict[str, np.ndarray] = {}
            vec_item_size = self.dimension * 2
            id_item_size = 8
            chunk_size = 10000

            with open(self._bin_path, "rb") as f_vec, open(self._ids_bin_path, "rb") as f_id:
                while True:
                    vec_data = f_vec.read(chunk_size * vec_item_size)
                    id_data = f_id.read(chunk_size * id_item_size)
                    if not vec_data:
                        break

                    batch_fp16 = np.frombuffer(vec_data, dtype=np.float16).reshape(-1, self.dimension)
                    batch_fp32 = batch_fp16.astype(np.float32)
                    faiss.normalize_L2(batch_fp32)
                    batch_ids = np.frombuffer(id_data, dtype=">i8").astype(np.int64)

                    for index, int_id in enumerate(batch_ids):
                        key = int_to_str.get(int(int_id))
                        if key is None or key in result or int_id in self._deleted_ids:
                            continue
                        result[key] = np.array(batch_fp32[index], dtype=np.float32, copy=True)
                        if len(result) >= len(int_to_str):
                            return result

            return result

    def warmup_index(self) -> Dict[str, Any]:
        """
        预热向量索引，验证索引状态并记录日志。

        Returns:
            预热状态摘要
        """
        started = time.perf_counter()
        logger.debug("metric.vector_index_prewarm_started=1")

        try:
            with self._lock:
                self._flush_write_buffer()

                if self._bin_path.exists():
                    self._bin_count = self._bin_path.stat().st_size // (self.dimension * 2)
                else:
                    self._bin_count = 0

                ntotal = int(self._index.ntotal)
                duration_ms = (time.perf_counter() - started) * 1000.0
                summary = {
                    "total": ntotal,
                    "dimension": self.dimension,
                }
        except Exception as e:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "向量索引预热失败", exception=e)
            logger.warning("操作失败", exc_info=True)
            duration_ms = (time.perf_counter() - started) * 1000.0
            summary = {
                "total": int(self._index.ntotal) if self._index is not None else 0,
                "dimension": self.dimension,
            }
            logger.error(
                "metric.vector_index_prewarm_fail=1 "
                f"metric.vector_index_prewarm_duration_ms={duration_ms:.2f} "
                f"error={e}"
            )
            return summary

        logger.debug(
            "metric.vector_index_prewarm_success=1 "
            f"metric.vector_index_prewarm_duration_ms={duration_ms:.2f} "
            f"ntotal={ntotal} "
            f"bin_count={self._bin_count}"
        )
        return summary

    def delete(self, ids: List[str]) -> int:
        with self._lock:
            count = 0
            for str_id in ids:
                if str_id not in self._known_hashes:
                    continue
                int_id = self._generate_id(str_id)
                if int_id not in self._deleted_ids:
                    self._deleted_ids.add(int_id)
                    self._index.remove_ids(np.array([int_id], dtype=np.int64))
                    count += 1
            self._total_deleted += count

            # Check GC
            self._check_rebuild_needed()
            return count

    def _check_rebuild_needed(self):
        """GC Excution Check"""
        if self._bin_count == 0:
            return
        ratio = len(self._deleted_ids) / self._bin_count
        if ratio > 0.3 and len(self._deleted_ids) > 1000:
            logger.info(f"Triggering GC/Rebuild (deleted ratio: {ratio:.2f})")
            self.rebuild_index()

    def rebuild_index(self):
        """GC: 重建索引，压缩 bin 文件。

        持锁设计（P2 批5.1 文档说明）：
        - compaction 是低频 GC 操作（ratio > 0.3 且 deleted > 1000 触发），非热路径
        - 步骤 1（文件 compact）+ 步骤 2（原子交换）+ 步骤 3（索引重建）需持锁保证一致性
        - 锁持有时间 = compaction 全程（几秒级），对低频 GC 可接受
        - 如需进一步优化，可将步骤 1 移到锁外（临时文件读写），但需保证与 save 不并发
        """
        with self._lock:
            self._rebuild_index_locked()

    def _rebuild_index_locked(self):
        """实际 GC 重建逻辑。"""
        logger.info("Starting Compaction (GC)...")

        tmp_bin = self.data_dir / "vectors.bin.tmp"
        tmp_ids = self.data_dir / "vectors_ids.bin.tmp"

        vec_item_size = self.dimension * 2
        id_item_size = 8
        chunk_size = 10000

        new_count = 0

        # 1. Compact Files
        with open(self._bin_path, "rb") as f_vec, open(self._ids_bin_path, "rb") as f_id, \
             open(tmp_bin, "wb") as w_vec, open(tmp_ids, "wb") as w_id:
            while True:
                vec_data = f_vec.read(chunk_size * vec_item_size)
                id_data = f_id.read(chunk_size * id_item_size)
                if not vec_data:
                    break

                batch_fp16 = np.frombuffer(vec_data, dtype=np.float16).reshape(-1, self.dimension)
                batch_ids = np.frombuffer(id_data, dtype='>i8').astype(np.int64)

                keep_mask = [id_ not in self._deleted_ids for id_ in batch_ids]

                if any(keep_mask):
                    keep_vecs = batch_fp16[keep_mask]
                    keep_ids = batch_ids[keep_mask]

                    w_vec.write(keep_vecs.tobytes())
                    w_id.write(keep_ids.astype('>i8').tobytes())
                    new_count += len(keep_ids)

        # 2. Reset State & Atomic Swap
        self._bin_count = new_count

        # Close current index
        self._index.reset()

        # Swap files
        shutil.move(str(tmp_bin), str(self._bin_path))
        shutil.move(str(tmp_ids), str(self._ids_bin_path))

        # Reset Tombstones (Critical)
        self._deleted_ids.clear()

        # 3. Rebuild HNSW index from compacted bin files
        if self._bin_path.exists() and self._ids_bin_path.exists():
            self._load_bin_into_index(self._bin_path, self._ids_bin_path)
        logger.info(f"Compaction Complete. ntotal={self._index.ntotal}")

    def save(
        self,
        data_dir: Optional[Union[str, Path]] = None,
        *,
        embedding_fingerprint: Optional[Dict[str, Any]] = None,
    ) -> None:
        with self._lock:
            if not data_dir:
                data_dir = self.data_dir
            if not data_dir:
                raise ValueError("No data_dir")

            data_dir = Path(data_dir)
            data_dir.mkdir(parents=True, exist_ok=True)

            self._flush_write_buffer_unlocked()

            previous_embedding_fingerprint: Optional[Dict[str, Any]] = None
            meta_path = data_dir / "vectors_metadata.pkl"
            if embedding_fingerprint is None and meta_path.exists():
                try:
                    with open(meta_path, "rb") as f:
                        previous_meta = pickle.load(f)
                except Exception as exc:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.WARNING, '读取旧向量元数据失败，跳过 embedding 指纹继承', exception=exc)
                    logger.warning(f"读取旧向量元数据失败，跳过 embedding 指纹继承: {exc}")
                else:
                    if isinstance(previous_meta, dict):
                        previous_raw = previous_meta.get("embedding_fingerprint")
                        if isinstance(previous_raw, dict) and previous_raw:
                            previous_embedding_fingerprint = dict(previous_raw)

            index_path = data_dir / "vectors.index"
            with atomic_save_path(index_path) as tmp:
                faiss.write_index(self._index, tmp)

            meta = {
                "dimension": self.dimension,
                "quantization_type": self.quantization_type.value,
                "index_type": self.index_type,
                "is_trained": True,
                "vector_norm": self._vector_norm,
                "deleted_ids": list(self._deleted_ids),
                "known_hashes": list(self._known_hashes),
            }
            if isinstance(embedding_fingerprint, dict) and embedding_fingerprint:
                meta["embedding_fingerprint"] = dict(embedding_fingerprint)
            elif previous_embedding_fingerprint is not None:
                meta["embedding_fingerprint"] = previous_embedding_fingerprint

            with atomic_write(meta_path, "wb") as f:
                pickle.dump(meta, f)

            logger.debug("VectorStore saved.")

    def migrate_legacy_npy(self, data_dir: Optional[Union[str, Path]] = None) -> Dict[str, Any]:
        """
        离线迁移入口：将 legacy vectors.npy 转为 vNext 二进制格式。
        """
        with self._lock:
            target_dir = Path(data_dir) if data_dir else self.data_dir
            if target_dir is None:
                raise ValueError("No data_dir")
            target_dir = Path(target_dir)
            npy_path = target_dir / "vectors.npy"
            idx_path = target_dir / "vectors.index"
            bin_path = target_dir / "vectors.bin"
            ids_bin_path = target_dir / "vectors_ids.bin"
            meta_path = target_dir / "vectors_metadata.pkl"

            if not npy_path.exists():
                return {"migrated": False, "reason": "npy_missing"}
            if not meta_path.exists():
                raise RuntimeError("legacy vectors.npy migration requires vectors_metadata.pkl")
            if bin_path.exists() and ids_bin_path.exists():
                return {"migrated": False, "reason": "bin_exists"}

            # Reset in-memory state to avoid appending to stale runtime buffers.
            self._known_hashes.clear()
            self._deleted_ids.clear()
            self._write_buffer_vecs.clear()
            self._write_buffer_ids.clear()
            self._init_index()
            self._bin_count = 0

            self._migrate_from_npy_unlocked(npy_path, idx_path, target_dir)
            self.save(target_dir)
            return {"migrated": True, "reason": "ok"}

    def load(self, data_dir: Optional[Union[str, Path]] = None) -> None:
        with self._lock:
            if not data_dir:
                data_dir = self.data_dir
            data_dir = Path(data_dir)

            npy_path = data_dir / "vectors.npy"
            idx_path = data_dir / "vectors.index"
            bin_path = data_dir / "vectors.bin"
            ids_bin_path = data_dir / "vectors_ids.bin"

            if npy_path.exists() and not bin_path.exists():
                raise RuntimeError(
                    "检测到 legacy vectors.npy，vNext 不再支持运行时自动迁移。"
                    " 请先执行 scripts/release_vnext_migrate.py migrate。"
                )

            meta_path = data_dir / "vectors_metadata.pkl"
            if not meta_path.exists():
                logger.warning("No metadata found, initialized empty.")
                return

            with open(meta_path, "rb") as f:
                meta = pickle.load(f)

            if meta.get("vector_norm") != "l2":
                logger.warning("Index IDMap2 version mismatch (L2 Norm), forcing rebuild...")
                self._known_hashes = set(meta.get("ids", [])) | set(meta.get("known_hashes", []))
                self._deleted_ids = set(meta.get("deleted_ids", []))
                self._init_index()
                return

            self._vector_norm = meta.get("vector_norm", "l2")
            self._deleted_ids = set(meta.get("deleted_ids", []))
            self._known_hashes = set(meta.get("known_hashes", []))

            # SQ8 → HNSW 迁移检测
            needs_migration = (
                meta.get("index_type") == "sq8" or not meta.get("is_trained", False)
            )
            if needs_migration and idx_path.exists():
                logger.warning("检测到旧 SQ8 索引，正在重建 HNSW...")
                # 备份旧索引
                bak_path = data_dir / "vectors.index.sq8.bak"
                shutil.move(str(idx_path), str(bak_path))
                logger.info(f"旧 SQ8 索引已备份至 {bak_path}")

                # 从 vectors.bin 重建 HNSW 索引
                if bin_path.exists() and ids_bin_path.exists():
                    self._load_bin_into_index(bin_path, ids_bin_path)
                    logger.info(f"HNSW 索引重建完成: ntotal={self._index.ntotal}")

                    # 保存新索引
                    with atomic_save_path(idx_path) as tmp:
                        faiss.write_index(self._index, tmp)
                else:
                    logger.warning("vectors.bin 缺失，无法重建 HNSW 索引，使用空索引")
                    self._init_index()

                # 更新元数据
                meta["index_type"] = "hnsw"
                meta["is_trained"] = True
                with atomic_write(meta_path, "wb") as f:
                    pickle.dump(meta, f)
            elif idx_path.exists():
                # HNSW 索引直接加载
                try:
                    self._index = faiss.read_index(str(idx_path))
                except Exception as e:
                    from src.core.error_escalation.types import ErrorLevel
                    from src.core.error_escalation_port_registry import get_error_escalation_port
                    port = get_error_escalation_port()
                    if port is not None:
                        port.report(ErrorLevel.ERROR, "加载向量索引失败", exception=e)
                    logger.error(f"Failed to load index: {e}. Rebuilding...")
                    self._init_index()
            else:
                logger.warning("Index file missing. Starting with empty index.")
                self._init_index()

            if bin_path.exists():
                self._bin_count = bin_path.stat().st_size // (self.dimension * 2)

    def _migrate_from_npy(self, npy_path, idx_path, data_dir):
        with self._lock:
            self._migrate_from_npy_unlocked(npy_path, idx_path, data_dir)

    def _migrate_from_npy_unlocked(self, npy_path, idx_path, data_dir):
        try:
            arr = np.load(npy_path, mmap_mode="r")
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, '操作异常: %s', exception=exc)
            logger.warning("操作异常: %s", exc)
        meta_path = data_dir / "vectors_metadata.pkl"
        old_ids = []
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                m = pickle.load(f)
                old_ids = m.get("ids", [])

        if len(arr) != len(old_ids):
            logger.error(f"Migration mismatch: arr {len(arr)} != ids {len(old_ids)}")
            return

        logger.info(f"Migrating {len(arr)} vectors...")

        chunk = 1000
        for i in range(0, len(arr), chunk):
            sub_arr = arr[i : i+chunk]
            sub_ids = old_ids[i : i+chunk]
            self.add(sub_arr, sub_ids)

        shutil.move(str(npy_path), str(npy_path) + ".bak")
        if idx_path.exists():
            shutil.move(str(idx_path), str(idx_path) + ".bak")

        logger.info("Migration complete.")

    def _load_bin_into_index(self, bin_path: Path, ids_bin_path: Path) -> None:
        """从 vectors.bin + vectors_ids.bin 重建 HNSW 索引（内部辅助方法）。"""
        self._init_index()
        vec_item_size = self.dimension * 2
        id_item_size = 8
        chunk_size = 10000

        with open(bin_path, "rb") as f_vec, open(ids_bin_path, "rb") as f_id:
            while True:
                vec_data = f_vec.read(chunk_size * vec_item_size)
                id_data = f_id.read(chunk_size * id_item_size)
                if not vec_data:
                    break

                batch_fp16 = np.frombuffer(vec_data, dtype=np.float16).reshape(-1, self.dimension)
                batch_fp32 = batch_fp16.astype(np.float32)
                faiss.normalize_L2(batch_fp32)
                batch_ids = np.frombuffer(id_data, dtype=">i8").astype(np.int64)

                self._index.add_with_ids(batch_fp32, batch_ids)

    def clear(self) -> None:
        with self._lock:
            self._ids_bin_path.unlink(missing_ok=True)
            self._bin_path.unlink(missing_ok=True)
            self._init_index()
            self._known_hashes.clear()
            self._deleted_ids.clear()
            self._bin_count = 0
            logger.info("VectorStore cleared.")

    def has_data(self) -> bool:
        return (self.data_dir / "vectors_metadata.pkl").exists()

    @property
    def num_vectors(self) -> int:
        return len(self._known_hashes) - len(self._deleted_ids)

    def __contains__(self, hash_value: str) -> bool:
        """Check if a hash exists in the store"""
        return hash_value in self._known_hashes and self._generate_id(hash_value) not in self._deleted_ids
