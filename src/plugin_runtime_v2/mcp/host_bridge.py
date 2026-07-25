"""MCP Host 协调器 — 协调 ToolProvider 注册/注销和 Event 分发。

Phoenix-2 阶段假设 1 Runner = 1 Plugin。
"""

from __future__ import annotations

import json
from typing import Any

from src.common.logger import get_logger
from src.core.protocols import PersonInfoPort
from src.core.tooling import ToolExecutionContext
from src.core.tooling import ToolInvocation
from src.core.tooling import ToolRegistry
from src.plugin_runtime_v2.host.connection import RunnerConnection
from src.plugin_runtime_v2.mcp.event_dispatcher import EventDispatcher
from src.plugin_runtime_v2.mcp.tool_provider import MCPToolProvider

logger = get_logger("plugin_runtime_v2.mcp.host_bridge")


class MCPHostBridge:
    """Host 端 MCP 协调器。

    协调 ToolProvider 注册/注销和 Event 分发。
    @Command 上下文注入在本层完成（MCPToolProvider.invoke 之前）。
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
        self._providers: dict[str, MCPToolProvider] = {}  # runner_id → MCPToolProvider
        self._event_declarations: dict[
            str, tuple[Any, str]
        ] = {}  # event_name → (EventDeclaration, plugin_id)

    # ── Runner 生命周期回调 ─────────────────────────────────────

    def on_runner_registered(self, conn: RunnerConnection) -> None:
        """Runner 注册成功：创建 MCPToolProvider 并注册到 ToolRegistry。"""
        runner_id = conn.runner_id
        if runner_id in self._providers:
            logger.warning("Runner %s 的 MCPToolProvider 已存在，跳过重复注册", runner_id)
            return

        if not conn.tools and not conn.events:
            return

        provider = MCPToolProvider(
            plugin_id=conn.plugin_id,
            runner_id=runner_id,
            tool_declarations=conn.tools,
            runner_listen_address=conn.runner_listen_address,
        )
        self._providers[runner_id] = provider
        self._tool_registry.register_provider(provider)

        # 注册 Event 声明到索引
        for evt in conn.events:
            self._event_declarations[evt.name] = (evt, conn.plugin_id)

        logger.info(
            "Runner %s 注册成功: plugin=%s tools=%d events=%d",
            runner_id, conn.plugin_id, len(conn.tools), len(conn.events),
        )

    async def on_runner_disconnected(self, runner_id: str) -> None:
        """Runner 断开：注销 MCPToolProvider 并清理 Event 声明。"""
        provider = self._providers.pop(runner_id, None)
        if provider is not None:
            self._tool_registry.unregister_provider(provider.provider_name)
            await provider.close()

        # 清理该 Runner 的 Event 声明
        conn = self._get_connection(runner_id)
        if conn is not None:
            for evt in conn.events:
                self._event_declarations.pop(evt.name, None)

        logger.info("Runner %s 已断开，MCPToolProvider 已注销", runner_id)

    # ── Event 分发 ──────────────────────────────────────────────

    async def dispatch_event(
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

    def inject_command_context(
        self,
        invocation: ToolInvocation,
        context: ToolExecutionContext | None,
        tool_spec_metadata: dict[str, Any],
    ) -> None:
        """为 @Command 注册的 Tool 注入群消息上下文参数。

        检测 ToolSpec.metadata 中是否含 pattern，若是则注入
        session_id/sender_id/sender_name/is_group_chat。
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
                name = ""
            invocation.arguments["sender_name"] = name
        if "is_group_chat" not in invocation.arguments:
            invocation.arguments["is_group_chat"] = bool(context.is_group_chat)

    # ── 内部工具 ────────────────────────────────────────────────

    def _get_connection(self, runner_id: str) -> RunnerConnection | None:
        """获取 RunnerConnection（从 registry 中查找）。"""
        # 由 HostEndpoint 注入 registry 引用后可用
        return getattr(self, "_registry", None) and self._registry.get(runner_id)  # type: ignore[attr-defined]
