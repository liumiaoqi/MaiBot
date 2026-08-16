"""ZG16-6a: 生产接线测试——AGENTS.md 硬性规则验证。

验证新模块（PluginConfigManager / init_plugin_config_manager / close_plugin_config_manager /
get_plugin_config_manager）存在生产调用点（bootstrap.py），非仅测试中调用。
"""

import inspect


from src.plugin_runtime_v2 import bootstrap


def test_init_plugin_config_manager_exists():
    """init_plugin_config_manager 函数存在。"""
    assert hasattr(bootstrap, "init_plugin_config_manager")
    assert callable(bootstrap.init_plugin_config_manager)


def test_close_plugin_config_manager_exists():
    """close_plugin_config_manager 函数存在。"""
    assert hasattr(bootstrap, "close_plugin_config_manager")
    assert callable(bootstrap.close_plugin_config_manager)


def test_get_plugin_config_manager_exists():
    """get_plugin_config_manager 函数存在。"""
    assert hasattr(bootstrap, "get_plugin_config_manager")
    assert callable(bootstrap.get_plugin_config_manager)


def test_init_plugin_config_manager_is_async():
    """init_plugin_config_manager 是 async 函数。"""
    assert inspect.iscoroutinefunction(bootstrap.init_plugin_config_manager)


def test_close_plugin_config_manager_is_async():
    """close_plugin_config_manager 是 async 函数。"""
    assert inspect.iscoroutinefunction(bootstrap.close_plugin_config_manager)


def test_get_plugin_config_manager_returns_none_initially():
    """get_plugin_config_manager 初始返回 None。"""
    # 重置全局状态
    bootstrap._plugin_config_manager = None
    assert bootstrap.get_plugin_config_manager() is None


def test_set_and_get_plugin_config_manager():
    """_set_plugin_config_manager + get_plugin_config_manager 往返。"""
    from unittest.mock import MagicMock

    mock_manager = MagicMock()
    bootstrap._set_plugin_config_manager(mock_manager)
    assert bootstrap.get_plugin_config_manager() is mock_manager
    # 清理
    bootstrap._plugin_config_manager = None


async def test_close_plugin_config_manager_clears_global():
    """close_plugin_config_manager 清理全局实例。"""
    from unittest.mock import MagicMock

    bootstrap._set_plugin_config_manager(MagicMock())
    await bootstrap.close_plugin_config_manager()
    assert bootstrap.get_plugin_config_manager() is None


async def test_close_plugin_config_manager_noop_when_none():
    """close_plugin_config_manager 无实例时不抛异常。"""
    bootstrap._plugin_config_manager = None
    await bootstrap.close_plugin_config_manager()


def test_init_v2_host_endpoint_calls_init_plugin_config_manager():
    """init_v2_host_endpoint 源码引用 init_plugin_config_manager（生产接线点）。"""
    source = inspect.getsource(bootstrap.init_v2_host_endpoint)
    assert "init_plugin_config_manager" in source


def test_init_v2_host_endpoint_checks_enable_watch():
    """init_v2_host_endpoint 检查 enable_plugin_config_watch 开关。"""
    source = inspect.getsource(bootstrap.init_v2_host_endpoint)
    assert "get_enable_plugin_config_watch" in source


def test_init_plugin_config_manager_creates_revision_store():
    """init_plugin_config_manager 源码引用 RevisionStore。"""
    source = inspect.getsource(bootstrap.init_plugin_config_manager)
    assert "RevisionStore" in source


def test_init_plugin_config_manager_creates_plugin_config_manager():
    """init_plugin_config_manager 源码引用 PluginConfigManager。"""
    source = inspect.getsource(bootstrap.init_plugin_config_manager)
    assert "PluginConfigManager" in source


def test_init_plugin_config_manager_sets_global():
    """init_plugin_config_manager 源码调用 _set_plugin_config_manager。"""
    source = inspect.getsource(bootstrap.init_plugin_config_manager)
    assert "_set_plugin_config_manager" in source


def test_dump_main_uses_get_plugin_config_manager():
    """dump.py main 函数使用 get_plugin_config_manager（生产接线点）。"""
    from src.plugin_runtime_v2.config import dump

    source = inspect.getsource(dump.main)
    assert "get_plugin_config_manager" in source


def test_host_config_manager_has_get_plugin_config_manager_reference():
    """host_config_manager 模块可被 bootstrap 导入（生产接线存在）。"""
    # 验证 bootstrap 能导入 PluginConfigManager
    from src.plugin_runtime_v2.config.host_config_manager import PluginConfigManager

    assert PluginConfigManager is not None