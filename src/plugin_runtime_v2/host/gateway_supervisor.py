"""V2 网关 Supervisor — 通过 gRPC 调用插件 Tool 的消息网关适配器。

实现 _GatewaySupervisorProtocol，使 PluginPlatformDriver 可通过 gRPC
调用插件声明的发送 Tool（如 napcat.send_text）。
"""


import json
from typing import Any

import grpc

from src.common.logger import get_logger
from src.plugin_runtime_v2.proto import plugin_runner_pb2
from src.plugin_runtime_v2.proto.plugin_runner_pb2_grpc import PluginRunnerStub

logger = get_logger("plugin_runtime_v2.host.gateway_supervisor")


class V2GatewaySupervisor:
    """通过 gRPC 调用插件 Tool 的网关 supervisor 适配器。

    实现 _GatewaySupervisorProtocol，由 V2GatewayRegistrar 在网关就绪时创建，
    注入到 PluginPlatformDriver 中。发送消息时 PluginPlatformDriver 调用
    invoke_message_gateway，本类通过 gRPC InvokeTool RPC 调用插件的发送 Tool。
    """

    def __init__(
        self,
        plugin_id: str,
        runner_listen_address: str,
        tool_name: str,
    ) -> None:
        self._plugin_id = plugin_id
        self._runner_listen_address = runner_listen_address
        self._tool_name = tool_name
        self._channel: grpc.aio.Channel | None = None
        self._stub: PluginRunnerStub | None = None

    async def _ensure_channel(self) -> None:
        """惰性创建 gRPC 通道和 stub。"""
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(
                self._runner_listen_address,
            )
            self._stub = PluginRunnerStub(self._channel)

    async def invoke_message_gateway(
        self,
        plugin_id: str,
        component_name: str,
        args: dict[str, Any] | None = None,
        timeout_ms: int = 30000,
    ) -> Any:
        """通过 gRPC 调用插件的发送 Tool。

        Args:
            plugin_id: 插件 ID（与构造时一致，用于日志）。
            component_name: 网关组件名称（用于日志，Tool 调用用 tool_name）。
            args: 调用参数，含 args["message"]（SessionMessage dict）。
            timeout_ms: 超时时间（毫秒）。

        Returns:
            Tool 执行结果（dict）。

        Raises:
            grpc.aio.AioRpcError: gRPC 调用失败时透传（由 PluginPlatformDriver 捕获）。
        """
        await self._ensure_channel()
        if self._stub is None:
            raise ConnectionError(
                f"V2GatewaySupervisor stub 未初始化 (plugin={self._plugin_id})"
            )

        tool_args = args or {}
        request = plugin_runner_pb2.InvokeToolRequest(
            tool_name=self._tool_name,
            args=json.dumps(tool_args, ensure_ascii=False),
            timeout_ms=timeout_ms,
        )

        logger.debug(
            "V2GatewaySupervisor: 调用 InvokeTool plugin=%s tool=%s component=%s",
            self._plugin_id, self._tool_name, component_name,
        )

        response: plugin_runner_pb2.InvokeToolResponse = await self._stub.InvokeTool(
            request,
            timeout=timeout_ms / 1000.0 if timeout_ms > 0 else 30.0,
        )

        if not response.success:
            raise RuntimeError(
                f"网关 Tool 调用失败: plugin={self._plugin_id} "
                f"tool={self._tool_name} error={response.error}"
            )

        try:
            return json.loads(response.result) if response.result else {}
        except json.JSONDecodeError:
            return {"raw_result": response.result}

    async def close(self) -> None:
        """关闭 gRPC 通道。"""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None