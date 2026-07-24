"""gRPC Runner 服务实现 — InvokeTool 一元 RPC。

Phoenix-1 阶段返回 NOT_IMPLEMENTED，Phoenix-2 接入 SDK v4 @Tool 装饰器。
"""

from __future__ import annotations

import grpc
from src.common.logger import get_logger
from src.plugin_runtime_v2.proto import plugin_runner_pb2
from src.plugin_runtime_v2.proto.plugin_runner_pb2_grpc import PluginRunnerServicer

logger = get_logger("plugin_runtime_v2.runner.servicer")


class _PluginRunnerServicer(PluginRunnerServicer):
    """PluginRunner gRPC 服务实现 — Phoenix-1 占位。"""

    async def InvokeTool(
        self,
        request: plugin_runner_pb2.InvokeToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> plugin_runner_pb2.InvokeToolResponse:
        """Phoenix-1 占位：所有 Tool 调用返回 NOT_IMPLEMENTED。"""
        logger.info("InvokeTool 收到调用: tool_name=%s (NOT_IMPLEMENTED)", request.tool_name)
        return plugin_runner_pb2.InvokeToolResponse(
            success=False,
            error="NOT_IMPLEMENTED",
        )
