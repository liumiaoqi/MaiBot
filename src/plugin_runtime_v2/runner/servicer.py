"""gRPC Runner 服务实现 — InvokeTool 一元 RPC。

Phoenix-1 阶段返回 NOT_IMPLEMENTED，Phoenix-2 接入 SDK v4 @Tool 装饰器。
"""


import json

import grpc
from src.common.logger import get_logger
from src.plugin_runtime_v2.proto import plugin_runner_pb2
from src.plugin_runtime_v2.proto.plugin_runner_pb2_grpc import PluginRunnerServicer
from src.plugin_runtime_v2.runner.tool_router import ToolRouter
from src.plugin_runtime_v2.lifecycle.refcount import PluginRefcount, PluginState

logger = get_logger("plugin_runtime_v2.runner.servicer")


class _PluginRunnerServicer(PluginRunnerServicer):
    """PluginRunner gRPC 服务实现。

    Phoenix-1 阶段返回 NOT_IMPLEMENTED，Phoenix-2 通过 ToolRouter 执行路由。
    """

    def __init__(self, tool_router: ToolRouter | None = None) -> None:
        self._tool_router = tool_router
        self._shutting_down: bool = False
        # ZG-15：插件活体引用（RunnerEndpoint 加载成功后注入）
        self._refcount: PluginRefcount | None = None

    def set_refcount(self, refcount: "PluginRefcount") -> None:
        """注入插件活体引用（加载后由 RunnerEndpoint 调用）。"""
        self._refcount = refcount

    async def GetInflightCount(
        self,
        request: plugin_runner_pb2.GetInflightCountRequest,
        context: grpc.aio.ServicerContext,
    ) -> plugin_runner_pb2.GetInflightCountResponse:
        """查询当前在途 Tool 调用数（ZG-15 排空轮询）。

        单一计数源：直接返回 PluginRefcount.refcount——
        ToolRouter.execute 的 try_acquire/release 就是 refcount 操作。
        """
        if self._refcount is None:
            return plugin_runner_pb2.GetInflightCountResponse(count=0)
        return plugin_runner_pb2.GetInflightCountResponse(count=self._refcount.refcount)

    async def InvokeTool(
        self,
        request: plugin_runner_pb2.InvokeToolRequest,
        context: grpc.aio.ServicerContext,
    ) -> plugin_runner_pb2.InvokeToolResponse:
        """根据 tool_name 执行路由。"""
        # ZG-15：拒新判断读 PluginRefcount.state（GOING 语义，对标 module_is_live）
        if self._refcount is not None and self._refcount.state == PluginState.GOING:
            return plugin_runner_pb2.InvokeToolResponse(
                success=False, error="SHUTTING_DOWN",
            )
        if self._shutting_down:  # 进程级关停信号（保留，用于 stream cancel 等）
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


# ZG16-6a: Runner 侧 PluginConfigService 实现
class _PluginConfigServicerRunner:
    """Runner 侧 PluginConfigService 实现——接收 Host 推送的合并后配置。

    收到 UpdatePluginConfig → 调用 handle_update_plugin_config →
    更新 ConfigContext 缓存 → plugin.on_config_update(new, prev)。
    """

    def __init__(self, plugin_instance=None) -> None:
        self._plugin = plugin_instance

    def set_plugin(self, plugin) -> None:
        """注入插件实例（加载后由 RunnerEndpoint 调用）。"""
        self._plugin = plugin

    async def UpdatePluginConfig(self, request, context):
        """接收 Host 推送 → handle_update_plugin_config。"""
        from src.plugin_runtime_v2.proto import plugin_config_pb2
        from src.plugin_runtime_v2.runner.rpc_handler import handle_update_plugin_config

        if self._plugin is None:
            return plugin_config_pb2.UpdatePluginConfigResponse(
                success=False, error="插件未加载",
            )
        registry = _SinglePluginRegistry(self._plugin)
        return await handle_update_plugin_config(
            request, registry, runner_supervisor=None,
        )


class _SinglePluginRegistry:
    """单插件 registry——Runner 侧只有一个插件实例。"""

    def __init__(self, plugin) -> None:
        self._plugin = plugin

    def get(self, plugin_id: str):
        """按 plugin_id 查找——Runner 侧只有自身一个插件。"""
        if self._plugin is not None and getattr(self._plugin, "plugin_id", None) == plugin_id:
            return self._plugin
        # fallback：Runner 侧单插件，plugin_id 不匹配也返回（宽容匹配）
        return self._plugin
