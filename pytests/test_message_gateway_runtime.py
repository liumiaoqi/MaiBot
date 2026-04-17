"""消息网关运行时状态同步测试。"""

from typing import Any, Dict

import pytest

from src.platform_io.manager import PlatformIOManager
from src.platform_io.types import RouteKey
from src.plugin_runtime.host.supervisor import PluginSupervisor
from src.plugin_runtime.protocol.envelope import Envelope, MessageType


def _make_request(method: str, plugin_id: str, payload: Dict[str, Any]) -> Envelope:
    """构造一个 RPC 请求信封。

    Args:
        method: RPC 方法名。
        plugin_id: 目标插件 ID。
        payload: 请求载荷。

    Returns:
        Envelope: 标准 RPC 请求信封。
    """

    return Envelope(
        request_id=1,
        message_type=MessageType.REQUEST,
        method=method,
        plugin_id=plugin_id,
        payload=payload,
    )


@pytest.mark.asyncio
async def test_message_gateway_runtime_state_binds_send_and_receive_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """消息网关就绪后应同时绑定发送表和接收表。"""

    import src.plugin_runtime.host.supervisor as supervisor_module

    platform_io_manager = PlatformIOManager()
    monkeypatch.setattr(supervisor_module, "get_platform_io_manager", lambda: platform_io_manager)

    supervisor = PluginSupervisor(plugin_dirs=[])
    register_response = await supervisor._handle_register_plugin(
        _make_request(
            "plugin.register_components",
            "napcat_plugin",
            {
                "plugin_id": "napcat_plugin",
                "plugin_version": "1.0.0",
                "components": [
                    {
                        "name": "napcat_gateway",
                        "component_type": "MESSAGE_GATEWAY",
                        "plugin_id": "napcat_plugin",
                        "metadata": {
                            "route_type": "duplex",
                            "platform": "qq",
                            "protocol": "napcat",
                        },
                    }
                ],
                "capabilities_required": [],
            },
        )
    )

    assert register_response.error is None
    response = await supervisor._handle_update_message_gateway_state(
        _make_request(
            "host.update_message_gateway_state",
            "napcat_plugin",
            {
                "gateway_name": "napcat_gateway",
                "ready": True,
                "platform": "qq",
                "account_id": "10001",
                "scope": "primary",
                "metadata": {},
            },
        )
    )

    assert response.error is None
    assert response.payload["accepted"] is True

    send_bindings = platform_io_manager.send_route_table.resolve_bindings(
        RouteKey(platform="qq", account_id="10001", scope="primary")
    )
    receive_bindings = platform_io_manager.receive_route_table.resolve_bindings(
        RouteKey(platform="qq", account_id="10001", scope="primary")
    )

    assert [binding.driver_id for binding in send_bindings] == ["gateway:napcat_plugin:napcat_gateway"]
    assert [binding.driver_id for binding in receive_bindings] == ["gateway:napcat_plugin:napcat_gateway"]


@pytest.mark.asyncio
async def test_message_gateway_runtime_state_unbinds_routes_when_not_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """消息网关断开后应撤销发送表和接收表中的绑定。"""

    import src.plugin_runtime.host.supervisor as supervisor_module

    platform_io_manager = PlatformIOManager()
    monkeypatch.setattr(supervisor_module, "get_platform_io_manager", lambda: platform_io_manager)

    supervisor = PluginSupervisor(plugin_dirs=[])
    await supervisor._handle_register_plugin(
        _make_request(
            "plugin.register_components",
            "napcat_plugin",
            {
                "plugin_id": "napcat_plugin",
                "plugin_version": "1.0.0",
                "components": [
                    {
                        "name": "napcat_gateway",
                        "component_type": "MESSAGE_GATEWAY",
                        "plugin_id": "napcat_plugin",
                        "metadata": {
                            "route_type": "duplex",
                            "platform": "qq",
                            "protocol": "napcat",
                        },
                    }
                ],
                "capabilities_required": [],
            },
        )
    )

    await supervisor._handle_update_message_gateway_state(
        _make_request(
            "host.update_message_gateway_state",
            "napcat_plugin",
            {
                "gateway_name": "napcat_gateway",
                "ready": True,
                "platform": "qq",
                "account_id": "10001",
                "scope": "primary",
                "metadata": {},
            },
        )
    )
    response = await supervisor._handle_update_message_gateway_state(
        _make_request(
            "host.update_message_gateway_state",
            "napcat_plugin",
            {
                "gateway_name": "napcat_gateway",
                "ready": False,
                "platform": "qq",
                "account_id": "",
                "scope": "",
                "metadata": {},
            },
        )
    )

    assert response.error is None
    assert response.payload["accepted"] is True
    assert platform_io_manager.send_route_table.resolve_bindings(RouteKey(platform="qq", account_id="10001")) == []
    assert (
        platform_io_manager.receive_route_table.resolve_bindings(RouteKey(platform="qq", account_id="10001")) == []
    )
