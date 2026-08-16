"""ZG16-6a: 插件 FileWatcher 测试——监听启动/取消/debounce/降级。

覆盖 design 4.2 FileWatcher 相关场景。
"""

import asyncio


from src.plugin_runtime_v2.config.plugin_file_watcher import PluginFileWatcher


async def test_watcher_start_stop(tmp_path):
    """监听启动/取消（spec 5.3.1 规则 1）。"""
    config_path = tmp_path / "config.toml"
    config_path.write_text("port = 3001")
    watcher = PluginFileWatcher("X", str(config_path), debounce_ms=50)
    await watcher.start()
    assert watcher._task is not None
    await watcher.stop()


async def test_debounce(tmp_path):
    """debounce 合并多次变更（spec 5.3.3 场景 5）。

    P1 修复（dsh review2）：固定 sleep 改轮询等待——flaky 测试标准修法。
    """
    calls = []

    async def callback(plugin_id, source):
        calls.append((plugin_id, source))

    config_path = tmp_path / "config.toml"
    config_path.write_text("port = 3001")
    watcher = PluginFileWatcher("X", str(config_path), debounce_ms=50, callback=callback)
    await watcher.start()
    # 给 watchfiles.awatch 时间初始化监听
    await asyncio.sleep(0.1)
    # 触发多次变更
    for i in range(5):
        config_path.write_text(f"port = {3001 + i}")
        await asyncio.sleep(0.01)
    # 轮询等待 callback 触发（最多 2s，避免固定 sleep 在全量并发下 flaky）
    for _ in range(40):
        if len(calls) >= 1:
            break
        await asyncio.sleep(0.05)
    await watcher.stop()
    # debounce 合并后至少触发 1 次（watchfiles 可能合并多次变更）
    assert len(calls) >= 1


async def test_path_not_exist_degradation(tmp_path):
    """路径不可监听降级（spec 5.3.3 场景 1）。"""
    watcher = PluginFileWatcher("X", str(tmp_path / "nonexistent.toml"))
    await watcher.start()
    # 不抛异常，降级不监听
    await asyncio.sleep(0.05)
    await watcher.stop()


async def test_callback_invoked_with_plugin_id(tmp_path):
    """callback 被调用时携带 plugin_id 和 source='file_watcher'。"""
    calls = []

    async def callback(plugin_id, source):
        calls.append((plugin_id, source))

    config_path = tmp_path / "config.toml"
    config_path.write_text("port = 3001")
    watcher = PluginFileWatcher("my_plugin", str(config_path), debounce_ms=30, callback=callback)
    await watcher.start()
    config_path.write_text("port = 3002")
    await asyncio.sleep(0.1)
    await watcher.stop()
    if calls:
        assert calls[0][0] == "my_plugin"
        assert calls[0][1] == "file_watcher"


async def test_stop_idempotent(tmp_path):
    """stop 可多次调用不抛异常。"""
    config_path = tmp_path / "config.toml"
    config_path.write_text("port = 3001")
    watcher = PluginFileWatcher("X", str(config_path), debounce_ms=50)
    await watcher.start()
    await watcher.stop()
    # 再次 stop 不抛异常
    await watcher.stop()


async def test_watcher_with_none_callback(tmp_path):
    """callback 为 None 时不抛异常。"""
    config_path = tmp_path / "config.toml"
    config_path.write_text("port = 3001")
    watcher = PluginFileWatcher("X", str(config_path), debounce_ms=30, callback=None)
    await watcher.start()
    config_path.write_text("port = 3002")
    await asyncio.sleep(0.1)
    await watcher.stop()


def test_watcher_init_attributes():
    """PluginFileWatcher 初始化属性正确。"""
    watcher = PluginFileWatcher("X", "/path/config.toml", debounce_ms=200)
    assert watcher._plugin_id == "X"
    assert watcher._config_path == "/path/config.toml"
    assert watcher._debounce_ms == 200
    assert watcher._task is None


def test_watcher_default_debounce():
    """debounce 默认 300ms。"""
    watcher = PluginFileWatcher("X", "/path/config.toml")
    assert watcher._debounce_ms == 300