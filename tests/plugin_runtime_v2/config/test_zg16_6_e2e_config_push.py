"""ZG16-6a P0-4: 端到端配置推送链路测试。

验证完整链路：Host gRPC stub → Runner gRPC server → handle_update_plugin_config
→ plugin.on_config_update(new, prev) 被调用。

dsh 审核 P0-4：填补 test_zg16_6_servicer.py 只测 proto 基类的盲区。
"""


import json
import sys
from pathlib import Path
from typing import Any

import grpc
import pytest

# grpc 生成文件使用裸 import，需将 proto 目录加入 sys.path
_proto_dir = str(Path(__file__).resolve().parents[3] / "src" / "plugin_runtime_v2" / "proto")
if _proto_dir not in sys.path:
    sys.path.insert(0, _proto_dir)

from src.plugin_runtime_v2.proto import plugin_config_pb2  # noqa: E402
from src.plugin_runtime_v2.proto.plugin_config_pb2_grpc import (  # noqa: E402
    PluginConfigServiceStub,
    add_PluginConfigServiceServicer_to_server,
)
from src.plugin_runtime_v2.runner.servicer import (  # noqa: E402
    _PluginConfigServicerRunner,
)
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin  # noqa: E402
from src.plugin_runtime_v2.sdk.context import ConfigContext, PluginContext  # noqa: E402


class _E2EPlugin(MaiBotPlugin):
    """测试插件——记录 on_config_update 调用参数。"""

    plugin_id = "org.e2e.test"

    def __init__(self) -> None:
        self.config_update_calls: list[tuple[dict, dict]] = []

    async def on_config_update(
        self, new_config: dict[str, Any], prev_config: dict[str, Any],
    ) -> None:
        self.config_update_calls.append((new_config, prev_config))


@pytest.mark.asyncio
async def test_e2e_config_push_on_config_update_called():
    """端到端：gRPC stub → Runner server → on_config_update 被调用。

    链路：
    1. 启动 gRPC server，注册 _PluginConfigServicerRunner
    2. 插件初始配置 {"port": 3000} 注入 ConfigContext
    3. stub.UpdatePluginConfig 推送新配置 {"port": 3001}
    4. 断言 on_config_update(new={"port":3001}, prev={"port":3000}) 被调用
    """
    # 1. 准备插件 + ConfigContext（初始配置）
    plugin = _E2EPlugin()
    config_ctx = ConfigContext(plugin_id="org.e2e.test", runner_endpoint=None)
    config_ctx._apply_update({"port": 3000}, revision=1)
    # 构造 PluginContext（config 已注入）
    ctx = PluginContext(
        plugin_id="org.e2e.test",
        granted_scopes=set(),
        runner_endpoint=None,
        homecard_registry={},
        config=config_ctx,
    )
    plugin.ctx = ctx

    # 2. 启动 gRPC server + 注册 _PluginConfigServicerRunner
    server = grpc.aio.server()
    config_servicer = _PluginConfigServicerRunner(plugin_instance=plugin)
    add_PluginConfigServiceServicer_to_server(config_servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        # 3. 创建 stub + 推送新配置
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        stub = PluginConfigServiceStub(channel)
        new_config = {"port": 3001}
        request = plugin_config_pb2.UpdatePluginConfigRequest(
            plugin_id="org.e2e.test",
            config_json=json.dumps(new_config),
            revision=2,
            source="file_watcher",
        )
        resp = await stub.UpdatePluginConfig(request)
        await channel.close()

        # 4. 断言推送成功 + on_config_update 被调用
        assert resp.success is True
        assert resp.new_revision == 2
        assert len(plugin.config_update_calls) == 1
        called_new, called_prev = plugin.config_update_calls[0]
        assert called_new == {"port": 3001}
        assert called_prev == {"port": 3000}
    finally:
        await server.stop(grace=0)


@pytest.mark.asyncio
async def test_e2e_config_push_plugin_not_loaded():
    """端到端：插件未加载时推送返回 success=False。"""
    server = grpc.aio.server()
    config_servicer = _PluginConfigServicerRunner(plugin_instance=None)
    add_PluginConfigServiceServicer_to_server(config_servicer, server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()
    try:
        channel = grpc.aio.insecure_channel(f"127.0.0.1:{port}")
        stub = PluginConfigServiceStub(channel)
        request = plugin_config_pb2.UpdatePluginConfigRequest(
            plugin_id="org.unknown",
            config_json="{}",
            revision=1,
            source="test",
        )
        resp = await stub.UpdatePluginConfig(request)
        await channel.close()
        assert resp.success is False
        assert "未加载" in resp.error
    finally:
        await server.stop(grace=0)


@pytest.mark.asyncio
async def test_e2e_runner_config_stub_routes_by_plugin_id():
    """端到端：RunnerConfigStub 按 plugin_id 从 registry 查 Runner 地址。"""
    from src.plugin_runtime_v2.config.host_config_manager import RunnerConfigStub
    from src.plugin_runtime_v2.host.connection import (
        ConnectionState,
        RunnerConnection,
    )
    from src.plugin_runtime_v2.host.registry import RunnerRegistry

    # 1. 准备 Runner 侧 gRPC server
    plugin = _E2EPlugin()
    config_ctx = ConfigContext(plugin_id="org.e2e.test", runner_endpoint=None)
    config_ctx._apply_update({"port": 3000}, revision=1)
    ctx = PluginContext(
        plugin_id="org.e2e.test",
        granted_scopes=set(),
        runner_endpoint=None,
        homecard_registry={},
        config=config_ctx,
    )
    plugin.ctx = ctx

    runner_server = grpc.aio.server()
    runner_servicer = _PluginConfigServicerRunner(plugin_instance=plugin)
    add_PluginConfigServiceServicer_to_server(runner_servicer, runner_server)
    runner_port = runner_server.add_insecure_port("127.0.0.1:0")
    await runner_server.start()
    try:
        # 2. 构造 registry——模拟 Host 侧已登记 Runner 连接
        registry = RunnerRegistry()
        conn = RunnerConnection(
            runner_id="runner-test",
            state=ConnectionState.READY,
            sdk_version="1.0.0",
            session_token="tok",
            scopes=[],
        )
        conn.plugin_id = "org.e2e.test"
        conn.runner_listen_address = f"127.0.0.1:{runner_port}"
        registry.register(conn)

        # 3. RunnerConfigStub → UpdatePluginConfig
        runner_stub = RunnerConfigStub(registry=registry)
        new_config = {"port": 4000}
        request = plugin_config_pb2.UpdatePluginConfigRequest(
            plugin_id="org.e2e.test",
            config_json=json.dumps(new_config),
            revision=2,
            source="file_watcher",
        )
        resp = await runner_stub.UpdatePluginConfig(request)

        # 4. 断言链路通 + on_config_update 被调用
        assert resp.success is True
        assert len(plugin.config_update_calls) == 1
        assert plugin.config_update_calls[0][0] == {"port": 4000}
    finally:
        await runner_server.stop(grace=0)


@pytest.mark.asyncio
async def test_e2e_runner_config_stub_runner_not_connected():
    """端到端：RunnerConfigStub 找不到 Runner 时抛 ConnectionError。"""
    from src.plugin_runtime_v2.config.host_config_manager import RunnerConfigStub
    from src.plugin_runtime_v2.host.registry import RunnerRegistry

    registry = RunnerRegistry()
    runner_stub = RunnerConfigStub(registry=registry)
    request = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="org.nonexistent",
        config_json="{}",
        revision=1,
        source="test",
    )
    with pytest.raises(ConnectionError, match="未连接"):
        await runner_stub.UpdatePluginConfig(request)