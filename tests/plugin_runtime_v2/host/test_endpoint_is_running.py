"""HostEndpoint.is_running 存活标志测试（2026-10-17）。

背景：plugin_runtime 不变量原先查 v1 的 IpcBridgePort.is_running（v1 已被
ZG-32 停用 ⇒ 恒假 ⇒ 恒红），改用 v2 端点后必须保证"真的没在跑"时标志为假，
所以这里覆盖三条路径：未启动 / 启动成功 / 绑定失败。

⚠️ 绑定失败那条用 mock 的 grpc server，不建真 native 对象：实测"真建
grpc.aio server 再让它绑定失败"在 pytest 的 per-test event loop 下会让**后续**
用例于 Windows 上吃 access violation（只选该用例即可复现，2/2）。那是 grpc/pytest
侧的问题，不该由本用例背。
"""

from unittest.mock import AsyncMock, MagicMock

import grpc
import pytest

from src.plugin_runtime_v2.host.connection import HostEndpointConfig
from src.plugin_runtime_v2.host.endpoint import HostEndpoint


class TestHostEndpointIsRunning:
    """HostEndpoint.is_running 只在真的开始监听后为真。"""

    async def test_false_before_start(self):
        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:0"))
        assert endpoint.is_running is False

    async def test_true_after_start_false_after_stop(self):
        endpoint = HostEndpoint(config=HostEndpointConfig(
            listen_address="0.0.0.0:0", default_drain_timeout_ms=0,
        ))
        await endpoint.start()
        try:
            assert endpoint.is_running is True
        finally:
            await endpoint.stop()
        assert endpoint.is_running is False

    async def test_false_and_released_when_bind_fails(self, monkeypatch):
        """绑定失败：start() 抛错、标志保持 False、半建 server 被收掉。"""
        fake_server = AsyncMock()
        fake_server.add_insecure_port = MagicMock(
            side_effect=RuntimeError("Failed to bind to address 0.0.0.0:8001"),
        )
        monkeypatch.setattr(grpc.aio, "server", lambda **kwargs: fake_server)

        endpoint = HostEndpoint(config=HostEndpointConfig(listen_address="0.0.0.0:8001"))
        with pytest.raises(RuntimeError):
            await endpoint.start()

        assert endpoint.is_running is False
        assert endpoint._server is None
        fake_server.stop.assert_awaited_once_with(grace=0)
