"""MF-P0-001 验收：ToolContext memory_port 延迟初始化保证非 None。

对应 tasks.md 1.4：首次访问经 get_memory_service_port() 注入；
memory_port 可调用 observe_experience 等 MemoryServicePort 方法。
"""

from unittest.mock import MagicMock

import pytest


def _build_context() -> object:
    from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext

    return BuiltinToolRuntimeContext(engine=None)


def test_memory_port_lazy_init_non_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """首次访问 memory_port 时注入，非 None。"""
    import src.core.adapters

    fake_port = MagicMock()
    monkeypatch.setattr(src.core.adapters, "get_memory_service_port", lambda: fake_port)
    ctx = _build_context()
    assert ctx._memory_port is None
    assert ctx.memory_port is fake_port
    assert ctx._memory_port is fake_port  # 已缓存


async def test_memory_port_supports_observe_experience(monkeypatch: pytest.MonkeyPatch) -> None:
    """memory_port 可调用 observe_experience（MemoryServicePort 方法）。"""
    import src.core.adapters

    from unittest.mock import AsyncMock

    fake_port = MagicMock()
    fake_port.observe_experience = AsyncMock(return_value=MagicMock(success=True))
    monkeypatch.setattr(src.core.adapters, "get_memory_service_port", lambda: fake_port)
    ctx = _build_context()

    result = await ctx.memory_port.observe_experience(MagicMock())
    assert result.success is True
    fake_port.observe_experience.assert_called_once()


def test_memory_port_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """端口获取失败时异常传播（不静默降级为 None）。"""
    import src.core.adapters

    def _boom() -> None:
        raise RuntimeError("A_memorix 未启动，端口注入失败")

    monkeypatch.setattr(src.core.adapters, "get_memory_service_port", _boom)
    ctx = _build_context()
    with pytest.raises(RuntimeError, match="端口注入失败"):
        _ = ctx.memory_port
