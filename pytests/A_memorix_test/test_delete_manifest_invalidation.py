from pathlib import Path
from typing import Any
from types import SimpleNamespace

import pytest

from src.A_memorix.core.runtime.admin.delete import DeleteAdminHandler
from src.A_memorix.core.runtime.sdk_memory_kernel import SDKMemoryKernel


class _DummyImportTaskManager:
    def __init__(self) -> None:
        self.sources: list[str] = []

    async def invalidate_manifest_for_sources(self, sources: list[str]) -> dict[str, Any]:
        self.sources.extend(sources)
        return {"removed_count": len(sources), "removed_keys": [f"key:{source}" for source in sources]}


@pytest.mark.asyncio
async def test_memory_delete_admin_execute_invalidates_import_manifest(monkeypatch) -> None:
    kernel = SDKMemoryKernel(plugin_root=Path.cwd(), config={})
    manager = _DummyImportTaskManager()
    kernel.import_task_manager = manager  # type: ignore[assignment]

    async def fake_initialize() -> None:
        return None

    async def fake_execute_delete_action(**kwargs):
        assert kwargs["mode"] == "source"
        assert kwargs["selector"] == {"sources": ["web_import:demo.txt"]}
        return {"success": True, "sources": ["web_import:demo.txt"], "deleted_source_count": 1}

    async def fake_invalidate_import_manifest_for_sources(result):
        await manager.invalidate_manifest_for_sources(result["sources"])

    monkeypatch.setattr(kernel, "initialize", fake_initialize)
    kernel._delete_service = SimpleNamespace(
        execute_delete_action=fake_execute_delete_action,
        invalidate_import_manifest_for_sources=fake_invalidate_import_manifest_for_sources,
    )

    result = await DeleteAdminHandler(kernel).handle(
        action="execute",
        mode="source",
        selector={"sources": ["web_import:demo.txt"]},
    )

    assert manager.sources == ["web_import:demo.txt"]
    assert result["success"] is True
