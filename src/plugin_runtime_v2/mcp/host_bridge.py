"""MCP Host 协调器 — 协调 ToolProvider 注册/注销和 Event 分发。

Phoenix-2 阶段假设 1 Runner = 1 Plugin。
"""


import json
from typing import Any

from src.common.logger import get_logger
from src.core.protocols import PersonInfoPort
from src.core.tooling import ToolExecutionContext
from src.core.tooling import ToolInvocation
from src.core.tooling import ToolRegistry
from src.plugin_runtime_v2.mcp.event_dispatcher import EventDispatcher
from src.plugin_runtime_v2.mcp.tool_provider import MCPToolProvider

logger = get_logger("plugin_runtime_v2.mcp.host_bridge")


class MCPHostBridge:
    """Host 端 MCP 协调器。

    协调 ToolProvider 注册/注销和 Event 分发。
    @Command 上下文注入在本层完成。
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        event_dispatcher: EventDispatcher,
        person_info_port: PersonInfoPort,
    ) -> None:
        self._tool_registry = tool_registry
        self._event_dispatcher = event_dispatcher
        self._person_info_port = person_info_port
        self._providers: dict[str, MCPToolProvider] = {}  # plugin_id → MCPToolProvider
        self._event_declarations: dict[
            str, tuple[Any, str]
        ] = {}  # event_name → (EventDeclaration, plugin_id)

    # ── Runner 生命周期回调 ─────────────────────────────────────

    def on_runner_registered(
        self,
        runner_id: str,
        plugin_id: str,
        tools: list,
        events: list,
        runner_listen_address: str,
    ) -> None:
        """Runner 注册成功：创建 MCPToolProvider 并注册到 ToolRegistry。

        重连时先注销旧的再注册新的。
        """
        if not tools and not events:
            return

        # 重连处理：先注销旧的
        old = self._providers.pop(plugin_id, None)
        if old is not None:
            self._tool_registry.unregister_provider(plugin_id)
            # close 是 async，这里用 asyncio.create_task 异步执行
            import asyncio
            asyncio.create_task(old.close(), name=f"close-old-provider-{plugin_id}")
            # 清理旧的 Event 声明
            self._clean_events_by_plugin(plugin_id)
            logger.info(
                "Runner %s 重连，重新注册 plugin %s",
                runner_id, plugin_id,
            )

        provider = MCPToolProvider(
            plugin_id=plugin_id,
            runner_id=runner_id,
            tool_declarations=tools,
            runner_listen_address=runner_listen_address,
        )
        self._providers[plugin_id] = provider
        self._tool_registry.register_provider(provider)

        for evt in events:
            self._event_declarations[evt.name] = (evt, plugin_id)

        logger.info(
            "Runner %s 注册成功: plugin=%s tools=%d events=%d",
            runner_id, plugin_id, len(tools), len(events),
        )

    async def on_runner_disconnected(self, runner_id: str, plugin_id: str) -> None:
        """Runner 断开：注销 MCPToolProvider 并清理 Event 声明。"""
        provider = self._providers.pop(plugin_id, None)
        if provider is not None:
            self._tool_registry.unregister_provider(plugin_id)
            await provider.close()

        self._clean_events_by_plugin(plugin_id)
        logger.info("Runner %s 已断开，MCPToolProvider 已注销", runner_id)

    # ── Event 分发 ──────────────────────────────────────────────

    async def on_event_received(
        self,
        event_name: str,
        payload_str: str,
        runner_id: str,
    ) -> None:
        """分发 Event 到 EventDispatcher。"""
        entry = self._event_declarations.get(event_name)
        if entry is None:
            logger.warning("未注册的 Event: %s (runner=%s)", event_name, runner_id)
            return

        evt_decl, plugin_id = entry
        try:
            payload = json.loads(payload_str) if payload_str else {}
        except json.JSONDecodeError:
            logger.warning("Event %s 载荷解析失败 (runner=%s)", event_name, runner_id)
            return

        await self._event_dispatcher.dispatch(
            event_name=event_name,
            payload=payload,
            plugin_id=plugin_id,
            event_declaration=evt_decl,
        )

    # ── @Command 上下文注入 ─────────────────────────────────────

    def _inject_command_context(
        self,
        invocation: ToolInvocation,
        context: ToolExecutionContext | None,
        tool_spec_metadata: dict[str, Any],
    ) -> None:
        """为 @Command 注册的 Tool 注入群消息上下文参数。

        不覆盖已有参数。
        """
        pattern = tool_spec_metadata.get("pattern")
        if not pattern:
            return
        if context is None:
            return

        if "session_id" not in invocation.arguments:
            invocation.arguments["session_id"] = context.session_id or ""
        if "sender_id" not in invocation.arguments:
            invocation.arguments["sender_id"] = context.user_id or ""
        if "sender_name" not in invocation.arguments:
            try:
                info = self._person_info_port.get_person_info(
                    "", context.user_id or ""
                )
                name = info.person_name if info else ""
            except Exception:
                logger.warning("操作异常 in host_bridge.py", exc_info=True)
                name = ""
            invocation.arguments["sender_name"] = name
        if "is_group_chat" not in invocation.arguments:
            invocation.arguments["is_group_chat"] = bool(context.is_group_chat)

    # ── 内部工具 ────────────────────────────────────────────────

    def _clean_events_by_plugin(self, plugin_id: str) -> None:
        """清理指定 plugin_id 的所有 Event 声明。"""
        to_remove = [
            name for name, (_, pid) in self._event_declarations.items()
            if pid == plugin_id
        ]
        for name in to_remove:
            self._event_declarations.pop(name, None)
