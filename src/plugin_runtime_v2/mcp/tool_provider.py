"""MCP ToolProvider 桥接 — 将远程插件的 Tool 桥接到本地 ToolRegistry。

实现 ToolProvider Protocol，将 Runner 上报的 ToolDeclaration 映射为 ToolSpec，
将 ToolInvocation 转发为 InvokeTool RPC 调用。
"""


import json
from typing import Any

import grpc

from src.common.logger import get_logger
from src.core.tooling import ToolAvailabilityContext, ToolExecutionContext
from src.core.tooling import ToolExecutionResult
from src.core.tooling import ToolInvocation
from src.core.tooling import ToolSpec
from src.plugin_runtime_v2.proto import plugin_runner_pb2
from src.plugin_runtime_v2.proto.plugin_runner_pb2_grpc import PluginRunnerStub

logger = get_logger("plugin_runtime_v2.mcp.tool_provider")

# ── x-maibot-command-pattern 扩展字段 ──
_COMMAND_PATTERN_KEY = "x-maibot-command-pattern"


class MCPToolProvider:
    """Host 端 ToolProvider 桥接。

    实现 ToolProvider Protocol，将远程插件 Tool 映射到 ToolRegistry。
    Phoenix-2 阶段假设 1 Runner = 1 Plugin。
    """

    def __init__(
        self,
        plugin_id: str,
        runner_id: str,
        tool_declarations: list,  # protobuf ToolDeclaration 对象
        runner_listen_address: str,
    ) -> None:
        self.provider_name = plugin_id
        self.provider_type = "mcp_remote"
        self._plugin_id = plugin_id
        self._runner_id = runner_id
        self._listen_address = runner_listen_address
        self._channel: grpc.aio.Channel | None = None
        self._stub: PluginRunnerStub | None = None
        self._tool_specs: list[ToolSpec] = []

        for td in tool_declarations:
            name = td.name
            if not name:
                continue

            # parameters_schema：解析失败记录 WARNING 并跳过该 Tool
            schema_dict = None
            if td.parameters_schema:
                try:
                    schema_dict = json.loads(td.parameters_schema)
                except json.JSONDecodeError:
                    logger.warning(
                        "Tool %s parameters_schema 解析失败，跳过: %s",
                        name, td.parameters_schema[:200] if td.parameters_schema else "",
                    )
                    continue

            # output_schema：解析失败记录 WARNING，设为 None（不跳过 Tool）
            output_dict = None
            if td.output_schema:
                try:
                    output_dict = json.loads(td.output_schema)
                except json.JSONDecodeError:
                    logger.warning(
                        "Tool %s output_schema 解析失败，降级为 None: %s",
                        name, td.output_schema[:200] if td.output_schema else "",
                    )

            # 剥离 x-maibot-command-pattern 扩展字段
            pattern: str | None = None
            cleaned_schema: dict[str, Any] | None = None
            if schema_dict is not None:
                cleaned_schema = dict(schema_dict)
                pattern = cleaned_schema.pop(_COMMAND_PATTERN_KEY, None)

            spec = ToolSpec(
                name=name,
                description=td.description,
                parameters_schema=cleaned_schema,
                output_schema=output_dict,
                provider_name=plugin_id,
                provider_type="mcp_remote",
                metadata={"pattern": pattern} if pattern else {},
            )
            self._tool_specs.append(spec)

        logger.info(
            "MCPToolProvider 已创建: plugin=%s runner=%s tools=%d",
            plugin_id, runner_id, len(self._tool_specs),
        )

    async def _ensure_channel(self) -> None:
        """惰性创建 gRPC 通道和 stub。"""
        if self._channel is None:
            logger.info("创建 gRPC channel: %s", self._listen_address)
            self._channel = grpc.aio.insecure_channel(self._listen_address)
            self._stub = PluginRunnerStub(self._channel)

    async def list_tools(
        self, context: ToolAvailabilityContext | None = None,
    ) -> list[ToolSpec]:
        """返回缓存的 ToolSpec 列表。"""
        return list(self._tool_specs)

    async def invoke(
        self,
        invocation: ToolInvocation,
        context: ToolExecutionContext | None = None,
    ) -> ToolExecutionResult:
        """转发 ToolInvocation 为 InvokeTool RPC。

        注意：@Command 上下文注入由 MCPHostBridge 在调用本方法前完成。
        """
        await self._ensure_channel()
        if self._stub is None:
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message=f"Runner {self._runner_id} 不可用（stub 未初始化）",
            )

        try:
            response: plugin_runner_pb2.InvokeToolResponse = await self._stub.InvokeTool(
                plugin_runner_pb2.InvokeToolRequest(
                    tool_name=invocation.tool_name,
                    args=json.dumps(invocation.arguments, ensure_ascii=False),
                    timeout_ms=30000,
                ),
                timeout=30.0,
            )
        except grpc.aio.AioRpcError as exc:
            code = exc.code()
            if code == grpc.StatusCode.DEADLINE_EXCEEDED:
                logger.warning("Tool %s 调用超时", invocation.tool_name)
                return ToolExecutionResult(
                    tool_name=invocation.tool_name,
                    success=False,
                    error_message=f"Tool {invocation.tool_name} 调用超时",
                )
            if code == grpc.StatusCode.UNAVAILABLE:
                logger.warning("Runner %s 不可用", self._runner_id)
                return ToolExecutionResult(
                    tool_name=invocation.tool_name,
                    success=False,
                    error_message=f"Runner {self._runner_id} 不可用",
                )
            logger.warning(
                "Tool %s 调用异常: %s: %s",
                invocation.tool_name, exc.__class__.__name__, exc.details(),
            )
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message=f"{exc.__class__.__name__}: {exc.details()}",
            )
        except Exception as exc:
            logger.warning(
                "Tool %s 调用异常: %s: %s",
                invocation.tool_name, exc.__class__.__name__, exc,
            )
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message=f"{exc.__class__.__name__}: {exc}",
            )

        return ToolExecutionResult(
            tool_name=invocation.tool_name,
            success=response.success,
            content=response.result,
            error_message=response.error,
        )

    async def close(self) -> None:
        """释放 gRPC 通道资源。"""
        if self._channel is not None:
            await self._channel.close()
            self._channel = None
            self._stub = None
        logger.info(
            "MCPToolProvider 已关闭: plugin=%s runner=%s",
            self._plugin_id, self._runner_id,
        )
