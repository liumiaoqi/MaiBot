"""MF-P0-002 验收：MemoryServicePort 契约完整。

对应 tasks.md 2.1-2.3：AMemorixMemoryServicePort 实现 get_paragraphs_by_source；
isinstance 检查通过；启动时契约检查（缺失方法 → RuntimeError 且列出缺失项）。
"""

from unittest.mock import MagicMock

from src.core.protocols import MemoryServicePort
from src.core.adapters.memory_service import (
    AMemorixMemoryServicePort,
    _find_protocol_missing_methods,
)


def test_amemorix_memory_service_port_satisfies_protocol() -> None:
    """AMemorixMemoryServicePort 满足 MemoryServicePort（runtime_checkable）。"""
    port = AMemorixMemoryServicePort(memory_service=MagicMock())
    assert isinstance(port, MemoryServicePort)
    assert _find_protocol_missing_methods(port, MemoryServicePort) == []


def test_find_missing_methods_reports_gap() -> None:
    """契约检查能列出缺失方法。"""

    class IncompletePort(AMemorixMemoryServicePort):
        async def get_paragraphs_by_source(self, source: str) -> list[dict]:  # pragma: no cover
            return []

    class BrokenPort:  # 缺失全部协议方法
        pass

    missing = _find_protocol_missing_methods(BrokenPort(), MemoryServicePort)
    assert "recall_with_intuition" in missing
    assert "get_paragraphs_by_source" in missing


async def test_get_paragraphs_by_source_delegates() -> None:
    """get_paragraphs_by_source 委托 memory_service 并返回段落列表。"""
    from unittest.mock import AsyncMock

    memory_service = MagicMock()
    memory_service.get_paragraphs_by_source = AsyncMock(
        return_value=[{"hash": "h1", "source": "chat_summary:test", "content": "段落"}],
    )
    port = AMemorixMemoryServicePort(memory_service=memory_service)

    paragraphs = await port.get_paragraphs_by_source("chat_summary:test")
    memory_service.get_paragraphs_by_source.assert_called_once_with("chat_summary:test")
    assert paragraphs[0]["hash"] == "h1"


async def test_memory_service_get_paragraphs_by_source_invokes_component() -> None:
    """MemoryService.get_paragraphs_by_source 走 _invoke 组件路由，返回 [] 兜底。"""
    from unittest.mock import AsyncMock

    from src.services.memory_service import MemoryService

    service = MemoryService()
    host = MagicMock()
    host.invoke = AsyncMock(
        return_value=[{"hash": "h1", "source": "chat_summary:test"}],
    )
    service._get_host_service = MagicMock(return_value=host)

    result = await service.get_paragraphs_by_source("chat_summary:test")
    assert result == [{"hash": "h1", "source": "chat_summary:test"}]
    host.invoke.assert_called_once_with(
        "metadata_get_paragraphs_by_source", {"source": "chat_summary:test"},
        timeout_ms=30000,
    )


def test_get_memory_service_port_contract_check_passes() -> None:
    """启动时契约检查通过（AMemorixMemoryServicePort 满足 Protocol）。"""
    from src.core.adapters.memory_service import (
        get_memory_service_port,
        reset_memory_service_port,
    )

    reset_memory_service_port()
    try:
        port = get_memory_service_port()
        assert isinstance(port, MemoryServicePort)
    finally:
        reset_memory_service_port()
