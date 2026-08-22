"""butler.py 管家工具集成测试。

验证 handle_switch_primary / handle_activate_agent 的成功/失败路径，
确保返回的 ToolExecutionResult 字段正确（tool_name/success/error_message/content），
不抛 TypeError/AttributeError。

接线四连问④：测试走生产路径——通过 mock from_context + _is_butler_agent 触发完整 butler 调用链。
"""


from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tooling import ToolExecutionResult, ToolInvocation
from src.maisaka.builtin_tool import butler


def _make_invocation(tool_name: str, agent_id: str = "") -> ToolInvocation:
    """构造测试用 ToolInvocation。"""

    return ToolInvocation(
        tool_name=tool_name,
        arguments={"agent_id": agent_id} if agent_id else {},
    )


def _make_mock_tool_ctx(is_butler: bool = True, orchestrator_raises: bool = False):
    """构造 mock BuiltinToolRuntimeContext + mock orchestrator。"""

    mock_orchestrator = MagicMock()
    mock_orchestrator.switch_primary_speaker = AsyncMock(
        side_effect=RuntimeError("orchestrator error") if orchestrator_raises else None
    )
    mock_orchestrator.activate_agent = AsyncMock(
        side_effect=RuntimeError("orchestrator error") if orchestrator_raises else None
    )

    mock_runtime = MagicMock()
    mock_runtime._agent_orchestrator = mock_orchestrator

    mock_tool_ctx = MagicMock()
    mock_tool_ctx.runtime = mock_runtime
    mock_tool_ctx.current_agent_id = "butler_rita"
    return mock_tool_ctx


class TestHandleSwitchPrimary:
    """handle_switch_primary 成功/失败路径测试。"""

    @pytest.mark.asyncio
    async def test_success_path(self):
        """成功路径：管家调用 + 有效 agent_id + orchestrator 不抛异常 → build_success_result。"""

        mock_tool_ctx = _make_mock_tool_ctx(is_butler=True)
        invocation = _make_invocation("switch_primary", "agent_aria")

        with patch.object(butler, "_is_butler_agent", return_value=True), \
             patch.object(
                 butler.BuiltinToolRuntimeContext, "from_context",
                 return_value=mock_tool_ctx,
             ):
            result = await butler.handle_switch_primary(invocation, MagicMock())

        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "switch_primary"
        assert result.success is True
        assert "agent_aria" in result.content

    @pytest.mark.asyncio
    async def test_not_butler_agent(self):
        """失败路径 1：非管家调用 → build_failure_result。"""

        mock_tool_ctx = _make_mock_tool_ctx()
        invocation = _make_invocation("switch_primary", "agent_aria")

        with patch.object(butler, "_is_butler_agent", return_value=False), \
             patch.object(
                 butler.BuiltinToolRuntimeContext, "from_context",
                 return_value=mock_tool_ctx,
             ):
            result = await butler.handle_switch_primary(invocation, MagicMock())

        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "switch_primary"
        assert result.success is False
        assert "管家丽塔" in result.error_message

    @pytest.mark.asyncio
    async def test_empty_agent_id(self):
        """失败路径 2：agent_id 为空 → build_failure_result。"""

        mock_tool_ctx = _make_mock_tool_ctx()
        invocation = _make_invocation("switch_primary", "")

        with patch.object(butler, "_is_butler_agent", return_value=True), \
             patch.object(
                 butler.BuiltinToolRuntimeContext, "from_context",
                 return_value=mock_tool_ctx,
             ):
            result = await butler.handle_switch_primary(invocation, MagicMock())

        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "switch_primary"
        assert result.success is False
        assert "agent_id" in result.error_message

    @pytest.mark.asyncio
    async def test_orchestrator_raises(self):
        """失败路径 3：orchestrator 抛异常 → build_failure_result(error_message=str(exc))。"""

        mock_tool_ctx = _make_mock_tool_ctx(orchestrator_raises=True)
        invocation = _make_invocation("switch_primary", "agent_aria")

        with patch.object(butler, "_is_butler_agent", return_value=True), \
             patch.object(
                 butler.BuiltinToolRuntimeContext, "from_context",
                 return_value=mock_tool_ctx,
             ):
            result = await butler.handle_switch_primary(invocation, MagicMock())

        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "switch_primary"
        assert result.success is False
        assert "orchestrator error" in result.error_message


class TestHandleActivateAgent:
    """handle_activate_agent 成功/失败路径测试。"""

    @pytest.mark.asyncio
    async def test_success_path(self):
        """成功路径：管家调用 + 有效 agent_id → build_success_result。"""

        mock_tool_ctx = _make_mock_tool_ctx(is_butler=True)
        invocation = _make_invocation("activate_agent", "agent_aria")

        with patch.object(butler, "_is_butler_agent", return_value=True), \
             patch.object(
                 butler.BuiltinToolRuntimeContext, "from_context",
                 return_value=mock_tool_ctx,
             ):
            result = await butler.handle_activate_agent(invocation, MagicMock())

        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "activate_agent"
        assert result.success is True
        assert "agent_aria" in result.content

    @pytest.mark.asyncio
    async def test_not_butler_agent(self):
        """失败路径 1：非管家调用 → build_failure_result。"""

        mock_tool_ctx = _make_mock_tool_ctx()
        invocation = _make_invocation("activate_agent", "agent_aria")

        with patch.object(butler, "_is_butler_agent", return_value=False), \
             patch.object(
                 butler.BuiltinToolRuntimeContext, "from_context",
                 return_value=mock_tool_ctx,
             ):
            result = await butler.handle_activate_agent(invocation, MagicMock())

        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "activate_agent"
        assert result.success is False
        assert "管家丽塔" in result.error_message

    @pytest.mark.asyncio
    async def test_orchestrator_raises(self):
        """失败路径 2：orchestrator 抛异常 → build_failure_result。"""

        mock_tool_ctx = _make_mock_tool_ctx(orchestrator_raises=True)
        invocation = _make_invocation("activate_agent", "agent_aria")

        with patch.object(butler, "_is_butler_agent", return_value=True), \
             patch.object(
                 butler.BuiltinToolRuntimeContext, "from_context",
                 return_value=mock_tool_ctx,
             ):
            result = await butler.handle_activate_agent(invocation, MagicMock())

        assert isinstance(result, ToolExecutionResult)
        assert result.tool_name == "activate_agent"
        assert result.success is False
        assert "orchestrator error" in result.error_message