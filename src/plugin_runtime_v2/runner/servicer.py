"""gRPC Runner 服务实现 — InvokeTool 一元 RPC。

Phoenix-1 阶段返回 NOT_IMPLEMENTED，Phoenix-2 接入 SDK v4 @Tool 装饰器。
"""

from __future__ import annotations

import json

import grpc
from src.common.logger import get_logger
from src.plugin_runtime_v2.proto import plugin_runner_pb2
from src.plugin_runtime_v2.proto.plugin_runner_pb2_grpc import PluginRunnerServicer
from src.plugin_runtime_v2.runner.tool_router import ToolRouter

logger = get_logger("plugin_runtime_v2.runner.servicer")


class _PluginRunnerServicer(PluginRunnerServicer):
    """PluginRunner gRPC 服务实现。

    Phoenix-1 阶段返回 NOT_IMPLEMENTED，Phoenix-2 通过 ToolRouter 执行路由。
    """

    def __init__(self) -> None:
        self._tool_router: ToolRouter | None = None
        self._shutting_down: bool = False

    def set_tool_router(self, router: ToolRouter) -> None:
        """注入 ToolRouter（由 RunnerEndpoint 在启动时调用）。"""
        self._tool_router = router

    async def InvokeTool(
        self,
        request: plugin_runner_pb2.InvokeToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> plugin_runner_pb2.InvokeToolResponse:
        """根据 tool_name 执行路由。"""
        if self._shutting_down:
            return plugin_runner_pb2.InvokeToolResponse(
                success=False, error="SHUTTING_DOWN",
            )

        if self._tool_router is None:
            logger.info(
                "InvokeTool 收到调用但 ToolRouter 未注入: tool_name=%s",
                request.tool_name,
            )
            return plugin_runner_pb2.InvokeToolResponse(
                success=False, error="NOT_IMPLEMENTED",
            )

        try:
            args = json.loads(request.args) if request.args else {}
        except json.JSONDecodeError:
            return plugin_runner_pb2.InvokeToolResponse(
                success=False, error="INVALID_ARGS_JSON",
            )

        return await self._tool_router.execute(
            tool_name=request.tool_name,
            args=args,
            timeout_ms=request.timeout_ms or 30000,
        )
