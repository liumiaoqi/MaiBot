from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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


def _build_kernel(*, entities: list[dict[str, Any]], relations: list[dict[str, Any]]) -> SDKMemoryKernel:
    kernel = SDKMemoryKernel(plugin_root=Path.cwd(), config={})

    async def _fake_initialize() -> None:
        return None

    kernel.initialize = _fake_initialize  # type: ignore[method-assign]
    kernel.metadata_store = _DummyMetadataStore(entities=entities, relations=relations)
    kernel.graph_store = object()  # type: ignore[assignment]
    return kernel


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
