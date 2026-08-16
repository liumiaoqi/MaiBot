"""ZG16-6a: plugin loader 测试——deliver_initial_config + FileWatcher 注册/取消。

覆盖 deliver_initial_config, _register_file_watcher, stop_file_watcher。
"""

from unittest.mock import AsyncMock, MagicMock


from src.plugin_runtime_v2.runner.plugin_loader import PluginLoader
from src.plugin_runtime_v2.sdk.plugin import MaiBotPlugin


class SimplePlugin(MaiBotPlugin):
    plugin_id = "org.test.simple"


def _make_loader_with_manager(tmp_path):
    """构造带 mock config_manager 的 PluginLoader。"""
    loader = PluginLoader(SimplePlugin)
    manager = MagicMock()
    manager._port = MagicMock()
    manager._port.get_enable_plugin_config_watch.return_value = True
    manager._port.get_plugin_config_debounce_ms.return_value = 50
    manager.load_plugin_config = AsyncMock(return_value={"port": 3001})
    manager.handle_file_change = AsyncMock()
    loader._config_manager = manager
    return loader, manager


async def test_deliver_initial_config(tmp_path):
    """deliver_initial_config 调用 config_manager.load_plugin_config。"""
    loader, manager = _make_loader_with_manager(tmp_path)
    base_path = str(tmp_path / "plugin_dir")
    await loader.deliver_initial_config("X", base_path)
    manager.load_plugin_config.assert_called_once_with("X", base_path)


async def test_deliver_initial_config_no_manager(tmp_path):
    """config_manager 未注入 → 跳过（v1 插件）。"""
    loader = PluginLoader(SimplePlugin)
    loader._config_manager = None
    # 不抛异常
    await loader.deliver_initial_config("X", str(tmp_path))


async def test_deliver_initial_config_registers_file_watcher(tmp_path):
    """deliver_initial_config 注册 PluginFileWatcher（spec 5.3.1 规则 1）。"""
    loader, manager = _make_loader_with_manager(tmp_path)
    base_path = str(tmp_path / "plugin_dir")
    (tmp_path / "plugin_dir").mkdir()
    await loader.deliver_initial_config("X", base_path)
    assert "X" in loader._file_watchers
    # 清理
    await loader.stop_file_watcher("X")


async def test_deliver_initial_config_watch_disabled(tmp_path):
    """enable_plugin_config_watch=False → 不注册 FileWatcher。"""
    loader, manager = _make_loader_with_manager(tmp_path)
    manager._port.get_enable_plugin_config_watch.return_value = False
    base_path = str(tmp_path / "plugin_dir")
    await loader.deliver_initial_config("X", base_path)
    assert "X" not in loader._file_watchers


async def test_stop_file_watcher(tmp_path):
    """stop_file_watcher 取消监听（spec 5.3.1 规则 1b）。"""
    loader, manager = _make_loader_with_manager(tmp_path)
    base_path = str(tmp_path / "plugin_dir")
    (tmp_path / "plugin_dir").mkdir()
    await loader.deliver_initial_config("X", base_path)
    assert "X" in loader._file_watchers
    await loader.stop_file_watcher("X")
    assert "X" not in loader._file_watchers


async def test_stop_file_watcher_nonexistent(tmp_path):
    """stop_file_watcher 不存在的插件不抛异常。"""
    loader = PluginLoader(SimplePlugin)
    await loader.stop_file_watcher("nonexistent")


async def test_deliver_initial_config_exception_degradation(tmp_path):
    """deliver_initial_config 异常降级空配置。"""
    loader, manager = _make_loader_with_manager(tmp_path)
    manager.load_plugin_config.side_effect = RuntimeError("load failed")
    # 不抛异常，降级
    await loader.deliver_initial_config("X", str(tmp_path))


async def test_register_file_watcher_debounce(tmp_path):
    """_register_file_watcher 使用配置的 debounce_ms。"""
    loader, manager = _make_loader_with_manager(tmp_path)
    manager._port.get_plugin_config_debounce_ms.return_value = 500
    base_path = str(tmp_path / "plugin_dir")
    (tmp_path / "plugin_dir").mkdir()
    await loader._register_file_watcher("X", base_path)
    watcher = loader._file_watchers["X"]
    assert watcher._debounce_ms == 500
    await loader.stop_file_watcher("X")


async def test_file_watcher_callback_is_handle_file_change(tmp_path):
    """FileWatcher callback 绑定为 config_manager.handle_file_change。"""
    loader, manager = _make_loader_with_manager(tmp_path)
    base_path = str(tmp_path / "plugin_dir")
    (tmp_path / "plugin_dir").mkdir()
    await loader._register_file_watcher("X", base_path)
    watcher = loader._file_watchers["X"]
    assert watcher._callback == manager.handle_file_change
    await loader.stop_file_watcher("X")


def test_loader_init_no_config_manager():
    """PluginLoader 初始化 config_manager 为 None。"""
    loader = PluginLoader(SimplePlugin)
    assert loader._config_manager is None
    assert loader._file_watchers == {}


def test_loader_file_watchers_dict():
    """_file_watchers 是 dict。"""
    loader = PluginLoader(SimplePlugin)
    assert isinstance(loader._file_watchers, dict)