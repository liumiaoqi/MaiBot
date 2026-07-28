"""Tool 执行路由 — 替换 InvokeTool 的 NOT_IMPLEMENTED 占位。

根据 tool_name 查找 @Tool/@Command 装饰器注册的处理函数并执行。
"""


import asyncio
import inspect
import json
from typing import Any, Callable

import jsonschema

from src.common.logger import get_logger
from src.plugin_runtime_v2.proto import plugin_runner_pb2
from src.plugin_runtime_v2.sdk.decorators import ToolDeclaration
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

logger = get_logger("plugin_runtime_v2.runner.tool_router")

HandlerEntry = tuple[MaiBotPlugin, Callable, ToolDeclaration | None]


class ToolRouter:
    """Tool 执行路由表 — tool_name → 处理函数。"""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerEntry] = {}

    def register(
        self,
        tool_name: str,
        plugin: MaiBotPlugin,
        handler: Callable,
        declaration: ToolDeclaration | None = None,
    ) -> None:
        """注册 Tool 处理函数。"""
        self._handlers[tool_name] = (plugin, handler, declaration)
        logger.debug("ToolRouter 注册: %s", tool_name)

    def unregister(self, tool_name: str) -> None:
        """注销 Tool 处理函数。"""
        self._handlers.pop(tool_name, None)
        logger.debug("ToolRouter 注销: %s", tool_name)

    def has(self, tool_name: str) -> bool:
        """判断 Tool 是否已注册。"""
        return tool_name in self._handlers

    async def execute(
        self,
        tool_name: str,
        args: dict[str, Any],
        timeout_ms: int = 30000,
    ) -> plugin_runner_pb2.InvokeToolResponse:
        """执行 Tool，含参数校验、超时控制、异常捕获。

        Args:
            tool_name: 工具名称
            args: 调用参数（已解析的 dict）
            timeout_ms: 超时时间（毫秒）

        Returns:
            InvokeToolResponse（success/result/error）
        """
        entry = self._handlers.get(tool_name)
        if entry is None:
            return plugin_runner_pb2.InvokeToolResponse(
                success=False, error="TOOL_NOT_FOUND",
            )

        plugin, handler, declaration = entry

        # 参数校验
        if declaration is not None and declaration.parameters_schema is not None:
            try:
                jsonschema.validate(args, declaration.parameters_schema)
            except jsonschema.ValidationError as exc:
                return plugin_runner_pb2.InvokeToolResponse(
                    success=False,
                    error=f"PARAMETER_VALIDATION_FAILED: {exc.message}",
                )

        # 执行处理函数（带超时）
        try:
            if inspect.iscoroutinefunction(handler):
                result = await asyncio.wait_for(
                    handler(plugin, args), timeout=timeout_ms / 1000.0,
                )
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(handler, plugin, args),
                    timeout=timeout_ms / 1000.0,
                )
        except asyncio.TimeoutError:
            return plugin_runner_pb2.InvokeToolResponse(
                success=False, error="TIMEOUT",
            )
        except Exception as exc:
            logger.warning(
                "Tool %s 执行异常: %s: %s",
                tool_name, exc.__class__.__name__, exc,
            )
            return plugin_runner_pb2.InvokeToolResponse(
                success=False,
                error=f"EXECUTION_ERROR: {exc.__class__.__name__}: {exc}",
            )

        return plugin_runner_pb2.InvokeToolResponse(
            success=True, result=json.dumps(result, ensure_ascii=False),
        )
