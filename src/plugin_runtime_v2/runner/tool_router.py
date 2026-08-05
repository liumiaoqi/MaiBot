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

# ZG-15：四元组——refcount 为插件活体引用（None 时兼容未注入场景，跳过 acquire）
HandlerEntry = tuple[MaiBotPlugin, Callable, ToolDeclaration | None, object | None]


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
        refcount: object | None = None,
    ) -> None:
        """注册 Tool 处理函数。

        Args:
            refcount: ZG-15 插件活体引用（PluginRefcount）——execute 时
                try_acquire/release；None 时跳过引用计数（向后兼容）。
        """
        self._handlers[tool_name] = (plugin, handler, declaration, refcount)
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

        plugin, handler, declaration, refcount = entry

        # ZG-15：执行前 acquire 活体引用（对标 try_module_get）
        if refcount is not None:
            if not refcount.try_acquire(tool_name=tool_name):
                logger.info("Tool %s 被拒绝：插件 GOING 中", tool_name)
                return plugin_runner_pb2.InvokeToolResponse(
                    success=False, error="PLUGIN_GOING",
                )

        # acquire 后所有路径（参数校验失败/超时/异常）都必须 release——
        # 泄漏 acquire 会让 refcount 永不归零，卸载卡 wait_drained
        released = False

        def _release() -> None:
            """幂等 release（防双重释放 + 防漏释放）。"""
            nonlocal released
            if refcount is not None and not released:
                refcount.release()
                released = True

        try:
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
            if inspect.iscoroutinefunction(handler):
                # 协程 handler：wait_for 超时会真正取消协程，finally release 安全
                result = await asyncio.wait_for(
                    handler(plugin, args), timeout=timeout_ms / 1000.0,
                )
            else:
                # 同步 handler：wait_for 超时只取消 Future，底层线程仍在运行
                # （CX 审查 P0-3）——引用保留到线程真正结束（done callback
                # release），避免卸载与幽灵线程并发；线程结束前 refcount 不归零，
                # 卸载 wait_drained 会等待（或排空超时由进程强杀兜底）
                thread_future = asyncio.ensure_future(
                    asyncio.to_thread(handler, plugin, args))
                try:
                    result = await asyncio.wait_for(
                        thread_future, timeout=timeout_ms / 1000.0,
                    )
                except asyncio.TimeoutError:
                    thread_future.add_done_callback(lambda _f: _release())
                    return plugin_runner_pb2.InvokeToolResponse(
                        success=False, error="TIMEOUT",
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
        finally:
            _release()

        return plugin_runner_pb2.InvokeToolResponse(
            success=True, result=json.dumps(result, ensure_ascii=False),
        )
