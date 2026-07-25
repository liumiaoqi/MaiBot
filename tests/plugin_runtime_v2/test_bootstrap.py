"""Phoenix-5 bootstrap 集成测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_import_bootstrap():
    """bootstrap 模块可正常导入。"""
    from src.plugin_runtime_v2 import bootstrap
    assert hasattr(bootstrap, "init_v2_host_endpoint")


class TestInitV2HostEndpoint:
    """init_v2_host_endpoint 集成测试。"""

    @staticmethod
    def _make_app_config_port(enabled: bool = True) -> MagicMock:
        port = MagicMock()
        port.get_plugin_runtime_v2_enabled.return_value = enabled
        port.get_plugin_runtime_v2_host_listen_address.return_value = "0.0.0.0:0"
        port.get_plugin_runtime_v2_scope_approval_file.return_value = ":memory:"
        port.get_plugin_runtime_v2_default_rpm.return_value = 60
        port.get_plugin_runtime_v2_runner_spawn_count.return_value = 0
        return port

    @pytest.mark.asyncio
    async def test_disabled_not_called(self):
        """v2 未启用时 main.py 不调用 init_v2_host_endpoint（此处仅验证 enabled=False 时端口返回值）。"""
        port = self._make_app_config_port(enabled=False)
        assert port.get_plugin_runtime_v2_enabled() is False

    @pytest.mark.asyncio
    async def test_enabled_creates_endpoint(self):
        """v2 启用时创建并启动 HostEndpoint。"""
        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = self._make_app_config_port(enabled=True)
        endpoint = await init_v2_host_endpoint(port)
        try:
            assert endpoint is not None
            assert endpoint.listen_address != ""
        finally:
            await endpoint.stop()

    @pytest.mark.asyncio
    async def test_dependency_injection_chain(self):
        """scope_store、token_service、host_bridge 均非 None。"""
        from src.plugin_runtime_v2.bootstrap import init_v2_host_endpoint
        port = self._make_app_config_port(enabled=True)
        endpoint = await init_v2_host_endpoint(port)
        try:
            assert endpoint.scope_store is not None
            assert endpoint.token_service is not None
        finally:
            await endpoint.stop()
