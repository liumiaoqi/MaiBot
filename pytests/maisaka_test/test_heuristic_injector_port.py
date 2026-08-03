"""MF-P0-001 验收：HeuristicMemoryInjector 移除 hasattr 防御检查。

对应 tasks.md 1.2：memory_port 延迟初始化非 None；直接调用 recall_with_intuition
不抛 AttributeError（MemoryServicePort Protocol 已声明该方法）；异常时降级 search。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.adapters.llm_service_port import set_llm_service

# heuristic_injector 模块级实例化（CLAUDE.md 踩坑 #1）在 import 时调用 get_llm_service()——
# 必须先注册再 import，否则收集期 RuntimeError。
set_llm_service(MagicMock())

from src.maisaka.memory.heuristic_injector import HeuristicMemoryInjector  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_llm_service():
    """模块级实例化已占用注册；测试内构造显式传 llm_service，无需干预。"""
    yield


def test_memory_port_lazy_init_non_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """延迟初始化：首次访问经 get_memory_service_port() 获取，非 None。"""
    import src.core.adapters

    fake_port = MagicMock()
    monkeypatch.setattr(src.core.adapters, "get_memory_service_port", lambda: fake_port)
    injector = HeuristicMemoryInjector(llm_service=MagicMock())
    assert injector._memory_port is None
    assert injector.memory_port is fake_port


async def test_recall_with_intuition_direct_call_no_hasattr_gate() -> None:
    """直接调用 recall_with_intuition，无 hasattr 防御检查。"""
    port = MagicMock()
    port.recall_with_intuition = AsyncMock(return_value=MagicMock(success=True))
    injector = HeuristicMemoryInjector(llm_service=MagicMock())
    injector._memory_port = port

    result = await injector._search_with_intuition_fallback(
        impression="今天 天气 不错",
        context_text="上下文",
        limit=3,
        cross_chat_enabled=True,
        chat_id="",
        user_id="",
        group_id="",
    )
    port.recall_with_intuition.assert_called_once()
    call_kwargs = port.recall_with_intuition.call_args.kwargs
    assert call_kwargs["seeds"] == ["今天", "天气", "不错"]
    assert call_kwargs["context_text"] == "上下文"
    assert result.success is True


async def test_recall_with_intuition_exception_falls_back_to_search() -> None:
    """recall_with_intuition 抛异常 → 降级到 search（不抛 AttributeError）。"""
    port = MagicMock()
    port.recall_with_intuition = AsyncMock(side_effect=RuntimeError("端口未就绪"))
    port.search = AsyncMock(return_value=MagicMock(success=True))
    injector = HeuristicMemoryInjector(llm_service=MagicMock())
    injector._memory_port = port

    result = await injector._search_with_intuition_fallback(
        impression="印象",
        context_text="上下文",
        limit=3,
        cross_chat_enabled=False,
        chat_id="chat_1",
        user_id="u1",
        group_id="g1",
    )
    port.search.assert_called_once()
    assert result.success is True


def test_memory_port_initialization_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    """端口获取失败时异常向上传播（不静默跳过检索）。"""
    import src.core.adapters

    def _boom() -> None:
        raise RuntimeError("A_memorix 未启动，端口注入失败")

    monkeypatch.setattr(src.core.adapters, "get_memory_service_port", _boom)
    injector = HeuristicMemoryInjector(llm_service=MagicMock())
    with pytest.raises(RuntimeError, match="端口注入失败"):
        _ = injector.memory_port
