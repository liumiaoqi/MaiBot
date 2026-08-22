"""BuiltinToolRuntimeContext.from_context 单元测试。

验证从 ToolExecutionContext 构造 BuiltinToolRuntimeContext 的正确性。
覆盖正常路径（含 runtime/agent_id）+ 边界路径（None ctx / 空 metadata）。
"""


from unittest.mock import MagicMock

import pytest

from src.core.tooling import ToolExecutionContext
from src.maisaka.builtin_tool.context import BuiltinToolRuntimeContext


class TestFromContext:
    """from_context 类方法测试。"""

    def test_from_context_with_runtime_and_agent_id(self):
        """正常路径：metadata 含 runtime + agent_id，构造实例字段正确。"""

        mock_runtime = MagicMock(name="maisaka_runtime")
        ctx = ToolExecutionContext(
            session_id="test_session",
            metadata={"runtime": mock_runtime, "agent_id": "butler_rita"},
        )

        result = BuiltinToolRuntimeContext.from_context(ctx)

        assert result.runtime is mock_runtime
        assert result.current_agent_id == "butler_rita"

    def test_from_context_without_runtime(self):
        """边界路径：metadata 不含 runtime，runtime 为 None 但不抛异常。"""

        ctx = ToolExecutionContext(
            session_id="test_session",
            metadata={"agent_id": "agent_a"},
        )

        result = BuiltinToolRuntimeContext.from_context(ctx)

        assert result.runtime is None
        assert result.current_agent_id == "agent_a"

    def test_from_context_without_agent_id(self):
        """边界路径：metadata 不含 agent_id，current_agent_id 为空字符串。"""

        mock_runtime = MagicMock(name="maisaka_runtime")
        ctx = ToolExecutionContext(
            session_id="test_session",
            metadata={"runtime": mock_runtime},
        )

        result = BuiltinToolRuntimeContext.from_context(ctx)

        assert result.runtime is mock_runtime
        assert result.current_agent_id == ""

    def test_from_context_empty_metadata(self):
        """边界路径：metadata 为空字典，runtime=None, agent_id=''。"""

        ctx = ToolExecutionContext(session_id="test_session", metadata={})

        result = BuiltinToolRuntimeContext.from_context(ctx)

        assert result.runtime is None
        assert result.current_agent_id == ""

    def test_from_context_none_ctx_raises(self):
        """异常路径：ctx 为 None 时抛 ValueError。"""

        with pytest.raises(ValueError, match="ToolExecutionContext 为 None"):
            BuiltinToolRuntimeContext.from_context(None)

    def test_from_context_returns_builtintool_instance(self):
        """类型验证：返回值是 BuiltinToolRuntimeContext 实例。"""

        ctx = ToolExecutionContext(
            metadata={"runtime": MagicMock(), "agent_id": "x"},
        )

        result = BuiltinToolRuntimeContext.from_context(ctx)

        assert isinstance(result, BuiltinToolRuntimeContext)