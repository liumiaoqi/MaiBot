"""ZG16-6a: Host 配置管理测试——合并 + 缓存 + revision bump + 推送。

覆盖 design 4.2 + 4.4 Host 管理器相关场景。
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.plugin_runtime_v2.config.host_config_manager import PluginConfigManager
from src.plugin_runtime_v2.config.revision_store import ConfigConflictError, RevisionStore


def _make_mock_port(
    debounce_ms=300,
    revision_path=None,
    enable_watch=True,
    enable_dump=True,
    enable_drift=True,
    plugin_override=({}, {}),
):
    """构造 mock AppConfigPort。"""
    port = MagicMock()
    port.get_plugin_config_debounce_ms.return_value = debounce_ms
    port.get_plugin_config_revision_path.return_value = revision_path or "data/rev.json"
    port.get_enable_plugin_config_watch.return_value = enable_watch
    port.get_enable_dump_plugin_config.return_value = enable_dump
    port.get_enable_schema_drift_detect.return_value = enable_drift
    port.get_plugin_override.return_value = plugin_override
    return port


def _make_manager(tmp_path, plugin_override=({}, {})):
    """构造 PluginConfigManager 实例。"""
    port = _make_mock_port(plugin_override=plugin_override)
    revision_store = RevisionStore(str(tmp_path / "rev.json"))
    grpc_stub = AsyncMock()
    manager = PluginConfigManager(port, revision_store, grpc_stub)
    return manager, port, grpc_stub


async def test_load_plugin_config(tmp_path):
    """加载插件配置——三层合并 + 缓存 + revision bump。"""
    manager, port, grpc_stub = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    config = await manager.load_plugin_config("X", str(base_path))
    assert config["port"] == 3001


async def test_load_plugin_config_caches_result(tmp_path):
    """加载后配置缓存到内存。"""
    manager, _, _ = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))
    assert manager.get_config("X") == {"port": 3001}


async def test_load_plugin_config_bumps_revision(tmp_path):
    """加载后 revision 递增。"""
    manager, _, _ = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    assert manager._revision_store.get("X") == 0
    await manager.load_plugin_config("X", str(base_path))
    assert manager._revision_store.get("X") == 1


async def test_load_plugin_config_with_global_override(tmp_path):
    """全局覆盖层合并。"""
    manager, _, _ = _make_manager(
        tmp_path, plugin_override=({"port": 9999}, {})
    )
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    config = await manager.load_plugin_config("X", str(base_path))
    assert config["port"] == 9999


async def test_load_plugin_config_file_not_exist(tmp_path):
    """配置文件不存在 → base 为空 dict。"""
    manager, _, _ = _make_manager(tmp_path)
    config = await manager.load_plugin_config("X", str(tmp_path / "nonexistent.toml"))
    assert config == {}


async def test_disk_reconcile_skip_unchanged(tmp_path):
    """磁盘对账——内容不变跳过推送（spec 5.3.1 规则 4a）。"""
    manager, _, grpc_stub = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))
    grpc_stub.UpdatePluginConfig.reset_mock()
    # 内容不变 → handle_file_change 跳过推送
    await manager.handle_file_change("X", "file_watcher")
    grpc_stub.UpdatePluginConfig.assert_not_called()


async def test_disk_reconcile_changed_pushes(tmp_path):
    """磁盘内容变化 → 触发推送。"""
    manager, _, grpc_stub = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))
    grpc_stub.UpdatePluginConfig.reset_mock()
    # 修改配置文件
    base_path.write_text("port = 9999")
    await manager.handle_file_change("X", "file_watcher")
    grpc_stub.UpdatePluginConfig.assert_called_once()


async def test_optimistic_concurrency_conflict(tmp_path):
    """乐观并发冲突（spec 5.4.1 规则 3a）。"""
    manager, _, _ = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))  # revision=1
    with pytest.raises(ConfigConflictError):
        await manager.update_config("X", {"port": 3002}, expected_revision=999, source="test", writer="test")


async def test_optimistic_concurrency_pass(tmp_path):
    """乐观并发通过——expected 匹配 actual。"""
    manager, _, _ = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))  # revision=1
    new_config = await manager.update_config(
        "X", {"port": 3002}, expected_revision=1, source="test", writer="test"
    )
    assert new_config["port"] == 3002


async def test_update_config_expected_none(tmp_path):
    """expected_revision=None 跳过并发检查。"""
    manager, _, _ = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))
    new_config = await manager.update_config(
        "X", {"port": 3002}, expected_revision=None, source="test", writer="test"
    )
    assert new_config["port"] == 3002


async def test_get_config_nonexistent(tmp_path):
    """get_config 不存在的插件返回空 dict。"""
    manager, _, _ = _make_manager(tmp_path)
    assert manager.get_config("nonexistent") == {}


async def test_register_schema(tmp_path):
    """register_schema 注册 schema。"""
    manager, _, _ = _make_manager(tmp_path)
    from pydantic import BaseModel

    class MySchema(BaseModel):
        port: int

    manager.register_schema("X", MySchema)
    assert manager._schemas["X"] is MySchema


async def test_dump_config_human(tmp_path):
    """dump_config human 格式返回字符串。"""
    manager, _, _ = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))
    result = await manager.dump_config("X", fmt="human")
    assert isinstance(result, str)
    assert "port" in result


async def test_dump_config_json(tmp_path):
    """dump_config json 格式返回合法 JSON 字符串。"""
    import json

    manager, _, _ = _make_manager(tmp_path)
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))
    result = await manager.dump_config("X", fmt="json")
    parsed = json.loads(result)
    assert parsed["config"]["port"] == 3001


async def test_grpc_push_retry(tmp_path):
    """gRPC 推送失败重试 3 次（spec 5.3.3 场景 2）。"""
    manager, _, grpc_stub = _make_manager(tmp_path)
    grpc_stub.UpdatePluginConfig.side_effect = RuntimeError("connection refused")
    base_path = tmp_path / "config.toml"
    base_path.write_text("port = 3001")
    await manager.load_plugin_config("X", str(base_path))
    grpc_stub.UpdatePluginConfig.reset_mock()
    grpc_stub.UpdatePluginConfig.side_effect = RuntimeError("connection refused")
    base_path.write_text("port = 9999")
    await manager.handle_file_change("X", "file_watcher")
    # 重试 3 次
    assert grpc_stub.UpdatePluginConfig.call_count == 3