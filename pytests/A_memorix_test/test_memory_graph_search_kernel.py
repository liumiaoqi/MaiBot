from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.A_memorix.core.retrieval import RetrievalResult
from src.A_memorix.core.runtime.sdk_memory_kernel import KernelSearchRequest
from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel


class _DummyMetadataStore:
    def __init__(self, *, entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> None:
        self._entities = entities
        self._relations = relations

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        sql_token = " ".join(str(sql or "").lower().split())
        keyword = str(params[0] or "").strip("%").lower() if params else ""
        if "from entities" in sql_token:
            rows = [dict(item) for item in self._entities if not bool(item.get("is_deleted", 0))]
            if not keyword:
                return rows
            return [
                row
                for row in rows
                if keyword in str(row.get("name", "") or "").lower()
                or keyword in str(row.get("hash", "") or "").lower()
            ]
        if "from relations" in sql_token:
            rows = [dict(item) for item in self._relations if not bool(item.get("is_inactive", 0))]
            if not keyword:
                return rows
            return [
                row
                for row in rows
                if keyword in str(row.get("subject", "") or "").lower()
                or keyword in str(row.get("object", "") or "").lower()
                or keyword in str(row.get("predicate", "") or "").lower()
                or keyword in str(row.get("hash", "") or "").lower()
            ]
        raise AssertionError(f"unexpected query: {sql_token}")


class _ScopedSearchMetadataStore:
    def __init__(self) -> None:
        self.paragraphs = {
            "para-current": {
                "hash": "para-current",
                "content": "当前群聊提到绿色围巾。",
                "source": "chat_summary:session-current",
                "metadata": {"chat_id": "session-current", "source_type": "chat_summary"},
            },
            "para-other": {
                "hash": "para-other",
                "content": "其他群聊提到秘密计划。",
                "source": "chat_summary:session-other",
                "metadata": {"chat_id": "session-other", "source_type": "chat_summary"},
            },
            "para-current-relation": {
                "hash": "para-current-relation",
                "content": "当前群聊支撑的关系。",
                "source": "chat_summary:session-current",
                "metadata": {"chat_id": "session-current", "source_type": "chat_summary"},
            },
            "para-other-relation": {
                "hash": "para-other-relation",
                "content": "其他群聊支撑的关系。",
                "source": "chat_summary:session-other",
                "metadata": {"chat_id": "session-other", "source_type": "chat_summary"},
            },
        }
        self.relation_paragraphs = {
            "rel-current": [self.paragraphs["para-current-relation"]],
            "rel-other": [self.paragraphs["para-other-relation"]],
        }

    def get_paragraphs_by_hashes(self, paragraph_hashes: list[str]) -> dict[str, dict[str, Any]]:
        return {
            paragraph_hash: self.paragraphs[paragraph_hash]
            for paragraph_hash in paragraph_hashes
            if paragraph_hash in self.paragraphs
        }

    def get_paragraphs_by_relation_hashes(self, relation_hashes: list[str]) -> dict[str, list[dict[str, Any]]]:
        return {
            relation_hash: list(self.relation_paragraphs.get(relation_hash, []))
            for relation_hash in relation_hashes
        }

    def get_relation_status_batch(self, hashes: list[str]) -> dict[str, dict[str, Any]]:
        return {str(hash_value): {"is_inactive": False} for hash_value in hashes}

    def reinforce_relations(self, hashes: list[str]) -> None:
        del hashes

    def get_paragraph_relations(self, paragraph_hash: str) -> list[dict[str, Any]]:
        del paragraph_hash
        return []

    def get_paragraph_stale_relation_marks_batch(self, paragraph_hashes: list[str]) -> dict[str, list[dict[str, Any]]]:
        return {str(paragraph_hash): [] for paragraph_hash in paragraph_hashes}


class _ScopedSearchRetriever:
    config = type("RetrieverConfig", (), {"enable_ppr": False})()

    def __init__(self) -> None:
        self.top_k_values: list[int] = []

    async def retrieve(self, *, query: str, top_k: int, temporal: Any) -> list[RetrievalResult]:
        del query, temporal
        self.top_k_values.append(top_k)
        return [
            RetrievalResult(
                hash_value="para-other",
                content="其他群聊提到秘密计划。",
                score=0.99,
                result_type="paragraph",
                source="paragraph_search",
                metadata={},
            ),
            RetrievalResult(
                hash_value="rel-other",
                content="其他群聊 讨论 秘密计划",
                score=0.98,
                result_type="relation",
                source="relation_search",
                metadata={},
            ),
            RetrievalResult(
                hash_value="para-current",
                content="当前群聊提到绿色围巾。",
                score=0.97,
                result_type="paragraph",
                source="paragraph_search",
                metadata={},
            ),
            RetrievalResult(
                hash_value="rel-current",
                content="当前群聊 讨论 绿色围巾",
                score=0.96,
                result_type="relation",
                source="relation_search",
                metadata={},
            ),
        ]


def _build_kernel(*, entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> SDKMemoryKernel:
    kernel = SDKMemoryKernel(plugin_root=Path.cwd(), config={})

    async def _fake_initialize() -> None:
        return None

    kernel.initialize = _fake_initialize  # type: ignore[method-assign]
    kernel.metadata_store = _DummyMetadataStore(entities=entities, relations=relations)
    kernel.graph_store = object()  # type: ignore[assignment]
    return kernel


def _build_scoped_search_kernel(tmp_path) -> tuple[SDKMemoryKernel, _ScopedSearchRetriever]:
    kernel = SDKMemoryKernel(
        plugin_root=tmp_path,
        config={
            "retrieval": {
                "search": {
                    "smart_fallback": {"enabled": False},
                    "safe_content_dedup": {"enabled": False},
                }
            }
        },
    )
    retriever = _ScopedSearchRetriever()

    async def _fake_initialize() -> None:
        return None

    kernel.initialize = _fake_initialize  # type: ignore[method-assign]
    kernel._initialized = True
    kernel.metadata_store = _ScopedSearchMetadataStore()  # type: ignore[assignment]
    kernel.graph_store = object()  # type: ignore[assignment]
    kernel.vector_store = object()  # type: ignore[assignment]
    kernel.embedding_manager = object()
    kernel.retriever = retriever  # type: ignore[assignment]
    kernel.episode_retriever = object()  # type: ignore[assignment]
    kernel.aggregate_query_service = object()  # type: ignore[assignment]
    kernel.threshold_filter = None
    return kernel, retriever


@pytest.mark.asyncio
async def test_memory_graph_admin_search_orders_and_dedupes_results() -> None:
    kernel = _build_kernel(
        entities=[
            {"hash": "e1", "name": "Alice", "appearance_count": 5, "is_deleted": 0},
            {"hash": "e1", "name": "Alice Duplicate", "appearance_count": 99, "is_deleted": 0},
            {"hash": "e2", "name": "Alice Cooper", "appearance_count": 7, "is_deleted": 0},
            {"hash": "e3", "name": "my alice note", "appearance_count": 11, "is_deleted": 0},
            {"hash": "e4", "name": "alice deleted", "appearance_count": 100, "is_deleted": 1},
        ],
        relations=[
            {"hash": "r1", "subject": "Alice", "predicate": "knows", "object": "Bob", "confidence": 0.6, "created_at": 100, "is_inactive": 0},
            {"hash": "r3", "subject": "Alice", "predicate": "supports", "object": "Carol", "confidence": 0.9, "created_at": 90, "is_inactive": 0},
            {"hash": "r1", "subject": "Alice", "predicate": "knows duplicate", "object": "Bob", "confidence": 0.99, "created_at": 200, "is_inactive": 0},
            {"hash": "r2", "subject": "Alice Cooper", "predicate": "likes", "object": "Tea", "confidence": 0.2, "created_at": 50, "is_inactive": 0},
            {"hash": "", "subject": "Carol", "predicate": "mentions alice", "object": "Topic", "confidence": 0.8, "created_at": 70, "is_inactive": 0},
            {"hash": "", "subject": "Carol", "predicate": "mentions alice", "object": "Topic", "confidence": 0.3, "created_at": 10, "is_inactive": 0},
            {"hash": "r4", "subject": "alice inactive", "predicate": "old", "object": "Data", "confidence": 1.0, "created_at": 300, "is_inactive": 1},
        ],
    )

    payload = await kernel.memory_graph_admin(action="search", query="alice", limit=20)

    assert payload["success"] is True
    assert payload["count"] == len(payload["items"])
    entity_items = [item for item in payload["items"] if item["type"] == "entity"]
    relation_items = [item for item in payload["items"] if item["type"] == "relation"]

    assert [item["entity_hash"] for item in entity_items] == ["e1", "e2", "e3"]
    assert [item["relation_hash"] for item in relation_items] == ["r3", "r1", "r2", ""]
    assert relation_items[0]["confidence"] == pytest.approx(0.9)
    assert relation_items[1]["confidence"] == pytest.approx(0.6)


@pytest.mark.asyncio
async def test_memory_graph_admin_search_filters_deleted_and_inactive_records() -> None:
    kernel = _build_kernel(
        entities=[
            {"hash": "e-deleted", "name": "Ghost Alice", "appearance_count": 10, "is_deleted": 1},
        ],
        relations=[
            {
                "hash": "r-inactive",
                "subject": "Ghost Alice",
                "predicate": "linked",
                "object": "Ghost Bob",
                "confidence": 0.9,
                "created_at": 10,
                "is_inactive": 1,
            },
        ],
    )

    payload = await kernel.memory_graph_admin(action="search", query="ghost", limit=50)

    assert payload["success"] is True
    assert payload["items"] == []
    assert payload["count"] == 0


@pytest.mark.asyncio
async def test_search_memory_filters_hits_to_current_chat_scope(tmp_path) -> None:
    kernel, retriever = _build_scoped_search_kernel(tmp_path)

    payload = await kernel.search_memory(
        KernelSearchRequest(
            query="围巾",
            limit=2,
            mode="search",
            chat_id="session-current",
        )
    )

    assert payload["summary"]
    assert [item["hash"] for item in payload["hits"]] == ["para-current", "rel-current"]
    assert retriever.top_k_values == [10]


@pytest.mark.asyncio
async def test_search_memory_allows_configured_shared_chat_scope(tmp_path) -> None:
    kernel, retriever = _build_scoped_search_kernel(tmp_path)

    payload = await kernel.search_memory(
        KernelSearchRequest(
            query="围巾",
            limit=4,
            mode="search",
            chat_id="session-current",
            shared_chat_ids=("session-current", "session-other"),
        )
    )

    assert [item["hash"] for item in payload["hits"]] == [
        "para-other",
        "rel-other",
        "para-current",
        "rel-current",
    ]
    assert retriever.top_k_values == [40]


@pytest.mark.asyncio
async def test_search_memory_keeps_global_results_without_chat_id(tmp_path) -> None:
    kernel, retriever = _build_scoped_search_kernel(tmp_path)

    payload = await kernel.search_memory(
        KernelSearchRequest(
            query="围巾",
            limit=2,
            mode="search",
            chat_id="",
        )
    )

    assert [item["hash"] for item in payload["hits"]] == ["para-other", "rel-other"]
    assert retriever.top_k_values == [2]
