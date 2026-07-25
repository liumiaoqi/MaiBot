"""插件加载器 — 扫描 MaiBotPlugin 子类、收集装饰器声明、管理生命周期。"""

from __future__ import annotations

import inspect
from typing import Any

from src.common.logger import get_logger
from src.plugin_runtime_v2.sdk.decorators import EventDeclaration
from src.plugin_runtime_v2.sdk.decorators import ToolDeclaration
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin

logger = get_logger("plugin_runtime_v2.runner.plugin_loader")


class PluginLoader:
    """插件加载器 — 扫描子类、收集声明、注入上下文、管理生命周期。

    维护 _plugin_loaded 标记，重连时避免重复加载。
    """

    def __init__(self, plugin_cls: type[MaiBotPlugin]) -> None:
        self._plugin_cls = plugin_cls
        self._instance: MaiBotPlugin | None = None
        self._plugin_loaded: bool = False
        self._tool_declarations: list[dict[str, Any]] = []
        self._event_declarations: list[dict[str, Any]] = []
        self._homecard_registry: dict[str, dict[str, Any]] = {}

    # ── 公共 API ────────────────────────────────────────────────

    async def load(
        self, plugin_cls: type[MaiBotPlugin] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], MaiBotPlugin | None]:
        """扫描装饰器、实例化插件。

        首次执行后 _plugin_loaded 设为 True，重连时复用。
        PluginContext 注入和 on_load 由 RunnerEndpoint 在调用本方法后执行。

        Returns:
            (tool_declarations, event_declarations, homecard_registry, plugin_instance)
        """
        if plugin_cls is not None:
            self._plugin_cls = plugin_cls

        if self._plugin_loaded:
            return (
                self._tool_declarations,
                self._event_declarations,
                self._homecard_registry,
                self._instance,
            )

        # 收集装饰器声明
        self._tool_declarations = []
        self._event_declarations = []
        self._homecard_registry = {}

        for name, method in inspect.getmembers(self._plugin_cls, predicate=inspect.isfunction):
            if name.startswith("_"):
                continue
            self._collect_tool(method)
            self._collect_event(method)

        # 实例化插件
        try:
            self._instance = self._plugin_cls()
        except Exception as exc:
            logger.error("插件 %s 实例化失败: %s", self._plugin_cls.__name__, exc)
            return [], [], {}, None

        self._plugin_loaded = True
        logger.info(
            "PluginLoader 扫描完成: cls=%s tools=%d events=%d cards=%d",
            self._plugin_cls.__name__,
            len(self._tool_declarations),
            len(self._event_declarations),
            len(self._homecard_registry),
        )
        return (
            self._tool_declarations,
            self._event_declarations,
            self._homecard_registry,
            self._instance,
        )

    async def unload(self, plugin: MaiBotPlugin) -> None:
        """调用插件的 on_unload 生命周期。"""
        try:
            on_unload = plugin.on_unload
            if inspect.iscoroutinefunction(on_unload):
                await on_unload()
            else:
                on_unload()
        except Exception as exc:
            logger.warning("插件 %s on_unload 异常: %s", plugin.plugin_id, exc)

    @property
    def instance(self) -> MaiBotPlugin | None:
        return self._instance

    @property
    def is_loaded(self) -> bool:
        return self._plugin_loaded

    # ── 内部：装饰器收集 ────────────────────────────────────────

    def _collect_tool(self, method: Any) -> None:
        """收集 @Tool/@Command 声明的 ToolDeclaration。"""
        td: ToolDeclaration | None = getattr(method, "_mcp_tool", None)
        if td is None:
            return

        entry: dict[str, Any] = {
            "name": td.name,
            "description": td.description,
            "handler": method,
        }
        if td.parameters_schema is not None:
            # 若含 pattern（@Command），注入 x-maibot-command-pattern 扩展字段
            schema = dict(td.parameters_schema)
            if td.pattern:
                schema["x-maibot-command-pattern"] = td.pattern
            entry["parameters_schema"] = schema
        if td.output_schema is not None:
            entry["output_schema"] = td.output_schema

        self._tool_declarations.append(entry)

    def _collect_event(self, method: Any) -> None:
        """收集 @Event/@HomeCard 声明的 EventDeclaration。"""
        ed: EventDeclaration | None = getattr(method, "_mcp_event", None)
        if ed is None:
            return

        entry: dict[str, Any] = {
            "name": ed.name,
            "description": ed.description,
        }
        if ed.event_schema is not None:
            entry["event_schema"] = ed.event_schema
        if ed.card_metadata is not None:
            entry["card_metadata"] = ed.card_metadata
            self._homecard_registry[ed.name] = ed.card_metadata

        self._event_declarations.append(entry)
