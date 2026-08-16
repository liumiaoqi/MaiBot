"""ZG16-6a: RPC handler 测试——Runner 侧 UpdatePluginConfig RPC 处理。

覆盖 handle_update_plugin_config + _plugin_implements_on_config_update。
"""

import json
from unittest.mock import AsyncMock, MagicMock


from src.plugin_runtime_v2.proto import plugin_config_pb2
from src.plugin_runtime_v2.runner.rpc_handler import (
    _plugin_implements_on_config_update,
    handle_update_plugin_config,
)
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin


class PluginWithUpdate(MaiBotPlugin):
    """实现了 on_config_update 的插件。"""

    def __init__(self):
        self.calls = []

    async def on_config_update(self, new_config, prev_config):
        self.calls.append((new_config, prev_config))


class PluginWithoutUpdate(MaiBotPlugin):
    """未实现 on_config_update 的插件。"""

    pass


def test_implements_detection_with_update():
    """判断实现了 on_config_update 的插件。"""
    assert _plugin_implements_on_config_update(PluginWithUpdate()) is True


def test_implements_detection_without_update():
    """判断未实现 on_config_update 的插件。"""
    assert _plugin_implements_on_config_update(PluginWithoutUpdate()) is False


async def test_handle_update_plugin_config_success():
    """handle_update_plugin_config 成功处理——更新缓存 + 调用 on_config_update。"""
    plugin = PluginWithUpdate()
    plugin.ctx = MagicMock()
    plugin.ctx.config = MagicMock()
    plugin.ctx.config.get.return_value = {"port": 3001}
    plugin.ctx.config._apply_update = MagicMock()

    plugin_registry = MagicMock()
    plugin_registry.get.return_value = plugin
    runner_supervisor = AsyncMock()

    request = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="X",
        config_json=json.dumps({"port": 3002}),
        revision=2,
        source="file_watcher",
    )

    response = await handle_update_plugin_config(request, plugin_registry, runner_supervisor)
    assert response.success is True
    assert response.new_revision == 2
    plugin.ctx.config._apply_update.assert_called_once_with({"port": 3002}, 2)
    assert plugin.calls == [({"port": 3002}, {"port": 3001})]


async def test_handle_update_plugin_config_plugin_not_found():
    """插件未加载 → success=False。"""
    plugin_registry = MagicMock()
    plugin_registry.get.return_value = None
    runner_supervisor = AsyncMock()

    request = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="nonexistent",
        config_json="{}",
        revision=1,
        source="test",
    )

    response = await handle_update_plugin_config(request, plugin_registry, runner_supervisor)
    assert response.success is False
    assert "未加载" in response.error


async def test_handle_update_plugin_config_degrade_reload():
    """未实现 on_config_update → 降级 reload（spec 5.3.3 场景 4）。"""
    plugin = PluginWithoutUpdate()
    plugin.ctx = MagicMock()
    plugin.ctx.config = MagicMock()
    plugin.ctx.config.get.return_value = {}
    plugin.ctx.config._apply_update = MagicMock()

    plugin_registry = MagicMock()
    plugin_registry.get.return_value = plugin
    runner_supervisor = AsyncMock()

    request = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="X",
        config_json=json.dumps({"port": 3002}),
        revision=1,
        source="file_watcher",
    )

    response = await handle_update_plugin_config(request, plugin_registry, runner_supervisor)
    assert response.success is True
    runner_supervisor.reload_one.assert_called_once_with("X")


async def test_handle_update_plugin_config_callback_exception_not_crash():
    """on_config_update 回调异常不崩溃 Runner（spec 5.3.3 场景 3）。"""

    class PluginWithBadUpdate(MaiBotPlugin):
        async def on_config_update(self, new_config, prev_config):
            raise RuntimeError("callback error")

    plugin = PluginWithBadUpdate()
    plugin.ctx = MagicMock()
    plugin.ctx.config = MagicMock()
    plugin.ctx.config.get.return_value = {}
    plugin.ctx.config._apply_update = MagicMock()

    plugin_registry = MagicMock()
    plugin_registry.get.return_value = plugin
    runner_supervisor = AsyncMock()

    request = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="X",
        config_json=json.dumps({"port": 3002}),
        revision=1,
        source="file_watcher",
    )

    response = await handle_update_plugin_config(request, plugin_registry, runner_supervisor)
    # 回调异常不影响响应——配置已更新
    assert response.success is True


async def test_handle_update_plugin_config_prev_config():
    """prev_config 从 ctx.config.get() 获取。"""
    plugin = PluginWithUpdate()
    plugin.ctx = MagicMock()
    plugin.ctx.config = MagicMock()
    plugin.ctx.config.get.return_value = {"port": 3001, "host": "a"}
    plugin.ctx.config._apply_update = MagicMock()

    plugin_registry = MagicMock()
    plugin_registry.get.return_value = plugin
    runner_supervisor = AsyncMock()

    request = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="X",
        config_json=json.dumps({"port": 3002}),
        revision=2,
        source="file_watcher",
    )

    await handle_update_plugin_config(request, plugin_registry, runner_supervisor)
    # 验证 on_config_update 收到的 prev_config 是更新前的配置
    assert plugin.calls[0][1] == {"port": 3001, "host": "a"}


def test_request_serialization():
    """消息序列化/反序列化。"""
    req = plugin_config_pb2.UpdatePluginConfigRequest(
        plugin_id="X", config_json='{"port": 3002}', revision=1, source="file_watcher"
    )
    serialized = req.SerializeToString()
    deserialized = plugin_config_pb2.UpdatePluginConfigRequest()
    deserialized.ParseFromString(serialized)
    assert deserialized.plugin_id == "X"
    assert deserialized.revision == 1
    assert deserialized.source == "file_watcher"
    assert deserialized.config_json == '{"port": 3002}'


def test_response_serialization():
    """响应消息序列化/反序列化。"""
    resp = plugin_config_pb2.UpdatePluginConfigResponse(
        success=True, new_revision=5
    )
    serialized = resp.SerializeToString()
    deserialized = plugin_config_pb2.UpdatePluginConfigResponse()
    deserialized.ParseFromString(serialized)
    assert deserialized.success is True
    assert deserialized.new_revision == 5