"""ToolRegistry 共享层测试（ZG-20——v2 插件工具跨会话可见）。

覆盖：全局单例 / shared 可见性 / 本层优先去重 / invoke 回退 / close 隔离。
"""

import asyncio

from src.core.tooling import (
    ToolExecutionResult,
    ToolInvocation,
    ToolRegistry,
    ToolSpec,
    get_global_tool_registry,
)


class FakeProvider:
    """测试用假 Provider。"""

    def __init__(self, name: str, tools: list[str]) -> None:
        self.provider_name = name
        self._tools = tools
        self.closed = False

    async def list_tools(self, context=None) -> list[ToolSpec]:
        return [
            ToolSpec(name=t, description=f"{self.provider_name} 的 {t}", provider_name=self.provider_name, enabled=True)
            for t in self._tools
        ]

    async def invoke(self, invocation: ToolInvocation, context=None) -> ToolExecutionResult:
        return ToolExecutionResult(tool_name=invocation.tool_name, success=True)

    async def close(self) -> None:
        self.closed = True


def test_global_registry_singleton() -> None:
    """全局共享注册表是单例。"""
    assert get_global_tool_registry() is get_global_tool_registry()


async def _list_names(registry: ToolRegistry) -> list[str]:
    return [spec.name for spec in await registry.list_tools()]


async def test_session_registry_sees_shared_tools() -> None:
    """会话 registry 通过 shared 层看到全局（v2）工具。"""
    shared = ToolRegistry()
    shared.register_provider(FakeProvider("v2-plugin", ["v2_tool_a", "v2_tool_b"]))

    session = ToolRegistry(shared=shared)
    session.register_provider(FakeProvider("builtin", ["builtin_tool"]))

    names = await _list_names(session)
    assert "builtin_tool" in names
    assert "v2_tool_a" in names  # ZG-20：v2 工具跨会话可见
    assert "v2_tool_b" in names


async def test_local_priority_on_name_conflict() -> None:
    """本层与 shared 同名工具——本层优先。"""
    shared = ToolRegistry()
    shared.register_provider(FakeProvider("v2-plugin", ["conflict_tool"]))

    session = ToolRegistry(shared=shared)
    session.register_provider(FakeProvider("builtin", ["conflict_tool"]))

    names = await _list_names(session)
    assert names.count("conflict_tool") == 1  # 去重

    # 调用命中本层 provider（provider_name 是 builtin 的假名）
    result = await session.invoke(ToolInvocation(tool_name="conflict_tool"))
    assert result.success


async def test_invoke_falls_back_to_shared() -> None:
    """本层没有该工具时 invoke 回退 shared 层。"""
    shared = ToolRegistry()
    shared.register_provider(FakeProvider("v2-plugin", ["only_in_v2"]))

    session = ToolRegistry(shared=shared)

    result = await session.invoke(ToolInvocation(tool_name="only_in_v2"))
    assert result.success

    # 两边都没有——返回失败结果而不是抛异常
    missing = await session.invoke(ToolInvocation(tool_name="nope"))
    assert not missing.success


async def test_close_only_closes_local_providers() -> None:
    """会话 close 不关闭 shared 层的全局 provider（归全局管理）。"""
    shared = ToolRegistry()
    shared_provider = FakeProvider("v2-plugin", ["v2_tool"])
    shared.register_provider(shared_provider)

    session = ToolRegistry(shared=shared)
    local_provider = FakeProvider("builtin", ["builtin_tool"])
    session.register_provider(local_provider)

    await session.close()

    assert local_provider.closed
    assert not shared_provider.closed  # shared 层不受会话 close 影响
    assert "v2_tool" in await _list_names(shared)


async def test_unregister_shared_isolated() -> None:
    """本层注销不影响 shared 层。"""
    shared = ToolRegistry()
    shared.register_provider(FakeProvider("v2-plugin", ["v2_tool"]))

    session = ToolRegistry(shared=shared)
    session.register_provider(FakeProvider("builtin", ["builtin_tool"]))
    session.unregister_provider("builtin")

    names = await _list_names(session)
    assert "builtin_tool" not in names
    assert "v2_tool" in names  # shared 层不受本层注销影响


def test_async_tests_harness() -> None:
    """pytest-asyncio 未启用时用 asyncio.run 兜底执行。"""
    asyncio.run(test_session_registry_sees_shared_tools())
    asyncio.run(test_local_priority_on_name_conflict())
    asyncio.run(test_invoke_falls_back_to_shared())
    asyncio.run(test_close_only_closes_local_providers())
    asyncio.run(test_unregister_shared_isolated())
