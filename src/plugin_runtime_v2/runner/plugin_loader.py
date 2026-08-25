"""插件加载器 — 扫描 MaiBotPlugin 子类、收集装饰器声明、管理生命周期。"""


import inspect
from typing import Any

from src.common.logger import get_logger
from src.plugin_runtime_v2.sdk.decorators import EventDeclaration
from src.plugin_runtime_v2.sdk.decorators import MessageGatewayDeclaration
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
        self._gateway_declarations: list[MessageGatewayDeclaration] = []
        self._homecard_registry: dict[str, dict[str, Any]] = {}
        # ZG16-6a: 配置管理 + 文件监听
        self._config_manager = None  # PluginConfigManager 实例（由外部注入）
        self._file_watchers: dict[str, Any] = {}  # plugin_id → PluginFileWatcher

    # ── 公共 API ────────────────────────────────────────────────

    async def load(
        self, plugin_cls: type[MaiBotPlugin] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]], list[MessageGatewayDeclaration], MaiBotPlugin | None]:
        """扫描装饰器、实例化插件。

        首次执行后 _plugin_loaded 设为 True，重连时复用。
        PluginContext 注入和 on_load 由 RunnerEndpoint 在调用本方法后执行。

        Returns:
            (tool_declarations, event_declarations, homecard_registry, gateway_declarations, plugin_instance)
        """
        if plugin_cls is not None:
            self._plugin_cls = plugin_cls

        if self._plugin_loaded:
            return (
                self._tool_declarations,
                self._event_declarations,
                self._homecard_registry,
                self._gateway_declarations,
                self._instance,
            )

        # 收集装饰器声明
        self._tool_declarations = []
        self._event_declarations = []
        self._gateway_declarations = []
        self._homecard_registry = {}

        for name, method in inspect.getmembers(self._plugin_cls, predicate=inspect.isfunction):
            if name.startswith("__"):
                continue
            self._collect_tool(method)
            self._collect_event(method)
            self._collect_message_gateway(method)

        # 实例化插件
        try:
            self._instance = self._plugin_cls()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.ERROR, "插件实例化失败", exception=exc)
            logger.error("插件 %s 实例化失败: %s", self._plugin_cls.__name__, exc)
            return [], [], {}, [], None

        self._plugin_loaded = True
        logger.info(
            "PluginLoader 扫描完成: cls=%s tools=%d events=%d gateways=%d cards=%d",
            self._plugin_cls.__name__,
            len(self._tool_declarations),
            len(self._event_declarations),
            len(self._gateway_declarations),
            len(self._homecard_registry),
        )
        return (
            self._tool_declarations,
            self._event_declarations,
            self._homecard_registry,
            self._gateway_declarations,
            self._instance,
        )

    # ZG16-6a: 初始配置下发 + 注册 PluginFileWatcher
    async def deliver_initial_config(
        self,
        plugin_id: str,
        base_path: str,
    ) -> None:
        """加载后调 PluginConfigManager 合并三层 → gRPC 下发初始配置 → 注册 PluginFileWatcher。

        spec 5.2.1 规则 6：插件加载时初始配置下发。
        """
        if self._config_manager is None:
            return  # 未注入 config_manager，跳过（v1 插件或未启用 v2 配置机制）
        try:
            await self._config_manager.load_plugin_config(
                plugin_id, base_path
            )
            # 注册 PluginFileWatcher（spec 5.3.1 规则 1）
            if self._config_manager._port.get_enable_plugin_config_watch():
                await self._register_file_watcher(plugin_id, base_path)
        except Exception as e:
            logger.warning(f"插件 {plugin_id} 初始配置下发失败，降级空配置: {e}")

    async def _register_file_watcher(self, plugin_id: str, base_path: str) -> None:
        """注册 PluginFileWatcher 监听插件 config.toml。"""
        from src.plugin_runtime_v2.config.plugin_file_watcher import PluginFileWatcher
        config_path = f"{base_path}/config.toml"
        watcher = PluginFileWatcher(
            plugin_id=plugin_id,
            config_path=config_path,
            debounce_ms=self._config_manager._port.get_plugin_config_debounce_ms(),
            callback=self._config_manager.handle_file_change,
        )
        await watcher.start()
        self._file_watchers[plugin_id] = watcher

    async def stop_file_watcher(self, plugin_id: str) -> None:
        """插件卸载时取消监听（spec 5.3.1 规则 1b）。"""
        watcher = self._file_watchers.pop(plugin_id, None)
        if watcher is not None:
            await watcher.stop()

    async def unload(self, plugin: MaiBotPlugin) -> None:
        """调用插件的 on_unload 生命周期。"""
        try:
            on_unload = plugin.on_unload
            if inspect.iscoroutinefunction(on_unload):
                await on_unload()
            else:
                on_unload()
        except Exception as exc:
            from src.core.error_escalation.types import ErrorLevel
            from src.core.error_escalation_port_registry import get_error_escalation_port
            port = get_error_escalation_port()
            if port is not None:
                port.report(ErrorLevel.WARNING, "插件 on_unload 回调异常", exception=exc)
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

    def _collect_message_gateway(self, method: Any) -> None:
        """收集 @MessageGateway 声明的 MessageGatewayDeclaration。"""
        gd: MessageGatewayDeclaration | None = getattr(method, "_message_gateway", None)
        if gd is None:
            return
        self._gateway_declarations.append(gd)
