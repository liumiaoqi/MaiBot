from types import SimpleNamespace

import numpy as np
import pytest

from src.A_memorix.core.strategies.base import ChunkContext, KnowledgeType, ProcessedChunk, SourceInfo
from src.A_memorix.core.utils.web_import_manager import (
    ImportChunkRecord,
    ImportFileRecord,
    ImportTaskManager,
    ImportTaskRecord,
)


class _DummyMetadataStore:
    def __init__(self) -> None:
        self.paragraphs: list[dict[str, object]] = []
        self.entities: list[str] = []
        self.relations: list[tuple[str, str, str]] = []

    def add_paragraph(self, **kwargs):
        self.paragraphs.append(dict(kwargs))
        return f"paragraph-{len(self.paragraphs)}"

    def add_entity(self, *, name: str, source_paragraph: str = "") -> str:
        del source_paragraph
        self.entities.append(name)
        return f"entity-{name}"

    def add_relation(self, *, subject: str, predicate: str, obj: str, **kwargs) -> str:
        del kwargs
        self.relations.append((subject, predicate, obj))
        return f"relation-{len(self.relations)}"

    def set_relation_vector_state(self, rel_hash: str, state: str) -> None:
        del rel_hash, state


class _DummyGraphStore:
    def __init__(self) -> None:
        self.nodes: list[list[str]] = []
        self.edges: list[list[tuple[str, str]]] = []

    def add_nodes(self, nodes):
        self.nodes.append(list(nodes))

    def add_edges(self, edges, relation_hashes=None):
        del relation_hashes
        self.edges.append(list(edges))


class _DummyVectorStore:
    def __contains__(self, item: str) -> bool:
        del item
        return False

    def add(self, vectors, ids):
        del vectors, ids


class _DummyEmbeddingManager:
    async def encode(self, text: str) -> np.ndarray:
        del text
        return np.ones(4, dtype=np.float32)


def _build_manager() -> tuple[ImportTaskManager, _DummyMetadataStore]:
    metadata_store = _DummyMetadataStore()
    plugin = SimpleNamespace(
        metadata_store=metadata_store,
        graph_store=_DummyGraphStore(),
        vector_store=_DummyVectorStore(),
        embedding_manager=_DummyEmbeddingManager(),
        relation_write_service=None,
        get_config=lambda key, default=None: default,
        _is_embedding_degraded=lambda: False,
        _allow_metadata_only_write=lambda: True,
        write_paragraph_vector_or_enqueue=None,
    )
    manager = ImportTaskManager(plugin)
    return manager, metadata_store


def _build_progress_task(task_id: str, total_chunks: int = 2) -> ImportTaskRecord:
    file_record = ImportFileRecord(
        file_id="file-1",
        name="demo.txt",
        source_kind="paste",
        input_mode="text",
        total_chunks=total_chunks,
        chunks=[
            ImportChunkRecord(chunk_id=f"chunk-{index}", index=index, chunk_type="text")
            for index in range(total_chunks)
        ],
    )
    return ImportTaskRecord(task_id=task_id, source="paste", params={}, files=[file_record])


def _build_chunk(data) -> ProcessedChunk:
    return ProcessedChunk(
        type=KnowledgeType.FACTUAL,
        source=SourceInfo(file="demo.txt", offset_start=0, offset_end=4),
        chunk=ChunkContext(chunk_id="chunk-1", index=0, text="Alice 持有地图"),
        data=data,
    )


@pytest.mark.asyncio
async def test_persist_processed_chunk_rejects_non_object_before_paragraph_write() -> None:
    manager, metadata_store = _build_manager()
    file_record = SimpleNamespace(source_path="", source_kind="paste", name="demo.txt")

    with pytest.raises(ValueError, match="分块抽取结果 必须返回 JSON 对象"):
        await manager._persist_processed_chunk(file_record, _build_chunk(["bad"]))

    assert metadata_store.paragraphs == []


@pytest.mark.asyncio
async def test_chunk_terminal_progress_uses_successful_chunks_only() -> None:
    manager, _ = _build_manager()

    task = _build_progress_task("task-fail-then-complete")
    manager._tasks[task.task_id] = task

    await manager._set_chunk_failed(task.task_id, "file-1", "chunk-0", "boom")
    await manager._set_chunk_completed(task.task_id, "file-1", "chunk-1")

    file_record = task.files[0]
    assert file_record.done_chunks == 1
    assert file_record.failed_chunks == 1
    assert file_record.progress == pytest.approx(0.5)
    assert task.progress == pytest.approx(0.5)

    reverse_task = _build_progress_task("task-complete-then-fail")
    manager._tasks[reverse_task.task_id] = reverse_task

    await manager._set_chunk_completed(reverse_task.task_id, "file-1", "chunk-0")
    await manager._set_chunk_failed(reverse_task.task_id, "file-1", "chunk-1", "boom")

    reverse_file = reverse_task.files[0]
    assert reverse_file.done_chunks == 1
    assert reverse_file.failed_chunks == 1
    assert reverse_file.progress == pytest.approx(0.5)
    assert reverse_task.progress == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_cancelled_chunks_do_not_increase_file_progress() -> None:
    manager, _ = _build_manager()
    task = _build_progress_task("task-cancelled-progress", total_chunks=3)
    manager._tasks[task.task_id] = task

    await manager._set_chunk_completed(task.task_id, "file-1", "chunk-0")
    await manager._set_chunk_cancelled(task.task_id, "file-1", "chunk-1", "任务已取消")

    file_record = task.files[0]
    assert file_record.done_chunks == 1
    assert file_record.cancelled_chunks == 1
    assert file_record.progress == pytest.approx(1 / 3)
    assert task.progress == pytest.approx(1 / 3)


@pytest.mark.asyncio
async def test_persist_processed_chunk_skips_invalid_nested_items() -> None:
    manager, metadata_store = _build_manager()
    file_record = SimpleNamespace(source_path="", source_kind="paste", name="demo.txt")

    await manager._persist_processed_chunk(
        file_record,
        _build_chunk(
            {
                "triples": [{"subject": "Alice", "predicate": "持有", "object": "地图"}, ["bad"]],
                "relations": [{"subject": "Alice", "predicate": "", "object": "地图"}],
                "entities": ["Alice", {"name": "地图"}, ["bad"]],
            }
        ),
    )

    assert len(metadata_store.paragraphs) == 1
    assert set(metadata_store.entities) >= {"Alice", "地图"}
    assert metadata_store.relations == [("Alice", "持有", "地图")]
