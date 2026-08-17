"""ZG-28 测试共享辅助模块。

提供 Fake 替身类 + 真实 SQLite MetadataStore 工厂 + 缓存配置工厂，
供所有 ZG-28 复杂测试（语义等价 / 缓存命中 / 降级保底 / 灰度 / 基准）复用。
"""

import hashlib
import sqlite3

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

from src.A_memorix.core.storage.metadata_store import MetadataStore


# ── Fake 替身类 ──────────────────────────────────────────────────────────


class FakeEmbeddingManager:
    """假 EmbeddingAPIAdapter，计数 encode 调用 + 确定性向量生成。"""

    def __init__(self, dimension: int = 8, model_name: str = "fake-emb") -> None:
        self.default_dimension = dimension
        self.model_name = model_name
        self.encode_calls: List[Any] = []

    async def _detect_dimension(self) -> int:
        return self.default_dimension

    async def encode(self, text: Any, **kwargs: Any) -> np.ndarray:
        del kwargs
        self.encode_calls.append(text)
        content = str(text or "")
        vector = np.zeros(self.default_dimension, dtype=np.float32)
        for idx, byte in enumerate(content.encode("utf-8")):
            vector[idx % self.default_dimension] += float((byte % 17) + 1)
        norm = float(np.linalg.norm(vector))
        if norm > 0:
            vector /= norm
        return vector.astype(np.float32)

    async def encode_batch(self, texts: Any, **kwargs: Any) -> np.ndarray:
        if isinstance(texts, (list, tuple)):
            return np.stack([await self.encode(t, **kwargs) for t in texts])
        return await self.encode(texts, **kwargs)

    def get_embedding_fingerprint(self, *, dimension: int | None = None) -> Dict[str, Any]:
        effective = int(dimension or self.default_dimension)
        raw = f"{self.model_name}|fake-provider|{effective}|explicit"
        return {
            "version": 1,
            "hash": f"sha256:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}",
            "model": self.model_name,
            "provider": "fake-provider",
            "dimension": effective,
            "dimension_request_mode": "explicit",
            "source": "configured",
        }


class FakeVectorStore:
    """假 VectorStore，返回预设 ids/scores + 计数 search 调用。"""

    def __init__(self, ids: List[str], scores: List[float], dimension: int = 8) -> None:
        self.ids = ids
        self.scores = scores
        self.dimension = dimension
        self.search_calls: int = 0

    def search(self, query: np.ndarray, k: int = 10, filter_deleted: bool = True):
        del query, filter_deleted
        self.search_calls += 1
        return self.ids[:k], self.scores[:k]

    async def search_async(self, query: np.ndarray, k: int = 10, filter_deleted: bool = True):
        return self.search(query, k=k, filter_deleted=filter_deleted)

    def insert(self, ids: Sequence[str], vectors: np.ndarray) -> None:
        pass

    def delete(self, ids: Sequence[str]) -> None:
        pass

    def get_vector(self, id: str) -> Optional[np.ndarray]:
        return None

    def count(self) -> int:
        return len(self.ids)


class FakeGraphStore:
    """假 GraphStore，内存节点/边管理 + 节点变更回调。"""

    def __init__(self, nodes: Optional[List[str]] = None) -> None:
        self._nodes: List[str] = list(nodes or [])
        self._node_callbacks: List[Callable[[], None]] = []
        self.get_nodes_calls: int = 0
        self.add_node_calls: int = 0
        self.delete_node_calls: int = 0

    def get_nodes(self) -> List[str]:
        self.get_nodes_calls += 1
        return list(self._nodes)

    def add_nodes(self, nodes: Sequence[str]) -> int:
        added = 0
        for n in nodes:
            if n not in self._nodes:
                self._nodes.append(n)
                added += 1
        self.add_node_calls += 1
        self._notify_node_change()
        return added

    def delete_nodes(self, nodes: Sequence[str]) -> int:
        deleted = 0
        for n in nodes:
            if n in self._nodes:
                self._nodes.remove(n)
                deleted += 1
        self.delete_node_calls += 1
        self._notify_node_change()
        return deleted

    def find_node(self, node: str, ignore_case: bool = False) -> Optional[str]:
        if ignore_case:
            lower = node.lower()
            for n in self._nodes:
                if n.lower() == lower:
                    return n
            return None
        return node if node in self._nodes else None

    def register_node_change_callback(self, callback: Callable[[], None]) -> None:
        self._node_callbacks.append(callback)

    def _notify_node_change(self) -> None:
        for cb in self._node_callbacks:
            try:
                cb()
            except Exception:
                pass

    def get_relation_hashes_for_edge(self, a: str, b: str) -> List[str]:
        return []

    def find_paths(self, a: str, b: str, max_depth: int = 2, max_paths: int = 4) -> List[List[str]]:
        return []

    def get_incident_relation_hashes(self, seed: str, limit: int = 100) -> List[str]:
        return []


# ── 真实 SQLite MetadataStore 工厂 ────────────────────────────────────────


def make_metadata_store(tmp_path: Path) -> MetadataStore:
    """创建真实 SQLite MetadataStore（已 connect）。调用方负责 close。"""
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    return store


def seed_relations_and_paragraphs(
    store: MetadataStore,
    *,
    entities: Sequence[str],
    relations: Sequence[tuple[str, str, str]],
    paragraphs: Sequence[tuple[str, str]],
) -> Dict[str, str]:
    """向 MetadataStore 插入测试数据。

    Args:
        entities: 实体名列表
        relations: (subject, predicate, object) 三元组列表
        paragraphs: (content, source) 段落列表

    Returns:
        dict 包含 "entity_hashes" / "relation_hashes" / "paragraph_hashes"
    """
    result: Dict[str, str] = {}
    result["entity_hashes"] = {}
    result["relation_hashes"] = []
    result["paragraph_hashes"] = []

    for name in entities:
        eh = store.add_entity(name)
        result["entity_hashes"][name] = eh

    paragraph_hash_map: Dict[str, str] = {}
    for content, source in paragraphs:
        ph = store.add_paragraph(content, source=source)
        result["paragraph_hashes"].append(ph)
        paragraph_hash_map[content] = ph

    for subj, pred, obj in relations:
        source_paragraph = None
        for content, ph in paragraph_hash_map.items():
            if subj in content and obj in content:
                source_paragraph = ph
                break
        rh = store.add_relation(subj, pred, obj, source_paragraph=source_paragraph)
        result["relation_hashes"].append(rh)

    return result


# ── 缓存配置工厂 ──────────────────────────────────────────────────────────


def make_cache_config(
    *,
    enable_embedding: bool = True,
    embedding_max: int = 256,
    embedding_ttl: float = 300.0,
    enable_bm25: bool = True,
    bm25_max: int = 256,
    bm25_ttl: float = 60.0,
    enable_profile: bool = True,
    profile_max: int = 256,
    profile_ttl: float = 300.0,
    enable_node: bool = True,
    node_ttl: float = 300.0,
) -> SimpleNamespace:
    """创建缓存配置 SimpleNamespace（对齐 DualPathRetrieverConfig.cache）。"""
    return SimpleNamespace(
        enable_embedding_cache=enable_embedding,
        embedding_cache_max_entries=embedding_max,
        embedding_cache_ttl_seconds=embedding_ttl,
        enable_bm25_cache=enable_bm25,
        bm25_cache_max_entries=bm25_max,
        bm25_cache_ttl_seconds=bm25_ttl,
        enable_profile_cache=enable_profile,
        profile_cache_max_entries=profile_max,
        profile_cache_ttl_seconds=profile_ttl,
        enable_node_cache=enable_node,
        node_cache_ttl_seconds=node_ttl,
    )


def make_cache_config_dict(
    *,
    enable_embedding: bool = True,
    enable_bm25: bool = True,
    enable_profile: bool = True,
    enable_node: bool = True,
) -> Dict[str, Any]:
    """创建缓存配置 dict（模拟从 TOML/JSON 读取的原始格式）。"""
    return {
        "enable_embedding_cache": enable_embedding,
        "embedding_cache_max_entries": 256,
        "embedding_cache_ttl_seconds": 300.0,
        "enable_bm25_cache": enable_bm25,
        "bm25_cache_max_entries": 256,
        "bm25_cache_ttl_seconds": 60.0,
        "enable_profile_cache": enable_profile,
        "profile_cache_max_entries": 256,
        "profile_cache_ttl_seconds": 300.0,
        "enable_node_cache": enable_node,
        "node_cache_ttl_seconds": 300.0,
    }


# ── SQL 调用计数器 ────────────────────────────────────────────────────────


class SqlCallCounter:
    """包装 sqlite3.Connection，计数 execute 调用（用于验证 N+1 降幅）。"""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self.execute_count: int = 0
        self.executemany_count: int = 0

    def execute(self, *args, **kwargs):
        self.execute_count += 1
        return self._conn.execute(*args, **kwargs)

    def executemany(self, *args, **kwargs):
        self.executemany_count += 1
        return self._conn.executemany(*args, **kwargs)

    def commit(self):
        return self._conn.commit()

    def close(self):
        return self._conn.close()

    @property
    def total_sql(self) -> int:
        return self.execute_count + self.executemany_count