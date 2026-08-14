"""Phoenix-5 v2 主程序集成 — 创建并启动 HostEndpoint。

将 Phoenix-1~4 的产出组件组装为完整的 v2 Host 端点。
"""


from src.common.logger import get_logger
from src.core.protocols import AppConfigPort
from src.plugin_runtime_v2.host.connection import HostEndpointConfig
from src.plugin_runtime_v2.host.endpoint import HostEndpoint
from src.plugin_runtime_v2.host.rate_limiter import PluginRateLimiter
from src.plugin_runtime_v2.host.storage_service import PerPluginStorage
from src.core.adapters.message_ingestion_port import get_message_ingestion_port
from src.plugin_runtime_v2.mcp.event_dispatcher import EventDispatcher
from src.plugin_runtime_v2.mcp.host_bridge import MCPHostBridge
from src.plugin_runtime_v2.scope.approval_store import ScopeApprovalStore
from src.plugin_runtime_v2.scope.token_service import TokenService

logger = get_logger("plugin_runtime_v2.bootstrap")


async def init_v2_host_endpoint(app_config_port: AppConfigPort) -> HostEndpoint:
    """创建并启动 v2 HostEndpoint。

    Args:
        app_config_port: AppConfigPort，用于读取 v2 配置。

    Returns:
        已启动的 HostEndpoint 实例。
    """
    # 1. 读取 v2 配置
    listen_address = app_config_port.get_plugin_runtime_v2_host_listen_address()
    scope_file = app_config_port.get_plugin_runtime_v2_scope_approval_file()

    config = HostEndpointConfig(
        listen_address=listen_address,
    )

    # 2. 创建 Scope + Token 服务
    scope_store = ScopeApprovalStore(file_path=scope_file)
    scope_store.load()
    token_service = TokenService()

    # 3. 创建 MCP Host Bridge
    tool_registry = _get_tool_registry()
    event_dispatcher = EventDispatcher(get_message_port=get_message_ingestion_port)
    person_info_port = _get_person_info_port()
    host_bridge = MCPHostBridge(
        tool_registry=tool_registry,
        event_dispatcher=event_dispatcher,
        person_info_port=person_info_port,
    )

    # 4. 创建速率限制器
    default_rpm = app_config_port.get_plugin_runtime_v2_default_rpm()
    rate_limiter = PluginRateLimiter(default_rpm=default_rpm)

    # 5. 创建 PerPluginStorage
    storage_service = PerPluginStorage()

    # 6. 创建 HostEndpoint
    endpoint = HostEndpoint(
        config=config,
        host_bridge=host_bridge,
        token_service=token_service,
        scope_store=scope_store,
        rate_limiter=rate_limiter,
        storage_service=storage_service,
    )

    # 7. 启动
    await endpoint.start()

    # 8. 创建 RunnerSupervisor
    from pathlib import Path

    from src.plugin_runtime_v2.host.runner_supervisor import RunnerSupervisor, RunnerSupervisorConfig

    runner_spawn_count = app_config_port.get_plugin_runtime_v2_runner_spawn_count()
    if runner_spawn_count != -1:
        sup_cfg = RunnerSupervisorConfig(
            max_restart_attempts=3,
            spawn_timeout_sec=30.0,
        )
        registry = endpoint._registry
        supervisor = RunnerSupervisor(config=sup_cfg, registry=registry, host_listen_address=listen_address, token_service=token_service)
        supervisor.start()
        endpoint.set_supervisor(supervisor)

        plugins_root = Path("plugins-v2")
        plugin_dirs = sorted(
            d for d in plugins_root.iterdir()
            if d.is_dir() and ((d / "manifest.json").is_file() or (d / "_manifest.json").is_file())
        ) if plugins_root.is_dir() else []

        spawned = 0
        for plugin_dir in plugin_dirs:
            runner_id = f"runner-{plugin_dir.name}"
            try:
                await supervisor.spawn_and_wait(runner_id, str(plugin_dir))
                spawned += 1
            except Exception as exc:
                from src.core.error_escalation.types import ErrorLevel
                from src.core.error_escalation_port_registry import get_error_escalation_port
                port = get_error_escalation_port()
                if port is not None:
                    port.report(ErrorLevel.ERROR, "启动 V2 Runner 失败", exception=exc)
                logger.error("spawn Runner %s 失败: %s", runner_id, exc)
            if runner_spawn_count > 0 and spawned >= runner_spawn_count:
                break

        if not plugin_dirs:
            logger.warning("plugins-v2/ 下未发现有效插件目录")
        limit_desc = str(runner_spawn_count) if runner_spawn_count > 0 else "不限"
        logger.info("RunnerSupervisor 已创建，spawn %d 个 Runner (上限=%s)", spawned, limit_desc)

    logger.info(
        "v2 HostEndpoint 已启动: listen=%s scope_file=%s",
        endpoint.listen_address,
        scope_file,
    )
    return endpoint


def _get_tool_registry():
    """获取全局共享 ToolRegistry（ZG-20）。

    曾尝试 import src.maisaka.agent_autonomy.tool_registry（该模块不存在）→
    回退孤立 ToolRegistry()——v2 插件工具注册进孤立实例——会话的 registry
    永远看不到（插件功能失效）。现在统一挂核心层全局单例——所有会话以
    shared 引用可见 v2 工具。
    """
    from src.core.tooling import get_global_tool_registry

    return get_global_tool_registry()


def _get_person_info_port():
    """从注册点获取 PersonInfoPort 实例。"""
    from src.core.person_info_port_registry import get_person_info_port

    port = get_person_info_port()
    if port is not None:
        return port
    from src.core.adapters.person_info_port import PersonInfoPortAdapter

    return PersonInfoPortAdapter()
