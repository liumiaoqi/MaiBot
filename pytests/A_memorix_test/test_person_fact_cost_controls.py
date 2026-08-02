from typing import Any, Dict, List, Optional

import pytest

from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel
from src.A_memorix.core.runtime.services.hit_filter import HitFilterService
from src.A_memorix.core.runtime.services.ingest import IngestService
from src.A_memorix.core.runtime.services.person_profile_facade import PersonProfileFacade
from src.A_memorix.core.storage.metadata_store import MetadataStore


class _FakeMetadataStore:
    def __init__(self) -> None:
        self.pending: List[Dict[str, Any]] = []
        self.profile_refreshes: List[Dict[str, str]] = []
        self.external_refs: List[Dict[str, Any]] = []
        self.paragraphs: List[Dict[str, Any]] = []

    def get_external_memory_ref(self, external_id: str) -> Optional[Dict[str, Any]]:
        del external_id
        return None

    def add_paragraph(self, **kwargs: Any) -> str:
        self.paragraphs.append(dict(kwargs))
        return f"paragraph-{len(self.paragraphs)}"

    def add_entity(self, *, name: str, source_paragraph: str) -> str:
        return f"entity:{name}:{source_paragraph}"

    def upsert_external_memory_ref(self, **kwargs: Any) -> None:
        self.external_refs.append(dict(kwargs))

    def enqueue_episode_pending(self, paragraph_hash: str, source: str | None = None) -> None:
        self.pending.append({"paragraph_hash": paragraph_hash, "source": source})

    def enqueue_person_profile_refresh(
        self,
        *,
        person_id: str,
        reason: str = "",
        source_query_tool_id: str = "",
    ) -> Dict[str, Any]:
        payload = {
            "person_id": person_id,
            "reason": reason,
            "source_query_tool_id": source_query_tool_id,
        }
        self.profile_refreshes.append(payload)
        return payload


class _FakeProfileRefreshRequestStore:
    def __init__(self, request: Dict[str, Any] | None) -> None:
        self.request = request

    def get_person_profile_refresh_request(self, person_id: str) -> Dict[str, Any] | None:
        assert person_id == "person-1"
        return self.request


class _FakeVectorResult:
    @staticmethod
    async def upsert_relation_with_vector(**kwargs: Any) -> Dict[str, Any]:
        del kwargs
        raise AssertionError("relations are not expected in this test")


async def _fake_initialize() -> None:
    return None


def _build_kernel(tmp_path, config: Dict[str, Any]) -> tuple[SDKMemoryKernel, _FakeMetadataStore]:
    kernel = SDKMemoryKernel(plugin_root=tmp_path, config=config)
    metadata_store = _FakeMetadataStore()
    kernel.metadata_store = metadata_store  # type: ignore[assignment]
    kernel.vector_store = object()  # type: ignore[assignment]
    kernel.graph_store = object()  # type: ignore[assignment]
    kernel.embedding_manager = object()
    kernel.relation_write_service = _FakeVectorResult()  # type: ignore[assignment]
    kernel.initialize = _fake_initialize  # type: ignore[method-assign]
    kernel._persist = lambda *args, **kwargs: None  # type: ignore[method-assign]

    async def fake_vector_write(**kwargs: Any) -> Dict[str, Any]:
        del kwargs
        return {}

    async def fake_entity_vector(*args: Any, **kwargs: Any) -> bool:
        del args, kwargs
        return True

    kernel._ingest_service = IngestService(
        get_metadata_store=lambda: kernel.metadata_store,
        get_vector_store=lambda: kernel.vector_store,
        get_graph_store=lambda: kernel.graph_store,
        get_embedding_manager=lambda: kernel.embedding_manager,
        get_relation_write_service=lambda: kernel.relation_write_service,
        get_summary_importer=lambda: None,
        get_episode_service=lambda: None,
        is_chat_filtered=lambda **kwargs: False,
        cfg=kernel._cfg,
        tokens=kernel._tokens,
        merge_tokens=kernel._merge_tokens,
        time_meta=kernel._time_meta,
        resolve_knowledge_type=HitFilterService.resolve_knowledge_type,
        write_paragraph_vector_or_enqueue=fake_vector_write,
        ensure_entity_vector=fake_entity_vector,
        should_auto_enqueue_episode=lambda *, source_type: _should_auto_enqueue_episode(kernel, source_type),
        persist=lambda: None,
        mark_person_active=lambda person_id: None,
        enqueue_person_profile_refresh=lambda person_id, reason="": metadata_store.enqueue_person_profile_refresh(
            person_id=person_id, reason=reason
        ),
        optional_int=kernel._optional_int,
        background_scheduler=None,
        argument_tokens=kernel._argument_tokens,
    )
    kernel._person_profile_facade = PersonProfileFacade(
        cfg=kernel._cfg,
        metadata_store_getter=lambda: kernel.metadata_store,
        person_profile_service_getter=lambda: None,
        hit_filter_service_getter=lambda: None,
        active_person_timestamps=kernel._active_person_timestamps,
        background_scheduler=None,
        initialize=lambda: None,
    )
    return kernel, metadata_store


def _should_auto_enqueue_episode(kernel: SDKMemoryKernel, source_type: str) -> bool:
    if not bool(kernel._cfg("episode.enabled", True)):
        return False
    if not bool(kernel._cfg("episode.generation_enabled", True)):
        return False
    disabled_types = kernel._argument_tokens(kernel._cfg("episode.disabled_source_types", ["person_fact"]))
    return str(source_type or "").strip().lower() not in disabled_types


@pytest.mark.asyncio
async def test_person_fact_ingest_skips_episode_and_debounces_profile_refresh(tmp_path) -> None:
    kernel, metadata_store = _build_kernel(tmp_path, config={})

    result = await kernel.ingest_text(
        external_id="fact-1",
        source_type="person_fact",
        text="测试用户喜欢猫。",
        person_ids=["person-1"],
        participants=["测试用户"],
    )

    assert result["stored_ids"] == ["paragraph-1"]
    assert metadata_store.pending == []
    assert metadata_store.profile_refreshes == [
        {
            "person_id": "person-1",
            "reason": "person_fact",
            "source_query_tool_id": "",
        }
    ]


@pytest.mark.asyncio
async def test_memory_ingest_enqueues_episode_without_synchronous_processing(tmp_path) -> None:
    kernel, metadata_store = _build_kernel(tmp_path, config={})

    result = await kernel.ingest_text(
        external_id="memory-1",
        source_type="memory",
        text="用户今天讨论了绿色围巾。",
        chat_id="session-1",
    )

    assert result["stored_ids"] == ["paragraph-1"]
    assert metadata_store.pending == [
        {
            "paragraph_hash": "paragraph-1",
            "source": "memory:session-1",
        }
    ]
    assert metadata_store.profile_refreshes == []


@pytest.mark.asyncio
async def test_episode_generation_disabled_skips_all_auto_episode_enqueue(tmp_path) -> None:
    kernel, metadata_store = _build_kernel(
        tmp_path,
        config={"episode": {"generation_enabled": False}},
    )

    await kernel.ingest_text(
        external_id="memory-1",
        source_type="memory",
        text="用户今天讨论了绿色围巾。",
        chat_id="session-1",
    )

    assert metadata_store.pending == []


def test_person_profile_refresh_queue_debounce_and_retry_backoff(tmp_path) -> None:
    store = MetadataStore(data_dir=tmp_path)
    store.connect()
    try:
        first = store.enqueue_person_profile_refresh(person_id="person-1", reason="first")
        second = store.enqueue_person_profile_refresh(person_id="person-1", reason="second")

        assert first is not None
        assert second is not None
        assert second["reason"] == "second"
        assert store.fetch_person_profile_refresh_batch(limit=10, debounce_seconds=3600) == []

        ready = store.fetch_person_profile_refresh_batch(limit=10, debounce_seconds=0)
        assert [row["person_id"] for row in ready] == ["person-1"]

        assert store.mark_person_profile_refresh_running("person-1", requested_at=ready[0]["requested_at"])
        assert store.mark_person_profile_refresh_failed(
            "person-1",
            "boom",
            requested_at=ready[0]["requested_at"],
        )
        assert (
            store.fetch_person_profile_refresh_batch(
                limit=10,
                max_retry=3,
                retry_backoff_seconds=3600,
            )
            == []
        )
        retry_ready = store.fetch_person_profile_refresh_batch(
            limit=10,
            max_retry=3,
            retry_backoff_seconds=0,
        )
        assert [row["person_id"] for row in retry_ready] == ["person-1"]
        assert retry_ready[0]["retry_count"] == 1
    finally:
        store.close()


def test_has_pending_person_profile_refresh_ignores_failed_after_max_retry(tmp_path) -> None:
    kernel = SDKMemoryKernel(
        plugin_root=tmp_path,
        config={"person_profile": {"max_retry": 3}},
    )

    kernel.metadata_store = _FakeProfileRefreshRequestStore(  # type: ignore[assignment]
        {"person_id": "person-1", "status": "pending", "retry_count": 0}
    )
    assert kernel._has_pending_person_profile_refresh("person-1") is True

    kernel.metadata_store = _FakeProfileRefreshRequestStore(  # type: ignore[assignment]
        {"person_id": "person-1", "status": "running", "retry_count": 0}
    )
    assert kernel._has_pending_person_profile_refresh("person-1") is True

    kernel.metadata_store = _FakeProfileRefreshRequestStore(  # type: ignore[assignment]
        {"person_id": "person-1", "status": "failed", "retry_count": 2}
    )
    assert kernel._has_pending_person_profile_refresh("person-1") is True

    kernel.metadata_store = _FakeProfileRefreshRequestStore(  # type: ignore[assignment]
        {"person_id": "person-1", "status": "failed", "retry_count": 3}
    )
    assert kernel._has_pending_person_profile_refresh("person-1") is False
