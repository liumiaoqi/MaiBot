"""V2GatewaySupervisor 单元测试。

覆盖测试接缝 5（gRPC 调用）。
用 mock gRPC stub，不依赖真实插件进程。
"""


import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.plugin_runtime_v2.host.gateway_supervisor import V2GatewaySupervisor


class TestV2GatewaySupervisor:
    """4.9 V2GatewaySupervisor gRPC 调用测试。"""

    @pytest.fixture
    def supervisor(self):
        return V2GatewaySupervisor(
            plugin_id="test_plugin",
            runner_listen_address="127.0.0.1:50051",
            tool_name="napcat.send_text",
        )

    @pytest.mark.asyncio
    async def test_invoke_triggers_grpc_call(self, supervisor):
        """invoke_message_gateway 触发 gRPC InvokeTool 调用。"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = json.dumps({"message_id": "msg_123"})
        mock_response.error = ""

        mock_stub = MagicMock()
        mock_stub.InvokeTool = AsyncMock(return_value=mock_response)

        supervisor._channel = MagicMock()
        supervisor._stub = mock_stub

        result = await supervisor.invoke_message_gateway(
            plugin_id="test_plugin",
            component_name="qq_gateway",
            args={"message": {"text": "hello"}, "session_id": "s1"},
            timeout_ms=30000,
        )

        mock_stub.InvokeTool.assert_called_once()
        request = mock_stub.InvokeTool.call_args[0][0]
        assert request.tool_name == "napcat.send_text"
        assert "message" in json.loads(request.args)
        assert request.timeout_ms == 30000
        assert result == {"message_id": "msg_123"}

    @pytest.mark.asyncio
    async def test_args_passed_correctly(self, supervisor):
        """args 正确传递为 JSON 字符串。"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = "{}"
        mock_response.error = ""

        mock_stub = MagicMock()
        mock_stub.InvokeTool = AsyncMock(return_value=mock_response)
        supervisor._channel = MagicMock()
        supervisor._stub = mock_stub

        test_args = {"message": {"text": "测试消息"}, "session_id": "s1"}
        await supervisor.invoke_message_gateway(
            plugin_id="test_plugin",
            component_name="qq_gateway",
            args=test_args,
        )

        request = mock_stub.InvokeTool.call_args[0][0]
        parsed = json.loads(request.args)
        assert parsed == test_args

    @pytest.mark.asyncio
    async def test_grpc_failure_raises(self, supervisor):
        """gRPC 调用失败时异常透传（不吞错）。"""
        import grpc

        mock_stub = MagicMock()
        mock_stub.InvokeTool = AsyncMock(
            side_effect=grpc.aio.AioRpcError(
                code=grpc.StatusCode.UNAVAILABLE,
                initial_metadata=grpc.aio.Metadata(),
                trailing_metadata=grpc.aio.Metadata(),
                details="Runner unavailable",
            )
        )
        supervisor._channel = MagicMock()
        supervisor._stub = mock_stub

        with pytest.raises(grpc.aio.AioRpcError):
            await supervisor.invoke_message_gateway(
                plugin_id="test_plugin",
                component_name="qq_gateway",
                args={"message": {"text": "hello"}},
            )

    @pytest.mark.asyncio
    async def test_tool_failure_raises_runtime_error(self, supervisor):
        """Tool 返回 success=False 时抛 RuntimeError。"""
        mock_response = MagicMock()
        mock_response.success = False
        mock_response.result = ""
        mock_response.error = "send failed"

        mock_stub = MagicMock()
        mock_stub.InvokeTool = AsyncMock(return_value=mock_response)
        supervisor._channel = MagicMock()
        supervisor._stub = mock_stub

        with pytest.raises(RuntimeError, match="send failed"):
            await supervisor.invoke_message_gateway(
                plugin_id="test_plugin",
                component_name="qq_gateway",
                args={"message": {"text": "hello"}},
            )

    @pytest.mark.asyncio
    async def test_timeout_passed_correctly(self, supervisor):
        """超时参数 timeout_ms 正确传递。"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = "{}"
        mock_response.error = ""

        mock_stub = MagicMock()
        mock_stub.InvokeTool = AsyncMock(return_value=mock_response)
        supervisor._channel = MagicMock()
        supervisor._stub = mock_stub

        await supervisor.invoke_message_gateway(
            plugin_id="test_plugin",
            component_name="qq_gateway",
            args={},
            timeout_ms=5000,
        )

        request = mock_stub.InvokeTool.call_args[0][0]
        assert request.timeout_ms == 5000
        # gRPC timeout 也应正确传递
        timeout_arg = mock_stub.InvokeTool.call_args.kwargs.get("timeout")
        assert timeout_arg == 5.0

    @pytest.mark.asyncio
    async def test_empty_result_returns_empty_dict(self, supervisor):
        """空 result 字符串返回空 dict。"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = ""
        mock_response.error = ""

        mock_stub = MagicMock()
        mock_stub.InvokeTool = AsyncMock(return_value=mock_response)
        supervisor._channel = MagicMock()
        supervisor._stub = mock_stub

        result = await supervisor.invoke_message_gateway(
            plugin_id="test_plugin",
            component_name="qq_gateway",
            args={},
        )
        assert result == {}

    @pytest.mark.asyncio
    async def test_none_args_handled(self, supervisor):
        """args=None 时不报错。"""
        mock_response = MagicMock()
        mock_response.success = True
        mock_response.result = "{}"
        mock_response.error = ""

        mock_stub = MagicMock()
        mock_stub.InvokeTool = AsyncMock(return_value=mock_response)
        supervisor._channel = MagicMock()
        supervisor._stub = mock_stub

        result = await supervisor.invoke_message_gateway(
            plugin_id="test_plugin",
            component_name="qq_gateway",
            args=None,
        )
        assert result == {}
        request = mock_stub.InvokeTool.call_args[0][0]
        assert json.loads(request.args) == {}