"""Phoenix-5 v2 主程序集成 — 创建并启动 HostEndpoint。

将 Phoenix-1~4 的产出组件组装为完整的 v2 Host 端点。
"""

from __future__ import annotations

from src.common.logger import get_logger
from src.core.protocols import AppConfigPort
from src.plugin_runtime_v2.host.connection import HostEndpointConfig
from src.plugin_runtime_v2.host.endpoint import HostEndpoint
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
    event_dispatcher = EventDispatcher()
    person_info_port = _get_person_info_port()
    host_bridge = MCPHostBridge(
        tool_registry=tool_registry,
        event_dispatcher=event_dispatcher,
        person_info_port=person_info_port,
    )

    # 4. 创建 HostEndpoint
    endpoint = HostEndpoint(
        config=config,
        host_bridge=host_bridge,
        token_service=token_service,
        scope_store=scope_store,
    )

    # 5. 启动
    await endpoint.start()
    logger.info(
        "v2 HostEndpoint 已启动: listen=%s scope_file=%s",
        endpoint.listen_address, scope_file,
    )
    return endpoint


def _get_tool_registry():
    """从核心层获取 ToolRegistry 实例。"""
    try:
        from src.maisaka.agent_autonomy.tool_registry import get_tool_registry
        return get_tool_registry()
    except ImportError:
        from src.core.tooling import ToolRegistry
        return ToolRegistry()


def _get_person_info_port():
    """从注册点获取 PersonInfoPort 实例。"""
    from src.core.person_info_port_registry import get_person_info_port
    port = get_person_info_port()
    if port is not None:
        return port
    from src.core.adapters.person_info_port import PersonInfoPortAdapter
    return PersonInfoPortAdapter()
